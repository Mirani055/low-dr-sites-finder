# ==========================================
# LOW DR FINDER - APPLICATION CONFIGURATION
# ==========================================
import os
from pathlib import Path

# Try to load local .env if present
env_file = Path(__file__).resolve().parent / ".env"
if env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file)
    except Exception:
        pass


def _get_secret(name: str, default: str = "") -> str:
    """
    Safely retrieve a configuration value or secret.
    Prioritizes environment variables, then falls back to Streamlit secrets (for Streamlit Cloud).
    """
    # 1. Environment variable (from .env or cloud environment)
    env_val = os.getenv(name)
    if env_val is not None and str(env_val).strip():
        return str(env_val).strip()

    # 2. Streamlit Cloud Secrets (st.secrets)
    try:
        import streamlit as st
        if hasattr(st, "secrets") and st.secrets is not None:
            # Check direct attribute or dict access
            if name in st.secrets:
                val = st.secrets[name]
                if val is not None and str(val).strip():
                    return str(val).strip()
            # In case nested under a section or has .get()
            val = st.secrets.get(name)
            if val is not None and str(val).strip():
                return str(val).strip()
    except Exception:
        pass

    return default


# Serper API (Websites dhundhne ke liye)
SERPER_API_KEY = _get_secret("SERPER_API_KEY")

# ==========================================
# Domain Rating APIs
# ==========================================
AHREFS_API_KEY = _get_secret("AHREFS_API_KEY")
OPAGERANK_API_KEY = _get_secret("OPAGERANK_API_KEY")

# ==========================================
# Contact Enrichment (Hunter.io)
# ==========================================
HUNTER_API_KEY = _get_secret("HUNTER_API_KEY")

# ==========================================
# Supabase PostgreSQL Database (Leads Storage)
# ==========================================
SUPABASE_URL = _get_secret("SUPABASE_URL")
SUPABASE_KEY = _get_secret("SUPABASE_KEY")

# ==========================================
# Admin Access
# ==========================================
# Comma-separated email addresses that get the Admin dashboard.
# Set ADMIN_EMAILS in Streamlit Secrets (share.streamlit.io -> App -> Settings -> Secrets), e.g.
# ADMIN_EMAILS = "you@example.com"
ADMIN_EMAILS = [
    email.strip().lower()
    for email in _get_secret("ADMIN_EMAILS").split(",")
    if email.strip()
]

# ==========================================
# Tool Settings
# ==========================================
MAX_WEBSITES_TO_CHECK = 50     # Kitni websites check karni hain per country
LOW_DR_THRESHOLD = 30          # Keep sites with DR from 1 through this limit
REQUEST_TIMEOUT = 15
DELAY_BETWEEN_REQUESTS = 1.0
OUTPUT_FILE = "link_loot_leads.xlsx"
