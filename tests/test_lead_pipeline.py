import contextlib
import io
import unittest
from unittest.mock import patch

import low_dr_finder
import website_scraper


class LeadPipelineTests(unittest.TestCase):
    def test_search_builds_expanded_unique_candidate_pool(self):
        first_page = [
            {"domain": f"first-{index}.example", "url": f"https://first-{index}.example", "title": ""}
            for index in range(100)
        ]
        second_page = [
            {"domain": f"second-{index}.example", "url": f"https://second-{index}.example", "title": ""}
            for index in range(100)
        ]
        with (
            patch.object(low_dr_finder, "build_search_queries", return_value=["query one", "query two"]),
            patch.object(low_dr_finder, "serper_search", side_effect=[first_page, second_page]) as search,
            patch.object(low_dr_finder.time, "sleep"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            candidates = low_dr_finder.find_websites("niche", "USA", max_results=20)

        self.assertEqual(len(candidates), 200)
        self.assertEqual(search.call_count, 2)
        self.assertTrue(all(call.kwargs["num_results"] == 100 for call in search.call_args_list))

    def test_dr_zero_is_eligible_and_result_count_is_capped(self):
        websites = [
            {"domain": domain, "url": f"https://{domain}", "title": domain}
            for domain in ("zero.example", "too-high.example", "low.example", "extra.example")
        ]
        scores = [
            (0, "Ahrefs DR", "ok"),
            (31, "Ahrefs DR", "ok"),
            (5, "Ahrefs DR", "ok"),
            (2, "Ahrefs DR", "ok"),
        ]
        contact = {
            "emails": ["contact@example.com"],
            "email_status": "valid",
            "facebook": "",
            "linkedin": "",
            "instagram": "",
            "twitter": "",
            "phone": "",
            "whatsapp": "+14155552671",
            "status": "ok",
        }
        with (
            patch.object(low_dr_finder, "get_dr_score", side_effect=scores),
            patch.object(low_dr_finder, "scrape_contact_info", return_value=contact),
            patch.object(low_dr_finder.time, "sleep"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            results = low_dr_finder.process_websites(
                websites,
                dr_threshold=30,
                max_results=2,
            )

        self.assertEqual([row["dr_score"] for row in results], [0, 5])
        self.assertEqual(len(results), 2)
        self.assertTrue(all(row["whatsapp"] == "+14155552671" for row in results))
        self.assertTrue(all(row["email_status"] == "valid" for row in results))

    def test_scraper_keeps_one_site_email_and_extracts_linked_whatsapp(self):
        html = """
        <html><body>
          <a href="mailto:support@examplebiz.com">Support</a>
          <a href="mailto:contact@examplebiz.com">Contact</a>
          <a href="mailto:owner@otherdomain.test">Other</a>
          <a href="tel:+14155552671">Call</a>
          <a href="https://wa.me/14155552671">WhatsApp</a>
        </body></html>
        """
        response = type("Response", (), {"status_code": 200, "text": html})()
        with (
            patch.object(website_scraper, "scraper") as scraper,
            patch.object(website_scraper, "HUNTER_API_KEY", ""),
            patch.object(website_scraper.time, "sleep"),
        ):
            scraper.get.return_value = response
            result = website_scraper.scrape_contact_info("https://www.examplebiz.com")

        self.assertEqual(result["emails"], ["contact@examplebiz.com"])
        self.assertEqual(result["email_status"], "not_configured")
        self.assertEqual(result["phone"], "+14155552671")
        self.assertEqual(result["whatsapp"], "+14155552671")

    def test_scraper_checks_contact_page_when_homepage_has_no_email(self):
        home = type(
            "Response",
            (),
            {"status_code": 200, "text": '<a href="/contact">Contact</a>'},
        )()
        contact = type(
            "Response",
            (),
            {
                "status_code": 200,
                "text": (
                    '<a href="mailto:hello@localbusiness.test">Email</a>'
                    '<a href="https://api.whatsapp.com/send?phone=442079460123">WhatsApp</a>'
                ),
            },
        )()
        with (
            patch.object(website_scraper, "scraper") as scraper,
            patch.object(website_scraper, "HUNTER_API_KEY", ""),
            patch.object(website_scraper.time, "sleep"),
        ):
            scraper.get.side_effect = [home, contact]
            result = website_scraper.scrape_contact_info("https://localbusiness.test")

        self.assertEqual(result["emails"], ["hello@localbusiness.test"])
        self.assertEqual(result["whatsapp"], "+442079460123")
        self.assertEqual(scraper.get.call_count, 2)

if __name__ == "__main__":
    unittest.main()
