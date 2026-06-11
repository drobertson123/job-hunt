"""Settings endpoints — UI-entered API keys + per-task model config.

Secrets are never returned; GET reports only whether each key is configured.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.config import get_config
from app.db import get_session
from app import settings_service as ss

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    agent_model: str | None = None


class SettingsView(BaseModel):
    anthropic_key_configured: bool
    openai_key_configured: bool
    agent_model: str
    default_agent_model: str
    deep_analysis_model: str


def _view(session: Session) -> SettingsView:
    cfg = get_config()
    return SettingsView(
        anthropic_key_configured=bool(ss.resolve_anthropic_key(session)),
        openai_key_configured=bool(ss.resolve_openai_key(session)),
        agent_model=ss.resolve_agent_model(session),
        default_agent_model=cfg.default_agent_model,
        deep_analysis_model=cfg.deep_analysis_model,
    )


@router.get("")
def get_settings(session: Session = Depends(get_session)) -> SettingsView:
    return _view(session)


@router.put("")
def update_settings(
    body: SettingsUpdate, session: Session = Depends(get_session)
) -> SettingsView:
    if body.anthropic_api_key is not None:
        ss.set_setting(session, ss.ANTHROPIC_API_KEY, body.anthropic_api_key.strip())
    if body.openai_api_key is not None:
        ss.set_setting(session, ss.OPENAI_API_KEY, body.openai_api_key.strip())
    if body.agent_model is not None:
        ss.set_setting(session, ss.AGENT_MODEL, body.agent_model.strip())
    return _view(session)
