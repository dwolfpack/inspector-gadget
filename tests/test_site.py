from gadget import site


def _item(headline="Headline", section="Models & Releases", url="https://example.com/a", day="2026-08-07"):
    return {
        "sent_at": f"{day}T06:00:00+00:00",
        "headline": headline,
        "summary": "What happened.",
        "why_it_matters": "Why it matters.",
        "outlet": "Reuters",
        "source_url": url,
        "section": section,
    }


def test_group_by_day_is_newest_first():
    days = site.group_by_day([_item(day="2026-08-05"), _item(day="2026-08-07")])

    assert list(days) == ["2026-08-07", "2026-08-05"]


def test_group_by_day_skips_pre_board_entries():
    # Old personal-idea entries have a "hook", not a "headline".
    old = {"sent_at": "2026-08-04T06:00:00+00:00", "hook": "An idea", "source_url": "https://x"}

    days = site.group_by_day([old, _item()])

    assert list(days) == ["2026-08-07"]
    assert len(days["2026-08-07"]) == 1


def test_group_by_day_skips_entries_without_a_usable_date():
    assert site.group_by_day([dict(_item(), sent_at="")]) == {}


def test_render_board_escapes_model_output():
    html = site.render_board("2026-08-07", [_item(headline="A & B <c>")], searches=5)

    assert "A &amp; B &lt;c&gt;" in html
    assert "<c>" not in html


def test_render_board_numbers_only_non_empty_sections():
    items = [_item(section="Models & Releases"), _item(section="Companies & Money", url="https://example.com/b")]

    html = site.render_board("2026-08-07", items, searches=5)

    assert "01" in html and "02" in html
    assert "03" not in html
    assert "Prompt Engineering" not in html


def test_render_board_keeps_items_filed_under_an_unknown_section():
    html = site.render_board("2026-08-07", [_item(section="Made Up")], searches=5)

    assert "Also today" in html
    assert "Headline" in html


def test_render_board_counts_unique_sources():
    items = [_item(url="https://a.example"), _item(url="https://a.example"), _item(url="https://b.example")]

    html = site.render_board("2026-08-07", items, searches=5)

    assert ">2<" in html  # two distinct sources, three items


def test_render_board_with_no_items_says_so():
    html = site.render_board("2026-08-07", [], searches=5)

    assert "Nothing cleared the bar" in html


def test_build_writes_index_archive_and_nojekyll(tmp_path):
    written = site.build([_item(day="2026-08-07"), _item(day="2026-08-06", url="https://b.example")],
                         searches=5, root=tmp_path)

    assert (tmp_path / "index.html").exists()
    assert (tmp_path / "archive" / "2026-08-07.html").exists()
    assert (tmp_path / "archive" / "2026-08-06.html").exists()
    assert (tmp_path / "archive" / "index.html").exists()
    assert (tmp_path / ".nojekyll").exists()
    assert len(written) == 4


def test_build_index_shows_only_the_newest_day(tmp_path):
    site.build([_item(headline="Today", day="2026-08-07"),
                _item(headline="Yesterday", day="2026-08-06", url="https://b.example")],
               searches=5, root=tmp_path)

    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "Today" in index
    assert "Yesterday" not in index


def test_build_on_an_empty_archive_says_it_is_not_published_yet(tmp_path):
    # Claiming "nothing cleared the bar today" before any board has ever been
    # published would be a statement about the news, not about this site.
    site.build([], searches=5, root=tmp_path)

    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "first board goes up" in index
    assert "Nothing cleared the bar" not in index
    assert "0 days on record" in (tmp_path / "archive" / "index.html").read_text(encoding="utf-8")


def test_a_real_day_with_no_items_still_says_the_bar_was_not_cleared(tmp_path):
    # Distinct from the never-published case: this day genuinely happened.
    empty_day = {"sent_at": "2026-08-07T06:00:00+00:00", "headline": "x",
                 "summary": "", "why_it_matters": "", "outlet": "",
                 "source_url": "", "section": "Models & Releases"}
    html = site.render_board("2026-08-07", [], searches=5)

    assert "Nothing cleared the bar" in html
    assert "first board goes up" not in html
