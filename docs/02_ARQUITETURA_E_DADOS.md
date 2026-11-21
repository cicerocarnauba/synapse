# Fase 2: Arquitetura, Modelagem de Dados (SQL) & Contratos da API — `Synapse`

**Projeto:** `Synapse` (Orquestrador Pessoal Multi-Domínio com IA)  
**Padrão Arquitetural:** Modular Monolith em camadas com *Tool-Based Orchestrator* + *Adapters* (Strategy/Port-and-Adapter).

---

## 1. Estrutura de Diretórios e Camadas

```text
synapse/
├── app/
│   ├── main.py                      # Entrada FastAPI, registro de rotas e arquivos estáticos
│   ├── config.py                    # Configurações via .env (timezone, DB path, API keys)
│   ├── database.py                  # Conexão SQL (SQLite/PostgreSQL compatível) e DDL
│   ├── schemas.py                   # Contratos Pydantic (validação estrita - RN01)
│   ├── services/
│   │   ├── orchestrator.py          # Cérebro do Synapse (Gemini Function Calling + fallback)
│   │   ├── financas_service.py      # Regras e agregações SQL de Finanças
│   │   ├── tarefas_service.py       # Regras e CRUD SQL de Tarefas Rápidas
│   │   ├── agenda_service.py        # Regras SQL de Agenda + Google Calendar Adapter
│   │   ├── saude_service.py         # Regras SQL de Hábitos & Check-ins (água, treino, almoço)
│   │   ├── notificacoes_service.py  # Fila de lembretes + disparo via Notifier Adapter
│   │   └── briefing_service.py      # Consolidador do Briefing Diário
│   └── adapters/
│       ├── google_calendar.py       # Adapter desacoplado (Google Calendar API real ou local)
│       └── notifier.py              # Adapter de canal (Webhook / In-App / Log)
├── frontend/                        # Interface web do Synapse (Chat + Painel do Dia)
├── tests/                           # Suíte de testes automatizados (pytest)
└── docs/                            # Elicitação, Arquitetura e Design
```

### Fluxo Principal (`POST /api/v1/inbox`)
1. O usuário envia uma mensagem livre (ex.: *"Gastei 35 no almoço, bebi 500ml de água e marca revisão amanhã às 19h"*).
2. O `orchestrator.py` injeta a data/hora atual (`America/Fortaleza`) no contexto e aciona o Gemini com as ferramentas Python registradas (`registrar_transacao`, `criar_tarefa`, `agendar_evento`, `registrar_checkin_saude`, `criar_habito_saude`, `agendar_notificacao`, `consultar_briefing`).
3. O LLM pode retornar **uma ou múltiplas chamadas de função** na mesma rodada.
4. Cada chamada passa por validação Pydantic (RN01) antes de ser executada no serviço correspondente e persistida em SQL.
5. O evento de agenda tenta sincronizar via `google_calendar.py`; em caso de ausência de credenciais ou erro de rede, persiste normalmente com `sync_status = 'PENDENTE'` (RNF02).
6. O resultado de todas as ações e a resposta final são gravados em `historico_interacoes` com `latencia_ms` (RNF03) e retornados ao cliente.
7. **Fallback Determinístico:** Caso `GEMINI_API_KEY` não esteja configurada, um parser heurístico/determinístico em Python permite testar e demonstrar os 5 módulos localmente sem erro.

### Decisões Tecnológicas & Stack
- **Backend & API:** Python 3 + FastAPI + Pydantic v2.
- **Persistência:** SQL (SQLite local sem dependências pesadas; queries compatíveis com PostgreSQL).
- **Motor de IA:** Google Gemini API (`google-genai` SDK) com *Function Calling*.
- **Testes:** `pytest` + `httpx` / `TestClient`.

---

## 2. Modelagem do Banco de Dados Relacional (SQL — 7 Tabelas)

### 2.1. `transacoes` (Finanças)
| Coluna | Tipo | Restrições | Descrição |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | ID interno |
| `tipo` | `VARCHAR(15)` | `NOT NULL` | `DESPESA` ou `RECEITA` |
| `valor` | `REAL` | `NOT NULL CHECK(valor > 0)` | Valor monetário positivo |
| `categoria` | `VARCHAR(30)` | `NOT NULL` | `ALIMENTACAO`, `TRANSPORTE`, `MORADIA`, `SAUDE`, `LAZER`, `ESTUDOS`, `SALARIO`, `OUTROS` |
| `descricao` | `VARCHAR(200)` | `NOT NULL` | Descrição curta do lançamento |
| `data_transacao` | `DATE` | `NOT NULL` | Data efetiva da transação |
| `criado_em` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | Data de criação |

### 2.2. `tarefas` (Tarefas Rápidas)
| Coluna | Tipo | Restrições | Descrição |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | ID interno |
| `titulo` | `VARCHAR(200)` | `NOT NULL` | Descrição objetiva da tarefa |
| `prioridade` | `VARCHAR(10)` | `NOT NULL DEFAULT 'MEDIA'` | `BAIXA`, `MEDIA`, `ALTA` |
| `status` | `VARCHAR(15)` | `NOT NULL DEFAULT 'PENDENTE'` | `PENDENTE` ou `CONCLUIDA` |
| `prazo` | `TIMESTAMP` | `NULL` | Prazo opcional em ISO 8601 |
| `criado_em` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | Data de criação |

