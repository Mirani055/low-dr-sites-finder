import io
from pathlib import Path
import time

import pandas as pd
import streamlit as st

from config import (
    AHREFS_API_KEY,
    HUNTER_API_KEY,
    LOW_DR_THRESHOLD,
    MAX_WEBSITES_TO_CHECK,
    SERPER_API_KEY,
    SUPABASE_KEY,
    SUPABASE_URL,
)
from low_dr_finder import (
    COUNTRY_SEARCH_SETTINGS,
    find_websites,
    process_websites,
    save_excel,
)
from supabase_db import (
    delete_lead_by_id,
    fetch_leads_from_supabase,
    get_database_stats,
    is_supabase_configured,
    save_leads_to_supabase,
    test_connection,
)


st.set_page_config(
    page_title="Link Loot",
    page_icon=":material/travel_explore:",
    layout="wide",
)

with st.sidebar:
    st.markdown("### Search settings")
    threshold = st.slider(
        "Maximum DR",
        min_value=0,
        max_value=100,
        value=int(LOW_DR_THRESHOLD),
        help="Sites with a verified DR above this score are left out.",
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
    )
    st.divider()
    st.markdown("### Services")
    st.caption(f"Web search: {'Ready' if SERPER_API_KEY else 'API key needed'}")
    st.caption(
        f"Ahrefs Domain Rating: {'Ready' if AHREFS_API_KEY else 'API key needed'}"
    )
    st.caption(
        f"Supabase Database: {'Connected ✅' if is_supabase_configured() else 'Not configured ⚠️'}"
    )
    st.caption(
        "One domain-matching email per website. Hunter.io verifies emails when configured."
    )


st.logo(str(Path(__file__).with_name("link_loot.svg")))
logo_col, title_col = st.columns([0.08, 1], vertical_alignment="center")
with logo_col:
    st.image(str(Path(__file__).with_name("link_loot.svg")), width=52)
with title_col:
    st.title("Link Loot")
    st.caption("Find low-DR websites for local SEO and outreach across every niche.")

tab_hunt, tab_database, tab_setup = st.tabs([
    "🎯 Hunt Leads",
    "🗄️ Supabase Database",
    "⚙️ Supabase Setup & SQL",
])

