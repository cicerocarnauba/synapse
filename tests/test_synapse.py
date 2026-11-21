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


def test_historico_conversas_por_dia_e_nova_conversa(tmp_path: Path) -> None:
    client = _make_client(tmp_path)

    r1 = client.post("/api/v1/inbox", json={"mensagem": "Bebi 500ml de água"}).json()
    cid = r1["conversa_id"]
    assert cid > 0

    r2 = client.post(
        "/api/v1/inbox",
        json={"mensagem": "Gastei 20 no café", "conversa_id": cid},
    ).json()
    assert r2["conversa_id"] == cid

    conversas = client.get("/api/v1/conversas").json()
    assert len(conversas) == 1
    assert conversas[0]["total_mensagens"] == 2
    assert "data_dia" in conversas[0]

    mensagens = client.get(f"/api/v1/conversas/{cid}/mensagens").json()
    assert len(mensagens) == 2
    assert mensagens[0]["mensagem_usuario"] == "Bebi 500ml de água"

    del_resp = client.delete(f"/api/v1/conversas/{cid}")
    assert del_resp.status_code == 200
    assert client.get("/api/v1/conversas").json() == []


def test_saudacao_nao_cria_tarefa_nem_suja_banco(tmp_path: Path) -> None:
    client = _make_client(tmp_path)

    resp = client.post("/api/v1/inbox", json={"mensagem": "Oi"}).json()
    assert resp["acoes"] == []
    assert "Oi!" in resp["resposta"]
    assert client.get("/api/v1/tarefas").json() == []


def test_financas_categorias_personalizadas_edicao_exclusao_e_origem_chat(tmp_path: Path) -> None:
    client = _make_client(tmp_path)

    # Cria categoria customizada
    cat = client.post("/api/v1/financas/categorias", json={"nome": "Academia", "cor": "#2a9d99"})
    assert cat.status_code == 201
    assert cat.json()["nome"] == "ACADEMIA"

    # Registra gasto pelo chat e valida vínculo com conversa_id
    inbox = client.post("/api/v1/inbox", json={"mensagem": "Gastei 89,90 na academia"}).json()
    cid = inbox["conversa_id"]
    txs = client.get("/api/v1/financas/transacoes").json()
    assert len(txs) == 1
    assert txs[0]["conversa_id"] == cid

    # Edita manualmente o lançamento (valor e categoria)
    tx_id = txs[0]["id"]
    upd = client.patch(
        f"/api/v1/financas/transacoes/{tx_id}",
        json={"valor": 99.9, "categoria": "ACADEMIA", "descricao": "Mensalidade Academia"},
    )
    assert upd.status_code == 200
    assert upd.json()["valor"] == 99.9
    assert upd.json()["categoria"] == "ACADEMIA"

    # Exclui o lançamento
    assert client.delete(f"/api/v1/financas/transacoes/{tx_id}").status_code == 200
    assert client.get("/api/v1/financas/transacoes").json() == []


def test_crud_agenda_tarefas_e_checkins_saude_com_rastreabilidade(tmp_path: Path) -> None:
    client = _make_client(tmp_path)

    # 1. Tarefa via chat -> editar -> excluir
    r_task = client.post("/api/v1/inbox", json={"mensagem": "Me lembra de revisar SQL hoje"}).json()
    tasks = client.get("/api/v1/tarefas").json()
    assert tasks[0]["conversa_id"] == r_task["conversa_id"]
    tid = tasks[0]["id"]
    upd_t = client.patch(f"/api/v1/tarefas/{tid}", json={"titulo": "Revisar SQL Avançado", "prioridade": "BAIXA"})
    assert upd_t.status_code == 200
    assert upd_t.json()["titulo"] == "Revisar SQL Avançado"
    assert client.delete(f"/api/v1/tarefas/{tid}").status_code == 200

    # 2. Evento via chat -> editar -> excluir
    r_ev = client.post("/api/v1/inbox", json={"mensagem": "Marca revisão amanhã às 15h"}).json()
    evs = client.get("/api/v1/agenda").json()
    assert evs[0]["conversa_id"] == r_ev["conversa_id"]
    eid = evs[0]["id"]
    upd_e = client.patch(f"/api/v1/agenda/{eid}", json={"titulo": "Revisão Final"})
    assert upd_e.status_code == 200
    assert upd_e.json()["titulo"] == "Revisão Final"
    assert client.delete(f"/api/v1/agenda/{eid}").status_code == 200

    # 3. Check-in saúde via chat -> listar -> desfazer
    r_s = client.post("/api/v1/inbox", json={"mensagem": "Bebi 300ml de água"}).json()
    checkins = client.get("/api/v1/saude/checkins").json()
    assert len(checkins) == 1
    assert checkins[0]["conversa_id"] == r_s["conversa_id"]
    assert client.delete(f"/api/v1/saude/checkins/{checkins[0]['id']}").status_code == 200
    assert client.get("/api/v1/saude/checkins").json() == []




