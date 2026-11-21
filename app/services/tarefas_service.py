"""Serviço do módulo Tarefas Rápidas (RF03): CRUD completo + rastreabilidade de conversa."""

from __future__ import annotations

from typing import Any

from app.database import Database
from app.schemas import TarefaCreate, TarefaUpdate


class TarefasService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def criar_tarefa(self, payload: TarefaCreate) -> dict[str, Any]:
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO tarefas (titulo, prioridade, status, prazo, conversa_id)
                VALUES (?, ?, 'PENDENTE', ?, ?)
                """,
                (payload.titulo.strip(), payload.prioridade.value, payload.prazo, payload.conversa_id),
            )
            row = conn.execute("SELECT * FROM tarefas WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return dict(row)

    def listar_tarefas(self, status: str | None = "PENDENTE") -> list[dict[str, Any]]:
        query = """
            SELECT * FROM tarefas
            {where_clause}
            ORDER BY
                CASE prioridade WHEN 'ALTA' THEN 1 WHEN 'MEDIA' THEN 2 ELSE 3 END,
                COALESCE(prazo, '9999-12-31') ASC,
                id DESC
        """
        params: tuple[Any, ...] = ()
        where_clause = ""
        if status and status.upper() != "TODAS":
            where_clause = "WHERE status = ?"
            params = (status.upper(),)

        with self.db.connect() as conn:
            rows = conn.execute(query.format(where_clause=where_clause), params).fetchall()
            return [dict(r) for r in rows]

    def atualizar_tarefa(self, tarefa_id: int, payload: TarefaUpdate) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            atual = conn.execute("SELECT * FROM tarefas WHERE id = ?", (tarefa_id,)).fetchone()
            if not atual:
                return None

            novo_titulo = payload.titulo.strip() if payload.titulo is not None else atual["titulo"]
            nova_prio = payload.prioridade.value if payload.prioridade is not None else atual["prioridade"]
            novo_status = payload.status.value if payload.status is not None else atual["status"]
            novo_prazo = payload.prazo if payload.prazo is not None else atual["prazo"]
            if novo_prazo == "":
                novo_prazo = None

            conn.execute(
                """
                UPDATE tarefas
                SET titulo = ?, prioridade = ?, status = ?, prazo = ?
                WHERE id = ?
                """,
                (novo_titulo, nova_prio, novo_status, novo_prazo, tarefa_id),
            )
            row = conn.execute("SELECT * FROM tarefas WHERE id = ?", (tarefa_id,)).fetchone()
            return dict(row)

    def concluir_tarefa(self, tarefa_id: int) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            cursor = conn.execute(
                "UPDATE tarefas SET status = 'CONCLUIDA' WHERE id = ?",
                (tarefa_id,),
            )
            if cursor.rowcount == 0:
                return None
            row = conn.execute("SELECT * FROM tarefas WHERE id = ?", (tarefa_id,)).fetchone()
            return dict(row)

    def excluir_tarefa(self, tarefa_id: int) -> bool:
        with self.db.connect() as conn:
            cursor = conn.execute("DELETE FROM tarefas WHERE id = ?", (tarefa_id,))
            return cursor.rowcount > 0
