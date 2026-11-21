"""Configurações centralizadas do Synapse carregadas via variáveis de ambiente."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    database_path: str
    timezone_name: str
    google_calendar_enabled: bool
    google_calendar_id: str
    google_calendar_access_token: str
    notification_webhook_url: str

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    def now_local(self) -> datetime:
        """Retorna a data/hora atual no fuso configurado (RN03)."""
        return datetime.now(self.tz)


def get_settings() -> Settings:
    default_db = str(BASE_DIR / "synapse.db")
    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest").strip(),
        database_path=os.getenv("DATABASE_PATH", default_db).strip(),
        timezone_name=os.getenv("TIMEZONE", "America/Fortaleza").strip(),
        google_calendar_enabled=os.getenv("GOOGLE_CALENDAR_ENABLED", "false").lower() == "true",
        google_calendar_id=os.getenv("GOOGLE_CALENDAR_ID", "primary").strip(),
        google_calendar_access_token=os.getenv("GOOGLE_CALENDAR_ACCESS_TOKEN", "").strip(),
        notification_webhook_url=os.getenv("NOTIFICATION_WEBHOOK_URL", "").strip(),
    )
