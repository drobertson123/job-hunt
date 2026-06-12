from __future__ import annotations

from app.grounding_service import annotate


def _finding(text, start, end, supported):
    return {"text": text, "start": start, "end": end, "score": 0.0,
            "chunk_id": None, "document_title": None, "supported": supported}


def test_unsupported_sentences_get_missing_markers():
    text = "I build python apis. I won a Nobel prize."
    findings = [
        _finding("I build python apis.", 0, 20, True),
        _finding("I won a Nobel prize.", 21, 41, False),
    ]
    out = annotate(text, findings)
    assert out == "I build python apis. [MISSING: I won a Nobel prize.]"
    assert text == "I build python apis. I won a Nobel prize."  # original untouched


def test_multiple_unsupported_spans_applied_in_reverse_offset_order():
    text = "Alpha beta gamma. Delta epsilon zeta. Eta theta iota."
    findings = [
        _finding("Alpha beta gamma.", 0, 17, False),
        _finding("Delta epsilon zeta.", 18, 37, True),
        _finding("Eta theta iota.", 38, 53, False),
    ]
    out = annotate(text, findings)
    assert out == "[MISSING: Alpha beta gamma.] Delta epsilon zeta. [MISSING: Eta theta iota.]"


def test_all_supported_returns_text_unchanged():
    text = "Everything here is fine."
    findings = [_finding(text, 0, len(text), True)]
    assert annotate(text, findings) == text


def test_no_findings_returns_text_unchanged():
    assert annotate("Some text.", []) == "Some text."
