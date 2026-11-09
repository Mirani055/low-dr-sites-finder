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
from auth import (
    ensure_profile,
    get_user_from_token,
    google_sign_in_url,
    is_admin,
    is_auth_configured,
    resend_confirmation,
    sign_in,
    sign_up,
)
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
    page_title="Link Loot. Low DR Lead Finder",
    page_icon=":material/travel_explore:",
    layout="wide",
)

STYLE_CSS = """
<style>
.hero {
    background: linear-gradient(120deg, #2E1065 0%, #5B2A9D 58%, #9A3412 135%);
    border-radius: 18px;
    padding: 40px 44px;
    color: #FFFFFF;
    margin-bottom: 10px;
}
.hero .kicker {
    letter-spacing: 2.5px; font-size: 0.78rem; font-weight: 600;
    color: #D8CCF2; text-transform: uppercase; margin-bottom: 10px;
}
.hero h1 { color: #FFFFFF; margin: 0 0 10px 0; font-size: 2.5rem; line-height: 1.15; }
.hero p.lede { color: #EFEAF9; font-size: 1.08rem; margin: 0; max-width: 760px; line-height: 1.55; }
.hero .facts { margin-top: 18px; color: #FFFFFF; font-size: 0.92rem; }
.hero .facts span {
    display: inline-block; border: 1px solid rgba(255,255,255,0.4);
    border-radius: 999px; padding: 3px 14px; margin: 0 8px 6px 0;
    background: rgba(255,255,255,0.10);
}
@keyframes riseIn {
    from { opacity: 0; transform: translateY(26px); }
    to { opacity: 1; transform: translateY(0); }
}
@keyframes drawCheck {
    to { stroke-dashoffset: 0; }
}
@keyframes popIn {
    0% { transform: scale(0.6); opacity: 0; }
    70% { transform: scale(1.06); opacity: 1; }
    100% { transform: scale(1); opacity: 1; }
}
.welcome {
    background: linear-gradient(130deg, #2E1065 0%, #5B2A9D 55%, #9A3412 140%);
    border-radius: 22px; color: #FFFFFF; text-align: center;
    padding: 56px 40px 46px 40px; margin-top: 18px;
}
.welcome .badge {
    width: 92px; height: 92px; margin: 0 auto 22px auto;
    animation: popIn 0.7s ease both;
}
.welcome .badge circle.bg { stroke: rgba(255,255,255,0.35); }
.welcome .badge path.tick {
    stroke-dasharray: 60; stroke-dashoffset: 60;
    animation: drawCheck 0.6s ease 0.55s forwards;
}
.welcome h1 { color: #FFFFFF; animation: riseIn 0.7s ease 0.25s both; margin-bottom: 8px; }
.welcome p.lede {
    color: #EFEAF9; font-size: 1.06rem; max-width: 640px;
    margin: 0 auto; line-height: 1.6; animation: riseIn 0.7s ease 0.45s both;
}
.welcome .points {
    margin: 26px auto 4px auto; max-width: 620px; text-align: left;
    animation: riseIn 0.7s ease 0.65s both; line-height: 1.75; color: #FFFFFF;
}
.welcome .signed { color: #CDBEF0; font-size: 0.9rem; margin-top: 18px; animation: riseIn 0.7s ease 0.85s both; }
</style>
"""
st.markdown(STYLE_CSS, unsafe_allow_html=True)

LOGO_PATH = str(Path(__file__).with_name("link_loot_logo.png"))


def current_user():
    return st.session_state.get("auth_user")


def do_logout():
    for key in ("auth_user", "results", "export_name", "export_data", "supabase_sync_msg", "show_welcome"):
        st.session_state.pop(key, None)
    st.rerun()


def build_excel_bytes(results):
    """Build the Excel export in memory, with one sheet per country.

    The export belongs to the signed in user and is generated inside their
    own session. Nothing is written to a shared file on the server, so two
    people hunting at the same time can never receive each others workbook.
    """
    cols = [
        "country", "domain", "url", "title", "dr_score", "dr_source",
        "emails", "facebook", "linkedin", "instagram",
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
    "created_at": "Saved",
}

