"""
=============================================================
  WEBSITE SCRAPER — Email, Facebook, LinkedIn, Phone Extractor
=============================================================
"""

import re
import time
import requests
import cloudscraper
from bs4 import BeautifulSoup
from urllib.parse import parse_qs, urljoin, urlparse
from config import REQUEST_TIMEOUT, DELAY_BETWEEN_REQUESTS, HUNTER_API_KEY

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

SPAM_DOMAINS = {
    "example.com", "sentry.io", "domain.com", "yourdomain.com",
    "email.com", "your-email.com", "github.io", "schema.org",
    "w3.org", "wordpress.org", "google.com", "facebook.com",
    "twitter.com", "youtube.com", "wikipedia.org"
}

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def clean_email(email):
    email = email.strip().lower()
    if not email or "@" not in email:
        return None
    domain = email.split("@")[-1]
    if domain in SPAM_DOMAINS or len(email) < 6 or len(email) > 80:
        return None
    if any(email.endswith(ext) for ext in [".png", ".jpg", ".gif", ".svg", ".webp", ".css", ".js"]):
        return None
    return email


def extract_emails(text, domain=None):
    raw = EMAIL_REGEX.findall(text or "")
    root_domain = (domain or "").lower().removeprefix("www.")
    emails = {
        cleaned
        for email in raw
        if (cleaned := clean_email(email))
        and (
            not root_domain
            or cleaned.rsplit("@", 1)[1] == root_domain
            or cleaned.rsplit("@", 1)[1].endswith(f".{root_domain}")
        )
    }
    return sorted(
        emails,
        key=lambda email: (
            not any(
                role in email.split("@", 1)[0]
                for role in ("contact", "info", "hello", "sales", "support")
            ),
            email,
        ),
    )


