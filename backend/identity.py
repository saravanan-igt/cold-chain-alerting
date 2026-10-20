"""OpenID Connect bearer-token verification for enterprise single sign-on.

Deploy behind an OIDC-aware proxy (for example oauth2-proxy, Azure App Service
Authentication or an AWS ALB) that forwards ``Authorization: Bearer <JWT>``. The API
still verifies the signature, issuer, audience and expiry itself, so bypassing the
proxy does not bypass authentication. Tenant and role come from signed claims.
"""
import os

import jwt


class OidcVerifier:
    def __init__(self, issuer, audience, jwks_url=None, tenant_claim="coldline_tenant",
                 roles_claim="roles", operator_role="coldline.operator", known_tenants=(),
                 algorithms=("RS256", "ES256"), key_resolver=None):
        if not key_resolver and not jwks_url:
            raise ValueError("OIDC verification requires a JWKS URL")
        self.issuer, self.audience = issuer, audience
        self.tenant_claim, self.roles_claim, self.operator_role = tenant_claim, roles_claim, operator_role
        self.known_tenants, self.algorithms = set(known_tenants), list(algorithms)
        if key_resolver is None:
            client = jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=3600, timeout=5)
            key_resolver = lambda token: client.get_signing_key_from_jwt(token).key  # noqa: E731
        self.key_resolver = key_resolver

    @classmethod
    def from_env(cls, known_tenants):
        issuer = os.getenv("COLDCHAIN_OIDC_ISSUER")
        if not issuer:
            return None
        audience = os.getenv("COLDCHAIN_OIDC_AUDIENCE")
        if not audience:
            raise ValueError("COLDCHAIN_OIDC_AUDIENCE is required when COLDCHAIN_OIDC_ISSUER is set")
        return cls(issuer, audience, os.getenv("COLDCHAIN_OIDC_JWKS_URL"),
                   os.getenv("COLDCHAIN_OIDC_TENANT_CLAIM", "coldline_tenant"),
                   os.getenv("COLDCHAIN_OIDC_ROLES_CLAIM", "roles"),
                   os.getenv("COLDCHAIN_OIDC_OPERATOR_ROLE", "coldline.operator"), known_tenants)

    def verify(self, token):
        """Return an operator identity, or None for any invalid, expired or unauthorised token."""
        try:
            claims = jwt.decode(token, self.key_resolver(token), algorithms=self.algorithms, audience=self.audience,
                                issuer=self.issuer, leeway=60, options={"require": ["exp", "iss", "aud", "sub"]})
        except (jwt.PyJWTError, ValueError):
            return None
        tenant = claims.get(self.tenant_claim)
        roles = claims.get(self.roles_claim) or []
        roles = [roles] if isinstance(roles, str) else roles
        if tenant not in self.known_tenants or self.operator_role not in roles:
            return None
        username = claims.get("preferred_username") or claims.get("email") or claims["sub"]
        return {"tenant": tenant, "role": "operator", "username": str(username)[:120], "auth": "oidc"}
