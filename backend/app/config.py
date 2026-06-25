"""Centralized configuration loaded from environment / .env.

Every external integration degrades gracefully: a missing credential flips
that channel to MOCK mode (see integrations/*), so the app always runs for a
demo even before keys are provisioned.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Core ────────────────────────────────────────────────────────
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    public_base_url: str = "http://localhost:8000"

    # ── Postgres ────────────────────────────────────────────────────
    database_url: str = (
        "postgresql+asyncpg://aquabro:aquabro@localhost:5432/aquabro"
    )

    # ── OpenWeatherMap ──────────────────────────────────────────────
    openweather_api_key: str = ""
    # Current-weather endpoint (works with a standard free API key).
    openweather_base_url: str = "https://api.openweathermap.org/data/2.5/weather"
    owm_lat: float = 3.0333
    owm_lon: float = 101.6158

    # ── Telegram ────────────────────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # ── ElevenLabs ──────────────────────────────────────────────────
    elevenlabs_api_key: str = ""
    elevenlabs_agent_id: str = ""
    voice_enabled: bool = False

    # ── LLM agent (Telegram natural-language control) ───────────────
    # OpenAI-compatible. Default = Alibaba DashScope (Qwen), same provider
    # as the SitePilot repo. Powers the 2-way Telegram operator bot.
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_text_model: str = "qwen-turbo"
    # Inbound Telegram command poller. Off => alerts stay one-way only.
    telegram_agent_enabled: bool = True

    # ── Vision / data ───────────────────────────────────────────────
    data_dir: str = "./data"
    vision_clips_dir: str = "./data/clips"
    telemetry_csv: str = "./data/meta_tilapia_set.csv"
    vision_detector: str = "motion"  # "motion" | "yolo"
    vision_yolo_weights: str = ""
    vision_fps: int = 15
    telemetry_interval: float = 2.0

    # ── Convenience flags ───────────────────────────────────────────
    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def weather_configured(self) -> bool:
        return bool(self.openweather_api_key)

    @property
    def voice_configured(self) -> bool:
        return self.voice_enabled and bool(
            self.elevenlabs_api_key and self.elevenlabs_agent_id
        )

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key)

    @property
    def telegram_agent_ready(self) -> bool:
        return self.telegram_agent_enabled and self.telegram_configured

    @property
    def clips_path(self) -> Path:
        return (REPO_ROOT / self.vision_clips_dir).resolve()

    @property
    def telemetry_csv_path(self) -> Path:
        return (REPO_ROOT / self.telemetry_csv).resolve()

    @field_validator("vision_detector")
    @classmethod
    def _valid_detector(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in {"motion", "yolo"}:
            raise ValueError("vision_detector must be 'motion' or 'yolo'")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
