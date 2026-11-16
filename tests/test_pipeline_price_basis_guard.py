"""Regression tests for historical OHLC price-adjustment basis validation."""
import unittest

import pandas as pd

from src.core.pipeline import _historical_price_basis_status


class HistoricalPriceBasisStatusTests(unittest.TestCase):
    def test_accepts_uniform_known_basis(self):
        frame = pd.DataFrame({"price_adjustment_basis": ["auto_adjusted"] * 3})
        self.assertEqual(_historical_price_basis_status(frame), (True, "auto_adjusted"))

    def test_rejects_mixed_basis(self):
        frame = pd.DataFrame({"price_adjustment_basis": ["qfq", "auto_adjusted"]})
        self.assertEqual(_historical_price_basis_status(frame), (False, "mixed"))

    def test_rejects_unknown_or_missing_basis(self):
        frame = pd.DataFrame({"price_adjustment_basis": [None, None]})
        self.assertEqual(
            _historical_price_basis_status(frame),
            (False, "unknown_or_incomplete"),
        )

    def test_rejects_unsupported_basis(self):
        frame = pd.DataFrame({"price_adjustment_basis": ["provider_default"]})
        self.assertEqual(
            _historical_price_basis_status(frame),
            (False, "unknown_or_unsupported"),
        )

    def test_rejects_empty_frame(self):
        self.assertEqual(
            _historical_price_basis_status(pd.DataFrame()),
            (False, "unknown_or_incomplete"),
        )


if __name__ == "__main__":
    unittest.main()