### 2.3. `eventos_agenda` (Agenda & Google Calendar)
| Coluna | Tipo | Restrições | Descrição |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | ID interno |
| `titulo` | `VARCHAR(200)` | `NOT NULL` | Título do compromisso |
| `descricao` | `TEXT` | `DEFAULT ''` | Detalhes adicionais |
| `inicio` | `TIMESTAMP` | `NOT NULL` | Data/hora de início |
| `fim` | `TIMESTAMP` | `NOT NULL` | Data/hora de término |
| `google_event_id` | `VARCHAR(120)` | `NULL` | ID retornado pela API do Google Calendar |
| `sync_status` | `VARCHAR(20)` | `NOT NULL DEFAULT 'PENDENTE'` | `SINCRONIZADO`, `PENDENTE`, `LOCAL_ONLY` |
| `criado_em` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | Data de criação |

### 2.4. `habitos_saude` (Metas Diárias — Água, Treino, Almoço)
| Coluna | Tipo | Restrições | Descrição |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | ID interno |
| `nome` | `VARCHAR(80)` | `UNIQUE NOT NULL` | Ex.: `Agua`, `Treino`, `Almoco` |
| `meta_diaria` | `REAL` | `NOT NULL` | Meta numérica diária (ex.: `2500`, `1`) |
| `unidade` | `VARCHAR(20)` | `NOT NULL` | Ex.: `ml`, `sessao`, `refeicao` |
| `horario_lembrete` | `VARCHAR(10)` | `NULL` | Horário recorrente sugerido (`HH:MM`, ex.: `12:30`) |
| `ativo` | `BOOLEAN` | `NOT NULL DEFAULT 1` | Flag de hábito ativo |

### 2.5. `checkins_saude` (Registros Diários de Saúde)
| Coluna | Tipo | Restrições | Descrição |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | ID interno |
| `habito_id` | `INTEGER` | `NOT NULL REFERENCES habitos_saude(id)` | Chave estrangeira do hábito |
| `quantidade` | `REAL` | `NOT NULL CHECK(quantidade > 0)` | Quantidade registrada (ex.: `500` ml) |
| `observacao` | `VARCHAR(200)` | `DEFAULT ''` | Nota opcional |
| `registrado_em` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | Timestamp do check-in |

### 2.6. `notificacoes` (Fila de Lembretes)
| Coluna | Tipo | Restrições | Descrição |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | ID interno |
| `origem` | `VARCHAR(20)` | `NOT NULL` | `AGENDA`, `TAREFA`, `SAUDE`, `MANUAL` |
| `titulo` | `VARCHAR(150)` | `NOT NULL` | Título curto da notificação |
| `mensagem` | `TEXT` | `NOT NULL` | Corpo do lembrete |
| `agendado_para` | `TIMESTAMP` | `NOT NULL` | Quando o lembrete deve ser disparado |
| `status` | `VARCHAR(15)` | `NOT NULL DEFAULT 'PENDENTE'` | `PENDENTE`, `ENVIADA`, `LIDA` |
| `canal` | `VARCHAR(20)` | `NOT NULL DEFAULT 'IN_APP'` | `IN_APP`, `WEBHOOK` |
| `criado_em` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | Data de criação |

### 2.7. `historico_interacoes` (Auditoria do Orquestrador)
| Coluna | Tipo | Restrições | Descrição |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | ID do log |
| `mensagem_usuario` | `TEXT` | `NOT NULL` | Texto original enviado no `/inbox` |
| `acoes_executadas_json` | `TEXT` | `NOT NULL` | JSON com ferramentas chamadas e resultados |
| `resposta_assistente` | `TEXT` | `NOT NULL` | Resposta retornada ao usuário |
| `latencia_ms` | `INTEGER` | `NOT NULL` | Tempo de processamento em ms |
| `criado_em` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | Data/hora da interação |

---

## 3. Contratos da API REST (FastAPI)

| Método | Endpoint | Propósito |
| :--- | :--- | :--- |
| `POST` | `/api/v1/inbox` | Entrada única conversacional: interpreta mensagem, executa múltiplas tools e retorna resposta + ações estruturadas. |
| `GET` | `/api/v1/briefing` | Consolida o dia: agenda de hoje, tarefas pendentes, progresso de saúde, notificações pendentes e resumo financeiro. |
| `GET` | `/api/v1/financas/resumo` | Analytics SQL: receitas, despesas, saldo e agrupamento por categoria. |
| `GET` | `/api/v1/tarefas` | Lista tarefas com filtro opcional de `status`. |
| `PATCH` | `/api/v1/tarefas/{id}/concluir` | Marca tarefa como concluída. |
| `GET` | `/api/v1/agenda` | Lista eventos da agenda e `sync_status` do Google Calendar. |
| `GET` / `POST` | `/api/v1/saude/hoje` / `/api/v1/saude/habitos` | Retorna progresso diário de água/treino/almoço e permite criar/editar metas. |
| `GET` / `POST` | `/api/v1/notificacoes/pendentes` / `/api/v1/notificacoes/disparar` | Lista lembretes pendentes e dispara os vencidos via adaptador de canal. |
