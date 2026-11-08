# Link Loot

Find low-DR websites for local SEO & outreach — with email, phone, WhatsApp and socials attached.

## Accounts update (multi-user)

- **Sign up / Log in** with Supabase Auth. Every user gets a **private dashboard**: their hunts and leads are saved with their `user_id`, and no user can see another user's leads.
- Regular users see only **Hunt Leads** and **My Leads**. The database browser and the Setup & SQL pages are **admin-only**.
- **Admin dashboard:** accounts whose email is listed in the `ADMIN_EMAILS` secret see an extra **Admin** tab inside the app (all users, all leads, system setup). A standalone version also exists in `admin_dashboard.py` — deploy it as a second Streamlit Cloud app (same repo, main file `admin_dashboard.py`, same secrets) if you want a separate admin link.

### One-time setup for accounts

1. In the Supabase SQL Editor, run `supabase_schema.sql` (v1, if not done) and then `supabase_schema_v2.sql` (adds `user_id`/`user_email` to leads, per-user unique leads, and the `profiles` table).
2. In Supabase → **Authentication → Providers**, make sure **Email** sign-in is enabled. If you don't want users to confirm their email before first login, turn **Confirm email** off in the same place.
3. In Streamlit Secrets add: `ADMIN_EMAILS = "your-email@example.com"` (comma-separated for multiple admins).

## Run on Windows

1. Install Python 3.10 or newer.
2. Double-click `run.bat`. On first start it creates `.env` from `.env.example` and installs the required packages.
3. Open `.env` and add your own Serper and Ahrefs API keys. Add a Hunter.io API key if you want the one collected email per site verified. Restart `run.bat` after adding them.
4. On this computer, open `http://localhost:8501`.

The lead workbook is saved as `link_loot_leads.xlsx` in this folder. Existing timestamped `link_loot_leads_*.xlsx` and `low_dr_leads_*.xlsx` exports are imported into it on the next successful search. Legacy rows without country information go to an `Unknown` sheet. Original exports are left untouched.

The dashboard collects up to the selected number of Ahrefs-verified sites per country with DR from 0 through the selected maximum. It searches an expanded Serper candidate pool because many discovered sites may exceed the DR limit. If fewer matching sites exist in that pool, fewer than the requested number can be returned. Each website contributes one matching-domain email at most, including from a linked contact page when needed. Hunter.io verifies that address when configured; verification does not guarantee that the recipient is the owner or will reply. Phone and WhatsApp numbers are shown only when found in public website contact details.

## Use from a phone or another computer

Keep the Windows computer running `run.bat`. Connect the phone/computer to the same trusted Wi-Fi network and open the Network URL printed by Streamlit in the terminal. Windows Firewall may ask to allow Python on the private network. This local link is not available when the host computer is off and should not be exposed on public Wi-Fi.

For a public link that friends can open from anywhere, deploy the app to a hosting service such as Streamlit Community Cloud. The source must be in a GitHub repository, and the API keys must be entered in the host's Secrets settings. Do not upload `.env` or lead workbooks.

## Notes

- Use newly rotated API keys in `.env`; keys previously stored in source code should be revoked.
- The DR limit is inclusive: a verified Ahrefs DR from 0 through the selected maximum is retained. OpenPageRank is not the same metric as Ahrefs DR and is not used to qualify DR-filtered leads.
- Serper provides search results, not keyword difficulty (KD). The app does not claim to measure KD.
- Contact numbers and WhatsApp details are extracted only when published on the website pages that are checked.
