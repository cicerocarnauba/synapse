# `Synapse` — Orquestrador Pessoal Multi-Domínio com IA

> **Caixa de entrada única conversacional (*Zero-Friction Inbox*)** em Python que transforma mensagens livres em ações estruturadas nos domínios de **Finanças**, **Tarefas Rápidas**, **Agenda (Google Calendar)**, **Saúde & Hábitos** e **Notificações**, consolidando tudo em um **Briefing Diário**.

---

## 1. Qual é a dor real?
No dia a dia, gastos, compromissos, tarefas e cuidados básicos de saúde (hidratação, treino, refeições) surgem de forma fragmentada. Gerenciar isso exige abrir 4 ou 5 aplicativos diferentes e preencher formulários manuais — atrito que leva ao abandono da rotina.

O **Synapse** elimina esse atrito: você envia uma única frase em linguagem natural — inclusive combinando vários assuntos (ex.: *"Gastei 38,50 no almoço, bebi 500ml de água e marca revisão amanhã às 19h"*) — e o orquestrador interpreta as intenções, valida os dados via **Pydantic**, persiste em **SQL**, sincroniza com a **API do Google Calendar** e atualiza seu painel em tempo real.

---

## 2. Arquitetura e Decisões de Engenharia
- **Modular Monolith + Tool-Based Orchestrator:** Cada domínio (`financas`, `tarefas`, `agenda`, `saude`, `notificacoes`) é encapsulado em seu próprio serviço e exposto como ferramenta (*Function Calling*) para o modelo **Google Gemini (`google-genai`)**.
- **Validação Estrita (RN01):** Toda extração da IA passa por contratos Pydantic v2 com *enums* fechados antes de tocar no banco SQL.
- **Padrão Adapter & Degradação Graciosa (RNF02):**
  - `GoogleCalendarAdapter`: Integra com a API REST v3 do Google Calendar; na ausência de credenciais ou falha de rede, o evento é salvo localmente com `sync_status = 'PENDENTE'` sem quebrar o fluxo.
  - `NotificationAdapter`: Dispara lembretes via Webhook externo (Discord/Slack/n8n) ou entrega *In-App*.
- **Modo Fallback Determinístico:** Permite rodar, demonstrar e testar 100% da aplicação offline mesmo sem `GEMINI_API_KEY` configurada.
- **Auditoria (Observabilidade):** Todas as mensagens, ferramentas acionadas e latências (`ms`) ficam registradas na tabela `historico_interacoes`.

### Documentação Completa do Processo de Engenharia
- [Fase 1 — Elicitação de Requisitos (RFs, RNs e RNFs ISO/IEC 25010)](./docs/01_ELICITACAO_REQUISITOS.md)
- [Fase 2 — Arquitetura, Modelagem SQL (7 Tabelas) e Contratos da API](./docs/02_ARQUITETURA_E_DADOS.md)
- [Fase 3 — Guia Visual / Design System (Notion)](./DESIGN.md)

---

## 3. Como executar localmente

```bash
# 1. Criar ambiente virtual e instalar dependências
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. (Opcional) Configurar chave do Gemini e integrações
cp .env.example .env

# 3. Subir a API + Interface Web
uvicorn app.main:app --reload
```

Acesse:
- **Interface Web do Synapse:** `http://127.0.0.1:8000`
- **Documentação Interativa OpenAPI (Swagger):** `http://127.0.0.1:8000/docs`

### Executar Testes Automatizados
```bash
pytest -v
```
