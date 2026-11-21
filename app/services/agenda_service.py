"""Serviço do módulo Agenda & Google Calendar (RF04 + RN04)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.adapters.google_calendar import GoogleCalendarAdapter
from app.config import Settings, get_settings
from app.database import Database
from app.schemas import EventoCreate, NotificacaoCreate, OrigemNotificacao
from app.services.notificacoes_service import NotificacoesService


class AgendaService:
    def __init__(
        self,
        db: Database,
        calendar_adapter: GoogleCalendarAdapter | None = None,
        notificacoes_service: NotificacoesService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.calendar_adapter = calendar_adapter or GoogleCalendarAdapter(self.settings)
        self.notificacoes_service = notificacoes_service or NotificacoesService(db, settings=self.settings)

    def agendar_evento(self, payload: EventoCreate, criar_lembrete: bool = True) -> dict[str, Any]:
        sync = self.calendar_adapter.criar_evento(
            titulo=payload.titulo,
            inicio_iso=payload.inicio,
            fim_iso=payload.fim,
            descricao=payload.descricao,
        )
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO eventos_agenda (titulo, descricao, inicio, fim, google_event_id, sync_status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.titulo.strip(),
                    payload.descricao.strip(),
                    payload.inicio,
                    payload.fim,
                    sync.google_event_id,
                    sync.sync_status,
                ),
            )
            row = conn.execute("SELECT * FROM eventos_agenda WHERE id = ?", (cursor.lastrowid,)).fetchone()
            evento = dict(row)

        if criar_lembrete:
            lembrete_iso = self._calcular_lembrete_15min(payload.inicio)
            self.notificacoes_service.agendar_notificacao(
                NotificacaoCreate(
                    origem=OrigemNotificacao.AGENDA,
                    titulo=f"Compromisso: {payload.titulo}",
                    mensagem=f"Começa em breve ({payload.inicio}).",
                    agendado_para=lembrete_iso,
                )
            )
        evento["sync_detalhe"] = sync.detalhe
        return evento

    def listar_eventos(self, data_filtro: str | None = None) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            if data_filtro:
                rows = conn.execute(
                    """
                    SELECT * FROM eventos_agenda
                    WHERE inicio LIKE ?
                    ORDER BY inicio ASC
                    """,
                    (f"{data_filtro}%",),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM eventos_agenda
                    ORDER BY inicio ASC
                    LIMIT 30
                    """
                ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def _calcular_lembrete_15min(inicio_iso: str) -> str:
        try:
            dt = datetime.fromisoformat(inicio_iso)
            return (dt - timedelta(minutes=15)).isoformat(timespec="seconds")
        except ValueError:
            return inicio_iso
