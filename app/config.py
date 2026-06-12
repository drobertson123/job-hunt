"""Application configuration.

Two layers:
  * AppConfig (this file) — static/bootstrap config from environment / .env:
    paths, host/port, model defaults, and agent safety caps.
  * The `settings` DB table (see models.py) — values entered through the UI at
    runtime (API keys, per-task model overrides). Runtime values take precedence
    over env; see app.settings_service.resolve_* helpers.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = parent of the app/ package directory.
ROOT_DIR = Path(__file__).resolve().parent.parent


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Networking ---
    # 0.0.0.0 so the app is reachable from a phone over Tailscale.
    host: str = "0.0.0.0"
    port: int = 8000

    # --- Storage ---
    data_dir: Path = ROOT_DIR / "data"
    sessions_dir: Path = ROOT_DIR / "sessions"  # per-agent-session working dirs
    # Authored-skill plugin (career pack). Absolute path — the agent session's
    # cwd is an isolated per-run dir, so discovery must NOT be cwd-relative.
    career_pack_dir: Path = ROOT_DIR / "skills" / "career-pack"

    # --- Static frontend (built Next.js export) ---
    frontend_dir: Path = ROOT_DIR / "frontend" / "out"

    # --- LLM models (per-task, overridable via the settings table) ---
    # Agent loops + web search are token-heavy -> default to Sonnet.
    default_agent_model: str = "claude-sonnet-4-6"
    # Reserve Opus for deep analysis.
    deep_analysis_model: str = "claude-opus-4-8"
    # Embeddings (RAG corpus). OpenAI; key via settings_service.resolve_openai_key.
    embedding_model: str = "text-embedding-3-small"
    # Grounding verifier: sentences scoring below this cosine similarity vs the
    # corpus are marked [MISSING]. Conservative default; tune from real runs
    # (the report stores raw scores and the threshold used per run).
    grounding_min_similarity: float = 0.40

    # --- Bootstrap API keys (UI-entered keys in the settings table win) ---
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # --- Agent safety caps (bound runaway loops / cost) ---
    agent_max_turns: int = 24
    agent_timeout_seconds: int = 300

    # --- "What needs attention" thresholds ---
    attention_stale_active_days: int = 7  # active/in-dialogue with no activity
    attention_untriaged_days: int = 14  # new/qualifying left sitting

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_config() -> AppConfig:
    cfg = AppConfig()
    cfg.ensure_dirs()
    return cfg
