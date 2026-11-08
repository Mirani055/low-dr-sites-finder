"""
=============================================================
  LINK LOOT — STANDALONE ADMIN DASHBOARD
=============================================================
Deploy this file as a SECOND app on Streamlit Cloud:
  share.streamlit.io -> New app -> repo Mirani055/low-dr-sites-finder
  -> Main file path: admin_dashboard.py
It uses the same Supabase project and the same secrets as the
user app. Only emails listed in ADMIN_EMAILS can enter.
"""

import io
from pathlib import Path
import sys

APP_ROOT = str(Path(__file__).resolve().parent)
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

import pandas as pd
import streamlit as st

from app_config import AHREFS_API_KEY, HUNTER_API_KEY, SERPER_API_KEY
from auth import ensure_profile, is_admin, sign_in
from supabase_db import (
    delete_lead_by_id,
    fetch_leads_from_supabase,
    get_admin_overview,
    is_supabase_configured,
    test_connection,
)

st.set_page_config(page_title="Link Loot Admin", page_icon="🛡️", layout="wide")

st.title("🛡️ Link Loot — Admin Dashboard")
st.caption("Full platform control: users, all leads, and system health. This app is separate from the user dashboard.")

user = st.session_state.get("auth_user")

if not user:
    with st.form("admin_login_form"):
        email = st.text_input("Admin email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in", type="primary")
    if submitted:
        ok, message, session_user = sign_in(email, password)
        if ok and session_user:
            if is_admin(session_user):
                st.session_state["auth_user"] = session_user
                ensure_profile(session_user)
                st.rerun()
            else:
                st.error("This account is not an admin. Add its email to ADMIN_EMAILS in Streamlit Secrets.")
        else:
            st.error(message)
    st.stop()

if not is_admin(user):
    st.error("Access denied — this account is not in ADMIN_EMAILS.")
    if st.button("Log out"):
        st.session_state.pop("auth_user", None)
        st.rerun()
    st.stop()

with st.sidebar:
    st.markdown(f"### 👤 {user.get('email')}")
    st.success("🛡️ Admin")
    if st.button("Log out", width="stretch"):
        st.session_state.pop("auth_user", None)
        st.rerun()
    st.divider()
    st.markdown("### Services")
    st.caption(f"Serper (web search): {'set ✅' if SERPER_API_KEY else 'missing ⚠️'}")
    st.caption(f"Ahrefs (DR): {'set ✅' if AHREFS_API_KEY else 'missing ⚠️'}")
    st.caption(f"Hunter (email verify): {'set ✅' if HUNTER_API_KEY else 'not set'}")
    st.caption(f"Supabase: {'configured ✅' if is_supabase_configured() else 'missing ⚠️'}")
    if st.button("🔌 Test Supabase connection"):
        success, message = test_connection()
        st.success(message) if success else st.error(message)

overview = get_admin_overview()
cols = st.columns(4)
cols[0].metric("Registered users", overview["total_users"])
cols[1].metric("Total leads (all users)", overview["total_leads"])
cols[2].metric("Leads with email", overview["with_email"])
cols[3].metric("Low DR (≤ 30)", overview["low_dr"])

st.markdown("#### Users & their leads")
if overview["per_user"]:
    st.dataframe(
        pd.DataFrame(overview["per_user"]).rename(columns={
            "email": "User", "leads": "Leads", "with_email": "With email", "last_hunt": "Last hunt (UTC)",
        }),
        width="stretch", hide_index=True,
    )
if overview["profiles"]:
    with st.expander(f"Registered accounts ({len(overview['profiles'])})"):
        st.dataframe(pd.DataFrame(overview["profiles"]), width="stretch", hide_index=True)

st.markdown("#### All leads (every user)")
search = st.text_input("Search (domain / title / email)", key="admin_search")
all_leads, _ = fetch_leads_from_supabase(limit=1000, search_query=search if search.strip() else None)
if all_leads:
    frame = pd.DataFrame(all_leads)
    show_cols = [c for c in ["user_email", "domain", "url", "niche", "country", "city", "dr_score", "emails", "phone", "whatsapp", "created_at"] if c in frame.columns]
    display = frame[show_cols]
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        display.to_excel(writer, index=False, sheet_name="All Leads")
    st.download_button(
        "📥 Download all leads (Excel)",
        data=buffer.getvalue(),
        file_name="all_link_loot_leads.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.dataframe(display, width="stretch", hide_index=True)

    with st.expander("🗑️ Delete a lead (any user)"):
        options = {
            f"{row.get('user_email') or '—'} · {row.get('domain') or row.get('url')}": row.get("id")
            for row in all_leads if row.get("id") is not None
        }
        if options:
            chosen = st.selectbox("Choose a lead", options=list(options))
            if st.button("Delete lead"):
                ok, message = delete_lead_by_id(options[chosen])
                if ok:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
else:
    st.info("No leads found.")