with tab_hunt:
    with st.form("search_form"):
        niche_col, country_col, city_col = st.columns([1, 1.35, 0.85])
        with niche_col:
            niche = st.text_input("Niche or market", placeholder="e.g. roofing, SaaS, pet supplies")
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
        submitted = st.form_submit_button("Hunt websites", type="primary", width="stretch")

    if submitted:
        if not SERPER_API_KEY:
            st.error("Web search is not configured. Add your Serper API key to the local .env file.")
        elif not AHREFS_API_KEY:
            st.error("Accurate Domain Rating filtering needs an Ahrefs API key in the local .env file.")
        elif not niche.strip() or not countries:
            st.warning("Enter a niche and select at least one country to start searching.")
        else:
            progress = st.progress(0, text="Preparing search...")
            status = st.status("Searching for websites", expanded=True)
            started_at = time.time()

            def update_search_progress(current, total, message):
                progress.progress(current / total, text=message)
                status.write(message)

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
                        export_path = save_excel(results, filename="link_loot_leads.xlsx")
                        st.session_state["export_name"] = Path(export_path).name
                        st.session_state["export_data"] = Path(export_path).read_bytes()

                        # Automatically save leads to Supabase if configured
                        if is_supabase_configured():
                            saved_count, msg = save_leads_to_supabase(
                                results,
                                niche=niche.strip(),
                                country=countries[0] if len(countries) == 1 else "",
                                city=city_target or "",
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
            st.success(f"🗄️ {st.session_state['supabase_sync_msg']}")

        st.caption(
            "DR 0 through the selected maximum is included. Ahrefs DR is required for DR filtering; "
            "OpenPageRank is not treated as Domain Rating."
        )
        if not HUNTER_API_KEY:
            st.info(
                "Add HUNTER_API_KEY in .env to verify the single collected email per site. "
                "An email address alone cannot guarantee that the owner will reply."
            )

        st.markdown("#### Website results")
        action_col1, action_col2 = st.columns([1, 4])
        with action_col1:
            if st.session_state.get("export_data"):
                st.download_button(
                    "Download Excel",
                    data=st.session_state["export_data"],
                    file_name=st.session_state["export_name"],
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

        results_frame = pd.DataFrame(results).rename(
            columns={
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
            }
        )
        st.dataframe(
            results_frame,
            width="stretch",
            hide_index=True,
            column_config={"Website": st.column_config.LinkColumn("Website", display_text="Open site")},
        )
    elif "results" in st.session_state:
        st.markdown("#### Lead overview")
        st.caption("No lead results to display yet.")

    master_workbook = Path(__file__).with_name("link_loot_leads.xlsx")
    if not results and master_workbook.exists():
        st.download_button(
            "Download master workbook",
            data=master_workbook.read_bytes(),
            file_name=master_workbook.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

with tab_database:
    st.markdown("### Supabase Leads Repository")
    st.caption("Browse, filter, and export all leads collected and stored in your Supabase PostgreSQL database.")

    if not is_supabase_configured():
        st.warning("⚠️ Supabase is not connected. Add `SUPABASE_URL` and `SUPABASE_KEY` in your `.env` or Streamlit Secrets.")
        st.info("👉 Check the **'⚙️ Supabase Setup & SQL'** tab for setup instructions.")
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
            max_dr_filter = st.slider("Max DR in DB", 0, 100, 100, key="db_dr_filter")
        with filter_col4:
            email_only = st.checkbox("Only leads with email", value=False, key="db_email_filter")
            search_query = st.text_input("Search (domain / title / email)", placeholder="e.g. acme", key="db_search_filter")

        if st.button("🔄 Refresh Database", type="secondary"):
            st.rerun()

        leads_data, status_msg = fetch_leads_from_supabase(
            limit=500,
            country=None if selected_country == "All" else selected_country,
            niche=niche_filter if niche_filter.strip() else None,
            max_dr=max_dr_filter if max_dr_filter < 100 else None,
            with_email_only=email_only,
            search_query=search_query if search_query.strip() else None,
        )

        total_db_leads = len(leads_data)
        with_emails_db = sum(1 for r in leads_data if r.get("emails"))
        low_dr_db = sum(1 for r in leads_data if r.get("dr_score") is not None and r["dr_score"] <= 30)

        stat_col1, stat_col2, stat_col3 = st.columns(3)
        stat_col1.metric("Leads Retrieved", total_db_leads)
        stat_col2.metric("With Email", with_emails_db)
        stat_col3.metric("Low DR (≤ 30)", low_dr_db)

        if leads_data:
            df_db = pd.DataFrame(leads_data)
            col_order = [
                "domain", "url", "niche", "country", "city", "dr_score",
                "emails", "phone", "whatsapp", "facebook", "linkedin", "title", "created_at"
            ]
            display_cols = [c for c in col_order if c in df_db.columns] + [
                c for c in df_db.columns if c not in col_order and c not in ("id",)
            ]
            df_display = df_db[display_cols].rename(columns={
                "domain": "Domain",
                "url": "Website",
                "niche": "Niche",
                "country": "Country",
                "city": "City",
                "dr_score": "DR",
                "emails": "Emails",
                "phone": "Phone",
                "whatsapp": "WhatsApp",
                "facebook": "Facebook",
                "linkedin": "LinkedIn",
                "title": "Title",
                "created_at": "Saved At",
            })

            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                df_display.to_excel(writer, index=False, sheet_name="Supabase Leads")
            excel_bytes = excel_buffer.getvalue()

            st.download_button(
                "📥 Download Filtered Leads (Excel)",
                data=excel_bytes,
                file_name="supabase_leads_export.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            st.dataframe(
                df_display,
                width="stretch",
                hide_index=True,
                column_config={"Website": st.column_config.LinkColumn("Website", display_text="Open site")},
            )
        else:
            st.info("No leads found in Supabase matching current filters.")

with tab_setup:
    st.markdown("### ⚙️ Supabase Database Setup Guide")
    st.markdown("""
    **Step 1: Create a Free Project on Supabase**
    - Go to [supabase.com](https://supabase.com) and sign in with GitHub (`Mirani055`).
    - Click **"New Project"**, name it `link-loot-db`, set a database password, and create the project.
    
    **Step 2: Run the SQL Schema**
    - In Supabase dashboard, click **SQL Editor** on the left menu.
    - Click **"New query"**, paste the SQL script below, and click **Run** (or press Ctrl + Enter).
    """)

    schema_file = Path(__file__).with_name("supabase_schema.sql")
    if schema_file.exists():
        sql_content = schema_file.read_text(encoding="utf-8")
        st.code(sql_content, language="sql")
        st.download_button(
            "📄 Download schema.sql",
            data=sql_content,
            file_name="supabase_schema.sql",
            mime="text/plain",
        )

    st.markdown("""
    **Step 3: Add Credentials**
    - In your Supabase dashboard, go to **Project Settings** (gear icon) ➔ **API**.
    - Copy:
      - **Project URL** ➔ `SUPABASE_URL`
      - **anon public key** ➔ `SUPABASE_KEY`
    - Put these into your `.env` file locally or in **Settings ➔ Secrets** on [share.streamlit.io](https://share.streamlit.io).
    """)

    st.divider()
    st.markdown("#### Test Supabase Connection")
    if st.button("🔌 Test Connection Now", type="primary"):
        success, message = test_connection()
        if success:
            st.success(f"✅ {message}")
        else:
            st.error(f"❌ {message}")
