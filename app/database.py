"""Camada de persistência SQL (SQLite local, queries compatíveis com PostgreSQL)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from app.config import get_settings

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS transacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo VARCHAR(15) NOT NULL CHECK (tipo IN ('DESPESA', 'RECEITA')),
    valor REAL NOT NULL CHECK (valor > 0),
    categoria VARCHAR(30) NOT NULL,
    descricao VARCHAR(200) NOT NULL,
    data_transacao DATE NOT NULL,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tarefas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo VARCHAR(200) NOT NULL,
    prioridade VARCHAR(10) NOT NULL DEFAULT 'MEDIA' CHECK (prioridade IN ('BAIXA', 'MEDIA', 'ALTA')),
    status VARCHAR(15) NOT NULL DEFAULT 'PENDENTE' CHECK (status IN ('PENDENTE', 'CONCLUIDA')),
    prazo TIMESTAMP NULL,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS eventos_agenda (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo VARCHAR(200) NOT NULL,
    descricao TEXT NOT NULL DEFAULT '',
    inicio TIMESTAMP NOT NULL,
    fim TIMESTAMP NOT NULL,
    google_event_id VARCHAR(120) NULL,
    sync_status VARCHAR(20) NOT NULL DEFAULT 'PENDENTE'
        CHECK (sync_status IN ('SINCRONIZADO', 'PENDENTE', 'LOCAL_ONLY')),
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS habitos_saude (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome VARCHAR(80) NOT NULL UNIQUE,
    meta_diaria REAL NOT NULL CHECK (meta_diaria > 0),
    unidade VARCHAR(20) NOT NULL,
    horario_lembrete VARCHAR(10) NULL,
    ativo BOOLEAN NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS checkins_saude (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    habito_id INTEGER NOT NULL REFERENCES habitos_saude(id) ON DELETE CASCADE,
    quantidade REAL NOT NULL CHECK (quantidade > 0),
    observacao VARCHAR(200) NOT NULL DEFAULT '',
    registrado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notificacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origem VARCHAR(20) NOT NULL CHECK (origem IN ('AGENDA', 'TAREFA', 'SAUDE', 'MANUAL')),
    titulo VARCHAR(150) NOT NULL,
    mensagem TEXT NOT NULL,
    agendado_para TIMESTAMP NOT NULL,
    status VARCHAR(15) NOT NULL DEFAULT 'PENDENTE'
        CHECK (status IN ('PENDENTE', 'ENVIADA', 'LIDA')),
    canal VARCHAR(20) NOT NULL DEFAULT 'IN_APP'
        CHECK (canal IN ('IN_APP', 'WEBHOOK')),
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS historico_interacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mensagem_usuario TEXT NOT NULL,
    acoes_executadas_json TEXT NOT NULL,
    resposta_assistente TEXT NOT NULL,
    latencia_ms INTEGER NOT NULL,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

DEFAULT_HABITS = [
    ("Agua", 2500.0, "ml", "10:00"),
    ("Treino", 1.0, "sessao", "18:00"),
    ("Almoco", 1.0, "refeicao", "12:30"),
]


class Database:
    """Wrapper leve sobre sqlite3 para facilitar injeção de dependência e testes isolados."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or get_settings().database_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self, seed_default_habits: bool = True) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)
            if seed_default_habits:
                for nome, meta, unidade, horario in DEFAULT_HABITS:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO habitos_saude (nome, meta_diaria, unidade, horario_lembrete, ativo)
                        VALUES (?, ?, ?, ?, 1)
                        """,
                        (nome, meta, unidade, horario),
                    )
