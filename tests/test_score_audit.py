import unittest

from oracle.score_audit import run_audit


class ScoreAuditTests(unittest.TestCase):
    def test_audit_includes_tag_alignment_block(self) -> None:
        payload = run_audit()
        self.assertIn("tag_alignment", payload)
        alignment = payload["tag_alignment"]
        self.assertIsInstance(alignment, dict)
        self.assertIn("agreement_rate", alignment)
        rate = float(alignment["agreement_rate"])
        self.assertGreaterEqual(rate, 0.0)
        self.assertLessEqual(rate, 1.0)


if __name__ == "__main__":
    unittest.main()

