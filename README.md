# Link Loot

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
