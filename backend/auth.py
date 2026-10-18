"""Local operator accounts and expiring opaque sessions for the single-instance MVP."""
import hashlib
import hmac
import secrets
import threading
import time
from collections import OrderedDict

from fastapi import HTTPException

COOKIE = "coldline_session"
SESSION_SECONDS = 8 * 60 * 60


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()
    return f"scrypt${salt.hex()}${digest}"


def verify_password(password, encoded):
    try:
        algorithm, salt, expected = encoded.split("$")
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


class OperatorSessions:
    def __init__(self, users):
        self.users = users
        self.sessions = OrderedDict()
        self.attempts = OrderedDict()
        self.lock = threading.RLock()
        self.dummy_hash = hash_password(secrets.token_urlsafe())

    def login(self, username, password, client):
        with self.lock:
            now = time.monotonic()
            start, count = self.attempts.get(client, (now, 0))
            if now - start >= 60:
                start, count = now, 0
            if count >= 10:
                raise HTTPException(429, "Too many login attempts. Try again in a minute.")
            self.attempts[client] = (start, count + 1)
            self.attempts.move_to_end(client)
            while len(self.attempts) > 1000:
                self.attempts.popitem(last=False)
            user = self.users.get(username)
            valid = verify_password(password, user["password_hash"] if user else self.dummy_hash)
            if not valid or not user:
                raise HTTPException(401, "Invalid username or password")
            self.sessions = OrderedDict((key, value) for key, value in self.sessions.items() if value[1] > now)
            if len(self.sessions) >= 4096:
                raise HTTPException(503, "Session capacity reached; try again later")
            token = secrets.token_urlsafe(32)
            identity = {"tenant": user["tenant"], "role": "operator", "username": username}
            self.sessions[hashlib.sha256(token.encode()).hexdigest()] = (identity, now + SESSION_SECONDS)
            return token, identity

    def resolve(self, token):
        if not token:
            return None
        key = hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            session = self.sessions.get(key)
            if session and session[1] > time.monotonic():
                return session[0]
            self.sessions.pop(key, None)
            return None

    def revoke(self, token):
        if token:
            with self.lock:
                self.sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)
