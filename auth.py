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

from urllib.parse import quote

from app_config import ADMIN_EMAILS, APP_URL, AUTH_BRIDGE_URL, SUPABASE_KEY, SUPABASE_URL


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
        # Send verified users back to the live app, never to a local address.
        # The app URL must also be allowed in Supabase under
        # Authentication, URL Configuration.
        response = requests.post(
            f"{_clean_base_url()}/auth/v1/signup?redirect_to={quote(APP_URL, safe='')}",
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


def resend_confirmation(email: str) -> Tuple[bool, str]:
    """Resend the signup confirmation email (for expired or lost links)."""
    if not is_auth_configured():
        return False, "Accounts are not configured yet. Please contact the admin."
    try:
        response = requests.post(
            f"{_clean_base_url()}/auth/v1/resend?redirect_to={quote(APP_URL, safe='')}",
            headers=_auth_headers(),
            json={"type": "signup", "email": email.strip()},
            timeout=15,
        )
    except Exception as error:
        return False, f"Connection error: {error}"
    if response.status_code in (200, 201):
        return True, "A new confirmation email is on its way. Please use the newest link."
    return False, _error_message(response)


def google_sign_in_url() -> str:
    """Supabase OAuth entry point for Google sign in.

    Google sends the user back to the static bridge page, which forwards
    them into the app. The Google provider must be enabled in Supabase
    (Authentication, Providers, Google) for this to work.
    """
    return (
        f"{_clean_base_url()}/auth/v1/authorize?provider=google"
        f"&redirect_to={quote(AUTH_BRIDGE_URL, safe='')}"
    )


def get_user_from_token(access_token: str, refresh_token: str = "") -> Optional[Dict[str, Any]]:
    """Validate an access token with Supabase and return the session user."""
    if not is_auth_configured() or not access_token:
        return None
    try:
        response = requests.get(
            f"{_clean_base_url()}/auth/v1/user",
            headers=_auth_headers(access_token),
            timeout=15,
        )
    except Exception:
        return None
    if response.status_code != 200:
        return None
    data = response.json()
    if not data.get("id"):
        return None
    return {
        "id": data.get("id"),
        "email": data.get("email"),
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


def refresh_session(refresh_token: str) -> Optional[Dict[str, Any]]:
    """
    Exchange a refresh token for a fresh session.
    Access tokens expire after about an hour; without a refresh, a user who
    keeps the app open finds that saving and loading leads quietly fails.
    Returns the new session user dict, or None when the refresh fails.
    """
    if not is_auth_configured() or not refresh_token:
        return None
    try:
        response = requests.post(
            f"{_clean_base_url()}/auth/v1/token?grant_type=refresh_token",
            headers=_auth_headers(),
            json={"refresh_token": refresh_token},
            timeout=15,
        )
    except Exception:
        return None
    if response.status_code != 200:
        return None
    data = response.json()
    user = data.get("user") or {}
    if not data.get("access_token"):
        return None
    return {
        "id": user.get("id"),
        "email": user.get("email"),
        "access_token": data.get("access_token"),
        "refresh_token": data.get("refresh_token") or refresh_token,
    }


def is_admin(user: Optional[Dict[str, Any]]) -> bool:
    """Admin = signed-in email listed in ADMIN_EMAILS (Streamlit Secrets)."""
    if not user:
        return False
    email = (user.get("email") or "").strip().lower()
    return bool(email and email in ADMIN_EMAILS)


def ensure_profile(user: Dict[str, Any]) -> bool:
    """
    Create/update the user's row in public.profiles (best effort).
    Used by the Admin dashboard to list registered users.
    Returns True only when this call created the profile, which means this
    is the user's first sign in ever. Silently ignores errors (e.g. v2 SQL
    not run yet) and returns False when it cannot tell.
    """
    if not is_auth_configured() or not user or not user.get("id"):
        return False
    existed = True
    try:
        check = requests.get(
            f"{_clean_base_url()}/rest/v1/profiles",
            params={"id": f"eq.{user['id']}", "select": "id"},
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
            },
            timeout=10,
        )
        if check.status_code == 200:
            existed = len(check.json()) > 0
    except Exception:
        existed = True
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
    return not existed
