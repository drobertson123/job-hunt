from sqlmodel import Session

from app.db import engine
from app import services
from app.models import ContentBlockKind


def test_add_list_delete_content_block():
    with Session(engine) as s:
        b = services.add_content_block(s, kind=ContentBlockKind.headline, text="IIoT & Digital Twin Leader", audience="technical", tags=["iiot"])
        assert b.id is not None
        assert any(x.id == b.id for x in services.list_content_blocks(s))
        assert services.list_content_blocks(s, kind=ContentBlockKind.summary) == []
        assert services.delete_content_block(s, b.id) is True
        assert services.delete_content_block(s, b.id) is False


async def test_save_content_block_tool_persists():
    from app.agent.tools import save_content_block
    res = await save_content_block.handler({"text": "Scaled platform 10x", "kind": "bullet", "tags": ["scale"]})
    assert res["content"][0]["text"].startswith("Saved content block")
    with Session(engine) as s:
        assert any(x.text == "Scaled platform 10x" for x in services.list_content_blocks(s))


def test_content_blocks_api(client):
    r = client.post  # noqa: F841 (writes go via tool; just exercise GET/DELETE)
    # seed via service
    from app.db import engine as e
    with Session(e) as s:
        b = services.add_content_block(s, kind=ContentBlockKind.bullet, text="Led 30 engineers")
        bid = b.id
    got = client.get("/api/content-blocks").json()
    assert any(x["id"] == bid for x in got)
    assert client.delete(f"/api/content-blocks/{bid}").status_code == 204
    assert client.delete(f"/api/content-blocks/{bid}").status_code == 404
