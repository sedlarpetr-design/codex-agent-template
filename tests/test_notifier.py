import unittest
from unittest.mock import patch
from notifier import send_run_notification


class TestNotifier(unittest.TestCase):
    def test_disabled_by_default(self):
        with patch.dict("os.environ", {}, clear=True):
            res = send_run_notification("t-1", "DONE", {"urls": 5})
            self.assertFalse(res["sent"])
            self.assertEqual(res["reason"], "disabled")

    def test_telegram_send_success(self):
        env = {
            "NOTIFY_ENABLED": "1",
            "NOTIFY_TELEGRAM_BOT_TOKEN": "123:ABC",
            "NOTIFY_TELEGRAM_CHAT_ID": "999",
        }
        with patch.dict("os.environ", env, clear=True), patch("notifier._post_json", return_value=(True, "http_200")) as mock_post:
            res = send_run_notification("t-2", "DONE", {"ok": 10}, "runs/t-2/audit.jsonl")
            self.assertTrue(res["sent"])
            self.assertEqual(res["reason"], "ok")
            self.assertTrue(res["channels"]["telegram"]["ok"])
            mock_post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
