import os

import httpx
from fastapi import Header, HTTPException


class CurrentUser:
    def __init__(self, id: str, email: str | None):
        self.id = id
        self.email = email


async def _fetch_supabase_user(token: str) -> dict:
    """Delegates JWT validation to Supabase Auth itself (signature, expiry, and
    revocation are all handled server-side) rather than reimplementing JWT
    verification in the Gateway, which would require guessing which signing
    scheme (shared HS256 secret vs. per-project JWKS) this project actually uses.
    """
    supabase_url = os.environ["SUPABASE_URL"]
    anon_key = os.environ["SUPABASE_ANON_KEY"]
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(
            f"{supabase_url}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": anon_key},
        )
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return response.json()


async def _user_profile_exists(user_id: str) -> bool:
    """Defense-in-depth check for the deleted-user case: a JWT can remain
    cryptographically valid and unexpired even after the underlying user row
    (and its cascaded user_profiles row) is deleted. Queries user_profiles
    directly via PostgREST using the service role key.
    """
    supabase_url = os.environ["SUPABASE_URL"]
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(
            f"{supabase_url}/rest/v1/user_profiles",
            params={"id": f"eq.{user_id}", "select": "id"},
            headers={
                "Authorization": f"Bearer {service_role_key}",
                "apikey": service_role_key,
            },
        )
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Could not verify account status")
    return len(response.json()) == 1


async def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    try:
        user = await _fetch_supabase_user(token)
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if not await _user_profile_exists(user_id):
        raise HTTPException(status_code=401, detail="Account no longer exists")

    return CurrentUser(id=user_id, email=user.get("email"))
