import io
import os
from pathlib import Path
import sys
import time

# Ensure application root directory is at the front of sys.path on Streamlit Cloud
APP_ROOT = str(Path(__file__).resolve().parent)
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

import pandas as pd
import streamlit as st

from app_config import (
    AHREFS_API_KEY,
    HUNTER_API_KEY,
    LOW_DR_THRESHOLD,
    MAX_WEBSITES_TO_CHECK,
    SERPER_API_KEY,
    SUPABASE_KEY,
    SUPABASE_URL,
)
from auth import ensure_profile, is_admin, is_auth_configured, sign_in, sign_up
from low_dr_finder import (
    COUNTRY_SEARCH_SETTINGS,
    find_websites,
    process_websites,
)
from supabase_db import (
    delete_lead_by_id,
    fetch_leads_from_supabase,
    fetch_profiles,
    get_admin_overview,
    get_database_stats,
    is_supabase_configured,
    save_leads_to_supabase,
    test_connection,
)


st.set_page_config(
    page_title="Link Loot — Low-DR Lead Finder",
    page_icon=":material/travel_explore:",
    layout="wide",
)

HERO_CSS = """
<style>
.linkloot-hero {
    background: linear-gradient(120deg, #3B1470 0%, #6D3FA3 55%, #C2410C 130%);
    border-radius: 16px;
    padding: 28px 32px;
    color: #FFFFFF;
    margin-bottom: 8px;
}
.linkloot-hero h1 { color: #FFFFFF; margin: 0 0 6px 0; font-size: 2.1rem; }
.linkloot-hero p { color: #EDE7F7; margin: 0; font-size: 1.02rem; }
.linkloot-hero .pill {
    display: inline-block; background: rgba(255,255,255,0.16);
    border: 1px solid rgba(255,255,255,0.35); border-radius: 999px;
    padding: 2px 12px; margin: 10px 6px 0 0; font-size: 0.82rem; color: #FFF;
}
</style>
"""
st.markdown(HERO_CSS, unsafe_allow_html=True)

LOGO_PATH = str(Path(__file__).with_name("link_loot.svg"))


def current_user():
    return st.session_state.get("auth_user")


def do_logout():
    for key in ("auth_user", "results", "export_name", "export_data", "supabase_sync_msg"):
        st.session_state.pop(key, None)
    st.rerun()


def build_excel_bytes(results):
    """Build the Excel export in memory — one sheet per country.

    Per-user and per-session: nothing is written to a shared file on the
    server, so two users hunting at the same time never mix workbooks.
    """
    cols = [
        "country", "domain", "url", "title", "dr_score", "dr_source",
        "emails", "email_status", "facebook", "linkedin", "instagram",
        "twitter", "phone", "whatsapp", "dr_status", "scrape_status",
    ]
    frame = pd.DataFrame(results)
    for col in cols:
        if col not in frame.columns:
            frame[col] = ""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        countries = sorted({str(c) for c in frame["country"].dropna() if str(c).strip()}) or ["Leads"]
        for country in countries:
            sheet = country[:31] or "Leads"
            subset = frame[frame["country"] == country] if country in set(frame["country"]) else frame
            subset[cols].to_excel(writer, index=False, sheet_name=sheet)
    return buffer.getvalue()


LEAD_DISPLAY_COLUMNS = {
    "country": "Country",
    "domain": "Domain",
    "url": "Website",
    "title": "Title",
    "dr_score": "DR",
    "dr_source": "DR source",
    "emails": "Emails",
    "email_status": "Email verification",
    "facebook": "Facebook",
    "linkedin": "LinkedIn",
    "instagram": "Instagram",
    "twitter": "X / Twitter",
    "phone": "Phone",
    "whatsapp": "WhatsApp",
    "dr_status": "DR status",
    "scrape_status": "Contact status",
    "niche": "Niche",
    "city": "City",
    "user_email": "Owner",
    "created_at": "Saved At",
}


