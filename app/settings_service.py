"""Runtime settings resolution.

The `settings` DB table holds values entered through the UI (API keys,
per-task model overrides). Those take precedence over environment/bootstrap
config. Everything funnels through here so the rest of the app never reads
keys/models from two places.
"""

from __future__ import annotations

from sqlmodel import Session, select

from app.config import get_config
from app.models import Setting

# Setting keys (UI-managed)
ANTHROPIC_API_KEY = "anthropic_api_key"
OPENAI_API_KEY = "openai_api_key"
AGENT_MODEL = "agent_model"
GOOGLE_CLIENT_ID = "google_client_id"
GOOGLE_CLIENT_SECRET = "google_client_secret"
GOOGLE_OAUTH_TOKEN = "google_oauth_token"  # JSON blob
GOOGLE_OAUTH_STATE = "google_oauth_state"


def get_setting(session: Session, key: str) -> str | None:
    row = session.get(Setting, key)
    return row.value if row else None


def set_setting(session: Session, key: str, value: str) -> None:
    row = session.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=value)
    else:
        row.value = value
    session.add(row)
    session.commit()


def all_settings(session: Session) -> dict[str, str]:
    return {s.key: s.value for s in session.exec(select(Setting)).all()}


def resolve_anthropic_key(session: Session) -> str | None:
    """UI-entered key wins; fall back to bootstrap env config."""
    return get_setting(session, ANTHROPIC_API_KEY) or get_config().anthropic_api_key


def resolve_openai_key(session: Session) -> str | None:
    return get_setting(session, OPENAI_API_KEY) or get_config().openai_api_key


def resolve_agent_model(session: Session) -> str:
    return get_setting(session, AGENT_MODEL) or get_config().default_agent_model


def resolve_google_client(session: Session) -> tuple[str | None, str | None]:
    return (get_setting(session, GOOGLE_CLIENT_ID), get_setting(session, GOOGLE_CLIENT_SECRET))
