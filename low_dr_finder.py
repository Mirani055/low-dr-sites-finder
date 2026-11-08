"""
=============================================================
  LOW DR WEBSITE FINDER + LEAD GENERATOR
=============================================================
"""

import os
import re
import sys
import time
import requests
import pandas as pd
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

try:
    from config import (
        SERPER_API_KEY, MAX_WEBSITES_TO_CHECK, LOW_DR_THRESHOLD,
        OUTPUT_FILE, AHREFS_API_KEY
    )
    from dr_checker import get_dr_score
    from website_scraper import scrape_contact_info
except ImportError as e:
    print("\n" + "="*60)
    print(f"❌ ERROR: {e}")
    print("✅ Sab files ek hi folder mein honi chahiye.")
    print("="*60 + "\n")
    sys.exit(1)


COUNTRY_SEARCH_SETTINGS = {
    "USA": ("us", "en"),
    "Brazil": ("br", "pt"),
    "UK": ("gb", "en"),
    "Germany": ("de", "de"),
    "Australia": ("au", "en"),
    "Spain": ("es", "es"),
    "UAE / Dubai": ("ae", "en"),
    "Saudi Arabia": ("sa", "en"),
    "Italy": ("it", "it"),
    "France": ("fr", "fr"),
    "Netherlands": ("nl", "nl"),
    "Japan": ("jp", "ja"),
    "Canada": ("ca", "en"),
    "Mexico": ("mx", "es"),
    "Ireland": ("ie", "en"),
    "Singapore": ("sg", "en"),
    "India": ("in", "en"),
    "New Zealand": ("nz", "en"),
    "South Africa": ("za", "en"),
    "Portugal": ("pt", "pt"),
    "Sweden": ("se", "sv"),
    "Norway": ("no", "no"),
    "Denmark": ("dk", "da"),
    "Switzerland": ("ch", "de"),
    "Belgium": ("be", "nl"),
    "Poland": ("pl", "pl"),
    "Turkey": ("tr", "tr"),
    "Indonesia": ("id", "id"),
    "Malaysia": ("my", "ms"),
    "Philippines": ("ph", "en"),
    "Argentina": ("ar", "es"),
    "Chile": ("cl", "es"),
    "Colombia": ("co", "es"),
    "Egypt": ("eg", "ar"),
    "Nigeria": ("ng", "en"),
    "Pakistan": ("pk", "en"),
    "Bangladesh": ("bd", "en"),
    "Kenya": ("ke", "en"),
    "Thailand": ("th", "th"),
    "Vietnam": ("vn", "vi"),
}


def build_search_queries(niche, country, city=None):
    """Build localized searches that favor real service and buying intent."""
    niche = niche.strip()
    city = city.strip() if city else ""
    location = f"{city}, {country}" if city else country
    language = COUNTRY_SEARCH_SETTINGS.get(country, (None, "en"))[1]

    if language == "fr":
        queries = [
            f"{niche} {location}",
            f"meilleur {niche} {location}",
            f"réserver {niche} {location}",
            f"{niche} prix devis {location}",
            f"service {niche} près de {city or country}",
            f"{niche} professionnel {location}",
        ]
    elif language == "es":
        queries = [
            f"{niche} {location}",
            f"mejor {niche} en {location}",
            f"reservar {niche} {location}",
            f"{niche} precio presupuesto {location}",
            f"servicio de {niche} cerca de {city or country}",
            f"{niche} profesional {location}",
        ]
    else:
        queries = [
            f"{niche} {location}",
            f"best {niche} in {location}",
            f"book {niche} {location}",
            f"{niche} prices quotes {location}",
            f"{niche} near {city or country}",
            f"top rated {niche} {location}",
        ]

    if any(term in niche.casefold() for term in ("taxi", "cab")):
        if country == "France":
            taxi_queries = [
                "taxi parisien",
                "taxi Paris",
                "meilleur taxi Paris",
                "taxi Orly Disneyland Paris",
                "taxi Charles de Gaulle Disneyland Paris",
                "transfert taxi Paris hôtel",
            ]
        elif country == "Spain":
            taxi_queries = [
                "taxi Barcelona",
                "taxi Madrid",
                "mejor taxi Barcelona",
                "taxi aeropuerto Barcelona hotel",
                "taxi aeropuerto Madrid hotel",
                "traslado taxi aeropuerto Barcelona",
            ]
        else:
            taxi_queries = []
        if city:
            taxi_queries.insert(0, f"{niche} {city} {country}")
        queries.extend(taxi_queries)

    return list(dict.fromkeys(query.strip() for query in queries))


