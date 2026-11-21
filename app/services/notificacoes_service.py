"""Serviço do módulo Notificações & Lembretes (RF06)."""

from __future__ import annotations

from typing import Any

from app.adapters.notifier import NotificationAdapter
from app.config import Settings, get_settings
from app.database import Database
from app.schemas import NotificacaoCreate


class NotificacoesService:
    def __init__(
        self,
        db: Database,
        adapter: NotificationAdapter | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.adapter = adapter or NotificationAdapter(self.settings)

    def agendar_notificacao(self, payload: NotificacaoCreate) -> dict[str, Any]:
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO notificacoes (origem, titulo, mensagem, agendado_para, status, canal)
                VALUES (?, ?, ?, ?, 'PENDENTE', ?)
                """,
                (
                    payload.origem.value,
                    payload.titulo.strip(),
                    payload.mensagem.strip(),
                    payload.agendado_para,
                    payload.canal,
                ),
            )
            row = conn.execute("SELECT * FROM notificacoes WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return dict(row)

    def listar_notificacoes(self, apenas_pendentes: bool = True) -> list[dict[str, Any]]:
        where = "WHERE status IN ('PENDENTE', 'ENVIADA')" if apenas_pendentes else ""
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM notificacoes
                {where}
                ORDER BY agendado_para ASC, id DESC
                LIMIT 30
                """
            ).fetchall()
            return [dict(r) for r in rows]

    def marcar_como_lida(self, notificacao_id: int) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            cursor = conn.execute(
                "UPDATE notificacoes SET status = 'LIDA' WHERE id = ?",
                (notificacao_id,),
            )
            if cursor.rowcount == 0:
                return None
            row = conn.execute("SELECT * FROM notificacoes WHERE id = ?", (notificacao_id,)).fetchone()
            return dict(row)

    def disparar_vencidas(self, referencia_iso: str | None = None) -> list[dict[str, Any]]:
        """Processa e dispara notificações cuja hora agendada já chegou."""
        agora_iso = referencia_iso or self.settings.now_local().isoformat(timespec="seconds")
        resultados: list[dict[str, Any]] = []
        with self.db.connect() as conn:
            pendentes = conn.execute(
                """
                SELECT * FROM notificacoes
                WHERE status = 'PENDENTE' AND agendado_para <= ?
                ORDER BY agendado_para ASC
                """,
                (agora_iso,),
            ).fetchall()

            for item in pendentes:
                entrega = self.adapter.enviar(
                    titulo=item["titulo"],
                    mensagem=item["mensagem"],
                    origem=item["origem"],
                )
                novo_status = "ENVIADA" if entrega.sucesso else "PENDENTE"
                conn.execute(
                    "UPDATE notificacoes SET status = ?, canal = ? WHERE id = ?",
                    (novo_status, entrega.canal, item["id"]),
                )
                resultados.append(
                    {
                        "id": item["id"],
                        "titulo": item["titulo"],
                        "origem": item["origem"],
                        "status": novo_status,
                        "canal": entrega.canal,
                        "detalhe": entrega.detalhe,
                    }
                )
        return resultados
