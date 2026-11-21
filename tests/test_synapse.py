"""Testes automatizados do Synapse (RNF05 — determinísticos e offline)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _make_client(tmp_path: Path) -> TestClient:
    db_file = str(tmp_path / "test_synapse.db")
    settings = Settings(
        gemini_api_key="",
        gemini_model="gemini-2.5-flash",
        database_path=db_file,
        timezone_name="America/Fortaleza",
        google_calendar_enabled=False,
        google_calendar_id="primary",
        google_calendar_access_token="",
        notification_webhook_url="",
    )
    app = create_app(db_path=db_file, settings=settings)
    return TestClient(app)


def test_inbox_multidominio_em_uma_unica_mensagem(tmp_path: Path) -> None:
    """Uma mensagem combinando Finanças + Saúde + Agenda deve acionar os 3 módulos."""
    client = _make_client(tmp_path)

    resp = client.post(
        "/api/v1/inbox",
        json={"mensagem": "Gastei 42,50 no almoço, bebi 500ml de água e marca revisão amanhã às 19h"},
    )
    assert resp.status_code == 200
    body = resp.json()

    modulos = {a["modulo"] for a in body["acoes"]}
    assert "FINANCAS" in modulos
    assert "SAUDE" in modulos
    assert "AGENDA" in modulos
    assert body["latencia_ms"] >= 0

    briefing = client.get("/api/v1/briefing").json()
    assert briefing["resumo_financeiro"]["total_despesas"] == 42.5
    assert briefing["resumo_financeiro"]["despesas_por_categoria"][0]["categoria"] == "ALIMENTACAO"

    agua = next(h for h in briefing["saude_hoje"] if h["nome"] == "Agua")
    assert agua["total_hoje"] == 500.0
    assert agua["percentual"] == 20

    assert len(briefing["proximos_eventos"]) == 1
    assert briefing["proximos_eventos"][0]["sync_status"] == "PENDENTE"
    # RN04: criar evento agenda automaticamente uma notificação de lembrete
    assert len(briefing["notificacoes_pendentes"]) >= 1


def test_ciclo_tarefas_e_conclusao(tmp_path: Path) -> None:
    client = _make_client(tmp_path)

    resp = client.post(
        "/api/v1/inbox",
        json={"mensagem": "Me lembra de enviar o currículo para a Blip hoje"},
    )
    assert resp.status_code == 200
    assert resp.json()["acoes"][0]["modulo"] == "TAREFAS"

    pendentes = client.get("/api/v1/tarefas").json()
    assert len(pendentes) == 1
    assert pendentes[0]["prioridade"] == "ALTA"

    tarefa_id = pendentes[0]["id"]
    concluida = client.patch(f"/api/v1/tarefas/{tarefa_id}/concluir").json()
    assert concluida["status"] == "CONCLUIDA"
    assert client.get("/api/v1/tarefas").json() == []


def test_saude_metas_e_notificacoes_disparo(tmp_path: Path) -> None:
    client = _make_client(tmp_path)

    # Configura hábito de treino com lembrete
    hab = client.post(
        "/api/v1/saude/habitos",
        json={"nome": "Treino", "meta_diaria": 1, "unidade": "sessao", "horario_lembrete": "18:00"},
    )
    assert hab.status_code == 201

    # Registra check-in via inbox
    resp = client.post("/api/v1/inbox", json={"mensagem": "Fiz o treino hoje e almocei!"})
    assert resp.status_code == 200
    saude = client.get("/api/v1/saude/hoje").json()
    treino = next(h for h in saude if h["nome"] == "Treino")
    almoco = next(h for h in saude if h["nome"] == "Almoco")
    assert treino["concluido"] is True
    assert almoco["concluido"] is True

    # Cria notificação já vencida e testa disparo
    notif = client.post(
        "/api/v1/notificacoes",
        json={
            "origem": "SAUDE",
            "titulo": "Beber água",
            "mensagem": "Hora de beber 300ml de água",
            "agendado_para": "2020-01-01T10:00:00",
        },
    )
    assert notif.status_code == 201
    disparo = client.post("/api/v1/notificacoes/disparar").json()
    assert disparo["total_disparadas"] >= 1
    assert disparo["itens"][0]["status"] == "ENVIADA"


def test_validacao_pydantic_rejeita_valor_negativo(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/v1/financas/transacoes",
        json={"tipo": "DESPESA", "valor": -10, "categoria": "OUTROS", "descricao": "Inválido"},
    )
    assert resp.status_code == 422
