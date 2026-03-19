from functools import lru_cache

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config.settings import settings

security = HTTPBearer()

SUPABASE_JWKS_URL = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"


@lru_cache(maxsize=1)
def _get_jwks() -> dict:
    """Cached in-process. Refresh on signature validation failure (key rotation)."""
    return httpx.get(SUPABASE_JWKS_URL).json()


def _decode_token(token: str) -> dict:
    jwks = _get_jwks()
    # Get the signing key from JWKS
    public_keys = {}
    for key_data in jwks.get("keys", []):
        kid = key_data.get("kid")
        if kid:
            public_keys[kid] = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)

    # Decode header to get kid
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")
    if kid not in public_keys:
        raise jwt.InvalidTokenError("Unknown key ID")

    return jwt.decode(
        token,
        public_keys[kid],
        algorithms=["RS256"],
        audience="authenticated",
    )


async def verify_token(token: str) -> dict:
    try:
        return _decode_token(token)
    except jwt.InvalidSignatureError:
        # Key may have rotated — clear cache and retry once
        _get_jwks.cache_clear()
        return _decode_token(token)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    try:
        payload = await verify_token(credentials.credentials)
        return payload
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {e}",
        )