RESULT_COLUMN_ORDER = [
    "country", "niche", "city", "domain", "url", "title", "dr_score",
    "dr_source", "emails", "phone", "whatsapp",
    "facebook", "linkedin", "instagram", "twitter",
]


def status_line(configured, what_it_does):
    icon = ":material/check_circle:" if configured else ":material/error:"
    word = "Operational" if configured else "Action required"
    st.caption(f"{icon} **{word}.** {what_it_does}")


def render_services_sidebar():
    """Connected services, described in terms of what they do for the user."""
    st.markdown("### Connected services")
    st.markdown("**Google search**")
    status_line(bool(SERPER_API_KEY), "Finds businesses that match your niche and location, using the phrases local customers actually search with.")
    st.markdown("**Ahrefs domain rating**")
    status_line(bool(AHREFS_API_KEY), "Rates the authority of every website found, so weak sites that need SEO surface first.")
    st.markdown("**Contact discovery**")
    status_line(True, "Reads each business website and its contact pages to collect an email address, phone number, WhatsApp and social profiles.")
    st.markdown("**Private lead storage**")
    status_line(is_supabase_configured(), "Saves every hunt to your account, so your leads are waiting for you whenever you sign in.")
    with st.expander("Getting better results"):
        st.markdown(
            "Set the maximum DR between 20 and 30. Those sites are established enough "
            "to pay for SEO and weak enough to need it.\n\n"
            "Choose one country and add a city when you want truly local clients. "
            "A focused hunt returns more relevant businesses than a wide one.\n\n"
            "Try more than one name for the same trade. Dentist, dental clinic and "
            "cosmetic dentist reach different businesses.\n\n"
            "Leads with both an email address and a WhatsApp number give you two "
            "ways to start a conversation, and they tend to reply fastest."
        )


# =============================================================
#  WELCOME INTRO, SHOWN ONCE AFTER A SUCCESSFUL SIGN IN
# =============================================================

