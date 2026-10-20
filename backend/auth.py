"""Operator accounts and expiring opaque sessions.

With a ``store`` the session table is shared by every API replica (multi-instance
safe; only the SHA-256 of the token is persisted). Without one, sessions stay in
process memory, which is kept for unit tests and embedded use. Login throttling is
per process; production deployments should also rate-limit at the edge or use OIDC.
"""
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
    def __init__(self, users, store=None):
        self.users = users
        self.store = store
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
            token = secrets.token_urlsafe(32)
            identity = {"tenant": user["tenant"], "role": "operator", "username": username}
            key = hashlib.sha256(token.encode()).hexdigest()
            if self.store is not None:
                self.store.create_session(key, identity, time.time() + SESSION_SECONDS)
                return token, identity
            self.sessions = OrderedDict((key, value) for key, value in self.sessions.items() if value[1] > now)
            if len(self.sessions) >= 4096:
                raise HTTPException(503, "Session capacity reached; try again later")
            self.sessions[key] = (identity, now + SESSION_SECONDS)
            return token, identity

    def resolve(self, token):
        if not token:
            return None
        key = hashlib.sha256(token.encode()).hexdigest()
        if self.store is not None:
            return self.store.resolve_session(key)
        with self.lock:
            session = self.sessions.get(key)
            if session and session[1] > time.monotonic():
                return session[0]
            self.sessions.pop(key, None)
            return None

    def revoke(self, token):
        if token:
            key = hashlib.sha256(token.encode()).hexdigest()
            if self.store is not None:
                self.store.revoke_session(key)
                return
            with self.lock:
                self.sessions.pop(key, None)