def check_api_setup():
    """Check karta hai ke DR check karne ke liye API configured hai."""
    if not SERPER_API_KEY:
        print("\n❌ SERPER_API_KEY missing hai!")
        sys.exit(1)
    
    if not AHREFS_API_KEY:
        print("\n❌ Ahrefs API key zaroori hai; OpenPageRank is not Domain Rating.")
        sys.exit(1)
    
    print("\n✅ Ahrefs Domain Rating is ready.")
    return True


def serper_search(query, num_results=20, country=None):
    """Serper API se websites dhundhta hai."""
    url = "https://google.serper.dev/search"
    country_settings = COUNTRY_SEARCH_SETTINGS.get(country)
    payload = {"q": query, "num": num_results, "hl": country_settings[1] if country_settings else "en"}
    if country_settings:
        payload["gl"] = country_settings[0]
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        r.raise_for_status()
        organic = r.json().get("organic", [])
        
        websites = []
        for item in organic:
            link = item.get("link", "")
            if link and not any(skip in urlparse(link).netloc.lower() for skip in [
                "google.com", "facebook.com", "youtube.com", 
                "wikipedia.org", "twitter.com", "instagram.com"
            ]):
                domain = urlparse(link).netloc.lower().removeprefix("www.")
                if not domain:
                    continue
                websites.append({
                    "url": link,
                    "domain": domain,
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", "")
                })
        return websites
    except requests.HTTPError as e:
        response = e.response
        if response is not None and response.status_code == 400:
            detail = response.text.strip().replace("\n", " ")[:240]
            raise RuntimeError(f"Serper rejected the search request (HTTP 400): {detail}") from e
        print(f"  ⚠️ Search error: {e}")
        return []
    except Exception as e:
        print(f"  ⚠️ Search error: {e}")
        return []


def find_websites(niche, country, city=None, max_results=None, progress_callback=None):
    """Find an expanded candidate pool so DR filtering can still meet the target."""
    location = f"{city}, {country}" if city else country
    queries = build_search_queries(niche, country, city)
    
    query_results = []
    result_limit = max_results or MAX_WEBSITES_TO_CHECK
    candidate_limit = min(500, max(100, result_limit * 10))
    results_per_query = 100
    
    print(f"\n Searching for {niche} websites in {location}...")
    for query_index, q in enumerate(queries, 1):
        if progress_callback:
            progress_callback(query_index, len(queries), f"Searching: {q}")
        print(f"  → {q}")
        sites = serper_search(q, num_results=results_per_query, country=country)
        query_results.append(sites)
        discovered_domains = {
            site["domain"]
            for results in query_results
            for site in results
            if site.get("domain")
        }
        if len(discovered_domains) >= candidate_limit:
            break
        time.sleep(0.3)

    all_websites = []
    seen_domains = set()
    for result_index in range(max(map(len, query_results), default=0)):
        for sites in query_results:
            if result_index >= len(sites):
                continue
            site = sites[result_index]
            if site["domain"] not in seen_domains:
                seen_domains.add(site["domain"])
                all_websites.append(site)
                if len(all_websites) >= candidate_limit:
                    return all_websites

    return all_websites


