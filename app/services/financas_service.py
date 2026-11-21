"""Serviço do módulo Finanças (RF02): transações, categorias personalizáveis e analytics SQL."""

from __future__ import annotations

import unicodedata
from typing import Any

from app.config import Settings, get_settings
from app.database import Database
from app.schemas import CategoriaFinanceiraCreate, TransacaoCreate, TransacaoUpdate


def _normalizar_categoria(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    limpo = "_".join(sem_acento.strip().upper().split())
    return limpo[:40] or "OUTROS"


class FinancasService:
    def __init__(self, db: Database, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    # --- Categorias personalizáveis ---
    def listar_categorias(self) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM categorias_financeiras ORDER BY padrao DESC, nome ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    def criar_categoria(self, payload: CategoriaFinanceiraCreate) -> dict[str, Any]:
        nome_norm = _normalizar_categoria(payload.nome)
        with self.db.connect() as conn:
            existente = conn.execute(
                "SELECT * FROM categorias_financeiras WHERE nome = ?", (nome_norm,)
            ).fetchone()
            if existente:
                conn.execute(
                    "UPDATE categorias_financeiras SET cor = ? WHERE id = ?",
                    (payload.cor.strip(), existente["id"]),
                )
                row = conn.execute(
                    "SELECT * FROM categorias_financeiras WHERE id = ?", (existente["id"],)
                ).fetchone()
                return dict(row)

            cursor = conn.execute(
                "INSERT INTO categorias_financeiras (nome, cor, padrao) VALUES (?, ?, 0)",
                (nome_norm, payload.cor.strip()),
            )
            row = conn.execute(
                "SELECT * FROM categorias_financeiras WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            return dict(row)

    def excluir_categoria(self, categoria_id: int) -> bool:
        with self.db.connect() as conn:
            cat = conn.execute(
                "SELECT * FROM categorias_financeiras WHERE id = ?", (categoria_id,)
            ).fetchone()
            if not cat or cat["padrao"]:
                return False
            conn.execute(
                "UPDATE transacoes SET categoria = 'OUTROS' WHERE categoria = ?",
                (cat["nome"],),
            )
            cursor = conn.execute(
                "DELETE FROM categorias_financeiras WHERE id = ?", (categoria_id,)
            )
            return cursor.rowcount > 0

    # --- Transações ---
    def registrar_transacao(self, payload: TransacaoCreate) -> dict[str, Any]:
        data_efetiva = payload.data_transacao or self.settings.now_local().date().isoformat()
        categoria_norm = _normalizar_categoria(payload.categoria)
        with self.db.connect() as conn:
            # Garante que a categoria exista no catálogo
            conn.execute(
                "INSERT OR IGNORE INTO categorias_financeiras (nome, cor, padrao) VALUES (?, '#615d59', 0)",
                (categoria_norm,),
            )
            cursor = conn.execute(
                """
                INSERT INTO transacoes (tipo, valor, categoria, descricao, data_transacao, conversa_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.tipo.value,
                    round(payload.valor, 2),
                    categoria_norm,
                    payload.descricao.strip(),
                    data_efetiva,
                    payload.conversa_id,
                ),
            )
            row = conn.execute("SELECT * FROM transacoes WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return dict(row)

    def atualizar_transacao(self, transacao_id: int, payload: TransacaoUpdate) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            atual = conn.execute("SELECT * FROM transacoes WHERE id = ?", (transacao_id,)).fetchone()
            if not atual:
                return None

            novo_tipo = payload.tipo.value if payload.tipo is not None else atual["tipo"]
            novo_valor = round(payload.valor, 2) if payload.valor is not None else atual["valor"]
            nova_cat = (
                _normalizar_categoria(payload.categoria)
                if payload.categoria is not None
                else atual["categoria"]
            )
            nova_desc = payload.descricao.strip() if payload.descricao is not None else atual["descricao"]
            nova_data = payload.data_transacao or atual["data_transacao"]

            conn.execute(
                "INSERT OR IGNORE INTO categorias_financeiras (nome, cor, padrao) VALUES (?, '#615d59', 0)",
                (nova_cat,),
            )
            conn.execute(
                """
                UPDATE transacoes
                SET tipo = ?, valor = ?, categoria = ?, descricao = ?, data_transacao = ?
                WHERE id = ?
                """,
                (novo_tipo, novo_valor, nova_cat, nova_desc, nova_data, transacao_id),
            )
            row = conn.execute("SELECT * FROM transacoes WHERE id = ?", (transacao_id,)).fetchone()
            return dict(row)

    def excluir_transacao(self, transacao_id: int) -> bool:
        with self.db.connect() as conn:
            cursor = conn.execute("DELETE FROM transacoes WHERE id = ?", (transacao_id,))
            return cursor.rowcount > 0

    def listar_transacoes(
        self,
        limite: int = 40,
        mes_prefixo: str | None = None,
        tipo: str | None = None,
        categoria: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if mes_prefixo:
            clauses.append("t.data_transacao LIKE ?")
            params.append(f"{mes_prefixo}%")
        if tipo and tipo.upper() in ("DESPESA", "RECEITA"):
            clauses.append("t.tipo = ?")
            params.append(tipo.upper())
        if categoria:
            clauses.append("t.categoria = ?")
            params.append(_normalizar_categoria(categoria))

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limite)

        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT t.*, COALESCE(c.cor, '#615d59') AS categoria_cor
                FROM transacoes t
                LEFT JOIN categorias_financeiras c ON c.nome = t.categoria
                {where}
                ORDER BY t.data_transacao DESC, t.id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
            return [dict(r) for r in rows]

    def resumo_periodo(self, mes_prefixo: str | None = None) -> dict[str, Any]:
        """Agrega receitas, despesas, saldo e totais por categoria com percentual e cor."""
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
                SELECT
                    t.categoria,
                    COALESCE(c.cor, '#615d59') AS cor,
                    ROUND(SUM(t.valor), 2) AS total,
                    COUNT(*) AS quantidade
                FROM transacoes t
                LEFT JOIN categorias_financeiras c ON c.nome = t.categoria
                WHERE t.tipo = 'DESPESA' AND t.data_transacao LIKE ?
                GROUP BY t.categoria
                ORDER BY total DESC
                """,
                (like_filter,),
            ).fetchall()

            total_receitas = round(float(totais["total_receitas"]), 2)
            total_despesas = round(float(totais["total_despesas"]), 2)
            cats_fmt = []
            for c in categorias:
                item = dict(c)
                item["percentual"] = (
                    round((float(item["total"]) / total_despesas) * 100) if total_despesas > 0 else 0
                )
                cats_fmt.append(item)

            return {
                "periodo": prefixo,
                "total_receitas": total_receitas,
                "total_despesas": total_despesas,
                "saldo": round(total_receitas - total_despesas, 2),
                "quantidade_lancamentos": int(totais["quantidade_lancamentos"]),
                "despesas_por_categoria": cats_fmt,
            }
