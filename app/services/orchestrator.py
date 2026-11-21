"""Orquestrador central do Synapse (RF01): Gemini Function Calling + Fallback Determinístico."""

import json
import logging
import re
import time
from datetime import timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

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

    def obter_chave_gemini(self) -> str:
        """Prioriza chave salva em Ajustes (SQL) e faz fallback para .env."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT valor FROM configuracoes_app WHERE chave = 'gemini_api_key'"
            ).fetchone()
            if row and row["valor"].strip():
                return str(row["valor"]).strip()
        return self.settings.gemini_api_key

    def obter_modelo_gemini(self) -> str:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT valor FROM configuracoes_app WHERE chave = 'gemini_model'"
            ).fetchone()
            if row and row["valor"].strip():
                return str(row["valor"]).strip()
        return self.settings.gemini_model

    def listar_modelos_disponiveis(self, api_key: str | None = None) -> list[str]:
        """Consulta dinamicamente a API para listar modelos reais habilitados na chave."""
        chave = (api_key if api_key is not None else self.obter_chave_gemini()).strip()
        if not chave:
            return []

        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=chave,
            http_options=types.HttpOptions(api_version="v1beta"),
        )
        modelos: list[str] = []
        for m in client.models.list():
            nome = (getattr(m, "name", "") or "").replace("models/", "")
            acoes = getattr(m, "supported_actions", None) or []
            if nome.startswith("gemini") and (not acoes or "generateContent" in acoes):
                modelos.append(nome)
        return sorted(set(modelos), reverse=True)

    def configurar_gemini(self, api_key: str, model: str | None = None) -> dict[str, Any]:
        limpa = api_key.strip()
        if not limpa:
            with self.db.connect() as conn:
                conn.execute("DELETE FROM configuracoes_app WHERE chave IN ('gemini_api_key', 'gemini_model')")
            return {"ia_ativa": False, "modelo": "", "modelos_disponiveis": []}

        modelos = self.listar_modelos_disponiveis(limpa)
        if not modelos:
            raise ValueError("Chave de API inválida ou nenhum modelo compatível encontrado.")

        modelo_escolhido = (model or "").strip()
        if not modelo_escolhido or modelo_escolhido not in modelos:
            preferidos = ("gemini-flash-lite-latest", "gemini-flash-latest", "gemini-pro-latest")
            modelo_escolhido = next((p for p in preferidos if p in modelos), modelos[0])

        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO configuracoes_app (chave, valor, atualizado_em)
                VALUES ('gemini_api_key', ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor, atualizado_em = CURRENT_TIMESTAMP
                """,
                (limpa,),
            )
            conn.execute(
                """
                INSERT INTO configuracoes_app (chave, valor, atualizado_em)
                VALUES ('gemini_model', ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor, atualizado_em = CURRENT_TIMESTAMP
                """,
                (modelo_escolhido,),
            )
        return {
            "ia_ativa": True,
            "modelo": modelo_escolhido,
            "modelos_disponiveis": modelos,
        }

    def atualizar_modelo_gemini(self, model: str) -> dict[str, Any]:
        modelo = model.strip()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO configuracoes_app (chave, valor, atualizado_em)
                VALUES ('gemini_model', ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor, atualizado_em = CURRENT_TIMESTAMP
                """,
                (modelo,),
            )
        return {"modelo": modelo}

    def processar_mensagem(self, mensagem: str, conversa_id: int | None = None) -> InboxResponse:
        inicio_ms = time.perf_counter()
        acoes: list[AcaoExecutada] = []
        usou_ia = False

        cid = self._garantir_conversa(conversa_id, mensagem)
        chave_gemini = self.obter_chave_gemini()

        if chave_gemini:
            try:
                resposta = self._executar_com_gemini(mensagem, acoes, chave_gemini, cid)
                usou_ia = True
            except Exception as exc:
                logger.warning("Falha ao chamar Gemini (%s).", exc)
                if acoes:
                    # As ferramentas já foram executadas com sucesso pela IA; não duplicar no fallback!
                    usou_ia = True
                    total = len(acoes)
                    plural = "ação" if total == 1 else "ações"
                    resposta = f"Pronto! Executei {total} {plural} e atualizei o seu painel do dia."
                else:
                    resposta = self._executar_fallback_deterministico(mensagem, acoes, cid)
        else:
            resposta = self._executar_fallback_deterministico(mensagem, acoes, cid)

        latencia_ms = int((time.perf_counter() - inicio_ms) * 1000)
        self._registrar_auditoria(cid, mensagem, acoes, resposta, latencia_ms)

        return InboxResponse(
            conversa_id=cid,
            resposta=resposta,
            acoes=acoes,
            usou_ia=usou_ia,
            latencia_ms=latencia_ms,
        )

    def criar_conversa(self, titulo: str = "Nova conversa") -> dict[str, Any]:
        hoje = self.settings.now_local().date().isoformat()
        with self.db.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO conversas (titulo, data_dia) VALUES (?, ?)",
                (titulo.strip()[:160], hoje),
            )
            row = conn.execute("SELECT * FROM conversas WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return dict(row)

    def listar_conversas(self) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    c.id,
                    c.titulo,
                    c.data_dia,
                    c.criado_em,
                    COUNT(h.id) AS total_mensagens
                FROM conversas c
                LEFT JOIN historico_interacoes h ON h.conversa_id = c.id
                GROUP BY c.id
                ORDER BY c.data_dia DESC, c.id DESC
                LIMIT 50
                """
            ).fetchall()
            return [dict(r) for r in rows]

    def excluir_conversa(self, conversa_id: int) -> bool:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM historico_interacoes WHERE conversa_id = ?", (conversa_id,))
            cursor = conn.execute("DELETE FROM conversas WHERE id = ?", (conversa_id,))
            return cursor.rowcount > 0

    def listar_mensagens_conversa(self, conversa_id: int) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, conversa_id, mensagem_usuario, acoes_executadas_json, resposta_assistente, latencia_ms, criado_em
                FROM historico_interacoes
                WHERE conversa_id = ?
                ORDER BY id ASC
                """,
                (conversa_id,),
            ).fetchall()
            resultado: list[dict[str, Any]] = []
            for r in rows:
                item = dict(r)
                item["acoes"] = json.loads(item.pop("acoes_executadas_json") or "[]")
                resultado.append(item)
            return resultado

    def _garantir_conversa(self, conversa_id: int | None, primeira_mensagem: str) -> int:
        titulo_auto = primeira_mensagem.strip()[:60]
        if len(primeira_mensagem.strip()) > 60:
            titulo_auto += "..."

        with self.db.connect() as conn:
            if conversa_id is not None:
                existente = conn.execute(
                    "SELECT id, titulo FROM conversas WHERE id = ?",
                    (conversa_id,),
                ).fetchone()
                if existente:
                    if existente["titulo"] == "Nova conversa":
                        conn.execute(
                            "UPDATE conversas SET titulo = ? WHERE id = ?",
                            (titulo_auto, conversa_id),
                        )
                    return int(existente["id"])

            hoje = self.settings.now_local().date().isoformat()
            cursor = conn.execute(
                "INSERT INTO conversas (titulo, data_dia) VALUES (?, ?)",
                (titulo_auto, hoje),
            )
            return int(cursor.lastrowid)

    def _construir_ferramentas(self, acoes: list[AcaoExecutada], conversa_id: int | None = None) -> list[Any]:
        """Cria funções Python tipadas para Function Calling com validação Pydantic (RN01)."""

        def registrar_transacao(
            tipo: str,
            valor: float,
            descricao: str,
            categoria: str,
            data_transacao: str,
        ) -> dict[str, Any]:
            """Registra uma DESPESA ou RECEITA financeira no banco SQL.
            tipo: DESPESA ou RECEITA.
            categoria: use uma das categorias financeiras cadastradas do usuário (ex.: ALIMENTACAO, TRANSPORTE, SALARIO, OUTROS).
            data_transacao: data YYYY-MM-DD ou string vazia para hoje.
            """
            payload = TransacaoCreate(
                tipo=TipoTransacao(tipo.upper()),
                valor=valor,
                categoria=(categoria or "OUTROS").upper(),
                descricao=descricao,
                data_transacao=data_transacao.strip() or None,
                conversa_id=conversa_id,
            )
            dados = self.financas.registrar_transacao(payload)
            acoes.append(
                AcaoExecutada(
                    modulo="FINANCAS",
                    ferramenta="registrar_transacao",
                    resumo=f"{payload.tipo.value} de R$ {payload.valor:.2f} ({dados['categoria']}): {payload.descricao}",
                    dados=dados,
                )
            )
            return dados

        def criar_tarefa(
            titulo: str,
            prioridade: str,
            prazo: str,
        ) -> dict[str, Any]:
            """Cria uma tarefa rápida.
            prioridade: BAIXA, MEDIA ou ALTA.
            prazo: timestamp ISO 8601 ou string vazia se não houver prazo.
            """
            payload = TarefaCreate(
                titulo=titulo,
                prioridade=PrioridadeTarefa((prioridade or "MEDIA").upper()),
                prazo=prazo.strip() or None,
                conversa_id=conversa_id,
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
            descricao: str,
        ) -> dict[str, Any]:
            """Agenda compromisso no banco SQL e tenta sincronizar com o Google Calendar.
            descricao: detalhes opcionais ou string vazia.
            """
            payload = EventoCreate(
                titulo=titulo,
                inicio=inicio_iso,
                fim=fim_iso,
                descricao=descricao or "",
                conversa_id=conversa_id,
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
            quantidade: float,
            observacao: str,
        ) -> dict[str, Any]:
            """Registra check-in diário de saúde (ex.: nome_habito='Agua' quantidade=500; 'Treino' quantidade=1; 'Almoco' quantidade=1)."""
            payload = CheckinSaudeCreate(
                nome_habito=nome_habito,
                quantidade=quantidade,
                observacao=observacao or "",
                conversa_id=conversa_id,
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
            horario_lembrete: str,
        ) -> dict[str, Any]:
            """Cria ou atualiza meta diária de saúde (ex.: Agua 2500 ml 10:00). horario_lembrete: HH:MM ou string vazia."""
            payload = HabitoCreate(
                nome=nome,
                meta_diaria=meta_diaria,
                unidade=unidade,
                horario_lembrete=horario_lembrete.strip() or None,
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
            origem: str,
        ) -> dict[str, Any]:
            """Agenda um lembrete/notificação na fila do Synapse. origem: AGENDA, TAREFA, SAUDE ou MANUAL."""
            payload = NotificacaoCreate(
                origem=OrigemNotificacao((origem or "MANUAL").upper()),
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

        def concluir_tarefa(tarefa_id: int) -> dict[str, Any]:
            """Marca uma tarefa existente como CONCLUIDA pelo seu ID numérico."""
            dados = self.tarefas.concluir_tarefa(int(tarefa_id))
            if not dados:
                return {"erro": f"Tarefa {tarefa_id} não encontrada."}
            acoes.append(
                AcaoExecutada(
                    modulo="TAREFAS",
                    ferramenta="concluir_tarefa",
                    resumo=f"Tarefa concluída: {dados['titulo']}",
                    dados=dados,
                )
            )
            return dados

        def atualizar_tarefa(
            tarefa_id: int,
            titulo: str,
            prioridade: str,
            prazo: str,
        ) -> dict[str, Any]:
            """Atualiza título, prioridade (BAIXA/MEDIA/ALTA) ou prazo (YYYY-MM-DD ou vazio) de uma tarefa existente."""
            from app.schemas import TarefaUpdate

            payload = TarefaUpdate(
                titulo=titulo.strip() or None,
                prioridade=PrioridadeTarefa(prioridade.upper()) if prioridade.strip() else None,
                prazo=prazo.strip() if prazo.strip() else None,
            )
            dados = self.tarefas.atualizar_tarefa(int(tarefa_id), payload)
            if not dados:
                return {"erro": f"Tarefa {tarefa_id} não encontrada."}
            acoes.append(
                AcaoExecutada(
                    modulo="TAREFAS",
                    ferramenta="atualizar_tarefa",
                    resumo=f"Tarefa atualizada: {dados['titulo']} [{dados['prioridade']}]",
                    dados=dados,
                )
            )
            return dados

        def excluir_tarefa(tarefa_id: int) -> dict[str, Any]:
            """Exclui/cancela uma tarefa existente pelo seu ID numérico (use quando o usuário disser que foi cancelada ou pedir para apagar)."""
            ok = self.tarefas.excluir_tarefa(int(tarefa_id))
            if not ok:
                return {"erro": f"Tarefa {tarefa_id} não encontrada."}
            acoes.append(
                AcaoExecutada(
                    modulo="TAREFAS",
                    ferramenta="excluir_tarefa",
                    resumo=f"Tarefa #{tarefa_id} excluída/cancelada",
                    dados={"id": tarefa_id, "excluida": True},
                )
            )
            return {"id": tarefa_id, "excluida": True}

        def excluir_evento(evento_id: int) -> dict[str, Any]:
            """Exclui/cancela um compromisso da agenda pelo seu ID numérico."""
            ok = self.agenda.excluir_evento(int(evento_id))
            if not ok:
                return {"erro": f"Evento {evento_id} não encontrado."}
            acoes.append(
                AcaoExecutada(
                    modulo="AGENDA",
                    ferramenta="excluir_evento",
                    resumo=f"Compromisso #{evento_id} cancelado/excluído",
                    dados={"id": evento_id, "excluido": True},
                )
            )
            return {"id": evento_id, "excluido": True}

        def excluir_transacao(transacao_id: int) -> dict[str, Any]:
            """Remove um lançamento financeiro (despesa/receita) pelo seu ID numérico."""
            ok = self.financas.excluir_transacao(int(transacao_id))
            if not ok:
                return {"erro": f"Transação {transacao_id} não encontrada."}
            acoes.append(
                AcaoExecutada(
                    modulo="FINANCAS",
                    ferramenta="excluir_transacao",
                    resumo=f"Lançamento #{transacao_id} removido",
                    dados={"id": transacao_id, "excluida": True},
                )
            )
            return {"id": transacao_id, "excluida": True}

        return [
            registrar_transacao,
            excluir_transacao,
            criar_tarefa,
            concluir_tarefa,
            atualizar_tarefa,
            excluir_tarefa,
            agendar_evento,
            excluir_evento,
            registrar_checkin_saude,
            configurar_habito_saude,
            agendar_notificacao,
            consultar_briefing,
        ]

    def _executar_com_gemini(
        self,
        mensagem: str,
        acoes: list[AcaoExecutada],
        api_key: str,
        conversa_id: int | None = None,
    ) -> str:
        from google import genai
        from google.genai import types

        agora = self.settings.now_local()
        cats = ", ".join(c["nome"] for c in self.financas.listar_categorias())
        habitos_ativos = ", ".join(
            f"{h['nome']} (meta={h['meta_diaria']:g} {h['unidade']})"
            for h in self.saude.progresso_diario()
        ) or "Agua, Treino, Almoco"

        # Contexto vivo dos itens atuais (para editar, concluir ou cancelar pelo prompt)
        tarefas_pend = self.tarefas.listar_tarefas("PENDENTE")[:15]
        eventos_prox = self.agenda.listar_eventos()[:15]
        trans_rec = self.financas.listar_transacoes(limite=8)

        resumo_tarefas = "; ".join(
            f"[id={t['id']}] {t['titulo']} (prio={t['prioridade']}, prazo={t['prazo'] or 'sem prazo'})"
            for t in tarefas_pend
        ) or "nenhuma"
        resumo_eventos = "; ".join(
            f"[id={e['id']}] {e['titulo']} ({e['inicio']})"
            for e in eventos_prox
        ) or "nenhum"
        resumo_trans = "; ".join(
            f"[id={tr['id']}] {tr['tipo']} R${tr['valor']:.2f} {tr['descricao']} ({tr['categoria']})"
            for tr in trans_rec
        ) or "nenhuma"

        # Memória curta da conversa atual
        historico_txt = ""
        if conversa_id is not None:
            msgs_ant = self.listar_mensagens_conversa(conversa_id)[-6:]
            if msgs_ant:
                linhas_h = []
                for m in msgs_ant:
                    linhas_h.append(f"Usuário: {m['mensagem_usuario']}")
                    linhas_h.append(f"Synapse: {m['resposta_assistente']}")
                historico_txt = "\nHistórico recente desta conversa:\n" + "\n".join(linhas_h)

        system_instruction = (
            "Você é o Synapse, um assistente pessoal orquestrador em português do Brasil. "
            f"Data e hora atual no fuso {self.settings.timezone_name}: {agora.isoformat(timespec='seconds')}. "
            f"Categorias financeiras cadastradas: {cats}. "
            f"\nHábitos de saúde cadastrados: {habitos_ativos}. "
            f"\nTarefas pendentes atuais: {resumo_tarefas}. "
            f"\nCompromissos atuais na agenda: {resumo_eventos}. "
            f"\nÚltimos lançamentos financeiros: {resumo_trans}. "
            f"{historico_txt}\n"
            "REGRAS IMPORTANTES:\n"
            "1. Se o usuário disser que algo foi CANCELADO, REMOVIDO ou APAGADO (ex.: 'cancelaram a prova'), "
            "use excluir_tarefa(id) ou excluir_evento(id) no item correspondente — NÃO crie uma nova tarefa sobre o cancelamento!\n"
            "2. Se o usuário disser que CONCLUIU/FEZ uma tarefa existente, use concluir_tarefa(id).\n"
            "3. Se o usuário pedir para MUDAR data, prazo, prioridade ou título de uma tarefa, use atualizar_tarefa(id, ...).\n"
            "4. Se for saudação ou conversa casual sem ação prática, responda naturalmente sem chamar ferramentas.\n"
            "5. Converta datas relativas (hoje, amanhã, próxima quarta) para ISO 8601 usando a data atual. Seja conciso e confirme exatamente o que fez."
        )

        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(api_version="v1beta"),
        )
        tools = self._construir_ferramentas(acoes, conversa_id=conversa_id)
        modelo = self.obter_modelo_gemini()

        # Desabilita thinking longo para respostas de baixa latência em chat/tool-calling
        config_kwargs: dict[str, Any] = {
            "system_instruction": system_instruction,
            "tools": tools,
            "temperature": 0.2,
        }
        try:
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
            response = client.models.generate_content(
                model=modelo,
                contents=mensagem,
                config=types.GenerateContentConfig(**config_kwargs),
            )
        except Exception:
            if acoes:
                raise
            config_kwargs.pop("thinking_config", None)
            response = client.models.generate_content(
                model=modelo,
                contents=mensagem,
                config=types.GenerateContentConfig(**config_kwargs),
            )
        return (response.text or "Ações processadas com sucesso.").strip()

    def _executar_fallback_deterministico(
        self,
        mensagem: str,
        acoes: list[AcaoExecutada],
        conversa_id: int | None = None,
    ) -> str:
        """Parser determinístico para operação offline, testes e demonstração sem GEMINI_API_KEY."""
        tools = {fn.__name__: fn for fn in self._construir_ferramentas(acoes, conversa_id=conversa_id)}
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
                data_transacao="",
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
                tools["criar_tarefa"](titulo=texto[:140], prioridade=prioridade, prazo="")
        elif any(p in lower for p in ("tarefa:", "fazer ", "preciso ", "enviar ", "estudar ")):
            prioridade = "ALTA" if any(p in lower for p in ("urgente", "hoje", "importante")) else "MEDIA"
            tools["criar_tarefa"](titulo=texto[:140], prioridade=prioridade, prazo="")

        # 6. Consulta de Resumo / Briefing
        if any(p in lower for p in ("resumo", "briefing", "como está meu dia", "quanto gastei", "saldo")):
            tools["consultar_briefing"]()

        # Sem ação identificada: responder conversacionalmente SEM sujar o banco com tarefa falsa
        if not acoes:
            saudacoes = ("oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "e ai", "e aí", "tudo bem", "opa")
            agradecimentos = ("obrigado", "obrigada", "valeu", "vlw", "show", "top", "perfeito", "ok")
            limpo = re.sub(r"[!?.,]+", "", lower).strip()
            if limpo in saudacoes or any(limpo.startswith(s + " ") for s in saudacoes):
                return (
                    "Oi! Tudo pronto por aqui. Me diga o que quer organizar hoje "
                    "(gastos, compromissos na agenda, tarefas, água, treino ou um resumo do seu dia)."
                )
            if limpo in agradecimentos:
                return "Por nada! Se precisar registrar mais alguma coisa ou consultar seu dia, é só mandar."
            if any(p in lower for p in ("ajuda", "o que você faz", "o que voce faz", "como funciona")):
                return (
                    "Posso organizar sua rotina em 5 áreas:\n"
                    "• Finanças (ex.: 'Gastei 35 no almoço')\n"
                    "• Agenda (ex.: 'Marca revisão amanhã às 19h')\n"
                    "• Tarefas (ex.: 'Me lembra de enviar o currículo hoje')\n"
                    "• Saúde (ex.: 'Bebi 500ml de água' ou 'Fiz o treino')\n"
                    "• Resumo do dia (ex.: 'Como está meu resumo?')"
                )
            return (
                "Não identifiquei nenhuma ação para registrar nessa mensagem. "
                "Tente algo como um gasto, compromisso, tarefa, check-in de água/treino ou peça o resumo do dia."
            )

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
        conversa_id: int,
        mensagem: str,
        acoes: list[AcaoExecutada],
        resposta: str,
        latencia_ms: int,
    ) -> None:
        acoes_json = json.dumps([a.model_dump() for a in acoes], ensure_ascii=False)
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO historico_interacoes (conversa_id, mensagem_usuario, acoes_executadas_json, resposta_assistente, latencia_ms)
                VALUES (?, ?, ?, ?, ?)
                """,
                (conversa_id, mensagem, acoes_json, resposta, latencia_ms),
            )