def process_websites(
    websites,
    check_dr=True,
    dr_threshold=LOW_DR_THRESHOLD,
    max_results=None,
    progress_callback=None,
):
    """Har website ka DR check karta hai aur contact info scrape karta hai."""
    results = []
    
    print(f"\n📊 Processing {len(websites)} websites...")
    print("="*60)
    
    for i, site in enumerate(websites, 1):
        domain = site["domain"]
        url = site["url"]

        if progress_callback:
            progress_callback(i, len(websites), f"Checking {domain}")
        
        print(f"\n[{i}/{len(websites)}] {domain}")
        
        # DR/DA check
        dr_score, dr_source, dr_status = (None, "none", "skipped")
        if check_dr:
            dr_score, dr_source, dr_status = get_dr_score(domain)
            
            if dr_status == "ok":
                print(f"  📈 DR: {dr_score}/100 ({dr_source})")

                if dr_source != "Ahrefs DR":
                    print("  ⏭️  Skipping (OpenPageRank is not Domain Rating)")
                    continue

                if dr_score > dr_threshold:
                    print(f"  ⏭️  Skipping (DR {dr_score} > {dr_threshold})")
                    continue
            else:
                print(f"  ⚠️  DR check failed: {dr_status}")
                continue
        
        # Contact info scrape
        print(f"  🔍 Scraping contact info...")
        contact = scrape_contact_info(url)
        
        email_str = contact["emails"][0] if contact["emails"] else "—"
        print(f"  📧 Emails: {email_str}")
        print(f"  📘 Facebook: {'✓' if contact['facebook'] else '✗'}")
        print(f"  💼 LinkedIn: {'✓' if contact['linkedin'] else '✗'}")
        
        results.append({
            "domain": domain,
            "url": url,
            "title": site["title"],
            "dr_score": dr_score,
            "dr_source": dr_source,
            "emails": email_str,
            "email_status": contact.get("email_status", "not_checked"),
            "facebook": contact["facebook"],
            "linkedin": contact["linkedin"],
            "instagram": contact["instagram"],
            "twitter": contact["twitter"],
            "phone": contact["phone"],
            "whatsapp": contact["whatsapp"],
            "dr_status": dr_status,
            "scrape_status": contact["status"]
        })
        
        time.sleep(0.5)
        if max_results is not None and len(results) >= max_results:
            break
    
    return results


def save_excel(results, filename=OUTPUT_FILE):
    """Merge leads into one styled workbook with one sheet per country."""
    if not results:
        print("\n❌ Koi result nahi mila.")
        return None

    output_path = Path(filename).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "country",
        "domain", "url", "title", "dr_score", "dr_source",
        "emails", "email_status", "facebook", "linkedin", "instagram", "twitter",
        "phone", "whatsapp", "dr_status", "scrape_status"
    ]

    dataframes = []

    def add_workbook_rows(workbook_path):
        try:
            with pd.ExcelFile(workbook_path) as workbook:
                for sheet in workbook.sheet_names:
                    existing = pd.read_excel(workbook, sheet_name=sheet)
                    if "country" not in existing.columns:
                        inferred_country = sheet if sheet not in {"Leads", "Low_DR_Leads"} else "Unknown"
                        existing["country"] = inferred_country
                    else:
                        missing_country = existing["country"].isna() | (existing["country"].astype(str).str.strip() == "")
                        inferred_country = sheet if sheet not in {"Leads", "Low_DR_Leads"} else "Unknown"
                        existing.loc[missing_country, "country"] = inferred_country
                    dataframes.append(existing)
        except (OSError, ValueError, ImportError) as error:
            print(f"  ⚠️ Could not import {workbook_path.name}: {error}")

    if output_path.exists():
        add_workbook_rows(output_path)

    for pattern in ("link_loot_leads_*.xlsx", "low_dr_leads_*.xlsx"):
        for legacy_path in output_path.parent.glob(pattern):
            if legacy_path.resolve() != output_path:
                add_workbook_rows(legacy_path)

    incoming = pd.DataFrame(results)
    if "country" not in incoming.columns:
        incoming["country"] = "Unknown"
    dataframes.append(incoming)

    df = pd.concat(dataframes, ignore_index=True, sort=False)
    for column in cols:
        if column not in df.columns:
            df[column] = ""
    df = df[cols]
    df["country"] = df["country"].fillna("Unknown").replace("", "Unknown")
    df["domain"] = df["domain"].fillna("").astype(str).str.strip().str.lower()
    df["domain"] = df["domain"].str.replace(r"^https?://", "", regex=True).str.replace(r"^www\.", "", regex=True).str.rstrip("/")
    df = df.drop_duplicates(subset=["country", "domain"], keep="last")
    df = df[df["domain"] != ""]
    df = df.sort_values(by=["country", "dr_score"], ascending=[True, True], na_position="last")

    used_sheet_names = set()
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for country, country_df in df.groupby("country", sort=False, dropna=False):
            base_sheet_name = re.sub(r"[\\/*?:\[\]]", " ", str(country)).strip() or "Unknown"
            sheet_name = base_sheet_name[:31]
            suffix_number = 2
            while sheet_name.casefold() in used_sheet_names:
                suffix = f"_{suffix_number}"
                sheet_name = f"{base_sheet_name[:31 - len(suffix)]}{suffix}"
                suffix_number += 1
            used_sheet_names.add(sheet_name.casefold())
            country_df.to_excel(writer, index=False, sheet_name=sheet_name)

        from openpyxl.styles import Alignment, Font, PatternFill

        widths = {
            "A": 18, "B": 28, "C": 42, "D": 42, "E": 10, "F": 18,
            "G": 34, "H": 20, "I": 30, "J": 30, "K": 30, "L": 30,
            "M": 20, "N": 22, "O": 20, "P": 20,
        }
        header_fill = PatternFill("solid", fgColor="C2410C")
        stripe_fill = PatternFill("solid", fgColor="FFF4EA")
        for worksheet in writer.book.worksheets:
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions
            worksheet.sheet_view.showGridLines = False
            for column_letter, width in widths.items():
                worksheet.column_dimensions[column_letter].width = width
            for cell in worksheet[1]:
                cell.fill = header_fill
                cell.font = Font(color="FFFFFF", bold=True)
                cell.alignment = Alignment(vertical="center", wrap_text=True)
            worksheet.row_dimensions[1].height = 30
            for row in worksheet.iter_rows(min_row=2):
                for cell in row:
                    cell.alignment = Alignment(vertical="top", wrap_text=True)
                    if cell.row % 2 == 0:
                        cell.fill = stripe_fill
                worksheet.row_dimensions[row[0].row].height = 32
            for row in range(2, worksheet.max_row + 1):
                for column in (3, 9, 10, 11, 12):
                    cell = worksheet.cell(row=row, column=column)
                    if cell.value and str(cell.value).startswith(("http://", "https://")):
                        cell.hyperlink = cell.value
                        cell.style = "Hyperlink"
    
    # Summary
    with_email = len([r for r in results if r.get("emails") and r["emails"] != "—"])
    with_fb = len([r for r in results if r.get("facebook")])
    with_li = len([r for r in results if r.get("linkedin")])
    low_dr_count = len([r for r in results if r.get("dr_score") is not None and r["dr_score"] <= LOW_DR_THRESHOLD])
    
    print("\n" + "="*60)
    print(f"💾 Saved to: {os.path.abspath(output_path)}")
    print(f"📊 Total Leads: {len(results)}")
    print(f"📉 Low DR (≤{LOW_DR_THRESHOLD}): {low_dr_count}")
    print(f"📧 With Email: {with_email}")
    print(f"📘 With Facebook: {with_fb}")
    print(f"💼 With LinkedIn: {with_li}")
    print("="*60)
    return str(output_path)


