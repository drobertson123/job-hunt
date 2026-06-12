from __future__ import annotations

from app.config import AppConfig, get_config


def test_grounding_min_similarity_default():
    assert get_config().grounding_min_similarity == 0.40


def test_grounding_min_similarity_env_override(monkeypatch):
    # Fresh AppConfig (not the lru-cached get_config) to test env wiring.
    monkeypatch.setenv("OH_GROUNDING_MIN_SIMILARITY", "0.85")
    assert AppConfig().grounding_min_similarity == 0.85
