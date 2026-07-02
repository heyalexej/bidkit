from generate_openapi import clean_description, trim_description


def test_clean_description_strips_tags_and_entities() -> None:
    raw = '<span class="tablenote"><b>Note:</b> Due to EU &amp; UK rules.</span>'
    assert clean_description(raw) == "Note: Due to EU & UK rules."


def test_clean_description_preserves_literal_comparison_prose() -> None:
    assert (
        clean_description("applies when quantity < 10 and price > 5 total")
        == "applies when quantity < 10 and price > 5 total"
    )


def test_clean_description_survives_escaped_html_inside_attributes() -> None:
    raw = '<p data-mc-autonum="&lt;b&gt;Important! &lt;/b&gt;"><b>Important!</b></p> Body.'
    assert clean_description(raw) == "Important! Body."


def test_clean_description_restores_sentence_breaks() -> None:
    assert clean_description("the filter parameter.Retrieving items") == (
        "the filter parameter. Retrieving items"
    )


def test_trim_description_cuts_at_sentence_boundary() -> None:
    text = ("First sentence. " * 40).strip()
    trimmed = trim_description(text, limit=100)
    assert trimmed.endswith(".")
    assert len(trimmed) <= 100
