"""
=============================================================
  Domain metrics - Ahrefs DR and separately labelled OpenPageRank
=============================================================
"""

import requests
from app_config import AHREFS_API_KEY, OPAGERANK_API_KEY, REQUEST_TIMEOUT


def check_ahrefs_dr(domain):
    """Ahrefs Free API se Domain Rating check karta hai."""
    if not AHREFS_API_KEY:
        return None, "no_key"
    
    url = "https://api.ahrefs.com/v3/public/domain-rating-free"
    params = {"target": domain}
    headers = {"Authorization": f"Bearer {AHREFS_API_KEY}"}
    
    try:
        r = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            dr = data.get("domain_rating", {}).get("domain_rating")
            if dr is not None:
                return float(dr), "ok"
            return None, "no_data"
        return None, f"http_{r.status_code}"
    except Exception as e:
        return None, f"error: {str(e)[:30]}"


def check_openpagerank(domain):
    """OpenPageRank API se PR score check karta hai (Fallback)."""
    if not OPAGERANK_API_KEY:
        return None, "no_key"
    
    url = "https://openpagerank.com/api/v1.0/getPageRank"
    headers = {"API-OPR": OPAGERANK_API_KEY}
    params = {"domains[]": domain}
    
    try:
        r = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            if data.get("status_code") == 200:
                response = data.get("response", [{}])[0]
                pr = response.get("page_rank_decimal")
                if pr is not None:
                    # PR 0-1 ko 0-100 scale mein convert karna
                    return int(pr * 10), "ok"
                return None, "no_data"
            return None, f"api_error_{data.get('status_code')}"
        return None, f"http_{r.status_code}"
    except Exception as e:
        return None, f"error: {str(e)[:30]}"


def get_dr_score(domain):
    """
    Domain ka DR check karta hai.
    Try Ahrefs DR first and label the optional OpenPageRank fallback separately.
    Callers filtering for Domain Rating must accept only the Ahrefs DR source.
    Returns: (score, source, status)
    """
    # Step 1: Try Ahrefs
    if AHREFS_API_KEY:
        dr, status = check_ahrefs_dr(domain)
        if dr is not None:
            return dr, "Ahrefs DR", status
    
    # Step 2: Fallback to OpenPageRank
    if OPAGERANK_API_KEY:
        pr, status = check_openpagerank(domain)
        if pr is not None:
            return pr, "OpenPageRank", status
            
    return None, "none", "no_api_configured"