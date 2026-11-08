# ==========================================
# LOW DR FINDER - CONFIGURATION
# ==========================================
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))


def _get_secret(name):
	value = os.getenv(name, "").strip()
	if value:
		return value
	try:
		import streamlit as st

		return str(st.secrets.get(name, "")).strip()
	except Exception:
		return ""

# Serper API (Websites dhundhne ke liye)
SERPER_API_KEY = _get_secret("SERPER_API_KEY")

# ==========================================
# Domain Rating must come from Ahrefs.
# ==========================================

# 1. Ahrefs Free API (Primary - Best & Most Accurate)
AHREFS_API_KEY = _get_secret("AHREFS_API_KEY")

# Optional OpenPageRank score; it is not interchangeable with Ahrefs DR.
OPAGERANK_API_KEY = _get_secret("OPAGERANK_API_KEY")

# ==========================================
# OPTIONAL: Hunter.io (Extra emails ke liye)
# ==========================================
HUNTER_API_KEY = _get_secret("HUNTER_API_KEY")

# ==========================================
# Tool Settings
# ==========================================
MAX_WEBSITES_TO_CHECK = 50     # Kitni websites check karni hain per country
LOW_DR_THRESHOLD = 30          # Keep sites with DR from 1 through this limit
REQUEST_TIMEOUT = 15
DELAY_BETWEEN_REQUESTS = 1.0
OUTPUT_FILE = "link_loot_leads.xlsx"