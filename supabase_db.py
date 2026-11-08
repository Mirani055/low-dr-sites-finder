"""
=============================================================
  SUPABASE DATABASE INTEGRATION FOR LINK LOOT
=============================================================
Provides seamless storage, querying, and lead management
using Supabase PostgreSQL database via standard PostgREST API.
Requires no heavy dependencies (uses requests).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import requests

from app_config import SUPABASE_KEY, SUPABASE_URL


def is_supabase_configured() -> bool:
    """Return True if both Supabase URL and API Key are present."""
    return bool(SUPABASE_URL and SUPABASE_KEY and SUPABASE_URL.startswith("http"))


def _clean_base_url() -> str:
    """Ensure URL is the base Supabase URL without trailing /rest/v1 or slash."""
    if not SUPABASE_URL:
        return ""
    url = SUPABASE_URL.strip().rstrip("/")
    if url.endswith("/rest/v1"):
        url = url[:-len("/rest/v1")].rstrip("/")
    return url


def _get_headers(access_token: Optional[str] = None) -> Dict[str, str]:
    """Build standard Supabase PostgREST authentication headers."""
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {access_token or SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def test_connection() -> Tuple[bool, str]:
    """
    Test connectivity to Supabase.
    Verifies that credentials are valid and the 'leads' table exists.
    """
    if not is_supabase_configured():
        return False, "SUPABASE_URL or SUPABASE_KEY is missing."

    url = f"{_clean_base_url()}/rest/v1/leads?select=id&limit=1"
    try:
        response = requests.get(url, headers=_get_headers(), timeout=10)
        if response.status_code == 200:
            return True, "Supabase connection successful!"
        if response.status_code == 401 or response.status_code == 403:
            return False, "Authentication failed. Check your SUPABASE_KEY (anon/service_role)."
        if response.status_code == 404:
            return False, "Table 'leads' not found. Please run the SQL schema in Supabase SQL Editor."
        return False, f"Supabase returned status {response.status_code}: {response.text[:200]}"
    except Exception as e:
        return False, f"Connection error: {e}"


def _format_lead_for_db(
    lead: Dict[str, Any],
    niche: str = "",
    country: str = "",
    city: str = "",
    user_id: Optional[str] = None,
    user_email: str = "",
) -> Dict[str, Any]:
    """Convert a lead dictionary into a clean row matching the Supabase leads table."""
    emails = lead.get("emails", "")
    if isinstance(emails, list):
        emails = ", ".join(e for e in emails if e)
    elif emails == "—":
        emails = ""

    dr_score = lead.get("dr_score")
    if dr_score is not None:
        try:
            dr_score = float(dr_score)
        except (ValueError, TypeError):
            dr_score = None

    row = {
        "niche": (lead.get("niche") or niche or "").strip(),
        "country": (lead.get("country") or country or "").strip(),
        "city": (lead.get("city") or city or "").strip(),
        "domain": (lead.get("domain") or "").strip(),
        "url": (lead.get("url") or "").strip(),
        "title": (lead.get("title") or "").strip()[:500],
        "dr_score": dr_score,
        "dr_source": lead.get("dr_source") or "",
        "emails": emails,
        "email_status": lead.get("email_status") or "",
        "facebook": lead.get("facebook") or "",
        "linkedin": lead.get("linkedin") or "",
        "instagram": lead.get("instagram") or "",
        "twitter": lead.get("twitter") or "",
        "phone": lead.get("phone") or "",
        "whatsapp": lead.get("whatsapp") or "",
        "dr_status": lead.get("dr_status") or "",
        "scrape_status": lead.get("scrape_status") or "",
    }
    # Per-user ownership (needs supabase_schema_v2.sql). Only added when known,
    # so older databases without the columns keep working until migrated.
    if user_id:
        row["user_id"] = user_id
    if user_email:
        row["user_email"] = user_email
    return row


def save_leads_to_supabase(
    leads: List[Dict[str, Any]],
    niche: str = "",
    country: str = "",
    city: str = "",
    user_id: Optional[str] = None,
    user_email: str = "",
    access_token: Optional[str] = None,
) -> Tuple[int, str]:
    """
    Save a batch of leads to Supabase 'leads' table.
    Uses upsert resolution=merge-duplicates on URL/domain when available.
    Returns (saved_count, message).
    """
    if not is_supabase_configured():
        return 0, "Supabase is not configured."

    if not leads:
        return 0, "No leads to save."

    cleaned_rows = [
        _format_lead_for_db(lead, niche, country, city, user_id=user_id, user_email=user_email)
        for lead in leads
    ]
    # Filter out empty URLs or domains
    cleaned_rows = [row for row in cleaned_rows if row.get("url") or row.get("domain")]

    if not cleaned_rows:
        return 0, "No valid lead rows to save."

    url = f"{_clean_base_url()}/rest/v1/leads"
    headers = _get_headers(access_token)
    headers["Prefer"] = "resolution=merge-duplicates,return=representation"

    try:
        response = requests.post(url, headers=headers, json=cleaned_rows, timeout=20)

        # v2 columns (user_id / user_email) not added yet -> retry without them
        # so saving keeps working until the admin runs supabase_schema_v2.sql.
        if response.status_code == 400 and user_id:
            legacy_rows = [
                {k: v for k, v in row.items() if k not in ("user_id", "user_email")}
                for row in cleaned_rows
            ]
            response = requests.post(url, headers=headers, json=legacy_rows, timeout=20)
            if response.status_code in (200, 201):
                count = len(response.json()) if isinstance(response.json(), list) else len(legacy_rows)
                return count, (
                    f"Saved {count} leads to your account. "
                    "Note for admin: run supabase_schema_v2.sql in Supabase to fully separate every user's leads."
                )
        if response.status_code in (200, 201):
            inserted_count = len(response.json()) if isinstance(response.json(), list) else len(cleaned_rows)
            return inserted_count, f"Successfully saved {inserted_count} leads to Supabase."
        
        # If upsert fails because of missing unique constraint, retry with standard insert
        if response.status_code == 400:
            headers.pop("Prefer", None)
            headers["Prefer"] = "return=representation"
            fallback_response = requests.post(url, headers=headers, json=cleaned_rows, timeout=20)
            if fallback_response.status_code in (200, 201):
                count = len(fallback_response.json()) if isinstance(fallback_response.json(), list) else len(cleaned_rows)
                return count, f"Successfully inserted {count} leads to Supabase."
            return 0, f"Supabase insert failed: {fallback_response.text[:200]}"

        return 0, f"Supabase error ({response.status_code}): {response.text[:200]}"
    except Exception as e:
        return 0, f"Error saving to Supabase: {e}"


def fetch_leads_from_supabase(
    limit: int = 500,
    country: Optional[str] = None,
    niche: Optional[str] = None,
    max_dr: Optional[float] = None,
    with_email_only: bool = False,
    search_query: Optional[str] = None,
    user_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Fetch saved leads from Supabase with optional filters.
    Returns (leads_list, status_message).
    """
    if not is_supabase_configured():
        return [], "Supabase is not configured."

    params = [
        "select=*",
        "order=created_at.desc",
        f"limit={limit}",
    ]

    # Per-user isolation: a normal user only ever receives their own leads.
    if user_id:
        params.append(f"user_id=eq.{user_id}")

    if country and country != "All":
        params.append(f"country=eq.{requests.utils.quote(country)}")

    if niche and niche.strip():
        params.append(f"niche=ilike.*{requests.utils.quote(niche.strip())}*")

    if max_dr is not None:
        params.append(f"dr_score=lte.{max_dr}")

    if with_email_only:
        params.append("emails=neq.")

    if search_query and search_query.strip():
        q = requests.utils.quote(search_query.strip())
        params.append(f"or=(domain.ilike.*{q}*,title.ilike.*{q}*,emails.ilike.*{q}*)")

    query_string = "&".join(params)
    url = f"{_clean_base_url()}/rest/v1/leads?{query_string}"

    try:
        response = requests.get(url, headers=_get_headers(access_token), timeout=15)
        if response.status_code == 200:
            data = response.json()
            return data, f"Loaded {len(data)} leads from Supabase."
        # user_id column missing (v2 SQL not run yet) -> fall back to unfiltered
        # only when the caller is not relying on isolation being enforced by SQL.
        if response.status_code == 400 and user_id:
            fallback_query = "&".join(p for p in params if not p.startswith("user_id="))
            fallback_url = f"{_clean_base_url()}/rest/v1/leads?{fallback_query}"
            fallback = requests.get(fallback_url, headers=_get_headers(access_token), timeout=15)
            if fallback.status_code == 200:
                return fallback.json(), "Loaded leads (admin: run supabase_schema_v2.sql to enable per-user separation)."
        return [], f"Failed to load leads ({response.status_code}): {response.text[:200]}"
    except Exception as e:
        return [], f"Error querying Supabase: {e}"


