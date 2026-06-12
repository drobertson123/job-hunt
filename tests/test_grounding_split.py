from __future__ import annotations

from app.grounding_service import Span, split_sentences


def test_offsets_are_exact():
    text = "I built APIs in Python. I led a team of five engineers."
    spans = split_sentences(text)
    assert [s.text for s in spans] == [
        "I built APIs in Python.",
        "I led a team of five engineers.",
    ]
    for s in spans:
        assert text[s.start:s.end] == s.text


def test_markdown_structure_headings_and_bullets():
    text = "## Experience\n- Built scalable APIs in Python at Acme.\n\nLed major data migrations safely."
    spans = split_sentences(text)
    # Bare heading "Experience" is < 3 words -> dropped; bullet marker excluded
    # from the span; offsets still index into the ORIGINAL text.
    assert [s.text for s in spans] == [
        "Built scalable APIs in Python at Acme.",
        "Led major data migrations safely.",
    ]
    for s in spans:
        assert text[s.start:s.end] == s.text


def test_abbreviations_do_not_split():
    text = "I used many tools, e.g. Python and Go, every day."
    spans = split_sentences(text)
    assert len(spans) == 1
    assert spans[0].text == text


def test_short_spans_are_skipped():
    # Signatures / closings / bare headings: degenerate-input guard.
    text = "Sincerely,\nJane Doe\n\nI delivered the project on time."
    spans = split_sentences(text)
    assert [s.text for s in spans] == ["I delivered the project on time."]


def test_numbers_with_periods_do_not_split():
    text = "I improved latency by 3.5 times in one quarter."
    spans = split_sentences(text)
    assert len(spans) == 1


def test_empty_text_yields_no_spans():
    assert split_sentences("") == []
    assert split_sentences("\n\n  \n") == []
