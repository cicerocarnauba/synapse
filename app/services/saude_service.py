"""Serviço do módulo Saúde & Hábitos (RF05): metas personalizáveis, check-ins e histórico."""

from __future__ import annotations

from datetime import timedelta
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

    def excluir_habito(self, habito_id: int) -> bool:
        with self.db.connect() as conn:
            cursor = conn.execute("DELETE FROM habitos_saude WHERE id = ?", (habito_id,))
            return cursor.rowcount > 0

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
                INSERT INTO checkins_saude (habito_id, quantidade, observacao, conversa_id, registrado_em)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    habito_escolhido["id"],
                    payload.quantidade,
                    payload.observacao.strip(),
                    payload.conversa_id,
                    agora_iso,
                ),
            )
            checkin = conn.execute("SELECT * FROM checkins_saude WHERE id = ?", (cursor.lastrowid,)).fetchone()

        progresso_hoje = self.progresso_diario()
        atual = next((p for p in progresso_hoje if p["id"] == habito_escolhido["id"]), None)
        return {
            "checkin": dict(checkin),
            "habito": habito_escolhido["nome"],
            "progresso_atual": atual,
        }

    def listar_checkins_dia(self, data_iso: str | None = None) -> list[dict[str, Any]]:
        dia = data_iso or self.settings.now_local().date().isoformat()
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    c.id,
                    c.habito_id,
                    h.nome AS habito_nome,
                    h.unidade,
                    c.quantidade,
                    c.observacao,
                    c.conversa_id,
                    c.registrado_em
                FROM checkins_saude c
                JOIN habitos_saude h ON h.id = c.habito_id
                WHERE c.registrado_em LIKE ?
                ORDER BY c.id DESC
                LIMIT 30
                """,
                (f"{dia}%",),
            ).fetchall()
            return [dict(r) for r in rows]

    def excluir_checkin(self, checkin_id: int) -> bool:
        with self.db.connect() as conn:
            cursor = conn.execute("DELETE FROM checkins_saude WHERE id = ?", (checkin_id,))
            return cursor.rowcount > 0

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

    def resumo_semanal(self) -> dict[str, Any]:
        """Calcula score de hoje e consistência dos últimos 7 dias via SQL."""
        hoje_dt = self.settings.now_local().date()
        hoje_iso = hoje_dt.isoformat()
        progresso_hoje = self.progresso_diario(data_iso=hoje_iso)

        total_habitos = len(progresso_hoje)
        metas_batidas = sum(1 for h in progresso_hoje if h["concluido"])
        score_hoje = (
            round(sum(h["percentual"] for h in progresso_hoje) / total_habitos)
            if total_habitos > 0
            else 0
        )

        dias_7: list[dict[str, Any]] = []
        letras_semana = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        with self.db.connect() as conn:
            for offset in range(6, -1, -1):
                d = hoje_dt - timedelta(days=offset)
                d_iso = d.isoformat()
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS qtd_checkins, COUNT(DISTINCT habito_id) AS habitos_ativos
                    FROM checkins_saude
                    WHERE registrado_em LIKE ?
                    """,
                    (f"{d_iso}%",),
                ).fetchone()
                dias_7.append(
                    {
                        "data": d_iso,
                        "label": letras_semana[d.weekday()],
                        "eh_hoje": offset == 0,
                        "qtd_checkins": int(row["qtd_checkins"]),
                        "habitos_ativos": int(row["habitos_ativos"]),
                    }
                )

        # Calcula sequência atual (dias consecutivos com pelo menos 1 check-in)
        streak = 0
        for item in reversed(dias_7):
            if item["qtd_checkins"] > 0:
                streak += 1
            elif not item["eh_hoje"]:
                break

        return {
            "score_hoje": score_hoje,
            "metas_batidas": metas_batidas,
            "total_habitos": total_habitos,
            "streak_dias": streak,
            "ultimos_7_dias": dias_7,
        }