def get_database_stats(user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch aggregate statistics about the database.
    Pass user_id to scope the stats to a single user.
    """
    leads, msg = fetch_leads_from_supabase(limit=2000, user_id=user_id)
    if not leads:
        return {
            "total_leads": 0,
            "with_email": 0,
            "low_dr": 0,
            "countries": [],
            "niches": [],
        }

    total = len(leads)
    with_email = sum(1 for row in leads if row.get("emails"))
    low_dr = sum(1 for row in leads if row.get("dr_score") is not None and row["dr_score"] <= 30)
    countries = sorted(list({row.get("country") for row in leads if row.get("country")}))
    niches = sorted(list({row.get("niche") for row in leads if row.get("niche")}))

    return {
        "total_leads": total,
        "with_email": with_email,
        "low_dr": low_dr,
        "countries": countries,
        "niches": niches,
    }


def delete_lead_by_id(lead_id: int, user_id: Optional[str] = None) -> Tuple[bool, str]:
    """Delete a lead record from Supabase by ID (optionally scoped to its owner)."""
    if not is_supabase_configured():
        return False, "Supabase is not configured."

    url = f"{_clean_base_url()}/rest/v1/leads?id=eq.{lead_id}"
    if user_id:
        url += f"&user_id=eq.{user_id}"
    try:
        response = requests.delete(url, headers=_get_headers(), timeout=10)
        if response.status_code in (200, 204):
            return True, "Lead deleted successfully."
        return False, f"Failed to delete ({response.status_code}): {response.text[:200]}"
    except Exception as e:
        return False, f"Error deleting lead: {e}"


# =============================================================
#  ADMIN HELPERS
# =============================================================

def fetch_profiles() -> List[Dict[str, Any]]:
    """List registered users from public.profiles (admin use). [] if not available."""
    if not is_supabase_configured():
        return []
    url = f"{_clean_base_url()}/rest/v1/profiles?select=*&order=created_at.desc&limit=1000"
    try:
        response = requests.get(url, headers=_get_headers(), timeout=15)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return []


def get_admin_overview() -> Dict[str, Any]:
    """
    Aggregate platform-wide numbers for the Admin dashboard:
    totals, per-user lead counts, per-niche and per-country counts.
    """
    leads, _ = fetch_leads_from_supabase(limit=5000)
    profiles = fetch_profiles()

    per_user: Dict[str, Dict[str, Any]] = {}
    per_niche: Dict[str, int] = {}
    per_country: Dict[str, int] = {}
    for row in leads:
        email = (row.get("user_email") or "— unassigned (before accounts) —")
        bucket = per_user.setdefault(email, {"email": email, "leads": 0, "with_email": 0, "last_hunt": ""})
        bucket["leads"] += 1
        if row.get("emails"):
            bucket["with_email"] += 1
        created = row.get("created_at") or ""
        if created > bucket["last_hunt"]:
            bucket["last_hunt"] = created
        if row.get("niche"):
            per_niche[row["niche"]] = per_niche.get(row["niche"], 0) + 1
        if row.get("country"):
            per_country[row["country"]] = per_country.get(row["country"], 0) + 1

    return {
        "total_leads": len(leads),
        "with_email": sum(1 for r in leads if r.get("emails")),
        "low_dr": sum(1 for r in leads if r.get("dr_score") is not None and r["dr_score"] <= 30),
        "total_users": len(profiles),
        "profiles": profiles,
        "per_user": sorted(per_user.values(), key=lambda b: b["leads"], reverse=True),
        "per_niche": per_niche,
        "per_country": per_country,
    }
