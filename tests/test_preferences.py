from sqlmodel import Session

from app.db import engine
from app import profile_service as ps
from app.models import Profile


def test_set_preferences_partial_and_clean():
    with Session(engine) as s:
        row = ps.set_preferences(s, dealbreakers=[" agency ", "crypto", "agency"], must_haves=["remote"])
        assert row.dealbreakers == ["agency", "crypto"]  # trimmed + deduped
        assert row.must_haves == ["remote"]
        assert row.nice_to_haves == []
        # partial update leaves the untouched field intact
        row2 = ps.set_preferences(s, nice_to_haves=["equity"])
        assert row2.dealbreakers == ["agency", "crypto"] and row2.nice_to_haves == ["equity"]


def test_synthesize_profile_does_not_touch_preferences():
    async def fake_query(*a, **k):
        from claude_agent_sdk import AssistantMessage, TextBlock
        yield AssistantMessage(content=[TextBlock(text='{"headline":"H","summary":"S","skills":[],"target_titles":[],"locations":[]}')], model="m")

    import asyncio
    with Session(engine) as s:
        ps.set_preferences(s, dealbreakers=["agency"])
    asyncio.run(_synth(fake_query))
    with Session(engine) as s:
        assert s.exec(__import__("sqlmodel").select(Profile)).first().dealbreakers == ["agency"]


async def _synth(fake_query):
    from sqlmodel import Session as S
    from app import profile_service as ps
    from app.models import Document, DocumentSource, DocumentMediaType
    import hashlib

    with S(engine) as s:
        # synthesize_profile requires at least one document in the corpus
        doc = Document(
            title="dummy",
            source_kind=DocumentSource.paste,
            media_type=DocumentMediaType.txt,
            raw_text="x",
            content_hash=hashlib.sha256(b"x").hexdigest(),
            char_count=1,
        )
        s.add(doc)
        s.commit()
        await ps.synthesize_profile(s, query_fn=fake_query)


def test_patch_profile_sets_preferences(client):
    r = client.patch("/api/corpus/profile", json={
        "dealbreakers": ["on-site only"], "must_haves": ["staff+"], "nice_to_haves": ["AI"],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["dealbreakers"] == ["on-site only"]
    assert body["must_haves"] == ["staff+"] and body["nice_to_haves"] == ["AI"]
