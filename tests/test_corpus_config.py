from __future__ import annotations

from app.config import get_config


def test_embedding_model_default():
    assert get_config().embedding_model == "text-embedding-3-small"
