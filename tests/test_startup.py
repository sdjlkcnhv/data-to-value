"""Startup receipts must express an explicit mode and complete, nonzero preferences."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from configure_preferences import PROFILES, validate_preferences
from build_demo import demo_report
from render_candidate_scores import validate


class Startup(unittest.TestCase):
    def receipt(self, mode):
        return dict(schema_version=1, mode=mode, confirmed=True,
                    weights={d[0]: d[2] for d in PROFILES[mode]})

    def test_unselected_unconfirmed_or_mixed_profile_rejected(self):
        for patch in [dict(mode=None), dict(confirmed=False),
                      dict(weights=self.receipt("business")["weights"])]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                validate_preferences(self.receipt("academic") | patch)

    def test_zero_weights_transfer_but_all_zero_rejected(self):
        for mode in PROFILES:
            receipt = self.receipt(mode)
            receipt["weights"][next(iter(receipt["weights"]))] = 0
            validate_preferences(receipt)
            report = demo_report(mode)
            for d in report["dimensions"]:
                d["weight"] = receipt["weights"][d["id"]]
            validate(report)
            for d in report["dimensions"]:
                d["weight"] = 0
            with self.assertRaises(ValueError):
                validate(report)
            receipt["weights"] = dict.fromkeys(receipt["weights"], 0)
            with self.assertRaises(ValueError):
                validate_preferences(receipt)

    def test_invalid_values_rejected(self):
        for value in [-1, True, float("nan"), float("inf")]:
            receipt = copy.deepcopy(self.receipt("academic"))
            receipt["weights"]["novelty"] = value
            with self.assertRaises(ValueError):
                validate_preferences(receipt)
