import unittest
from unittest import mock

from oracle.acquirers import waterfall


class WaterfallGuardTests(unittest.TestCase):
    def test_guard_reject_stops_all_tiers(self) -> None:
        with mock.patch("oracle.acquirers.waterfall._guard_check", return_value={"allowed": False, "reason": "bad track", "category": "karaoke"}), \
             mock.patch("oracle.acquirers.waterfall._try_tier1_qobuz") as t1, \
             mock.patch("oracle.acquirers.waterfall._try_tier2_slskd") as t2, \
             mock.patch("oracle.acquirers.waterfall._try_tier3_realdebrid") as t3, \
             mock.patch("oracle.acquirers.waterfall._try_tier4_spotdl") as t4:
            result = waterfall.acquire("Artist", "Title")

        self.assertFalse(result.success)
        self.assertEqual(result.source, "guard")
        self.assertIn("Guard rejected", result.error or "")
        t1.assert_not_called()
        t2.assert_not_called()
        t3.assert_not_called()
        t4.assert_not_called()

    def test_guard_exception_fails_closed(self) -> None:
        with mock.patch("oracle.acquirers.waterfall.guard_bypass_allowed", return_value=False), \
             mock.patch("oracle.acquirers.waterfall.guard_bypass_reason", return_value="test"):
            result = waterfall._guard_check("Artist", "Title", skip_guard=True)

        self.assertFalse(result["allowed"])
        self.assertEqual(result["category"], "policy")


if __name__ == "__main__":
    unittest.main()
