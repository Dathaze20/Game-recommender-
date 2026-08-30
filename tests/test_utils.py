"""Tests for the pure helpers."""

from __future__ import annotations

import pytest

from gamerec.utils import (
    Generation,
    as_dict,
    as_list,
    backoff_delay,
    clamp,
    dedupe_by_id,
    format_release,
    join_names,
    metacritic_band,
    rating_compact,
    rating_text,
    release_year,
    safe_float,
    safe_int,
    safe_str,
    sized_image_url,
    strip_html,
)


class TestRatingText:
    @pytest.mark.parametrize(
        ("rating", "expected"),
        [
            (0, "..... 0.0"),
            (4.47, "****. 4.5"),
            (5, "***** 5.0"),
            (3.0, "***.. 3.0"),
        ],
    )
    def test_renders_stars_and_value(self, rating, expected):
        assert rating_text(rating) == expected

    def test_is_ascii_only(self):
        # Pydroid 3's bundled font renders "★" as an empty box, so the star
        # display must stay in ASCII.
        assert rating_text(4.5).isascii()

    @pytest.mark.parametrize("bad", [None, "", "abc", [], {}])
    def test_tolerates_junk(self, bad):
        assert rating_text(bad) == "..... 0.0"

    def test_clamps_out_of_range(self):
        assert rating_text(9.9) == "***** 5.0"
        assert rating_text(-3) == "..... 0.0"


class TestMetacriticBand:
    @pytest.mark.parametrize(
        ("score", "band"),
        [(97, "great"), (75, "great"), (74, "mixed"), (50, "mixed"), (49, "weak"), (1, "weak")],
    )
    def test_bands(self, score, band):
        assert metacritic_band(score) == band

    @pytest.mark.parametrize("missing", [None, 0, -5, "", "n/a"])
    def test_missing_scores_have_no_band(self, missing):
        assert metacritic_band(missing) is None


class TestCoercion:
    def test_safe_float(self):
        assert safe_float("4.5") == 4.5
        assert safe_float(None) == 0.0
        assert safe_float("nope", 1.0) == 1.0
        assert safe_float(True) == 0.0  # bools are not ratings

    def test_safe_int(self):
        assert safe_int("92") == 92
        assert safe_int(None) is None
        assert safe_int("x", 0) == 0
        assert safe_int(False) is None

    def test_safe_str(self):
        assert safe_str("  hi  ") == "hi"
        assert safe_str(None) == ""
        assert safe_str({"a": 1}) == ""
        assert safe_str(7) == "7"

    def test_as_list_and_as_dict(self):
        assert as_list(None) == []
        assert as_list("abc") == []
        assert as_list([1, 2]) == [1, 2]
        assert as_dict(None) == {}
        assert as_dict({"a": 1}) == {"a": 1}


class TestStripHtml:
    def test_removes_tags_and_entities(self):
        raw = "<p>Great &amp; <b>bold</b></p><p>Second</p>"
        assert strip_html(raw) == "Great & bold\n\nSecond"

    def test_converts_breaks_to_newlines(self):
        assert strip_html("a<br/>b") == "a\nb"

    def test_handles_missing_input(self):
        assert strip_html(None) == ""


class TestDates:
    def test_release_year(self):
        assert release_year("2013-09-17") == "2013"
        assert release_year(None) == ""
        assert release_year("soon") == ""

    def test_format_release(self):
        assert format_release("2013-09-17") == "17 Sep 2013"
        assert format_release("") == "Unknown"
        assert format_release("2013") == "2013"
        assert format_release("2013-13-01") == "2013-13-01"


class TestMisc:
    def test_clamp(self):
        assert clamp(5, 0, 3) == 3
        assert clamp(-1, 0, 3) == 0

    def test_join_names(self):
        assert join_names(["A", "", None, "B"]) == "A, B"
        assert join_names(["A", "B", "C"], limit=2) == "A, B"
        assert join_names(None) == ""

    def test_backoff_grows_and_caps(self):
        assert backoff_delay(1, base=1.0, cap=8.0) == 1.0
        assert backoff_delay(2, base=1.0, cap=8.0) == 2.0
        assert backoff_delay(9, base=1.0, cap=8.0) == 8.0
        assert backoff_delay(0) == 0.0

    def test_dedupe_by_id(self):
        class Item:
            def __init__(self, game_id):
                self.game_id = game_id

        items = [Item(1), Item(2), Item(1), Item(3)]
        assert [i.game_id for i in dedupe_by_id(items)] == [1, 2, 3]
        assert [i.game_id for i in dedupe_by_id(items, exclude_id=2)] == [1, 3]


class TestGeneration:
    def test_only_the_latest_token_is_current(self):
        generation = Generation()
        first = generation.next()
        assert generation.is_current(first)

        second = generation.next()
        assert not generation.is_current(first)
        assert generation.is_current(second)

    def test_current_reports_latest(self):
        generation = Generation()
        assert generation.current == 0
        token = generation.next()
        assert generation.current == token


class TestRatingCompact:
    @pytest.mark.parametrize(
        ("rating", "expected"),
        [(4.47, "4.5"), (5, "5.0"), (3.0, "3.0"), (9.9, "5.0")],
    )
    def test_formats_one_decimal(self, rating, expected):
        assert rating_compact(rating) == expected

    @pytest.mark.parametrize("missing", [0, None, "", "abc", -2, []])
    def test_unrated_games_show_nothing(self, missing):
        assert rating_compact(missing) == ""

    def test_is_ascii_only(self):
        assert rating_compact(4.5).isascii()


class TestSizedImageUrl:
    BASE = "https://media.rawg.io/media/games/456/456dea5e.jpg"

    def test_inserts_a_resize_segment(self):
        assert sized_image_url(self.BASE, 420) == (
            "https://media.rawg.io/media/resize/420/-/games/456/456dea5e.jpg"
        )

    def test_screenshot_paths_work_too(self):
        url = "https://media.rawg.io/media/screenshots/abc/def.jpg"
        assert sized_image_url(url, 800) == (
            "https://media.rawg.io/media/resize/800/-/screenshots/abc/def.jpg"
        )

    @pytest.mark.parametrize(
        "already",
        [
            "https://media.rawg.io/media/resize/640/-/games/a/b.jpg",
            "https://media.rawg.io/media/crop/600/400/games/a/b.jpg",
        ],
    )
    def test_leaves_already_sized_urls_alone(self, already):
        assert sized_image_url(already, 420) == already

    @pytest.mark.parametrize(
        "foreign",
        [
            "https://example.com/cover.jpg",
            "http://media.rawg.io/media/games/a/b.jpg",
            "https://cdn.rawg.io/media/games/a/b.jpg",
        ],
    )
    def test_non_rawg_urls_are_untouched(self, foreign):
        assert sized_image_url(foreign, 420) == foreign

    @pytest.mark.parametrize("bad", [None, "", [], {}])
    def test_missing_url_returns_empty(self, bad):
        assert sized_image_url(bad, 420) == ""

    @pytest.mark.parametrize("width", [0, -1])
    def test_non_positive_width_is_a_no_op(self, width):
        assert sized_image_url(self.BASE, width) == self.BASE

    def test_result_is_a_plain_https_url(self):
        assert sized_image_url(self.BASE, 420).startswith("https://")
