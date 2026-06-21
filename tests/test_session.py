import pytest

from claude_agent_sdk import CLIConnectionError
from app.agent.session import ClaudeCliSession


class _Opts:
    """Minimal stand-in for ClaudeAgentOptions (only attrs the session reads)."""
    def __init__(self, model=None, api_key=None):
        self.model = model
        self.env = {"ANTHROPIC_API_KEY": api_key} if api_key else {}


class FakeClient:
    def __init__(self, options, script, fail_first_stream=False):
        self.options = options
        self.script = script
        self._fail = fail_first_stream
        self.connects = 0
        self.disconnects = 0
        self.set_models = []
        self.probes = 0
        self.server_info_raises = False

    async def connect(self):
        self.connects += 1

    async def disconnect(self):
        self.disconnects += 1

    async def set_model(self, model):
        self.set_models.append(model)

    async def get_server_info(self):
        self.probes += 1
        if self.server_info_raises:
            raise CLIConnectionError("dead")
        return {}

    async def query(self, prompt, session_id="default"):
        self._last_prompt = prompt

    async def receive_response(self):
        if self._fail:
            self._fail = False
            raise CLIConnectionError("dropped")
        for m in self.script:
            yield m


def _factory(script, fail_first=False):
    created = []

    def make(options):
        c = FakeClient(options, script, fail_first_stream=(fail_first and not created))
        created.append(c)
        return c

    return make, created


@pytest.mark.asyncio
async def test_run_yields_messages_in_order():
    script = ["a", "b", "RESULT"]
    make, created = _factory(script)
    s = ClaudeCliSession(client_factory=make)
    out = [m async for m in s.run(prompt="hi", options=_Opts(model="m1"))]
    assert out == script
    assert created[0].connects == 1


@pytest.mark.asyncio
async def test_second_run_reuses_connection():
    make, created = _factory(["RESULT"])
    s = ClaudeCliSession(client_factory=make)
    _ = [m async for m in s.run(prompt="1", options=_Opts(model="m1"))]
    _ = [m async for m in s.run(prompt="2", options=_Opts(model="m1"))]
    assert len(created) == 1          # connected once, reused
    assert created[0].connects == 1
    assert created[0].set_models == []  # same model → no set_model


@pytest.mark.asyncio
async def test_model_change_calls_set_model_without_reconnect():
    make, created = _factory(["RESULT"])
    s = ClaudeCliSession(client_factory=make)
    _ = [m async for m in s.run(prompt="1", options=_Opts(model="m1"))]
    _ = [m async for m in s.run(prompt="2", options=_Opts(model="m2"))]
    assert len(created) == 1
    assert created[0].set_models == ["m2"]


@pytest.mark.asyncio
async def test_reconnect_on_dropped_session():
    make, created = _factory(["RESULT"], fail_first=True)
    s = ClaudeCliSession(client_factory=make)
    out = [m async for m in s.run(prompt="hi", options=_Opts(model="m1"))]
    assert out == ["RESULT"]            # retried after reconnect
    assert len(created) == 2            # first failed, reconnected to a new client
    assert created[0].disconnects == 1


@pytest.mark.asyncio
async def test_api_key_change_reconnects():
    make, created = _factory(["RESULT"])
    s = ClaudeCliSession(client_factory=make)
    _ = [m async for m in s.run(prompt="1", options=_Opts(model="m1", api_key="k1"))]
    _ = [m async for m in s.run(prompt="2", options=_Opts(model="m1", api_key="k2"))]
    assert len(created) == 2            # key changed → reconnect


@pytest.mark.asyncio
async def test_probe_drops_dead_session():
    make, created = _factory(["RESULT"])
    s = ClaudeCliSession(client_factory=make)
    _ = [m async for m in s.run(prompt="1", options=_Opts(model="m1"))]
    created[0].server_info_raises = True
    await s._probe()
    assert created[0].disconnects == 1  # dead probe → session reset
    # next run reconnects
    _ = [m async for m in s.run(prompt="2", options=_Opts(model="m1"))]
    assert len(created) == 2
