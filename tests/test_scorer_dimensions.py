import unittest

from oracle.anchors import ANCHORS


CANONICAL_DIMENSIONS = {
    "energy",
    "valence",
    "tension",
    "density",
    "warmth",
    "movement",
    "space",
    "rawness",
    "complexity",
    "nostalgia",
}


class ScorerDimensionTests(unittest.TestCase):
    def test_anchor_dimensions_are_canonical(self) -> None:
        self.assertEqual(set(ANCHORS.keys()), CANONICAL_DIMENSIONS)

    def test_each_dimension_has_low_and_high_poles(self) -> None:
        for dim, poles in ANCHORS.items():
            self.assertIn("low", poles, msg=dim)
            self.assertIn("high", poles, msg=dim)
            self.assertTrue(poles["low"], msg=f"{dim}:low empty")
            self.assertTrue(poles["high"], msg=f"{dim}:high empty")


if __name__ == "__main__":
    unittest.main()
