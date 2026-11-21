"""Serviço do módulo Tarefas Rápidas (RF03)."""

from __future__ import annotations

from typing import Any

from app.database import Database
from app.schemas import TarefaCreate


class TarefasService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def criar_tarefa(self, payload: TarefaCreate) -> dict[str, Any]:
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO tarefas (titulo, prioridade, status, prazo)
                VALUES (?, ?, 'PENDENTE', ?)
                """,
                (payload.titulo.strip(), payload.prioridade.value, payload.prazo),
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
