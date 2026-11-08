"""
=============================================================
  SUPABASE AUTH FOR LINK LOOT (Signup / Login)
=============================================================
Uses the Supabase Auth (GoTrue) REST API directly with
`requests` — no extra dependency needed.

Every signed-in user gets their own private dashboard:
leads are saved with their user_id and only they can see them.
"""

from typing import Any, Dict, Optional, Tuple
import requests

from app_config import ADMIN_EMAILS, SUPABASE_KEY, SUPABASE_URL


def _clean_base_url() -> str:
    if not SUPABASE_URL:
        return ""
    url = SUPABASE_URL.strip().rstrip("/")
    if url.endswith("/rest/v1"):
        url = url[: -len("/rest/v1")].rstrip("/")
    if url.endswith("/auth/v1"):
        url = url[: -len("/auth/v1")].rstrip("/")
    return url


def is_auth_configured() -> bool:
    """True when Supabase URL + key are present so Auth can work."""
    return bool(_clean_base_url() and SUPABASE_KEY)


def _auth_headers(access_token: Optional[str] = None) -> Dict[str, str]:
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def _error_message(response: requests.Response) -> str:
    try:
        data = response.json()
        return (
            data.get("error_description")
            or data.get("msg")
            or data.get("message")
            or str(data)
        )
    except Exception:
        return response.text[:200] or f"HTTP {response.status_code}"


def sign_up(email: str, password: str, full_name: str = "") -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Create a new account with Supabase Auth.
    Returns (success, message, session_user_or_None).
    When email confirmation is ON in Supabase, no session is returned —
    the user must confirm the email link before logging in.
    """
    if not is_auth_configured():
        return False, "Accounts are not configured yet. Please contact the admin.", None

    payload: Dict[str, Any] = {"email": email.strip(), "password": password}
    if full_name.strip():
        payload["data"] = {"full_name": full_name.strip()}

    try:
        response = requests.post(
            f"{_clean_base_url()}/auth/v1/signup",
            headers=_auth_headers(),
            json=payload,
            timeout=15,
        )
    except Exception as error:
        return False, f"Connection error: {error}", None

    if response.status_code in (200, 201):
        data = response.json()
        user = data.get("user")
        if data.get("access_token") and user:
            return True, "Account created — you are logged in.", {
                "id": user.get("id"),
                "email": user.get("email"),
                "access_token": data.get("access_token"),
                "refresh_token": data.get("refresh_token"),
            }
        return (
            True,
            "Account created! Please check your email and click the confirmation link, then log in.",
            None,
        )
    return False, _error_message(response), None


def sign_in(email: str, password: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Log in with email + password. Returns (success, message, session_user)."""
    if not is_auth_configured():
        return False, "Accounts are not configured yet. Please contact the admin.", None

    try:
        response = requests.post(
            f"{_clean_base_url()}/auth/v1/token?grant_type=password",
            headers=_auth_headers(),
            json={"email": email.strip(), "password": password},
            timeout=15,
        )
    except Exception as error:
        return False, f"Connection error: {error}", None

    if response.status_code == 200:
        data = response.json()
        user = data.get("user") or {}
        return True, "Welcome back!", {
            "id": user.get("id"),
            "email": user.get("email"),
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token"),
        }
    return False, _error_message(response), None


def is_admin(user: Optional[Dict[str, Any]]) -> bool:
    """Admin = signed-in email listed in ADMIN_EMAILS (Streamlit Secrets)."""
    if not user:
        return False
    email = (user.get("email") or "").strip().lower()
    return bool(email and email in ADMIN_EMAILS)


def ensure_profile(user: Dict[str, Any]) -> None:
    """
    Create/update the user's row in public.profiles (best effort).
    Used by the Admin dashboard to list registered users.
    Silently ignores errors (e.g. v2 SQL not run yet).
    """
    if not is_auth_configured() or not user or not user.get("id"):
        return
    try:
        requests.post(
            f"{_clean_base_url()}/rest/v1/profiles",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates",
            },
            json={
                "id": user["id"],
                "email": (user.get("email") or "").strip(),
            },
            timeout=10,
        )
    except Exception:
        pass
