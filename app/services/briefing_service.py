"""Serviço do Briefing Diário Consolidado (RF07)."""

from __future__ import annotations

from typing import Any

from app.config import Settings, get_settings
from app.services.agenda_service import AgendaService
from app.services.financas_service import FinancasService
from app.services.notificacoes_service import NotificacoesService
from app.services.saude_service import SaudeService
from app.services.tarefas_service import TarefasService


class BriefingService:
    def __init__(
        self,
        financas: FinancasService,
        tarefas: TarefasService,
        agenda: AgendaService,
        saude: SaudeService,
        notificacoes: NotificacoesService,
        settings: Settings | None = None,
    ) -> None:
        self.financas = financas
        self.tarefas = tarefas
        self.agenda = agenda
        self.saude = saude
        self.notificacoes = notificacoes
        self.settings = settings or get_settings()

    def gerar_briefing(self) -> dict[str, Any]:
        agora = self.settings.now_local()
        hoje = agora.date().isoformat()
        return {
            "data_referencia": hoje,
            "hora_atual": agora.strftime("%H:%M"),
            "fuso_horario": self.settings.timezone_name,
            "agenda_hoje": self.agenda.listar_eventos(data_filtro=hoje),
            "proximos_eventos": self.agenda.listar_eventos(),
            "tarefas_pendentes": self.tarefas.listar_tarefas(status="PENDENTE"),
            "saude_hoje": self.saude.progresso_diario(data_iso=hoje),
            "notificacoes_pendentes": self.notificacoes.listar_notificacoes(apenas_pendentes=True),
            "resumo_financeiro": self.financas.resumo_periodo(),
        }
