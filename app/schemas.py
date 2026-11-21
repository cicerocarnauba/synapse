"""Contratos Pydantic v2 para validação estrita de domínio (RN01)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TipoTransacao(str, Enum):
    DESPESA = "DESPESA"
    RECEITA = "RECEITA"


class CategoriaTransacao(str, Enum):
    ALIMENTACAO = "ALIMENTACAO"
    TRANSPORTE = "TRANSPORTE"
    MORADIA = "MORADIA"
    SAUDE = "SAUDE"
    LAZER = "LAZER"
    ESTUDOS = "ESTUDOS"
    SALARIO = "SALARIO"
    OUTROS = "OUTROS"


class PrioridadeTarefa(str, Enum):
    BAIXA = "BAIXA"
    MEDIA = "MEDIA"
    ALTA = "ALTA"


class StatusTarefa(str, Enum):
    PENDENTE = "PENDENTE"
    CONCLUIDA = "CONCLUIDA"


class SyncStatus(str, Enum):
    SINCRONIZADO = "SINCRONIZADO"
    PENDENTE = "PENDENTE"
    LOCAL_ONLY = "LOCAL_ONLY"


class OrigemNotificacao(str, Enum):
    AGENDA = "AGENDA"
    TAREFA = "TAREFA"
    SAUDE = "SAUDE"
    MANUAL = "MANUAL"


class StatusNotificacao(str, Enum):
    PENDENTE = "PENDENTE"
    ENVIADA = "ENVIADA"
    LIDA = "LIDA"


class CategoriaFinanceiraCreate(BaseModel):
    nome: str = Field(..., min_length=2, max_length=40)
    cor: str = Field(default="#0075de", max_length=20)


class TransacaoCreate(BaseModel):
    tipo: TipoTransacao
    valor: float = Field(..., gt=0, description="Valor monetário positivo")
    categoria: str = Field(default="OUTROS", min_length=2, max_length=40)
    descricao: str = Field(..., min_length=1, max_length=200)
    data_transacao: str | None = Field(None, description="Data YYYY-MM-DD (default: hoje)")
    conversa_id: int | None = Field(None, description="ID da conversa de origem (se veio do Chat)")


class TransacaoUpdate(BaseModel):
    tipo: TipoTransacao | None = None
    valor: float | None = Field(None, gt=0)
    categoria: str | None = Field(None, min_length=2, max_length=40)
    descricao: str | None = Field(None, min_length=1, max_length=200)
    data_transacao: str | None = None


class TarefaCreate(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=200)
    prioridade: PrioridadeTarefa = PrioridadeTarefa.MEDIA
    prazo: str | None = Field(None, description="Prazo ISO 8601 opcional")
    conversa_id: int | None = None


class TarefaUpdate(BaseModel):
    titulo: str | None = Field(None, min_length=1, max_length=200)
    prioridade: PrioridadeTarefa | None = None
    status: StatusTarefa | None = None
    prazo: str | None = None


class EventoCreate(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=200)
    inicio: str = Field(..., description="Data/hora ISO 8601 de início")
    fim: str = Field(..., description="Data/hora ISO 8601 de término")
    descricao: str = ""
    conversa_id: int | None = None


class EventoUpdate(BaseModel):
    titulo: str | None = Field(None, min_length=1, max_length=200)
    inicio: str | None = None
    fim: str | None = None
    descricao: str | None = None


class HabitoCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=80)
    meta_diaria: float = Field(..., gt=0)
    unidade: str = Field(..., min_length=1, max_length=20)
    horario_lembrete: str | None = Field(None, description="Horário HH:MM opcional")


class CheckinSaudeCreate(BaseModel):
    nome_habito: str = Field(..., min_length=1, max_length=80)
    quantidade: float = Field(..., gt=0)
    observacao: str = ""
    conversa_id: int | None = None


class NotificacaoCreate(BaseModel):
    origem: OrigemNotificacao = OrigemNotificacao.MANUAL
    titulo: str = Field(..., min_length=1, max_length=150)
    mensagem: str = Field(..., min_length=1)
    agendado_para: str = Field(..., description="Timestamp ISO 8601 do lembrete")
    canal: str = "IN_APP"


class InboxRequest(BaseModel):
    mensagem: str = Field(..., min_length=1, max_length=2000)
    conversa_id: int | None = None


class AcaoExecutada(BaseModel):
    modulo: str
    ferramenta: str
    resumo: str
    dados: dict[str, Any]


class InboxResponse(BaseModel):
    conversa_id: int
    resposta: str
    acoes: list[AcaoExecutada]
    usou_ia: bool
    latencia_ms: int


class GeminiConfigRequest(BaseModel):
    api_key: str = Field(default="", description="Chave API (vazio para desconectar)")
    model: str | None = Field(default=None, max_length=80)


class ModelSelectRequest(BaseModel):
    model: str = Field(..., min_length=1, max_length=80)
