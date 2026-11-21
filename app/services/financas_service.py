"""Serviço do módulo Finanças (RF02): registro e analytics SQL."""

from __future__ import annotations

from typing import Any

from app.config import Settings, get_settings
from app.database import Database
from app.schemas import TransacaoCreate


class FinancasService:
    def __init__(self, db: Database, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def registrar_transacao(self, payload: TransacaoCreate) -> dict[str, Any]:
        data_efetiva = payload.data_transacao or self.settings.now_local().date().isoformat()
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO transacoes (tipo, valor, categoria, descricao, data_transacao)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    payload.tipo.value,
                    round(payload.valor, 2),
                    payload.categoria.value,
                    payload.descricao.strip(),
                    data_efetiva,
                ),
            )
            row = conn.execute("SELECT * FROM transacoes WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return dict(row)

    def listar_transacoes(self, limite: int = 20) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM transacoes
                ORDER BY data_transacao DESC, id DESC
                LIMIT ?
                """,
                (limite,),
            ).fetchall()
            return [dict(r) for r in rows]

    def resumo_periodo(self, mes_prefixo: str | None = None) -> dict[str, Any]:
        """Agrega receitas, despesas, saldo e totais por categoria via SQL."""
        prefixo = mes_prefixo or self.settings.now_local().strftime("%Y-%m")
        like_filter = f"{prefixo}%"
        with self.db.connect() as conn:
            totais = conn.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN tipo = 'RECEITA' THEN valor ELSE 0 END), 0) AS total_receitas,
                    COALESCE(SUM(CASE WHEN tipo = 'DESPESA' THEN valor ELSE 0 END), 0) AS total_despesas,
                    COUNT(*) AS quantidade_lancamentos
                FROM transacoes
                WHERE data_transacao LIKE ?
                """,
                (like_filter,),
            ).fetchone()

            categorias = conn.execute(
                """
                SELECT categoria, ROUND(SUM(valor), 2) AS total, COUNT(*) AS quantidade
                FROM transacoes
                WHERE tipo = 'DESPESA' AND data_transacao LIKE ?
                GROUP BY categoria
                ORDER BY total DESC
                """,
                (like_filter,),
            ).fetchall()

            total_receitas = round(float(totais["total_receitas"]), 2)
            total_despesas = round(float(totais["total_despesas"]), 2)
            return {
                "periodo": prefixo,
                "total_receitas": total_receitas,
                "total_despesas": total_despesas,
                "saldo": round(total_receitas - total_despesas, 2),
                "quantidade_lancamentos": int(totais["quantidade_lancamentos"]),
                "despesas_por_categoria": [dict(c) for c in categorias],
            }
