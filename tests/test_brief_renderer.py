#!/usr/bin/env python3
"""Contract tests for apps.brief.renderer (Phase 6).

Tests cover:
- render_brief: CNR ordering, CCIR_ORDER enforcement
- render_list: score threshold, sorting
- render_bluf: citation rules, LLM failure handling
- render_cluster: grouping by CCIR section
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from apps.brief.renderer import (
    render_brief,
    render_list,
    render_bluf,
    render_cluster,
    CCIR_ORDER,
    _CNR_PRIORITY,
    _group_by_cnr_and_ccir,
)


# ---- helpers ----------------------------------------------------------------


def _make_item(
    item_id: str = "abc123",
    ccir: str = "PIR-1",
    cnr: str = "I",
    score: int = 8,
    bucket: str = "keep",
    why: str = "Test item",
    title: str = "Test Title",
    summary: str = "Test summary",
    source: str = "TestSource",
    url: str = "http://example.com",
    pmesii: str = "Military",
    tessoc: str = "Sabotage",
) -> dict:
    """Factory for enrichment row dicts."""
    return {
        "item_id": item_id,
        "ccir": ccir,
        "cnr": cnr,
        "score": score,
        "bucket": bucket,
        "why": why,
        "title": title,
        "summary": summary,
        "source": source,
        "url": url,
        "pmesii": pmesii,
        "tessoc": tessoc,
    }


# ---- render_brief tests -----------------------------------------------------


class TestRenderBriefCnrFirst(unittest.TestCase):
    """CNR CAT I items must appear before CAT II and Routine."""

    def test_cnr_i_appears_first(self):
        items = [
            _make_item(item_id="i1", ccir="PIR-1", cnr="II", score=9),
            _make_item(item_id="i2", ccir="PIR-1", cnr="I", score=7),
            _make_item(item_id="i3", ccir="PIR-1", cnr="none", score=5),
        ]
        output = render_brief(items)
        cat_i_idx = output.find("varsle straks")
        self.assertNotEqual(cat_i_idx, -1, "CAT I header not found")

    def test_cnr_i_item_in_cat_i_section(self):
        items = [_make_item(item_id="only_i", ccir="PIR-1", cnr="I", score=8)]
        output = render_brief(items)
        self.assertIn("varsle straks", output)
        self.assertIn("PIR-1", output)


class TestRenderBriefCcirOrder(unittest.TestCase):
    """CCIR sections must appear in CCIR_ORDER sequence."""

    def test_ccir_order_enforced(self):
        items = [
            _make_item(
                item_id="p2", ccir="PIR-2", cnr="II", score=8, title="PIR-2 Title"
            ),
            _make_item(
                item_id="p1", ccir="PIR-1", cnr="II", score=8, title="PIR-1 Title"
            ),
            _make_item(
                item_id="p3", ccir="PIR-3", cnr="II", score=8, title="PIR-3 Title"
            ),
        ]
        output = render_brief(items)
        p1_pos = output.find("PIR-1")
        p2_pos = output.find("PIR-2")
        p3_pos = output.find("PIR-3")
        self.assertNotEqual(p1_pos, -1, "PIR-1 not found in output")
        self.assertNotEqual(p2_pos, -1, "PIR-2 not found in output")
        self.assertNotEqual(p3_pos, -1, "PIR-3 not found in output")
        self.assertLess(p1_pos, p2_pos, "PIR-1 should appear before PIR-2")
        self.assertLess(p2_pos, p3_pos, "PIR-2 should appear before PIR-3")


class TestRenderBriefRoutineItems(unittest.TestCase):
    """Items with cnr='none' should be grouped as Routine."""

    def test_routine_items_grouped(self):
        items = [
            _make_item(ccir="none", cnr="none", score=3),
            _make_item(ccir="none", cnr="none", score=5),
        ]
        output = render_brief(items)
        self.assertIn("Routine", output)


# ---- render_list tests ------------------------------------------------------


class TestRenderListScoreThreshold(unittest.TestCase):
    """render_list must only include items with score >= 8, sorted descending."""

    def test_score_below_threshold_excluded(self):
        items = [
            _make_item(item_id="high", title="High Score Title", score=9),
            _make_item(item_id="mid", title="Mid Score Title", score=5),
            _make_item(item_id="low", title="Low Score Title", score=2),
        ]
        output = render_list(items)
        self.assertIn("High Score Title", output)
        self.assertNotIn("Mid Score Title", output)
        self.assertNotIn("Low Score Title", output)

    def test_score_at_threshold_included(self):
        items = [_make_item(item_id="exactly_8", title="Exact Eight", score=8)]
        output = render_list(items)
        self.assertIn("Exact Eight", output)

    def test_sorted_descending(self):
        items = [
            _make_item(item_id="low_score", title="Low", score=8),
            _make_item(item_id="mid_score", title="Mid", score=9),
            _make_item(item_id="high_score", title="High", score=10),
        ]
        output = render_list(items)
        pos_10 = output.find("10")
        pos_9 = output.find("9")
        pos_8 = output.find("8")
        self.assertLess(pos_10, pos_9, "Score 10 should appear before 9")
        self.assertLess(pos_9, pos_8, "Score 9 should appear before 8")


# ---- render_bluf tests ------------------------------------------------------


class TestRenderBlufCitations(unittest.TestCase):
    """The LLM prompt must include citation instructions."""

    def test_prompt_contains_citation_instructions(self):
        items = [_make_item(title="Item 1", summary="Summary 1", ccir="PIR-1")]
        with patch("apps.brief.renderer.llm") as mock_llm:
            mock_llm.return_value = "Mock BLUF text"
            render_bluf(items, ccir_title="Test Topic", ccir_id="PIR-1", top_n=5)
            mock_llm.assert_called_once()
            messages = mock_llm.call_args[0][0]
            prompt_text = messages[0]["content"]
            # [N] in template is replaced by format(), so check for [1] and [2][4] examples
            self.assertIn("[1]", prompt_text, "Prompt must show example [1] citation")
            self.assertIn(
                "[2][4]", prompt_text, "Prompt must show multi-citation example"
            )

    def test_prompt_includes_citation_rules(self):
        items = [_make_item(ccir="PIR-1")]
        with patch("apps.brief.renderer.llm") as mock_llm:
            mock_llm.return_value = "BLUF"
            render_bluf(items, ccir_title="Test", ccir_id="PIR-1")
            messages = mock_llm.call_args[0][0]
            prompt_text = messages[0]["content"]
            self.assertIn(
                "citation", prompt_text.lower(), "Prompt must mention citations"
            )


class TestRenderBlufLlmFailure(unittest.TestCase):
    """render_bluf must return placeholder text when LLM call fails."""

    def test_placeholder_on_connection_error(self):
        items = [_make_item(ccir="PIR-1", score=8)]
        with patch(
            "apps.brief.renderer.llm", side_effect=Exception("Connection refused")
        ):
            result = render_bluf(items, ccir_title="Test", ccir_id="PIR-1")
            self.assertIn(
                "unavailable", result.lower(), "Should return placeholder on failure"
            )
            self.assertNotIn("Exception", result, "Should not leak exception details")

    def test_placeholder_on_none_llm(self):
        """When llm is None, should return placeholder."""
        items = [_make_item(ccir="PIR-1", score=8)]
        with patch("apps.brief.renderer.llm", None):
            result = render_bluf(items, ccir_title="Test", ccir_id="PIR-1")
            # Norwegian placeholder: "bluf utilgjengelig"
            self.assertIn(
                "utilgjengelig",
                result.lower(),
                "Should return placeholder when llm is None",
            )


class TestRenderBlufEmptyItems(unittest.TestCase):
    """Empty items list should return placeholder."""

    def test_no_items_returns_placeholder(self):
        with patch("apps.brief.renderer.llm", None):
            result = render_bluf([], ccir_title="Test", ccir_id="PIR-1")
            self.assertIn("utilgjengelig", result.lower())


# ---- render_cluster tests ---------------------------------------------------


class TestRenderClusterGrouping(unittest.TestCase):
    """render_cluster must group items by CCIR section."""

    def test_items_grouped_by_ccir(self):
        items = [
            _make_item(item_id="p1a", ccir="PIR-1", score=8, title="Item P1A"),
            _make_item(item_id="p1b", ccir="PIR-1", score=7, title="Item P1B"),
            _make_item(item_id="p2a", ccir="PIR-2", score=8, title="Item P2A"),
        ]
        output = render_cluster(items)
        self.assertIn("PIR-1", output)
        self.assertIn("PIR-2", output)
        p1_section_start = output.find("PIR-1")
        p2_section_start = output.find("PIR-2")
        p1a_idx = output.find("Item P1A")
        p1b_idx = output.find("Item P1B")
        p2a_idx = output.find("Item P2A")
        self.assertNotEqual(p1a_idx, -1, "p1a should be in output")
        self.assertNotEqual(p1b_idx, -1, "p1b should be in output")
        self.assertNotEqual(p2a_idx, -1, "p2a should be in output")
        self.assertGreater(p1a_idx, p1_section_start)
        self.assertGreater(p1b_idx, p1_section_start)
        self.assertGreater(p2a_idx, p2_section_start)

    def test_multiple_clusters_in_section(self):
        items = [
            _make_item(
                item_id="a",
                ccir="PIR-1",
                cnr="I",
                score=10,
                title="Story about Ukraine war",
            ),
            _make_item(
                item_id="b",
                ccir="PIR-1",
                cnr="II",
                score=9,
                title="Ukraine conflict update",
            ),
            _make_item(
                item_id="c",
                ccir="PIR-1",
                cnr="II",
                score=7,
                title="Ukraine peace talks",
            ),
        ]
        output = render_cluster(items)
        self.assertIn("Story about Ukraine war", output)
        self.assertIn("Ukraine conflict update", output)
        self.assertIn("Ukraine peace talks", output)


class TestRenderClusterNoCcir(unittest.TestCase):
    """Items without CCIR should be grouped separately."""

    def test_items_without_ccir_have_separate_section(self):
        items = [
            _make_item(
                item_id="with_ccir", ccir="PIR-1", score=8, title="With Ccir Title"
            ),
            _make_item(item_id="no_ccir", ccir="none", score=5, title="No Ccir Title"),
        ]
        output = render_cluster(items)
        # Section header uses uppercase
        self.assertIn("Uten CCIR", output)
        # Items appear by title
        self.assertIn("With Ccir Title", output)
        self.assertIn("No Ccir Title", output)


# ---- _group_by_cnr_and_ccir tests ------------------------------------------


class TestCnrGrouping(unittest.TestCase):
    """Test the internal CNR grouping function."""

    def test_cnr_i_has_priority_zero(self):
        self.assertEqual(_CNR_PRIORITY["I"], 0)

    def test_cnr_ii_has_priority_one(self):
        self.assertEqual(_CNR_PRIORITY["II"], 1)

    def test_cnr_none_has_priority_two(self):
        self.assertEqual(_CNR_PRIORITY["none"], 2)

    def test_grouping_returns_three_keys(self):
        items = [
            _make_item(cnr="I"),
            _make_item(cnr="II"),
            _make_item(cnr="none"),
        ]
        groups = _group_by_cnr_and_ccir(items, CCIR_ORDER)
        self.assertIn("CAT_I", groups)
        self.assertIn("CAT_II", groups)
        self.assertIn("ROUTINE", groups)
        self.assertEqual(len(groups["CAT_I"]), 1)
        self.assertEqual(len(groups["CAT_II"]), 1)
        self.assertEqual(len(groups["ROUTINE"]), 1)


# ---- CCIR_ORDER verification ------------------------------------------------


class TestRenderBriefIncludesAllItemFields(unittest.TestCase):
    """Regression: CAT_II/ROUTINE item lines must include title, score, AND why.

    Previously render_brief() called `digest.line()` in the CCIR-iteration path,
    which formats as `f"- {why or title}  [les](url)"` — when `why` is truthy,
    `or` short-circuits and `title` is dropped. The rendered line was:
    `- <why>  [les](<url>)` — no score, no title.
    """

    def test_cat_ii_line_includes_title_score_and_why(self):
        items = [
            _make_item(
                item_id="cat-ii-1",
                ccir="PIR-1",
                cnr="II",
                score=7,
                title="Russland varsler nye sanksjoner",
                why="Krigsøkonomi under press",
            ),
        ]
        output = render_brief(items)
        # Title must be present (the bug dropped it).
        self.assertIn("Russland varsler nye sanksjoner", output)
        # Score must be present (the bug dropped it via the `_digest_line` path).
        self.assertIn("[7]", output)
        # Why must be present (still useful to the operator).
        self.assertIn("Krigsøkonomi under press", output)

    def test_routine_no_ccir_line_includes_title(self):
        items = [
            _make_item(
                item_id="routine-1",
                ccir="none",
                cnr="none",
                score=3,
                title="Lokal nyhet utenriks",
                why="Bakgrunn på saken",
            ),
        ]
        output = render_brief(items)
        self.assertIn("Lokal nyhet utenriks", output)
        self.assertIn("[3]", output)


class TestCcirOrder(unittest.TestCase):
    """Verify CCIR_ORDER has the expected structure."""

    def test_ccir_order_is_not_empty(self):
        self.assertGreater(len(CCIR_ORDER), 0, "CCIR_ORDER should not be empty")

    def test_ccir_order_contains_tuples(self):
        for item in CCIR_ORDER:
            self.assertIsInstance(item, tuple)
            self.assertEqual(len(item), 2)

    def test_ccir_order_ids_are_strings(self):
        for cid, _ in CCIR_ORDER:
            self.assertIsInstance(cid, str)

    def test_ccir_order_titles_are_strings(self):
        for _, title in CCIR_ORDER:
            self.assertIsInstance(title, str)
            self.assertGreater(len(title), 0, "Title should not be empty")


if __name__ == "__main__":
    unittest.main()