def render_services_sidebar():
    """Helpful, plain-language status of every connected service."""
    st.markdown("### Services")
    st.caption(
        f"🔍 **Web search** — {'Ready ✅' if SERPER_API_KEY else 'API key needed ⚠️'}"
        "\nFinds real local businesses on Google for your niche + city."
    )
    st.caption(
        f"📊 **Ahrefs Domain Rating** — {'Ready ✅' if AHREFS_API_KEY else 'API key needed ⚠️'}"
        "\nChecks each site's real DR so only low-DR, easy-to-pitch sites pass."
    )
    st.caption(
        f"✉️ **Email finder & verifier** — {'Ready ✅' if HUNTER_API_KEY else 'Basic mode'}"
        "\nCollects one domain-matching email per site. Hunter.io also verifies it when configured."
    )
    st.caption(
        f"🗄️ **Your private lead vault** — {'Connected ✅' if is_supabase_configured() else 'Not configured ⚠️'}"
        "\nEvery lead you hunt is saved to your own account. Nobody else can see your leads."
    )
    with st.expander("How Link Loot works"):
        st.markdown(
            "1. **Pick a niche + country** (add a city for laser-focused local leads).\n"
            "2. **We search Google** with local service & pricing phrases buyers actually use.\n"
            "3. **DR filter** drops strong sites you would waste time pitching.\n"
            "4. **Contacts are scraped** — email, phone, WhatsApp and socials.\n"
            "5. **Download Excel** or find everything later under **My Leads**."
        )
    with st.expander("Tips for better leads"):
        st.markdown(
            "- Start with **Max DR 20–30** — the easiest sites to win.\n"
            "- One country + one city gives the most relevant local leads.\n"
            "- Try niche variations: `dentist`, `dental clinic`, `cosmetic dentist`.\n"
            "- Leads **with email + WhatsApp** reply the fastest — filter for them in My Leads."
        )


# =============================================================
#  PUBLIC HOME + LOGIN / SIGNUP
# =============================================================

