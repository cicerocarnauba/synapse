# Fase 1: Elicitação de Requisitos — `Synapse`

**Projeto:** `Synapse` (Orquestrador Pessoal Multi-Domínio com IA)  
**Contexto:** Produtividade pessoal, automação de rotina e orquestração de múltiplos domínios via linguagem natural.  
**Ator Principal:** Usuário final (estudante/profissional gerenciando rotina, finanças, agenda e saúde).

---

## 1. Definição do Problema ("Qual é a dor real?")

No dia a dia, eventos, gastos, tarefas e cuidados básicos de saúde (beber água, almoçar no horário, treinar) surgem de forma rápida e desestruturada.  
Gerenciar isso hoje exige abrir **4 ou 5 aplicativos diferentes** (planilha/app financeiro, gerenciador de tarefas, Google Agenda, rastreador de hábitos) e preencher formulários manuais em cada um. Esse atrito operacional faz com que o usuário abandone o controle financeiro, acumule tarefas esquecidas e negligencie hábitos básicos de saúde.

### Proposta de Valor do `Synapse`
Oferecer uma **Caixa de Entrada Única Conversacional (*Zero-Friction Inbox*)**: o usuário envia qualquer mensagem em texto livre — inclusive combinando múltiplos assuntos na mesma frase — e o agente orquestrador interpreta as intenções, executa as ferramentas especializadas (*Function Calling*), persiste em banco relacional (SQL), sincroniza com o Google Calendar e dispara lembretes/notificações no momento certo.

---

## 2. Requisitos Funcionais (RFs)

| ID | Módulo / Requisito | Descrição |
| :--- | :--- | :--- |
| **RF01** | **Entrada Única Conversacional (Orquestrador)** | O usuário envia texto livre (`POST /api/v1/inbox`). O agente identifica automaticamente a(s) intenção(ões) — podendo acionar múltiplos domínios em uma única mensagem (ex.: *"Gastei 35 no almoço, bebi 500ml de água e marca revisão amanhã às 19h"*) — e executa as ferramentas correspondentes. |
| **RF02** | **Módulo Finanças (SQL + Analytics)** | Registro automático de transações (`tipo`: `DESPESA`/`RECEITA`, `valor`, `categoria`, `descricao`, `data`) e consultas analíticas em SQL (total por período, gastos agrupados por categoria e saldo). |
| **RF03** | **Módulo Tarefas Rápidas (SQL)** | Criação, listagem e conclusão de tarefas com extração automática de `titulo`, `prioridade` (`BAIXA`, `MEDIA`, `ALTA`) e `prazo` opcional. |
| **RF04** | **Módulo Agenda & Google Calendar** | Criação e consulta de compromissos (`titulo`, `inicio`, `fim`, `descricao`) salvos localmente em SQL e sincronizados com a API do **Google Calendar** via adaptador desacoplado. |
| **RF05** | **Módulo Saúde & Hábitos (Água, Treino, Refeições)** | Cadastro de metas/hábitos recorrentes (ex.: meta diária de água em `ml`, horário de treino, horário de almoço) e registro rápido de check-ins diários em linguagem natural (ex.: *"Bebi 500ml de água"*, *"Concluí o treino"*), com cálculo automático de progresso diário. |
| **RF06** | **Módulo Notificações & Lembretes** | Agendamento automático e manual de lembretes baseados em compromissos da agenda, prazos de tarefas e horários de hábitos de saúde (água, treino, almoço), com fila persistida em SQL, consulta de notificações pendentes e disparo via adaptador de canal (Webhook / Log / In-App). |
| **RF07** | **Briefing Diário Consolidado** | Endpoint (`GET /api/v1/briefing`) que consolida em uma única resposta: compromissos do dia, tarefas prioritárias/atrasadas, progresso dos hábitos de saúde do dia, notificações pendentes e resumo financeiro do mês. |

---

## 3. Regras de Negócio (RNs)

* **RN01 — Validação Estrita de Domínio (Pydantic):** Nenhum dado extraído pela IA é persistido sem validação prévia de tipo e domínio (ex.: `valor > 0`, datas ISO 8601 válidas, categorias e prioridades dentro de *enums* controlados).
* **RN02 — Transparência de Ações Executadas:** Toda resposta do `/inbox` deve listar explicitamente quais ferramentas/módulos foram acionados e o resultado estruturado de cada ação, permitindo conferência rápida pelo usuário.
* **RN03 — Resolução Temporal Relativa:** Referências como *"hoje"*, *"amanhã às 18h"* ou *"daqui a 2 horas"* devem ser convertidas para timestamps exatos com base na data/hora atual no fuso horário configurado (`America/Fortaleza`).
* **RN04 — Geração Automática de Lembrete:** Ao criar um evento na agenda ou um hábito de saúde com horário fixo (ex.: treino às 18h, almoço às 12h30), o sistema pode agendar automaticamente uma notificação correspondente na fila de lembretes.

---

## 4. Requisitos Não-Funcionais (RNFs — ISO/IEC 25010)

* **RNF01 — Extensibilidade e Modularidade:** Cada domínio (`financas`, `tarefas`, `agenda`, `saude`, `notificacoes`) deve ser encapsulado como um módulo/ferramenta independente, permitindo acoplar novos domínios sem alterar o núcleo do orquestrador.
* **RNF02 — Confiabilidade e Resiliência em Integrações Externas:** Indisponibilidade ou ausência de credenciais na API do Google Calendar ou em webhooks de notificação não podem falhar a operação local; o registro deve ser salvo em SQL com `sync_status = 'PENDENTE'` para posterior retentativa.
* **RNF03 — Auditabilidade:** Todas as entradas conversacionais, ferramentas acionadas e tempos de resposta (`latencia_ms`) devem ser persistidos em log de auditoria (`historico_interacoes`).
* **RNF04 — Desempenho:** Consultas diretas de leitura (briefing, listagens e notificações) devem responder em até `300ms` (p95); o processamento conversacional via LLM deve concluir em até `5s` em condições normais de rede.
* **RNF05 — Testabilidade e Isolamento:** Regras de negócio, persistência SQL, motor de notificações e adaptadores externos devem ser 100% testáveis de forma determinística e offline via *mocks/stubs*.