def find_hunter_emails(domain):
    if not HUNTER_API_KEY or not domain:
        return []
    url = "https://api.hunter.io/v2/domain-search"
    response = requests.get(
        url,
        params={"domain": domain, "api_key": HUNTER_API_KEY},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json().get("data", {}).get("emails", [])
    return [email["value"] for email in data if email.get("value")]


def verify_hunter_email(email):
    if not HUNTER_API_KEY or not email:
        return "not_configured"
    response = requests.get(
        "https://api.hunter.io/v2/email-verifier",
        params={"email": email, "api_key": HUNTER_API_KEY},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json().get("data", {}).get("status", "unknown")


def scrape_contact_info(url):
    """Website se email, Facebook, LinkedIn, phone extract karta hai."""
    data = {
        "emails": [],
        "facebook": "",
        "linkedin": "",
        "instagram": "",
        "twitter": "",
        "phone": "",
        "whatsapp": "",
        "email_status": "not_found",
        "status": "ok"
    }

    try:
        domain = urlparse(url).netloc.replace("www.", "")

        try:
            r = scraper.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        except Exception:
            r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)

        if r.status_code != 200:
            data["status"] = f"http_{r.status_code}"
            return data

        soup = BeautifulSoup(r.text, "html.parser")
        page_soups = [soup]

        # Emails
        emails = extract_emails(r.text, domain)
        contact_links = []
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            if href.lower().startswith("mailto:"):
                cleaned = clean_email(href[7:].split("?")[0])
                if cleaned and (
                    cleaned.rsplit("@", 1)[1] == domain
                    or cleaned.rsplit("@", 1)[1].endswith(f".{domain}")
                ):
                    emails.append(cleaned)
            elif re.search(r"contact|about|team|staff", f"{href} {anchor.get_text(' ', strip=True)}", re.I):
                page_url = urljoin(url, href)
                page_domain = urlparse(page_url).netloc.lower().removeprefix("www.")
                if page_domain == domain and page_url not in contact_links:
                    contact_links.append(page_url)

        for contact_url in contact_links[:2] if not emails else []:
            time.sleep(DELAY_BETWEEN_REQUESTS)
            try:
                contact_response = scraper.get(contact_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            except requests.RequestException:
                try:
                    contact_response = requests.get(
                        contact_url, headers=HEADERS, timeout=REQUEST_TIMEOUT
                    )
                except requests.RequestException:
                    continue
            if contact_response.status_code == 200:
                page_soups.append(BeautifulSoup(contact_response.text, "html.parser"))
                emails.extend(extract_emails(contact_response.text, domain))

        for page_soup in page_soups:
            for anchor in page_soup.find_all("a", href=True):
                href = anchor["href"].strip()
                if href.lower().startswith("mailto:"):
                    cleaned = clean_email(href[7:].split("?")[0])
                    if cleaned and (
                        cleaned.rsplit("@", 1)[1] == domain
                        or cleaned.rsplit("@", 1)[1].endswith(f".{domain}")
                    ):
                        emails.append(cleaned)
        data["emails"] = sorted(set(emails))

        # Hunter.io se extra emails
        if len(data["emails"]) < 1:
            try:
                data["emails"] = sorted(
                    {
                        email
                        for raw_email in find_hunter_emails(domain)
                        if (email := clean_email(raw_email))
                        and (
                            email.rsplit("@", 1)[1] == domain
                            or email.rsplit("@", 1)[1].endswith(f".{domain}")
                        )
                    }
                )
            except requests.RequestException:
                data["email_status"] = "lookup_error"

        if data["emails"]:
            data["emails"] = sorted(
                data["emails"],
                key=lambda email: (
                    not any(
                        role in email.split("@", 1)[0]
                        for role in ("contact", "info", "hello", "sales", "support")
                    ),
                    email,
                ),
            )[:1]
            data["email_status"] = "not_configured"
            if HUNTER_API_KEY:
                try:
                    data["email_status"] = verify_hunter_email(data["emails"][0])
                except requests.RequestException:
                    data["email_status"] = "verification_error"
        elif HUNTER_API_KEY and data["email_status"] != "lookup_error":
            data["email_status"] = "no_email_found"

        # Social links
        for page_soup in page_soups:
            for anchor in page_soup.find_all("a", href=True):
                href = anchor["href"].lower()
                if "facebook.com/" in href and not data["facebook"]:
                    data["facebook"] = anchor["href"]
                elif "linkedin.com/" in href and not data["linkedin"]:
                    data["linkedin"] = anchor["href"]
                elif "instagram.com/" in href and not data["instagram"]:
                    data["instagram"] = anchor["href"]
                elif ("twitter.com/" in href or "x.com/" in href) and not data["twitter"]:
                    data["twitter"] = anchor["href"]

        # Prefer structured phone and WhatsApp links over unrelated page numbers.
        for page_soup in page_soups:
            for anchor in page_soup.find_all("a", href=True):
                href = anchor["href"].strip()
                parsed_href = urlparse(href)
                if href.lower().startswith("tel:") and not data["phone"]:
                    data["phone"] = href.split(":", 1)[1].strip()[:30]
                whatsapp_target = parsed_href.netloc.lower() in {
                    "wa.me",
                    "www.wa.me",
                    "api.whatsapp.com",
                    "www.whatsapp.com",
                    "whatsapp.com",
                } or parsed_href.scheme.lower() == "whatsapp"
                if whatsapp_target and not data["whatsapp"]:
                    phone = parse_qs(parsed_href.query).get("phone", [""])[0]
                    if not phone and parsed_href.netloc.lower().endswith("wa.me"):
                        phone = parsed_href.path.strip("/").split("/")[0]
                    if phone:
                        digits = re.sub(r"\D", "", phone)
                        if 7 <= len(digits) <= 15:
                            data["whatsapp"] = f"+{digits}"

        if not data["phone"]:
            phone_match = re.search(
                r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}",
                " ".join(page_soup.get_text(" ", strip=True) for page_soup in page_soups)
            )
            if phone_match:
                data["phone"] = phone_match.group(0).strip()[:30]

        time.sleep(DELAY_BETWEEN_REQUESTS)
        return data

    except requests.exceptions.Timeout:
        data["status"] = "timeout"
        return data
    except requests.HTTPError as e:
        data["status"] = f"http_{e.response.status_code}" if e.response is not None else "http_error"
        return data
    except Exception as e:
        data["status"] = f"error: {str(e)[:40]}"
        return data