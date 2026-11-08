import unittest
from unittest.mock import MagicMock, patch

import supabase_db


class SupabaseDbTests(unittest.TestCase):
    def test_is_supabase_configured_false_when_empty(self):
        with patch.object(supabase_db, "SUPABASE_URL", ""), patch.object(supabase_db, "SUPABASE_KEY", ""):
            self.assertFalse(supabase_db.is_supabase_configured())

    def test_is_supabase_configured_true_when_valid(self):
        with patch.object(supabase_db, "SUPABASE_URL", "https://xyz.supabase.co"), patch.object(supabase_db, "SUPABASE_KEY", "sb_key"):
            self.assertTrue(supabase_db.is_supabase_configured())

    def test_format_lead_for_db(self):
        lead = {
            "domain": "test.com",
            "url": "https://test.com",
            "title": "Test Title",
            "dr_score": "12.5",
            "emails": ["info@test.com", "sales@test.com"],
            "phone": "+123456",
            "whatsapp": "+123456",
            "facebook": "https://facebook.com/test",
        }
        formatted = supabase_db._format_lead_for_db(lead, niche="plumber", country="USA", city="Dallas")
        self.assertEqual(formatted["domain"], "test.com")
        self.assertEqual(formatted["niche"], "plumber")
        self.assertEqual(formatted["country"], "USA")
        self.assertEqual(formatted["city"], "Dallas")
        self.assertEqual(formatted["dr_score"], 12.5)
        self.assertEqual(formatted["emails"], "info@test.com, sales@test.com")

    def test_save_leads_when_not_configured(self):
        with patch.object(supabase_db, "is_supabase_configured", return_value=False):
            count, msg = supabase_db.save_leads_to_supabase([{"url": "https://test.com"}])
            self.assertEqual(count, 0)
            self.assertIn("not configured", msg)

    def test_save_leads_success_mock(self):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = [{"id": 1}, {"id": 2}]

        with (
            patch.object(supabase_db, "is_supabase_configured", return_value=True),
            patch.object(supabase_db, "SUPABASE_URL", "https://xyz.supabase.co"),
            patch.object(supabase_db, "SUPABASE_KEY", "secret_key"),
            patch.object(supabase_db.requests, "post", return_value=mock_response) as mock_post,
        ):
            leads = [
                {"domain": "a.com", "url": "https://a.com"},
                {"domain": "b.com", "url": "https://b.com"},
            ]
            count, msg = supabase_db.save_leads_to_supabase(leads, niche="dentist", country="UK")
            self.assertEqual(count, 2)
            self.assertTrue(mock_post.called)


if __name__ == "__main__":
    unittest.main()
