"""Aplicação FastAPI do Synapse — API REST + Interface Web."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.adapters.google_calendar import GoogleCalendarAdapter
from app.adapters.notifier import NotificationAdapter
from app.config import Settings, get_settings
from app.database import Database
from app.schemas import (
    CheckinSaudeCreate,
    EventoCreate,
    GeminiConfigRequest,
    HabitoCreate,
    InboxRequest,
    InboxResponse,
    ModelSelectRequest,
    NotificacaoCreate,
    TarefaCreate,
    TransacaoCreate,
)
from app.services.agenda_service import AgendaService
from app.services.briefing_service import BriefingService
from app.services.financas_service import FinancasService
from app.services.notificacoes_service import NotificacoesService
from app.services.orchestrator import SynapseOrchestrator
from app.services.saude_service import SaudeService
from app.services.tarefas_service import TarefasService

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def create_app(db_path: str | None = None, settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    db = Database(db_path or app_settings.database_path)
    db.init_db()

    calendar_adapter = GoogleCalendarAdapter(app_settings)
    notifier_adapter = NotificationAdapter(app_settings)

    financas_service = FinancasService(db, settings=app_settings)
    tarefas_service = TarefasService(db)
    notificacoes_service = NotificacoesService(db, adapter=notifier_adapter, settings=app_settings)
    agenda_service = AgendaService(
        db,
        calendar_adapter=calendar_adapter,
        notificacoes_service=notificacoes_service,
        settings=app_settings,
    )
    saude_service = SaudeService(db, notificacoes_service=notificacoes_service, settings=app_settings)
    briefing_service = BriefingService(
        financas=financas_service,
        tarefas=tarefas_service,
        agenda=agenda_service,
        saude=saude_service,
        notificacoes=notificacoes_service,
        settings=app_settings,
    )
    orchestrator = SynapseOrchestrator(
        db=db,
        financas=financas_service,
        tarefas=tarefas_service,
        agenda=agenda_service,
        saude=saude_service,
        notificacoes=notificacoes_service,
        briefing=briefing_service,
        settings=app_settings,
    )

    app = FastAPI(
        title="Synapse API",
        description="Orquestrador Pessoal Multi-Domínio com IA (Finanças, Tarefas, Agenda, Saúde e Notificações).",
        version="1.0.0",
    )

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "ia_ativa": bool(orchestrator.obter_chave_gemini()),
            "modelo_ia": orchestrator.obter_modelo_gemini(),
            "google_calendar_ativo": app_settings.google_calendar_enabled,
            "timezone": app_settings.timezone_name,
        }

    @app.post("/api/v1/config/ia")
    def configurar_ia(payload: GeminiConfigRequest) -> dict[str, Any]:
        try:
            return orchestrator.configurar_gemini(api_key=payload.api_key, model=payload.model)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Não foi possível validar a chave: {exc}") from exc

    @app.get("/api/v1/config/ia/modelos")
    def listar_modelos_ia() -> dict[str, Any]:
        try:
            modelos = orchestrator.listar_modelos_disponiveis()
            return {"modelos": modelos, "modelo_atual": orchestrator.obter_modelo_gemini()}
        except Exception:
            return {"modelos": [], "modelo_atual": orchestrator.obter_modelo_gemini()}

    @app.patch("/api/v1/config/ia/modelo")
    def selecionar_modelo_ia(payload: ModelSelectRequest) -> dict[str, Any]:
        return orchestrator.atualizar_modelo_gemini(payload.model)

    @app.post("/api/v1/inbox", response_model=InboxResponse)
    def inbox(payload: InboxRequest) -> InboxResponse:
        return orchestrator.processar_mensagem(payload.mensagem, conversa_id=payload.conversa_id)

    @app.get("/api/v1/conversas")
    def listar_conversas() -> list[dict[str, Any]]:
        return orchestrator.listar_conversas()

    @app.post("/api/v1/conversas", status_code=201)
    def criar_conversa() -> dict[str, Any]:
        return orchestrator.criar_conversa()

    @app.get("/api/v1/conversas/{conversa_id}/mensagens")
    def listar_mensagens(conversa_id: int) -> list[dict[str, Any]]:
        return orchestrator.listar_mensagens_conversa(conversa_id)

    @app.delete("/api/v1/conversas/{conversa_id}")
    def excluir_conversa(conversa_id: int) -> dict[str, Any]:
        if not orchestrator.excluir_conversa(conversa_id):
            raise HTTPException(status_code=404, detail="Conversa não encontrada.")
        return {"excluida": True, "id": conversa_id}

    @app.get("/api/v1/briefing")
    def obter_briefing() -> dict[str, Any]:
        return briefing_service.gerar_briefing()

    # --- Finanças ---
    @app.get("/api/v1/financas/resumo")
    def resumo_financas(mes: str | None = None) -> dict[str, Any]:
        return financas_service.resumo_periodo(mes_prefixo=mes)

    @app.get("/api/v1/financas/transacoes")
    def listar_transacoes(limite: int = 20) -> list[dict[str, Any]]:
        return financas_service.listar_transacoes(limite=limite)

    @app.post("/api/v1/financas/transacoes", status_code=201)
    def criar_transacao(payload: TransacaoCreate) -> dict[str, Any]:
        return financas_service.registrar_transacao(payload)

    # --- Tarefas ---
    @app.get("/api/v1/tarefas")
    def listar_tarefas(status: str | None = "PENDENTE") -> list[dict[str, Any]]:
        return tarefas_service.listar_tarefas(status=status)

    @app.post("/api/v1/tarefas", status_code=201)
    def criar_tarefa(payload: TarefaCreate) -> dict[str, Any]:
        return tarefas_service.criar_tarefa(payload)

    @app.patch("/api/v1/tarefas/{tarefa_id}/concluir")
    def concluir_tarefa(tarefa_id: int) -> dict[str, Any]:
        atualizada = tarefas_service.concluir_tarefa(tarefa_id)
        if not atualizada:
            raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
        return atualizada

    # --- Agenda ---
    @app.get("/api/v1/agenda")
    def listar_agenda(data: str | None = None) -> list[dict[str, Any]]:
        return agenda_service.listar_eventos(data_filtro=data)

    @app.post("/api/v1/agenda", status_code=201)
    def criar_evento(payload: EventoCreate) -> dict[str, Any]:
        return agenda_service.agendar_evento(payload)

    # --- Saúde & Hábitos ---
    @app.get("/api/v1/saude/hoje")
    def saude_hoje(data: str | None = None) -> list[dict[str, Any]]:
        return saude_service.progresso_diario(data_iso=data)

    @app.post("/api/v1/saude/habitos", status_code=201)
    def configurar_habito(payload: HabitoCreate) -> dict[str, Any]:
        return saude_service.criar_ou_atualizar_habito(payload)

    @app.post("/api/v1/saude/checkins", status_code=201)
    def registrar_checkin(payload: CheckinSaudeCreate) -> dict[str, Any]:
        return saude_service.registrar_checkin(payload)

    # --- Notificações ---
    @app.get("/api/v1/notificacoes/pendentes")
    def listar_notificacoes(apenas_pendentes: bool = True) -> list[dict[str, Any]]:
        return notificacoes_service.listar_notificacoes(apenas_pendentes=apenas_pendentes)

    @app.post("/api/v1/notificacoes", status_code=201)
    def criar_notificacao(payload: NotificacaoCreate) -> dict[str, Any]:
        return notificacoes_service.agendar_notificacao(payload)

    @app.post("/api/v1/notificacoes/disparar")
    def disparar_notificacoes() -> dict[str, Any]:
        disparadas = notificacoes_service.disparar_vencidas()
        return {"total_disparadas": len(disparadas), "itens": disparadas}

    @app.patch("/api/v1/notificacoes/{notificacao_id}/lida")
    def marcar_notificacao_lida(notificacao_id: int) -> dict[str, Any]:
        atualizada = notificacoes_service.marcar_como_lida(notificacao_id)
        if not atualizada:
            raise HTTPException(status_code=404, detail="Notificação não encontrada.")
        return atualizada

    # --- Frontend estático + PWA ---
    if FRONTEND_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

        @app.get("/", include_in_schema=False)
        def serve_index() -> FileResponse:
            return FileResponse(FRONTEND_DIR / "index.html")

        @app.get("/manifest.webmanifest", include_in_schema=False)
        def serve_manifest() -> FileResponse:
            return FileResponse(
                FRONTEND_DIR / "manifest.webmanifest",
                media_type="application/manifest+json",
            )

        @app.get("/sw.js", include_in_schema=False)
        def serve_sw() -> FileResponse:
            return FileResponse(
                FRONTEND_DIR / "sw.js",
                media_type="application/javascript",
            )

    return app


app = create_app()