def render_auth_page():
    with st.sidebar:
        st.image(LOGO_PATH, width=64)
        st.markdown("### Why create an account?")
        st.markdown(
            "- 🎯 **Your own dashboard** — your hunts, your leads, nobody else's\n"
            "- 🔒 **Private by design** — a dentist hunt and a roofing hunt never mix\n"
            "- 💾 **Leads saved automatically** — come back any time, download any time\n"
            "- 🆓 **Free to start** — sign up in under a minute"
        )
        st.divider()
        render_services_sidebar()

    st.markdown(
        """
        <div class="linkloot-hero">
            <h1>🎯 Link Loot</h1>
            <p>Find <b>low-DR websites</b> for local SEO &amp; outreach — with email, phone,
            WhatsApp and socials already attached. The easiest clients to pitch, in any niche,
            in any country.</p>
            <span class="pill">✅ Real Ahrefs DR</span>
            <span class="pill">✅ Contacts included</span>
            <span class="pill">✅ Private dashboard</span>
            <span class="pill">✅ Excel export</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    feat1, feat2, feat3 = st.columns(3)
    feat1.markdown("#### 🎯 Low-DR, high chance\nStrong sites ignore cold outreach. Link Loot filters for **DR 0–30** sites that actually need SEO help — and reply.")
    feat2.markdown("#### 📇 Contacts, not just URLs\nEvery lead comes with **email, phone, WhatsApp, Facebook, LinkedIn, Instagram & X** where available. Pitch the same day.")
    feat3.markdown("#### 🔒 Yours alone\nYour searches and leads are tied to **your account only**. Another user's roofing hunt will never touch your dentist leads.")

    st.divider()

    auth_col, how_col = st.columns([1.05, 1])
    with auth_col:
        tab_login, tab_signup = st.tabs(["🔐 Log in", "✨ Create account"])
        with tab_login:
            with st.form("login_form"):
                login_email = st.text_input("Email", placeholder="you@example.com")
                login_password = st.text_input("Password", type="password")
                login_submitted = st.form_submit_button("Log in", type="primary", width="stretch")
            if login_submitted:
                if not login_email.strip() or not login_password:
                    st.warning("Enter your email and password.")
                else:
                    ok, message, user = sign_in(login_email, login_password)
                    if ok and user:
                        st.session_state["auth_user"] = user
                        ensure_profile(user)
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
        with tab_signup:
            with st.form("signup_form"):
                signup_name = st.text_input("Your name", placeholder="e.g. Ali Khan")
                signup_email = st.text_input("Email", placeholder="you@example.com", key="signup_email")
                signup_password = st.text_input("Create a password", type="password", key="signup_password",
                                                 help="At least 6 characters.")
                signup_submitted = st.form_submit_button("Create my free account", type="primary", width="stretch")
            if signup_submitted:
                if not signup_email.strip() or not signup_password:
                    st.warning("Enter an email and a password to create your account.")
                elif len(signup_password) < 6:
                    st.warning("Password must be at least 6 characters.")
                else:
                    ok, message, user = sign_up(signup_email, signup_password, signup_name)
                    if ok and user:
                        st.session_state["auth_user"] = user
                        ensure_profile(user)
                        st.success(message)
                        st.rerun()
                    elif ok:
                        st.success(message)
                    else:
                        st.error(message)
            st.caption("By creating an account you get your own private dashboard. We never share your leads with other users.")
    with how_col:
        st.markdown("#### How it works")
        st.markdown(
            "**1. Sign up free** — your private dashboard is created instantly.\n\n"
            "**2. Hunt a niche** — e.g. *dentist in Austin, USA* or *roofing in London, UK*.\n\n"
            "**3. Get pitch-ready leads** — low-DR sites with contacts, saved to **My Leads**.\n\n"
            "**4. Export & outreach** — download Excel and start pitching the same day."
        )
        st.markdown("#### Who is it for?")
        st.markdown(
            "- SEO freelancers hunting their first (or next) clients\n"
            "- Agencies building outreach & guest-post lists\n"
            "- Local SEO specialists who need low-competition targets, fast"
        )
        with st.expander("FAQ"):
            st.markdown(
                "**Is my data shared with other users?** No. Every account sees only its own hunts and leads.\n\n"
                "**What DR should I choose?** DR 0–30 is the sweet spot: real businesses with weak SEO.\n\n"
                "**Do I need my own API keys?** No — search, DR checks and contact scraping are already connected.\n\n"
                "**Can I export my leads?** Yes, one click downloads an Excel file, one sheet per country."
            )

    if not is_auth_configured():
        st.warning("⚠️ Accounts are not configured yet (Supabase Auth). Admin: add SUPABASE_URL and SUPABASE_KEY in Streamlit Secrets.")


user = current_user()
if not user:
    render_auth_page()
    st.stop()

# =============================================================
#  LOGGED-IN APP
# =============================================================

ensure_profile(user)
user_is_admin = is_admin(user)

with st.sidebar:
    st.markdown(f"### 👤 {user.get('email', 'My account')}")
    if user_is_admin:
        st.success("🛡️ Admin account")
    else:
        st.caption("🔒 Private dashboard — only you can see your leads.")
    if st.button("Log out", width="stretch"):
        do_logout()
    st.divider()
    st.markdown("### Search settings")
    threshold = st.slider(
        "Maximum DR",
        min_value=0,
        max_value=100,
        value=int(LOW_DR_THRESHOLD),
        help="Sites with a verified DR above this score are left out. 20–30 is the sweet spot for easy wins.",
    )
    website_options = [20, 30, 50, 100]
    default_website_count = (
        MAX_WEBSITES_TO_CHECK
        if MAX_WEBSITES_TO_CHECK in website_options
        else 50
    )
    max_websites = st.selectbox(
        "Websites per country",
        options=website_options,
        index=website_options.index(default_website_count),
        help="More websites = a wider hunt, but it takes a little longer.",
    )
    st.divider()
    render_services_sidebar()

st.logo(LOGO_PATH)
st.markdown(
    """
    <div class="linkloot-hero">
        <h1>🎯 Link Loot</h1>
        <p>Find low-DR websites for local SEO and outreach across every niche —
        with contacts attached and saved privately to your account.</p>
        <span class="pill">🎯 Hunt Leads</span>
        <span class="pill">📁 My Leads — only yours</span>
        <span class="pill">📥 Excel export</span>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_names = ["🎯 Hunt Leads", "📁 My Leads"]
if user_is_admin:
    tab_names.append("🛡️ Admin")
tabs = st.tabs(tab_names)
tab_hunt = tabs[0]
tab_my_leads = tabs[1]
tab_admin = tabs[2] if user_is_admin else None

# =============================================================
#  TAB: HUNT LEADS
# =============================================================

with tab_hunt:
    st.markdown("#### Start a hunt")
    st.caption("Pick a niche, choose where to hunt, and Link Loot returns low-DR sites with contact details — saved privately to your account.")
    with st.form("search_form"):
        niche_col, country_col, city_col = st.columns([1, 1.35, 0.85])
        with niche_col:
            niche = st.text_input("Niche or market", placeholder="e.g. roofing, dentist, pet supplies")
        with country_col:
            countries = st.multiselect(
                "Countries",
                options=list(COUNTRY_SEARCH_SETTINGS),
                default=["USA", "UK"],
                help="Each country is saved to its own sheet in the same Excel workbook.",
            )
        with city_col:
            city = st.text_input("City (optional)", placeholder="e.g. Austin")
        st.caption("Search uses local-language service, booking, pricing, and best-provider phrases. Search results do not include keyword difficulty.")
        st.caption("City is used for single-country hunts; multi-country hunts search each country broadly.")
        submitted = st.form_submit_button("🎯 Hunt websites", type="primary", width="stretch")

    if submitted:
        if not SERPER_API_KEY:
            st.error("Web search is not configured. Please contact the admin.")
        elif not AHREFS_API_KEY:
            st.error("Domain Rating checks are not configured. Please contact the admin.")
        elif not niche.strip() or not countries:
            st.warning("Enter a niche and select at least one country to start searching.")
        else:
            progress = st.progress(0, text="Preparing search...")
            status = st.status("Searching for websites", expanded=True)
            started_at = time.time()

            try:
                websites_by_country = {}
                city_target = city.strip() if len(countries) == 1 else None
                for country_index, country in enumerate(countries):
                    def update_country_search_progress(current, total, message, country=country, country_index=country_index):
                        fraction = (country_index + current / total) / len(countries) * 0.45
                        progress.progress(fraction, text=f"{country}: {message}")
                        status.write(f"{country}: {message}")

                    websites_by_country[country] = find_websites(
                        niche.strip(),
                        country,
                        city_target,
                        max_results=max_websites,
                        progress_callback=update_country_search_progress,
                    )

                countries_with_websites = [
                    country for country, websites in websites_by_country.items() if websites
                ]
                all_websites = sum(len(websites) for websites in websites_by_country.values())
                if all_websites:
                    progress.progress(0.45, text="Checking domain ratings and contact details...")
                    status.update(label=f"Checking {all_websites} websites across {len(countries_with_websites)} countries", state="running")

                    results = []
                    for country_index, country in enumerate(countries_with_websites):
                        def update_process_progress(current, total, message, country=country, country_index=country_index):
                            fraction = 0.45 + 0.55 * (country_index + current / total) / len(countries_with_websites)
                            progress.progress(fraction, text=f"{country}: {message}")
                            status.write(f"{country}: {message}")

                        country_results = process_websites(
                            websites_by_country[country],
                            check_dr=True,
                            dr_threshold=threshold,
                            max_results=max_websites,
                            progress_callback=update_process_progress,
                        )
                        for result in country_results:
                            result["country"] = country
                            result["niche"] = niche.strip()
                            if city_target:
                                result["city"] = city_target
                        results.extend(country_results)

                    st.session_state["results"] = results
                    st.session_state["threshold"] = threshold
                    if results:
                        st.session_state["export_name"] = "link_loot_leads.xlsx"
                        st.session_state["export_data"] = build_excel_bytes(results)

                        # Save to the user's OWN lead vault
                        if is_supabase_configured():
                            saved_count, msg = save_leads_to_supabase(
                                results,
                                niche=niche.strip(),
                                country=countries[0] if len(countries) == 1 else "",
                                city=city_target or "",
                                user_id=user.get("id"),
                                user_email=user.get("email", ""),
                                access_token=user.get("access_token"),
                            )
                            st.session_state["supabase_sync_msg"] = msg
                    else:
                        st.session_state.pop("export_name", None)
                        st.session_state.pop("export_data", None)
                        st.session_state.pop("supabase_sync_msg", None)

                    status.update(
                        label=f"Completed in {time.time() - started_at:.1f} seconds",
                        state="complete",
                        expanded=False,
                    )
                    progress.empty()
                    if not results:
                        st.info("No sites matched this DR threshold. Try a higher maximum DR.")
                else:
                    st.session_state["results"] = []
                    status.update(label="Search complete: no websites found", state="complete")
                    progress.empty()
                    st.info("No websites found for that search. Try another niche or location.")
            except Exception as error:
                status.update(label="The search could not be completed", state="error")
                progress.empty()
                st.error(f"Something went wrong: {error}")

    results = st.session_state.get("results", [])
    if results:
        st.markdown("#### Lead overview")
        with_email = sum(bool(row.get("emails") and row["emails"] != "—") for row in results)
        low_dr = sum(
            row.get("dr_score") is not None and row["dr_score"] <= st.session_state.get("threshold", threshold)
            for row in results
        )
        with_social = sum(
            bool(row.get("facebook") or row.get("linkedin") or row.get("instagram") or row.get("twitter"))
            for row in results
        )
        metric_cols = st.columns(4)
        metric_cols[0].metric("Leads found", len(results))
        metric_cols[1].metric("Low DR", low_dr)
        metric_cols[2].metric("With email", with_email)
        metric_cols[3].metric("With social links", with_social)

        if st.session_state.get("supabase_sync_msg"):
            st.success(f"🗄️ {st.session_state['supabase_sync_msg']} — find them any time in **My Leads**.")

        st.caption(
            "DR 0 through the selected maximum is included. Ahrefs DR is required for DR filtering; "
            "OpenPageRank is not treated as Domain Rating."
        )
        if not HUNTER_API_KEY:
            st.info(
                "Email verification (Hunter.io) is not switched on by the admin yet. "
                "Emails shown are collected from the sites themselves — a quick manual check before a big campaign is a good idea."
            )

        st.markdown("#### Website results")
        if st.session_state.get("export_data"):
            st.download_button(
                "📥 Download Excel",
                data=st.session_state["export_data"],
                file_name=st.session_state["export_name"],
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        results_frame = pd.DataFrame(results).rename(columns=LEAD_DISPLAY_COLUMNS)
        st.dataframe(
            results_frame,
            width="stretch",
            hide_index=True,
            column_config={"Website": st.column_config.LinkColumn("Website", display_text="Open site")},
        )
    elif "results" in st.session_state:
        st.markdown("#### Lead overview")
        st.caption("No lead results to display yet.")
    else:
        st.info("👆 Run your first hunt above — try **dentist + USA + Austin** or **roofing + UK** to see it in action.")

# =============================================================
#  TAB: MY LEADS (private — only the signed-in user's leads)
# =============================================================

with tab_my_leads:
    st.markdown("### 📁 My Leads")
    st.caption("Only your leads live here. They are saved to your account every time you hunt — no other user can see, download or delete them.")

    if not is_supabase_configured():
        st.warning("⚠️ Lead storage is not connected yet. Please contact the admin.")
    else:
        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([1, 1, 1, 1.2])
        with filter_col1:
            selected_country = st.selectbox(
                "Filter Country",
                options=["All"] + list(COUNTRY_SEARCH_SETTINGS.keys()),
                index=0,
                key="db_country_filter",
            )
        with filter_col2:
            niche_filter = st.text_input("Filter Niche", placeholder="e.g. roofing", key="db_niche_filter")
        with filter_col3:
            max_dr_filter = st.slider("Max DR", 0, 100, 100, key="db_dr_filter")
        with filter_col4:
            email_only = st.checkbox("Only leads with email", value=False, key="db_email_filter")
            search_query = st.text_input("Search (domain / title / email)", placeholder="e.g. acme", key="db_search_filter")

        if st.button("🔄 Refresh my leads", type="secondary"):
            st.rerun()

        leads_data, status_msg = fetch_leads_from_supabase(
            limit=500,
            country=None if selected_country == "All" else selected_country,
            niche=niche_filter if niche_filter.strip() else None,
            max_dr=max_dr_filter if max_dr_filter < 100 else None,
            with_email_only=email_only,
            search_query=search_query if search_query.strip() else None,
            user_id=user.get("id"),
            access_token=user.get("access_token"),
        )
        # Safety net: even if the database returned extra rows, only ever
        # display rows that belong to this account.
        my_email = (user.get("email") or "").lower()
        leads_data = [
            row for row in leads_data
            if row.get("user_id") == user.get("id")
            or (row.get("user_email") or "").lower() == my_email and my_email
        ]

        stat_col1, stat_col2, stat_col3 = st.columns(3)
        stat_col1.metric("My leads", len(leads_data))
        stat_col2.metric("With email", sum(1 for r in leads_data if r.get("emails")))
        stat_col3.metric("Low DR (≤ 30)", sum(1 for r in leads_data if r.get("dr_score") is not None and r["dr_score"] <= 30))

        if leads_data:
            df_db = pd.DataFrame(leads_data)
            col_order = [
                "domain", "url", "niche", "country", "city", "dr_score",
                "emails", "phone", "whatsapp", "facebook", "linkedin", "title", "created_at"
            ]
            display_cols = [c for c in col_order if c in df_db.columns]
            df_display = df_db[display_cols].rename(columns=LEAD_DISPLAY_COLUMNS)

            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                df_display.to_excel(writer, index=False, sheet_name="My Leads")
            st.download_button(
                "📥 Download my leads (Excel)",
                data=excel_buffer.getvalue(),
                file_name="my_link_loot_leads.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            st.dataframe(
                df_display,
                width="stretch",
                hide_index=True,
                column_config={"Website": st.column_config.LinkColumn("Website", display_text="Open site")},
            )

            with st.expander("🗑️ Delete one of my leads"):
                delete_options = {
                    f"{row.get('domain') or row.get('url')} (DR {row.get('dr_score')})": row.get("id")
                    for row in leads_data if row.get("id") is not None
                }
                if delete_options:
                    chosen_label = st.selectbox("Choose a lead to delete", options=list(delete_options), key="my_delete_select")
                    if st.button("Delete this lead", key="my_delete_button"):
                        ok, message = delete_lead_by_id(delete_options[chosen_label], user_id=user.get("id"))
                        if ok:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)
        else:
            st.info("No leads here yet. Run a hunt in **🎯 Hunt Leads** and your leads will appear here automatically.")


# =============================================================
#  TAB: ADMIN (only for ADMIN_EMAILS accounts)
#  Database browser, Setup & SQL and platform controls live
#  here — regular users never see them.
# =============================================================

if tab_admin is not None:
    with tab_admin:
        st.markdown("### 🛡️ Admin Dashboard")
        st.caption("Platform-wide control: every user, every lead, system health and setup. Regular users never see this tab.")

        overview = get_admin_overview()
        admin_metric_cols = st.columns(4)
        admin_metric_cols[0].metric("Registered users", overview["total_users"])
        admin_metric_cols[1].metric("Total leads (all users)", overview["total_leads"])
        admin_metric_cols[2].metric("Leads with email", overview["with_email"])
        admin_metric_cols[3].metric("Low DR (≤ 30)", overview["low_dr"])

        st.markdown("#### Users & their leads")
        if overview["per_user"]:
            st.dataframe(
                pd.DataFrame(overview["per_user"]).rename(columns={
                    "email": "User", "leads": "Leads", "with_email": "With email", "last_hunt": "Last hunt (UTC)",
                }),
                width="stretch", hide_index=True,
            )
        else:
            st.info("No leads saved yet.")
        if overview["profiles"]:
            with st.expander(f"Registered accounts ({len(overview['profiles'])})"):
                st.dataframe(
                    pd.DataFrame(overview["profiles"]).rename(columns={
                        "email": "Email", "full_name": "Name", "created_at": "Signed up (UTC)",
                    }),
                    width="stretch", hide_index=True,
                )
        else:
            st.caption("No rows in public.profiles yet — run supabase_schema_v2.sql and profiles will fill in as users log in.")

        niche_col, country_col = st.columns(2)
        with niche_col:
            st.markdown("#### Leads by niche")
            if overview["per_niche"]:
                st.dataframe(pd.DataFrame(
                    [{"Niche": k, "Leads": v} for k, v in sorted(overview["per_niche"].items(), key=lambda kv: -kv[1])]
                ), width="stretch", hide_index=True)
        with country_col:
            st.markdown("#### Leads by country")
            if overview["per_country"]:
                st.dataframe(pd.DataFrame(
                    [{"Country": k, "Leads": v} for k, v in sorted(overview["per_country"].items(), key=lambda kv: -kv[1])]
                ), width="stretch", hide_index=True)

        st.divider()
        st.markdown("#### All leads (every user)")
        admin_search = st.text_input("Search all leads (domain / title / email)", key="admin_search")
        all_leads, _ = fetch_leads_from_supabase(
            limit=1000,
            search_query=admin_search if admin_search.strip() else None,
        )
        if all_leads:
            admin_frame = pd.DataFrame(all_leads)
            admin_cols = [c for c in ["user_email", "domain", "url", "niche", "country", "city", "dr_score", "emails", "phone", "whatsapp", "created_at"] if c in admin_frame.columns]
            admin_display = admin_frame[admin_cols].rename(columns=LEAD_DISPLAY_COLUMNS)
            admin_buffer = io.BytesIO()
            with pd.ExcelWriter(admin_buffer, engine="openpyxl") as writer:
                admin_display.to_excel(writer, index=False, sheet_name="All Leads")
            st.download_button(
                "📥 Download all leads (Excel)",
                data=admin_buffer.getvalue(),
                file_name="all_link_loot_leads.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            st.dataframe(
                admin_display, width="stretch", hide_index=True,
                column_config={"Website": st.column_config.LinkColumn("Website", display_text="Open site")},
            )
            with st.expander("🗑️ Delete a lead (any user)"):
                admin_delete_options = {
                    f"{row.get('user_email') or '—'} · {row.get('domain') or row.get('url')}": row.get("id")
                    for row in all_leads if row.get("id") is not None
                }
                if admin_delete_options:
                    admin_chosen = st.selectbox("Choose a lead", options=list(admin_delete_options), key="admin_delete_select")
                    if st.button("Delete lead", key="admin_delete_button"):
                        ok, message = delete_lead_by_id(admin_delete_options[admin_chosen])
                        if ok:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)
        else:
            st.info("No leads found.")

        st.divider()
        st.markdown("#### System & setup")
        sys_col1, sys_col2 = st.columns(2)
        with sys_col1:
            st.markdown("**Service keys (values never shown)**")
            st.caption(f"Serper (web search): {'set ✅' if SERPER_API_KEY else 'missing ⚠️'}")
            st.caption(f"Ahrefs (DR): {'set ✅' if AHREFS_API_KEY else 'missing ⚠️'}")
            st.caption(f"Hunter (email verify): {'set ✅' if HUNTER_API_KEY else 'not set'}")
            st.caption(f"Supabase: {'configured ✅' if is_supabase_configured() else 'missing ⚠️'}")
            if st.button("🔌 Test Supabase connection", type="primary"):
                success, message = test_connection()
                if success:
                    st.success(f"✅ {message}")
                else:
                    st.error(f"❌ {message}")
        with sys_col2:
            st.markdown("**One-time setup checklist**")
            st.markdown(
                "1. Run **supabase_schema.sql** (v1) in Supabase SQL Editor — creates the leads table.\n"
                "2. Run **supabase_schema_v2.sql** — adds per-user leads + profiles (accounts update).\n"
                "3. In Supabase → Authentication → Providers → Email: keep **Email** enabled so users can sign up.\n"
                "4. In Streamlit Secrets set **ADMIN_EMAILS** to your email to unlock this Admin tab.\n"
                "5. Make sure **SUPABASE_URL / SUPABASE_KEY** and the API keys are in Streamlit Secrets."
            )

        for schema_name in ("supabase_schema_v2.sql", "supabase_schema.sql"):
            schema_file = Path(__file__).with_name(schema_name)
            if schema_file.exists():
                with st.expander(f"📄 {schema_name}"):
                    sql_content = schema_file.read_text(encoding="utf-8")
                    st.code(sql_content, language="sql")
                    st.download_button(
                        f"Download {schema_name}",
                        data=sql_content,
                        file_name=schema_name,
                        mime="text/plain",
                        key=f"dl_{schema_name}",
                    )