def main():
    has_dr_api = check_api_setup()
    
    print("="*60)
    print("🎯 LOW DR WEBSITE FINDER + LEAD GENERATOR")
    print("   Powered by Ahrefs & OpenPageRank")
    print("="*60)
    print(f"\n📊 DR Threshold: {LOW_DR_THRESHOLD} (is se kam DR wali sites)")
    print(f"🔢 Max Websites: {MAX_WEBSITES_TO_CHECK}")
    print("="*60)
    
    niche = input("\n🎯 Niche (e.g., roofing, dentist, plumber): ").strip()
    if not niche:
        print("❌ Niche zaroori hai!")
        sys.exit(1)
    
    country = input("🌍 Country (e.g., USA, Brazil, UK): ").strip()
    if not country:
        print("❌ Country zaroori hai!")
        sys.exit(1)
    
    city = input("🏙️  City (optional — press Enter to skip): ").strip()
    
    print("\n" + "="*60)
    print(f"🚀 Starting search...")
    print("="*60)
    
    start = time.time()
    
    # Step 1: Websites dhundhna
    websites = find_websites(niche, country, city)
    
    if not websites:
        print("\n❌ Koi website nahi mili.")
        sys.exit(0)
    
    # Step 2: DR check + Contact scrape
    results = process_websites(websites, check_dr=has_dr_api)
    
    # Step 3: Excel save
    save_excel(results)
    
    print(f"\n✅ Done in {time.time() - start:.1f} seconds")
    print("\n📝 Attribution: Domain Rating by Ahrefs (https://ahrefs.com/)")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Cancelled by user.")
        sys.exit(0)