"""Orquestrador central do Synapse (RF01): Gemini Function Calling + Fallback Determinístico."""

from __future__ import annotations

import json
import re
import time
from datetime import timedelta
from typing import Any

from app.config import Settings, get_settings
from app.database import Database
from app.schemas import (
    AcaoExecutada,
    CategoriaTransacao,
    CheckinSaudeCreate,
    EventoCreate,
    HabitoCreate,
    InboxResponse,
    NotificacaoCreate,
    OrigemNotificacao,
    PrioridadeTarefa,
    TarefaCreate,
    TipoTransacao,
    TransacaoCreate,
)
from app.services.agenda_service import AgendaService
from app.services.briefing_service import BriefingService
from app.services.financas_service import FinancasService
from app.services.notificacoes_service import NotificacoesService
from app.services.saude_service import SaudeService
from app.services.tarefas_service import TarefasService


class SynapseOrchestrator:
    """Interpreta mensagens livres e aciona os 5 domínios do Synapse."""

    def __init__(
        self,
        db: Database,
        financas: FinancasService,
        tarefas: TarefasService,
        agenda: AgendaService,
        saude: SaudeService,
        notificacoes: NotificacoesService,
        briefing: BriefingService,
        settings: Settings | None = None,
    ) -> None:
        self.db = db
        self.financas = financas
        self.tarefas = tarefas
        self.agenda = agenda
        self.saude = saude
        self.notificacoes = notificacoes
        self.briefing = briefing
        self.settings = settings or get_settings()

    def processar_mensagem(self, mensagem: str) -> InboxResponse:
        inicio_ms = time.perf_counter()
        acoes: list[AcaoExecutada] = []
        usou_ia = False

        if self.settings.gemini_api_key:
            try:
                resposta = self._executar_com_gemini(mensagem, acoes)
                usou_ia = True
            except Exception:
                resposta = self._executar_fallback_deterministico(mensagem, acoes)
        else:
            resposta = self._executar_fallback_deterministico(mensagem, acoes)

        latencia_ms = int((time.perf_counter() - inicio_ms) * 1000)
        self._registrar_auditoria(mensagem, acoes, resposta, latencia_ms)

        return InboxResponse(
            resposta=resposta,
            acoes=acoes,
            usou_ia=usou_ia,
            latencia_ms=latencia_ms,
        )

    def _construir_ferramentas(self, acoes: list[AcaoExecutada]) -> list[Any]:
        """Cria funções Python tipadas para Function Calling com validação Pydantic (RN01)."""

        def registrar_transacao(
            tipo: str,
            valor: float,
            descricao: str,
            categoria: str = "OUTROS",
            data_transacao: str | None = None,
        ) -> dict[str, Any]:
            """Registra uma DESPESA ou RECEITA financeira no banco SQL.
            Categorias válidas: ALIMENTACAO, TRANSPORTE, MORADIA, SAUDE, LAZER, ESTUDOS, SALARIO, OUTROS.
            """
            payload = TransacaoCreate(
                tipo=TipoTransacao(tipo.upper()),
                valor=valor,
                categoria=CategoriaTransacao(categoria.upper()),
                descricao=descricao,
                data_transacao=data_transacao,
            )
            dados = self.financas.registrar_transacao(payload)
            acoes.append(
                AcaoExecutada(
                    modulo="FINANCAS",
                    ferramenta="registrar_transacao",
                    resumo=f"{payload.tipo.value} de R$ {payload.valor:.2f} ({payload.categoria.value}): {payload.descricao}",
                    dados=dados,
                )
            )
            return dados

        def criar_tarefa(
            titulo: str,
            prioridade: str = "MEDIA",
            prazo: str | None = None,
        ) -> dict[str, Any]:
            """Cria uma tarefa rápida. Prioridades: BAIXA, MEDIA, ALTA. Prazo opcional em ISO 8601."""
            payload = TarefaCreate(
                titulo=titulo,
                prioridade=PrioridadeTarefa(prioridade.upper()),
                prazo=prazo,
            )
            dados = self.tarefas.criar_tarefa(payload)
            acoes.append(
                AcaoExecutada(
                    modulo="TAREFAS",
                    ferramenta="criar_tarefa",
                    resumo=f"Tarefa [{payload.prioridade.value}]: {payload.titulo}",
                    dados=dados,
                )
            )
            return dados

        def agendar_evento(
            titulo: str,
            inicio_iso: str,
            fim_iso: str,
            descricao: str = "",
        ) -> dict[str, Any]:
            """Agenda compromisso no banco SQL e tenta sincronizar com o Google Calendar."""
            payload = EventoCreate(
                titulo=titulo,
                inicio=inicio_iso,
                fim=fim_iso,
                descricao=descricao,
            )
            dados = self.agenda.agendar_evento(payload)
            acoes.append(
                AcaoExecutada(
                    modulo="AGENDA",
                    ferramenta="agendar_evento",
                    resumo=f"Evento '{payload.titulo}' em {payload.inicio} ({dados['sync_status']})",
                    dados=dados,
                )
            )
            return dados

        def registrar_checkin_saude(
            nome_habito: str,
            quantidade: float = 1.0,
            observacao: str = "",
        ) -> dict[str, Any]:
            """Registra check-in diário de saúde (ex.: nome_habito='Agua' quantidade=500; 'Treino' quantidade=1; 'Almoco' quantidade=1)."""
            payload = CheckinSaudeCreate(
                nome_habito=nome_habito,
                quantidade=quantidade,
                observacao=observacao,
            )
            dados = self.saude.registrar_checkin(payload)
            prog = dados.get("progresso_atual") or {}
            acoes.append(
                AcaoExecutada(
                    modulo="SAUDE",
                    ferramenta="registrar_checkin_saude",
                    resumo=f"{dados['habito']}: +{quantidade:g} {prog.get('unidade', '')} ({prog.get('percentual', 0)}% da meta)",
                    dados=dados,
                )
            )
            return dados

        def configurar_habito_saude(
            nome: str,
            meta_diaria: float,
            unidade: str,
            horario_lembrete: str | None = None,
        ) -> dict[str, Any]:
            """Cria ou atualiza uma meta diária de saúde (ex.: Agua 2500 ml, Treino 1 sessao 18:00)."""
            payload = HabitoCreate(
                nome=nome,
                meta_diaria=meta_diaria,
                unidade=unidade,
                horario_lembrete=horario_lembrete,
            )
            dados = self.saude.criar_ou_atualizar_habito(payload)
            acoes.append(
                AcaoExecutada(
                    modulo="SAUDE",
                    ferramenta="configurar_habito_saude",
                    resumo=f"Meta configurada: {dados['nome']} ({dados['meta_diaria']:g} {dados['unidade']}/dia)",
                    dados=dados,
                )
            )
            return dados

        def agendar_notificacao(
            titulo: str,
            mensagem: str,
            agendado_para_iso: str,
            origem: str = "MANUAL",
        ) -> dict[str, Any]:
            """Agenda um lembrete/notificação na fila do Synapse."""
            payload = NotificacaoCreate(
                origem=OrigemNotificacao(origem.upper()),
                titulo=titulo,
                mensagem=mensagem,
                agendado_para=agendado_para_iso,
            )
            dados = self.notificacoes.agendar_notificacao(payload)
            acoes.append(
                AcaoExecutada(
                    modulo="NOTIFICACOES",
                    ferramenta="agendar_notificacao",
                    resumo=f"Lembrete agendado: {payload.titulo} ({payload.agendado_para})",
                    dados=dados,
                )
            )
            return dados

        def consultar_briefing() -> dict[str, Any]:
            """Consulta o resumo consolidado do dia (agenda, tarefas, saúde, notificações e finanças)."""
            dados = self.briefing.gerar_briefing()
            acoes.append(
                AcaoExecutada(
                    modulo="BRIEFING",
                    ferramenta="consultar_briefing",
                    resumo="Resumo consolidado do dia consultado.",
                    dados=dados,
                )
            )
            return dados

        return [
            registrar_transacao,
            criar_tarefa,
            agendar_evento,
            registrar_checkin_saude,
            configurar_habito_saude,
            agendar_notificacao,
            consultar_briefing,
        ]

    def _executar_com_gemini(self, mensagem: str, acoes: list[AcaoExecutada]) -> str:
        from google import genai
        from google.genai import types

        agora = self.settings.now_local()
        system_instruction = (
            "Você é o Synapse, um assistente pessoal orquestrador em português do Brasil. "
            f"Data e hora atual no fuso {self.settings.timezone_name}: {agora.isoformat(timespec='seconds')}. "
            "Analise a mensagem do usuário e acione UMA OU MAIS ferramentas apropriadas (Finanças, Tarefas, Agenda, Saúde, Notificações ou Briefing). "
            "Converta expressões temporais relativas (hoje, amanhã, às 19h) para ISO 8601 usando a data atual. "
            "Seja conciso, objetivo e sempre confirme claramente o que foi registrado."
        )

        client = genai.Client(api_key=self.settings.gemini_api_key)
        tools = self._construir_ferramentas(acoes)
        response = client.models.generate_content(
            model=self.settings.gemini_model,
            contents=mensagem,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=tools,
                temperature=0.2,
            ),
        )
        return (response.text or "Ações processadas com sucesso.").strip()

    def _executar_fallback_deterministico(self, mensagem: str, acoes: list[AcaoExecutada]) -> str:
        """Parser determinístico para operação offline, testes e demonstração sem GEMINI_API_KEY."""
        tools = {fn.__name__: fn for fn in self._construir_ferramentas(acoes)}
        texto = mensagem.strip()
        lower = texto.lower()
        agora = self.settings.now_local()

        # 1. Finanças (despesa/receita com valor numérico)
        match_fin = re.search(
            r"(gastei|paguei|comprei|recebi|ganhei)\s+(?:r\$\s*)?(\d+(?:[.,]\d{1,2})?)(?:\s+(?:no|na|em|com|de)\s+([^,.;]+))?",
            lower,
        )
        if match_fin:
            verbo = match_fin.group(1)
            valor = float(match_fin.group(2).replace(",", "."))
            tipo = "RECEITA" if verbo in ("recebi", "ganhei") else "DESPESA"
            trecho_desc = (match_fin.group(3) or "").strip()
            descricao = trecho_desc.capitalize()[:120] if trecho_desc else texto[:120]
            categoria = self._inferir_categoria(trecho_desc or lower, tipo)
            tools["registrar_transacao"](
                tipo=tipo,
                valor=valor,
                descricao=descricao,
                categoria=categoria,
            )

        # 2. Saúde — Água
        match_agua = re.search(r"(\d+(?:[.,]\d+)?)\s*(ml|l|litros?)\s*(?:de\s*)?[aá]gua", lower)
        if match_agua:
            qtd = float(match_agua.group(1).replace(",", "."))
            unidade = match_agua.group(2)
            if unidade.startswith("l"):
                qtd *= 1000
            tools["registrar_checkin_saude"](nome_habito="Agua", quantidade=qtd, observacao=texto[:100])

        # 3. Saúde — Treino ou Almoço
        if any(p in lower for p in ("treinei", "fiz treino", "fiz o treino", "academia conclu")):
            tools["registrar_checkin_saude"](nome_habito="Treino", quantidade=1.0, observacao=texto[:100])
        if any(p in lower for p in ("almocei", "fiz o almoço", "ja almoco", "já almocei")):
            tools["registrar_checkin_saude"](nome_habito="Almoco", quantidade=1.0, observacao=texto[:100])

        # 4. Agenda (marcar / agendar evento)
        if any(p in lower for p in ("marca ", "marcar ", "agendar ", "agenda ", "reunião", "reuniao")):
            base_dt = agora + timedelta(days=1) if "amanh" in lower else agora
            match_hora = re.search(r"(\d{1,2})(?:h|:(\d{2}))", lower)
            hora = int(match_hora.group(1)) if match_hora else 10
            minuto = int(match_hora.group(2)) if (match_hora and match_hora.group(2)) else 0
            inicio = base_dt.replace(hour=min(hora, 23), minute=min(minuto, 59), second=0, microsecond=0)
            fim = inicio + timedelta(hours=1)
            match_titulo = re.search(r"(?:marcar?|agendar?)\s+(.+?)(?:\s+(?:amanh[ãa]|hoje|[àa]s\s+\d)|\s*$)", texto, re.IGNORECASE)
            titulo_evento = match_titulo.group(1).strip().capitalize() if match_titulo else texto[:120]
            tools["agendar_evento"](
                titulo=titulo_evento[:120],
                inicio_iso=inicio.isoformat(timespec="seconds"),
                fim_iso=fim.isoformat(timespec="seconds"),
                descricao="Criado via Synapse Inbox",
            )

        # 5. Notificações / Lembrete ou Tarefa
        if any(p in lower for p in ("lembra", "lembrete", "notifica", "avisa")):
            if any(p in lower for p in ("água", "agua", "treino", "almoço", "almoco")):
                agendado = (agora + timedelta(hours=1)).isoformat(timespec="seconds")
                tools["agendar_notificacao"](
                    titulo="Lembrete de Saúde",
                    mensagem=texto,
                    agendado_para_iso=agendado,
                    origem="SAUDE",
                )
            else:
                prioridade = "ALTA" if any(p in lower for p in ("urgente", "hoje", "blip", "importante")) else "MEDIA"
                tools["criar_tarefa"](titulo=texto[:140], prioridade=prioridade)
        elif any(p in lower for p in ("tarefa:", "fazer ", "preciso ", "enviar ", "estudar ")):
            prioridade = "ALTA" if any(p in lower for p in ("urgente", "hoje", "importante")) else "MEDIA"
            tools["criar_tarefa"](titulo=texto[:140], prioridade=prioridade)

        # 6. Consulta de Resumo / Briefing
        if any(p in lower for p in ("resumo", "briefing", "como está meu dia", "quanto gastei", "saldo")):
            tools["consultar_briefing"]()

        # Fallback final: se nada casou, salva como tarefa rápida para não perder a captura
        if not acoes:
            tools["criar_tarefa"](titulo=texto[:140], prioridade="MEDIA")

        total = len(acoes)
        plural = "ação" if total == 1 else "ações"
        return f"Pronto! Executei {total} {plural} e atualizei o seu painel do dia."

    @staticmethod
    def _inferir_categoria(texto_lower: str, tipo: str) -> str:
        if tipo == "RECEITA":
            return "SALARIO"
        mapa = {
            "ALIMENTACAO": ("almo", "jantar", "café", "cafe", "lanche", "comida", "mercado", "ifood", "pizza"),
            "TRANSPORTE": ("uber", "99", "ônibus", "onibus", "gasolina", "passagem"),
            "SAUDE": ("farmácia", "farmacia", "remédio", "remedio", "academia", "consulta", "médico"),
            "ESTUDOS": ("livro", "curso", "faculdade", "ufc", "xerox"),
            "MORADIA": ("aluguel", "energia", "internet", "água", "agua", "luz"),
            "LAZER": ("cinema", "jogo", "show", "bar", "viagem"),
        }
        for categoria, termos in mapa.items():
            if any(t in texto_lower for t in termos):
                return categoria
        return "OUTROS"

    def _registrar_auditoria(
        self,
        mensagem: str,
        acoes: list[AcaoExecutada],
        resposta: str,
        latencia_ms: int,
    ) -> None:
        acoes_json = json.dumps([a.model_dump() for a in acoes], ensure_ascii=False)
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO historico_interacoes (mensagem_usuario, acoes_executadas_json, resposta_assistente, latencia_ms)
                VALUES (?, ?, ?, ?)
                """,
                (mensagem, acoes_json, resposta, latencia_ms),
            )