def render_welcome(user):
    _wl, _wm, _wr = st.columns([1, 1.4, 1])
    with _wm:
        st.image(LOGO_PATH, width=280)
    st.markdown(
        f"""
        <div class="welcome">
            <div class="badge">
                <svg viewBox="0 0 100 100" width="92" height="92" fill="none">
                    <circle class="bg" cx="50" cy="50" r="45" stroke-width="3"/>
                    <circle cx="50" cy="50" r="45" stroke="#FFFFFF" stroke-width="3"
                        stroke-dasharray="283" stroke-dashoffset="283" opacity="0.9">
                        <animate attributeName="stroke-dashoffset" from="283" to="0" dur="0.9s" fill="freeze"/>
                    </circle>
                    <path class="tick" d="M32 51 L45 64 L69 38" stroke="#FFFFFF"
                        stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </div>
            <h1>Congratulations, your account is ready</h1>
            <p class="lede">
                Welcome to Link Loot. Your email address is confirmed, your private
                workspace is open, and from this moment everything you find here
                belongs to you alone.
            </p>
            <div class="points">
                <div>Search any niche in any supported country and receive businesses with low domain rating scores.</div>
                <div>Every lead arrives with contact details, ready for outreach on the same day.</div>
                <div>Your hunts save automatically to My Leads. No other account can see them.</div>
            </div>
            <div class="signed">Signed in as {user.get('email', '')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")
    _, button_col, _ = st.columns([1, 1, 1])
    with button_col:
        if st.button("Enter my dashboard", type="primary", width="stretch"):
            st.session_state["show_welcome"] = False
            st.rerun()


# =============================================================
#  PUBLIC HOME PAGE WITH SIGN IN AND SIGN UP
# =============================================================

def render_auth_page():
    with st.sidebar:
        st.image(LOGO_PATH, width=200)
        st.markdown("### Your account, your leads")
        st.markdown(
            "Link Loot is built for professionals who sell SEO services. "
            "An account gives you a private workspace where every search you run "
            "and every lead you collect stays yours. Other users cannot see your "
            "markets, your niches or your results, and your exports are generated "
            "for you alone."
        )
        st.divider()
        render_services_sidebar()

    st.markdown(
        """
        <div class="hero">
            <div class="kicker">Link Loot. Client acquisition for local SEO</div>
            <h1>Find local businesses that need SEO, with the contact details to reach them.</h1>
            <p class="lede">
                Link Loot searches a market for independent businesses, screens every website
                by its Ahrefs domain rating, and keeps only the low scoring sites that are
                realistic to pitch. Each lead arrives with an email address, phone number,
                WhatsApp and social profiles collected from the business itself, so a search
                in the morning can become a conversation by the afternoon.
            </p>
            <div class="facts">
                <span>Real Ahrefs DR on every lead</span>
                <span>Contacts collected for you</span>
                <span>A private dashboard per account</span>
                <span>Excel export included</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.get("auth_error_msg"):
        st.error(st.session_state.pop("auth_error_msg"))

    # Sign in and sign up, in one clean card directly under the hero.
    _, card_col, _ = st.columns([1, 1.7, 1])
    with card_col:
        with st.container(border=True):
            logo_left, logo_mid, logo_right = st.columns([0.6, 2, 0.6])
            with logo_mid:
                st.image(LOGO_PATH, width=300)
            st.markdown(
                "<h3 style='text-align: center; margin-bottom: 0;'>Welcome to Link Loot</h3>"
                "<p style='text-align: center; color: #6B6472; margin-top: 4px;'>"
                "Sign in to your workspace, or create a free account.</p>",
                unsafe_allow_html=True,
            )
            tab_login, tab_signup = st.tabs(["Sign in", "Create account"])
            with tab_login:
                with st.form("login_form"):
                    login_email = st.text_input("Email", placeholder="you@example.com")
                    login_password = st.text_input("Password", type="password")
                    login_submitted = st.form_submit_button("Continue", type="primary", width="stretch")
                if login_submitted:
                    if not login_email.strip() or not login_password:
                        st.warning("Enter your email address and your password.")
                    else:
                        ok, message, user = sign_in(login_email, login_password)
                        if ok and user:
                            st.session_state["auth_user"] = user
                            st.session_state["show_welcome"] = True
                            ensure_profile(user)
                            st.rerun()
                        else:
                            st.error("We could not sign you in. Check your email address and password, and make sure your email address has been confirmed.")
                st.caption("Confirmed your email address a moment ago? Sign in above and your dashboard will open.")
                with st.expander("The confirmation link has expired"):
                    st.markdown(
                        "Confirmation links work once and only for a limited time. Enter your "
                        "email address and we will send a fresh one. Always use the newest "
                        "link in your inbox."
                    )
                    with st.form("resend_form"):
                        resend_email = st.text_input("Email", placeholder="you@example.com", key="resend_email")
                        resend_submitted = st.form_submit_button("Send a new confirmation link", width="stretch")
                    if resend_submitted:
                        if not resend_email.strip():
                            st.warning("Enter the email address you signed up with.")
                        else:
                            ok, message = resend_confirmation(resend_email)
                            if ok:
                                st.success(message)
                            else:
                                st.error(message)
            with tab_signup:
                with st.form("signup_form"):
                    signup_name = st.text_input("Your name", placeholder="Full name")
                    signup_email = st.text_input("Email", placeholder="you@example.com", key="signup_email")
                    signup_password = st.text_input("Create a password", type="password", key="signup_password",
                                                     help="Use at least 6 characters.")
                    signup_submitted = st.form_submit_button("Create my account", type="primary", width="stretch")
                if signup_submitted:
                    if not signup_email.strip() or not signup_password:
                        st.warning("Enter an email address and a password to create your account.")
                    elif len(signup_password) < 6:
                        st.warning("Your password needs at least 6 characters.")
                    else:
                        ok, message, user = sign_up(signup_email, signup_password, signup_name)
                        if ok and user:
                            st.session_state["auth_user"] = user
                            st.session_state["show_welcome"] = True
                            ensure_profile(user)
                            st.rerun()
                        elif ok:
                            st.success("Your account has been created. We have emailed you a confirmation link. Select it once, then sign in here and your dashboard will open.")
                        else:
                            st.error(message)
                st.caption("Creating an account opens your private workspace. Your leads are never shared with other users.")
            st.markdown(
                "<div style='display: flex; align-items: center; gap: 12px; margin: 14px 0 10px 0;'>"
                "<hr style='flex: 1; border: none; border-top: 1px solid #E3DCF0;'>"
                "<span style='color: #6B6472; font-size: 0.85rem;'>or</span>"
                "<hr style='flex: 1; border: none; border-top: 1px solid #E3DCF0;'></div>",
                unsafe_allow_html=True,
            )
            st.link_button("Continue with Google", google_sign_in_url(), width="stretch")
            st.markdown(
                "<p style='text-align: center; color: #6B6472; font-size: 0.85rem; margin-bottom: 0;'>"
                "Protected by Supabase authentication. No captcha, no card, no commitment.</p>",
                unsafe_allow_html=True,
            )

    st.divider()

    st.markdown("### A lead is more than a web address")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.markdown(":material/verified: **Authority you can trust**")
        st.markdown(
            "Domain rating decides who is worth your time. Strong sites rarely answer "
            "cold outreach because they already rank. Link Loot verifies the DR of "
            "every candidate with Ahrefs and keeps only the range you set, which by "
            "default means scores of 30 or lower."
        )
    with col_b:
        st.markdown(":material/contacts: **Contacts that start conversations**")
        st.markdown(
            "A list of domains is not a pipeline. Every lead is enriched from the "
            "business website and its contact pages with an email address, phone "
            "number, WhatsApp and links to Facebook, LinkedIn, Instagram and X "
            "wherever the business publishes them."
        )
    with col_c:
        st.markdown(":material/person_search: **Context for a relevant pitch**")
        st.markdown(
            "Each result carries the business name, its niche, city and country. "
            "That context is what turns a generic message into a relevant one, and "
            "relevant messages are the ones owners reply to."
        )

    st.markdown("### How Link Loot qualifies every lead")
    step1, step2, step3, step4 = st.columns(4)
    step1.markdown("**Step 1. Search with local intent**\n\nQueries are built from the phrases customers use when they are ready to buy a local service, in the language of the country you choose.")
    step2.markdown("**Step 2. Authority screening**\n\nEvery website found is checked against Ahrefs. Anything above your maximum DR is removed before it reaches you.")
    step3.markdown("**Step 3. Contact discovery**\n\nSurviving sites are visited and read. Contact details are taken only from pages the business publishes itself.")
    step4.markdown("**Step 4. Private delivery**\n\nResults appear in your dashboard, save to My Leads under your account, and export to Excel with one sheet per country.")

    st.divider()

    who_col, data_col = st.columns(2)
    with who_col:
        st.markdown("#### Who uses Link Loot")
        st.markdown(
            "**Freelance SEO consultants** who need a steady flow of realistic first clients "
            "without spending their week on manual prospecting.\n\n"
            "**Local SEO agencies** building prospect lists for new service areas and new trades.\n\n"
            "**Outreach and link building teams** who need low authority sites with a named "
            "business and a working route to the owner."
        )
    with data_col:
        st.markdown("#### Your data stays yours")
        st.markdown(
            "Accounts are separated at the data level. Your searches are saved against your "
            "account only, your exports are generated inside your own session, and your "
            "leads never appear in another customer dashboard."
        )

    with st.expander("Questions, answered properly"):
        st.markdown(
            "**How is domain rating measured?** Every candidate is checked against the Ahrefs "
            "index at the moment of your search. The figure in your results is the live score, "
            "not an estimate from a smaller database.\n\n"
            "**Which markets can I search?** You can search "
            f"{len(COUNTRY_SEARCH_SETTINGS)} countries, and add a city whenever you hunt in a "
            "single country for a tighter local list.\n\n"
            "**Do I need my own API keys?** No. Search, authority checks and contact discovery "
            "run on the platform accounts, which is why the services panel on the left simply "
            "shows their status.\n\n"
            "**Where do my leads go?** Into My Leads, under your account, and into an Excel file "
            "whenever you choose to download one. Nothing is posted publicly and nothing is "
            "shared with other users.\n\n"
            "**What makes a lead good?** In our experience a DR between 10 and 30, a business "
            "that clearly sells a local service, and both an email address and a phone number. "
            "That combination replies at the highest rate."
        )

    if not is_auth_configured():
        st.warning("Accounts are not configured yet. The administrator needs to add the Supabase settings before anyone can sign in.")


# Google sign in returns through the bridge page with a token in the
# address. Validate it once, open the session, then clean the address so
# the token is not kept in the browser history or a bookmark.
if not current_user():
    _qp = st.query_params
    if "access_token" in _qp:
        _token_user = get_user_from_token(_qp.get("access_token", ""), _qp.get("refresh_token", ""))
        st.query_params.clear()
        if _token_user:
            st.session_state["auth_user"] = _token_user
            st.session_state["show_welcome"] = True
            ensure_profile(_token_user)
        else:
            st.session_state["auth_error_msg"] = "Google sign in did not complete. Please try again, or sign in with your email address and password."
        st.rerun()
    elif "auth_error" in _qp:
        st.session_state["auth_error_msg"] = _qp.get("auth_error", "Sign in did not complete.")
        st.query_params.clear()
        st.rerun()

user = current_user()
if not user:
    render_auth_page()
    st.stop()

# =============================================================
#  LOGGED IN APPLICATION
# =============================================================

ensure_profile(user)
user_is_admin = is_admin(user)

if st.session_state.get("show_welcome"):
    render_welcome(user)
    st.stop()

with st.sidebar:
    st.markdown("### Account")
    st.write(user.get("email", ""))
    if user_is_admin:
        st.success("Administrator account")
    else:
        st.caption("Private workspace. Only you can see your leads.")
    if st.button("Sign out", width="stretch"):
        do_logout()
    st.divider()
    st.markdown("### Search settings")
    threshold = st.slider(
        "Maximum DR",
        min_value=0,
        max_value=100,
        value=int(LOW_DR_THRESHOLD),
        help="Websites with a verified DR above this score are left out. A maximum between 20 and 30 gives the best balance of quality and reply rate.",
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
        help="A larger hunt covers more ground and takes a little longer.",
    )
    st.divider()
    render_services_sidebar()

st.logo(LOGO_PATH)
st.markdown(
    """
    <div class="hero">
        <div class="kicker">Link Loot</div>
        <h1>Your lead workspace</h1>
        <p class="lede">
            Search a niche, screen it by domain rating, and receive businesses with the
            contact details attached. Everything you find is saved privately to your account.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_names = ["Hunt Leads", "My Leads"]
if user_is_admin:
    tab_names.append("Admin")
tabs = st.tabs(tab_names)
tab_hunt = tabs[0]
tab_my_leads = tabs[1]
tab_admin = tabs[2] if user_is_admin else None


# =============================================================
#  TAB: HUNT LEADS
# =============================================================

with tab_hunt:
    st.markdown("#### Start a hunt")
    st.caption("Choose a niche and a market. Link Loot returns low DR businesses with contact details, and saves them to My Leads under your account.")
    with st.form("search_form"):
        niche_col, country_col, city_col = st.columns([1, 1.35, 0.85])
        with niche_col:
            niche = st.text_input("Niche or market", placeholder="For example, roofing or dentistry")
        with country_col:
            countries = st.multiselect(
                "Countries",
                options=list(COUNTRY_SEARCH_SETTINGS),
                default=["USA", "UK"],
                help="Each country is saved to its own sheet in the same Excel workbook.",
            )
        with city_col:
            city = st.text_input("City (optional)", placeholder="For example, Austin")
        st.caption("Search uses local language service, booking, pricing and best provider phrases, because those are the searches buyers make.")
        st.caption("A city applies when you hunt in a single country. With several countries, each one is searched broadly.")
        submitted = st.form_submit_button("Start search", type="primary", width="stretch")

    if submitted:
        if not SERPER_API_KEY:
            st.error("Web search is not configured. Please contact the administrator.")
        elif not AHREFS_API_KEY:
            st.error("Domain rating checks are not configured. Please contact the administrator.")
        elif not niche.strip() or not countries:
            st.warning("Enter a niche and select at least one country to start searching.")
        else:
            progress = st.progress(0, text="Preparing search")
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
                    progress.progress(0.45, text="Checking domain ratings and contact details")
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
                        st.info("No websites matched this DR threshold. Raising the maximum DR usually widens the field.")
                else:
                    st.session_state["results"] = []
                    status.update(label="Search complete. No websites found", state="complete")
                    progress.empty()
                    st.info("No websites were found for that search. Try another niche name or a wider location.")
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
            st.success(st.session_state["supabase_sync_msg"])

        st.caption(
            "Scores from zero through your selected maximum are included, and every score shown "
            "is the Ahrefs domain rating verified during this search."
        )
        st.caption(
            "Email addresses are collected from public business pages. Personal, relevant "
            "outreach consistently outperforms bulk messaging, so use the niche and city on "
            "each lead when you write."
        )

        st.markdown("#### Website results")
        if st.session_state.get("export_data"):
            st.download_button(
                "Download Excel",
                data=st.session_state["export_data"],
                file_name=st.session_state["export_name"],
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        results_frame_full = pd.DataFrame(results)
        display_columns = [c for c in RESULT_COLUMN_ORDER if c in results_frame_full.columns]
        results_frame = results_frame_full[display_columns].rename(columns=LEAD_DISPLAY_COLUMNS)
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
        st.info("Run your first hunt above. A focused starting point is one trade, one country and one city, for example dentistry in Austin, USA.")


# =============================================================
#  TAB: MY LEADS. PRIVATE TO THE SIGNED IN USER
# =============================================================

with tab_my_leads:
    st.markdown("### My Leads")
    st.caption("Every lead you have collected, saved under your account. Only you can see this list, download it or remove entries from it.")

    if not is_supabase_configured():
        st.warning("Lead storage is not connected yet. Please contact the administrator.")
    else:
        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([1, 1, 1, 1.2])
        with filter_col1:
            selected_country = st.selectbox(
                "Filter by country",
                options=["All"] + list(COUNTRY_SEARCH_SETTINGS.keys()),
                index=0,
                key="db_country_filter",
            )
        with filter_col2:
            niche_filter = st.text_input("Filter by niche", placeholder="For example, roofing", key="db_niche_filter")
        with filter_col3:
            max_dr_filter = st.slider("Maximum DR", 0, 100, 100, key="db_dr_filter")
        with filter_col4:
            email_only = st.checkbox("Only leads with email", value=False, key="db_email_filter")
            search_query = st.text_input("Search domain, title or email", placeholder="Search text", key="db_search_filter")

        if st.button("Refresh", type="secondary"):
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
        my_email = (user.get("email") or "").lower()
        leads_data = [
            row for row in leads_data
            if row.get("user_id") == user.get("id")
            or (row.get("user_email") or "").lower() == my_email and my_email
        ]

        stat_col1, stat_col2, stat_col3 = st.columns(3)
        stat_col1.metric("My leads", len(leads_data))
        stat_col2.metric("With email", sum(1 for r in leads_data if r.get("emails")))
        stat_col3.metric("Low DR, 30 or below", sum(1 for r in leads_data if r.get("dr_score") is not None and r["dr_score"] <= 30))

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
                "Download my leads as Excel",
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

            with st.expander("Remove one of my leads"):
                delete_options = {
                    f"{row.get('domain') or row.get('url')} (DR {row.get('dr_score')})": row.get("id")
                    for row in leads_data if row.get("id") is not None
                }
                if delete_options:
                    chosen_label = st.selectbox("Choose a lead to remove", options=list(delete_options), key="my_delete_select")
                    if st.button("Remove this lead", key="my_delete_button"):
                        ok, message = delete_lead_by_id(delete_options[chosen_label], user_id=user.get("id"))
                        if ok:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)
        else:
            st.info("Nothing here yet. Run a hunt in Hunt Leads and your results will be saved here automatically.")


# =============================================================
#  TAB: ADMIN. VISIBLE ONLY TO ADMIN ACCOUNTS
# =============================================================

if tab_admin is not None:
    with tab_admin:
        st.markdown("### Admin dashboard")
        st.caption("Platform wide control for the owner. Registered users, every lead, service health and the one time setup all live here, and regular users never see this tab.")

        overview = get_admin_overview()
        admin_metric_cols = st.columns(4)
        admin_metric_cols[0].metric("Registered users", overview["total_users"])
        admin_metric_cols[1].metric("Total leads, all users", overview["total_leads"])
        admin_metric_cols[2].metric("Leads with email", overview["with_email"])
        admin_metric_cols[3].metric("Low DR, 30 or below", overview["low_dr"])

        st.markdown("#### Users and their leads")
        if overview["per_user"]:
            st.dataframe(
                pd.DataFrame(overview["per_user"]).rename(columns={
                    "email": "User", "leads": "Leads", "with_email": "With email", "last_hunt": "Last hunt (UTC)",
                }),
                width="stretch", hide_index=True,
            )
        else:
            st.info("No leads have been saved yet.")
        if overview["profiles"]:
            with st.expander(f"Registered accounts ({len(overview['profiles'])})"):
                profiles_frame = pd.DataFrame(overview["profiles"])
                profile_cols = [c for c in ["email", "full_name", "created_at"] if c in profiles_frame.columns]
                st.dataframe(
                    profiles_frame[profile_cols].rename(columns={
                        "email": "Email", "full_name": "Name", "created_at": "Signed up (UTC)",
                    }),
                    width="stretch", hide_index=True,
                )
        else:
            st.caption("No profiles yet. Profiles fill in automatically as users sign in, once the version 2 SQL has been run.")

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
        st.markdown("#### All leads, every user")
        admin_search = st.text_input("Search all leads by domain, title or email", key="admin_search")
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
                "Download all leads as Excel",
                data=admin_buffer.getvalue(),
                file_name="all_link_loot_leads.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            st.dataframe(
                admin_display, width="stretch", hide_index=True,
                column_config={"Website": st.column_config.LinkColumn("Website", display_text="Open site")},
            )
            with st.expander("Remove a lead belonging to any user"):
                admin_delete_options = {
                    f"{row.get('user_email') or 'Unassigned'} · {row.get('domain') or row.get('url')}": row.get("id")
                    for row in all_leads if row.get("id") is not None
                }
                if admin_delete_options:
                    admin_chosen = st.selectbox("Choose a lead", options=list(admin_delete_options), key="admin_delete_select")
                    if st.button("Remove lead", key="admin_delete_button"):
                        ok, message = delete_lead_by_id(admin_delete_options[admin_chosen])
                        if ok:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)
        else:
            st.info("No leads found.")

        st.divider()
        st.markdown("#### System and setup")
        sys_col1, sys_col2 = st.columns(2)
        with sys_col1:
            st.markdown("**Service configuration. Values are never displayed.**")
            st.caption(f"Serper, web search: {'Set' if SERPER_API_KEY else 'Missing'}")
            st.caption(f"Ahrefs, domain rating: {'Set' if AHREFS_API_KEY else 'Missing'}")
            st.caption(f"Hunter, email checking: {'Set' if HUNTER_API_KEY else 'Not set'}")
            st.caption(f"Supabase: {'Configured' if is_supabase_configured() else 'Missing'}")
            if st.button("Test the Supabase connection", type="primary"):
                success, message = test_connection()
                if success:
                    st.success(message)
                else:
                    st.error(message)
        with sys_col2:
            st.markdown("**One time setup checklist**")
            st.markdown(
                "Step 1. Run supabase_schema.sql in the Supabase SQL Editor to create the leads table.\n\n"
                "Step 2. Run supabase_schema_v2.sql to add per user leads and the profiles table.\n\n"
                "Step 3. In Supabase, open Authentication and then URL Configuration. Set the Site URL to the live address of this app, and add the same address under Redirect URLs. Confirmation emails send users there.\n\n"
                "Step 4. In Supabase, open Authentication and then Providers, and keep Email sign in enabled.\n\n"
                "Step 5. In Streamlit Secrets, set ADMIN_EMAILS to your own email address to unlock this tab, and confirm that the Supabase and API settings are present."
            )

        for schema_name in ("supabase_schema_v2.sql", "supabase_schema.sql"):
            schema_file = Path(__file__).with_name(schema_name)
            if schema_file.exists():
                with st.expander(schema_name):
                    sql_content = schema_file.read_text(encoding="utf-8")
                    st.code(sql_content, language="sql")
                    st.download_button(
                        f"Download {schema_name}",
                        data=sql_content,
                        file_name=schema_name,
                        mime="text/plain",
                        key=f"dl_{schema_name}",
                    )
