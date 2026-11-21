"""Serviço do módulo Saúde & Hábitos (RF05): água, treino, refeições."""

from __future__ import annotations

import unicodedata
from typing import Any

from app.config import Settings, get_settings
from app.database import Database
from app.schemas import CheckinSaudeCreate, HabitoCreate, NotificacaoCreate, OrigemNotificacao
from app.services.notificacoes_service import NotificacoesService


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sem_acento.strip().lower()


class SaudeService:
    def __init__(
        self,
        db: Database,
        notificacoes_service: NotificacoesService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.notificacoes_service = notificacoes_service or NotificacoesService(db, settings=self.settings)

    def criar_ou_atualizar_habito(self, payload: HabitoCreate) -> dict[str, Any]:
        with self.db.connect() as conn:
            existente = conn.execute(
                "SELECT * FROM habitos_saude WHERE LOWER(nome) = LOWER(?)",
                (payload.nome.strip(),),
            ).fetchone()
            if existente:
                conn.execute(
                    """
                    UPDATE habitos_saude
                    SET meta_diaria = ?, unidade = ?, horario_lembrete = ?, ativo = 1
                    WHERE id = ?
                    """,
                    (payload.meta_diaria, payload.unidade.strip(), payload.horario_lembrete, existente["id"]),
                )
                habito_id = existente["id"]
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO habitos_saude (nome, meta_diaria, unidade, horario_lembrete, ativo)
                    VALUES (?, ?, ?, ?, 1)
                    """,
                    (payload.nome.strip(), payload.meta_diaria, payload.unidade.strip(), payload.horario_lembrete),
                )
                habito_id = cursor.lastrowid
            row = conn.execute("SELECT * FROM habitos_saude WHERE id = ?", (habito_id,)).fetchone()
            habito = dict(row)

        if payload.horario_lembrete:
            hoje = self.settings.now_local().date().isoformat()
            self.notificacoes_service.agendar_notificacao(
                NotificacaoCreate(
                    origem=OrigemNotificacao.SAUDE,
                    titulo=f"Lembrete de Saúde: {habito['nome']}",
                    mensagem=f"Hora do seu hábito '{habito['nome']}' (meta diária: {habito['meta_diaria']} {habito['unidade']}).",
                    agendado_para=f"{hoje}T{payload.horario_lembrete}:00",
                )
            )
        return habito

    def registrar_checkin(self, payload: CheckinSaudeCreate) -> dict[str, Any]:
        alvo = _normalizar(payload.nome_habito)
        agora_iso = self.settings.now_local().isoformat(timespec="seconds")

        with self.db.connect() as conn:
            habitos = conn.execute("SELECT * FROM habitos_saude WHERE ativo = 1").fetchall()
            habito_escolhido = None
            for h in habitos:
                if _normalizar(h["nome"]) == alvo or alvo in _normalizar(h["nome"]):
                    habito_escolhido = h
                    break

            if not habito_escolhido:
                cursor = conn.execute(
                    """
                    INSERT INTO habitos_saude (nome, meta_diaria, unidade, horario_lembrete, ativo)
                    VALUES (?, ?, 'unidade', NULL, 1)
                    """,
                    (payload.nome_habito.strip().capitalize(), max(1.0, payload.quantidade)),
                )
                habito_escolhido = conn.execute(
                    "SELECT * FROM habitos_saude WHERE id = ?", (cursor.lastrowid,)
                ).fetchone()

            cursor = conn.execute(
                """
                INSERT INTO checkins_saude (habito_id, quantidade, observacao, registrado_em)
                VALUES (?, ?, ?, ?)
                """,
                (habito_escolhido["id"], payload.quantidade, payload.observacao.strip(), agora_iso),
            )
            checkin = conn.execute("SELECT * FROM checkins_saude WHERE id = ?", (cursor.lastrowid,)).fetchone()

        progresso_hoje = self.progresso_diario()
        atual = next((p for p in progresso_hoje if p["id"] == habito_escolhido["id"]), None)
        return {
            "checkin": dict(checkin),
            "habito": habito_escolhido["nome"],
            "progresso_atual": atual,
        }

    def progresso_diario(self, data_iso: str | None = None) -> list[dict[str, Any]]:
        dia = data_iso or self.settings.now_local().date().isoformat()
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    h.id,
                    h.nome,
                    h.meta_diaria,
                    h.unidade,
                    h.horario_lembrete,
                    COALESCE(SUM(c.quantidade), 0) AS total_hoje
                FROM habitos_saude h
                LEFT JOIN checkins_saude c
                    ON c.habito_id = h.id AND c.registrado_em LIKE ?
                WHERE h.ativo = 1
                GROUP BY h.id
                ORDER BY h.id ASC
                """,
                (f"{dia}%",),
            ).fetchall()

            resultado: list[dict[str, Any]] = []
            for r in rows:
                total = round(float(r["total_hoje"]), 2)
                meta = float(r["meta_diaria"])
                percentual = min(100, round((total / meta) * 100)) if meta > 0 else 0
                resultado.append(
                    {
                        "id": r["id"],
                        "nome": r["nome"],
                        "total_hoje": total,
                        "meta_diaria": meta,
                        "unidade": r["unidade"],
                        "horario_lembrete": r["horario_lembrete"],
                        "percentual": percentual,
                        "concluido": total >= meta,
                    }
                )
            return resultado
