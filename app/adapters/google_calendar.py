"""Adapter desacoplado para integração com a API do Google Calendar (RNF02)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import Settings, get_settings


@dataclass
class CalendarSyncResult:
    sync_status: str  # SINCRONIZADO | PENDENTE | LOCAL_ONLY
    google_event_id: str | None = None
    detalhe: str = ""


class GoogleCalendarAdapter:
    """Envia eventos para a API REST v3 do Google Calendar com degradação graciosa."""

    BASE_URL = "https://www.googleapis.com/calendar/v3"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def criar_evento(
        self,
        titulo: str,
        inicio_iso: str,
        fim_iso: str,
        descricao: str = "",
    ) -> CalendarSyncResult:
        if not self.settings.google_calendar_enabled or not self.settings.google_calendar_access_token:
            return CalendarSyncResult(
                sync_status="PENDENTE",
                google_event_id=None,
                detalhe="Google Calendar não configurado; salvo localmente como PENDENTE.",
            )

        url = f"{self.BASE_URL}/calendars/{self.settings.google_calendar_id}/events"
        payload = {
            "summary": titulo,
            "description": descricao,
            "start": {"dateTime": inicio_iso, "timeZone": self.settings.timezone_name},
            "end": {"dateTime": fim_iso, "timeZone": self.settings.timezone_name},
        }
        headers = {
            "Authorization": f"Bearer {self.settings.google_calendar_access_token}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                return CalendarSyncResult(
                    sync_status="SINCRONIZADO",
                    google_event_id=data.get("id"),
                    detalhe="Evento sincronizado com Google Calendar.",
                )
        except Exception as exc:
            return CalendarSyncResult(
                sync_status="PENDENTE",
                google_event_id=None,
                detalhe=f"Falha temporária no Google Calendar ({exc}); mantido como PENDENTE.",
            )
