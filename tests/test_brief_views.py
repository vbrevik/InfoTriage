#!/usr/bin/env python3
"""Tests for apps.brief.views (COP/CIP/CRP picture filters, ADR-012)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from apps.brief.views import filter_rows


def _make_item(
    item_id: str = "abc123",
    ccir: str = "PIR-1",
    pmesii: str = "Military",
    tessoc: str = "Sabotage",
    score: int = 8,
) -> dict:
    return {
        "item_id": item_id,
        "ccir": ccir,
        "cnr": "II",
        "score": score,
        "bucket": "keep",
        "why": "Test",
        "title": "Test Title",
        "summary": "Test summary",
        "source": "TestSource",
        "url": "http://example.com",
        "pmesii": pmesii,
        "tessoc": tessoc,
    }


class TestFilterRowsNoView(unittest.TestCase):
    def test_no_view_returns_all_rows(self):
        rows = [_make_item(), _make_item(item_id="2", ccir="FFIR-1")]
        self.assertEqual(filter_rows(rows, None), rows)


class TestCopView(unittest.TestCase):
    def test_cop_includes_matching_rows(self):
        rows = [
            _make_item(ccir="FFIR-1", pmesii="Political"),
            _make_item(ccir="PIR-3", pmesii="Military"),
            _make_item(ccir="PIR-1", pmesii="Military"),  # not COP ccir
        ]
        result = filter_rows(rows, "cop")
        self.assertEqual(len(result), 2)
        self.assertEqual({r["ccir"] for r in result}, {"FFIR-1", "PIR-3"})

    def test_cop_excludes_wrong_pmesii(self):
        rows = [_make_item(ccir="FFIR-1", pmesii="Economic")]
        self.assertEqual(filter_rows(rows, "cop"), [])


class TestCipView(unittest.TestCase):
    def test_cip_includes_pir_with_tessoc(self):
        rows = [
            _make_item(ccir="PIR-4", pmesii="Information", tessoc="Sabotage"),
            _make_item(ccir="PIR-1", pmesii="Military", tessoc="Espionage"),
            _make_item(ccir="PIR-1", pmesii="Military", tessoc="none"),  # no tessoc
        ]
        result = filter_rows(rows, "cip")
        self.assertEqual(len(result), 2)

    def test_cip_excludes_non_pir(self):
        rows = [_make_item(ccir="FFIR-1", pmesii="Military", tessoc="Sabotage")]
        self.assertEqual(filter_rows(rows, "cip"), [])

    def test_cip_excludes_wrong_pmesii(self):
        rows = [_make_item(ccir="PIR-1", pmesii="Social", tessoc="Sabotage")]
        self.assertEqual(filter_rows(rows, "cip"), [])


class TestCrpView(unittest.TestCase):
    def test_crp_filters_by_ccir(self):
        rows = [
            _make_item(ccir="PIR-1"),
            _make_item(ccir="PIR-2", item_id="2"),
        ]
        result = filter_rows(rows, "crp", {"ccir": "PIR-1"})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ccir"], "PIR-1")

    def test_crp_filters_by_pmesii(self):
        rows = [
            _make_item(pmesii="Military"),
            _make_item(pmesii="Economic", item_id="2"),
        ]
        result = filter_rows(rows, "crp", {"pmesii": "Economic"})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["pmesii"], "Economic")

    def test_crp_filters_by_tessoc(self):
        rows = [
            _make_item(tessoc="Sabotage"),
            _make_item(tessoc="Espionage", item_id="2"),
        ]
        result = filter_rows(rows, "crp", {"tessoc": "Espionage"})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["tessoc"], "Espionage")

    def test_crp_filters_by_min_score(self):
        rows = [
            _make_item(score=5),
            _make_item(score=9, item_id="2"),
        ]
        result = filter_rows(rows, "crp", {"min_score": "8"})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["score"], 9)

    def test_crp_combined_filters(self):
        rows = [
            _make_item(ccir="PIR-1", pmesii="Military", score=9),
            _make_item(ccir="PIR-2", pmesii="Military", score=9, item_id="2"),
            _make_item(ccir="PIR-1", pmesii="Economic", score=9, item_id="3"),
        ]
        result = filter_rows(rows, "crp", {"ccir": "PIR-1", "pmesii": "Military"})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["item_id"], "abc123")


class TestFilterRowsUnknownView(unittest.TestCase):
    def test_unknown_view_raises(self):
        with self.assertRaises(ValueError):
            filter_rows([], "unknown")


class TestCaseInsensitiveNormalization(unittest.TestCase):
    """Lock in the case-insensitive behavior of _normalize (regression for
    the seed_sample_data.py path: it inserts pmesii/tessoc in lowercase, but
    the COP/CIP sets are title-cased). Without the title-case fix in
    _normalize, the lowercase seeded rows would silently fail every filter
    and /sab?view=cop /view=cip would render empty SABs.
    """

    def test_cip_accepts_lowercase_pmesii_from_seed(self):
        rows = [_make_item(ccir="PIR-1", pmesii="military", tessoc="terror")]
        result = filter_rows(rows, "cip")
        self.assertEqual(len(result), 1, "lowercase pmesii must match _CIP_PMESII")

    def test_cop_accepts_lowercase_pmesii_from_seed(self):
        rows = [_make_item(ccir="FFIR-1", pmesii="political", tessoc="subversion")]
        result = filter_rows(rows, "cop")
        self.assertEqual(len(result), 1, "lowercase pmesii must match _COP_PMESII")

    def test_cip_rejects_lowercase_none_tessoc(self):
        # _normalize title-cases "none" → "None"; the check must stay
        # case-insensitive (tessoc.lower()) to correctly reject it.
        rows = [_make_item(ccir="PIR-1", pmesii="military", tessoc="none")]
        result = filter_rows(rows, "cip")
        self.assertEqual(
            result, [], 'tessoc="none" must not be treated as a real TESSOC label'
        )

    def test_crp_accepts_lowercase_user_param(self):
        rows = [_make_item(pmesii="Military")]
        result = filter_rows(rows, "crp", {"pmesii": "military"})
        self.assertEqual(len(result), 1, "user-supplied lowercase param must match")


if __name__ == "__main__":
    unittest.main()
