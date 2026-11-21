const chatFeed = document.getElementById("chat-feed");
const inboxForm = document.getElementById("inbox-form");
const inboxInput = document.getElementById("inbox-input");
const sendBtn = document.getElementById("send-btn");
const micBtn = document.getElementById("mic-btn");
const notifBadge = document.getElementById("notif-badge");
const notifBackdrop = document.getElementById("notif-sheet-backdrop");
const historyBackdrop = document.getElementById("history-sheet-backdrop");
const historyList = document.getElementById("history-list");

let conversaAtualId = null;
let finMesAtual = new Date().toISOString().slice(0, 7);
let finTipoFiltro = "";
let finCategoriaFiltro = "";
let categoriasCache = [];
let transacoesCache = [];
let txConversaOrigemId = null;
let eventosCache = [];
let tarefasCache = [];
let habitosCache = [];
let taskStatusFiltro = "PENDENTE";
let taskConversaOrigemId = null;
let eventConversaOrigemId = null;
let calAno = new Date().getFullYear();
let calMes = new Date().getMonth(); // 0-11
let calDiaSelecionado = null; // YYYY-MM-DD ou null (todos)

const MESES_PT = [
  "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
];

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

// Registra Service Worker (PWA instalável no celular)
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function irParaAba(tab) {
  document.querySelectorAll(".tab-item").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".screen").forEach((s) => {
    const isTarget = s.id === `screen-${tab}`;
    s.classList.toggle("active", isTarget);
  });
  if (tab !== "chat") {
    carregarBriefing();
  }
}

// Navegação por Bottom Tab Bar
document.querySelectorAll(".tab-item").forEach((btn) => {
  btn.addEventListener("click", () => irParaAba(btn.dataset.tab));
});

function renderEmptyChat() {
  chatFeed.innerHTML = `
    <div class="empty-chat" id="empty-chat">
      <h2>Como posso organizar seu dia?</h2>
      <p>Envie gastos, compromissos, tarefas ou registros de saúde em linguagem natural.</p>
    </div>
  `;
}

function limparEstadoVazio() {
  const empty = document.getElementById("empty-chat");
  if (empty) empty.remove();
}

// Mensagens no Chat
function appendUserMessage(text) {
  limparEstadoVazio();
  const el = document.createElement("div");
  el.className = "msg user";
  el.innerHTML = `<div class="msg-bubble">${escapeHtml(text)}</div>`;
  chatFeed.appendChild(el);
  chatFeed.scrollTop = chatFeed.scrollHeight;
}

function appendAssistantMessage(data) {
  limparEstadoVazio();
  const el = document.createElement("div");
  el.className = "msg assistant";

  const tags = (data.acoes || [])
    .map(
      (a) =>
        `<div class="action-tag" data-mod="${escapeHtml(a.modulo)}"><strong>${escapeHtml(
          a.modulo
        )}</strong><span>${escapeHtml(a.resumo)}</span></div>`
    )
    .join("");

  const modo = data.usou_ia ? "Gemini IA" : "Modo Local";
  const metaTexto = data.latencia_ms !== undefined ? `${modo} · ${data.latencia_ms}ms` : "";
  el.innerHTML = `
    <div class="msg-bubble">${escapeHtml(data.resposta)}</div>
    ${tags ? `<div class="action-list">${tags}</div>` : ""}
    ${metaTexto ? `<div class="msg-meta">${metaTexto}</div>` : ""}
  `;
  chatFeed.appendChild(el);
  chatFeed.scrollTop = chatFeed.scrollHeight;
}

function dataLocalISO(offsetDias = 0) {
  const d = new Date(Date.now() + offsetDias * 86400000);
  const ano = d.getFullYear();
  const mes = String(d.getMonth() + 1).padStart(2, "0");
  const dia = String(d.getDate()).padStart(2, "0");
  return `${ano}-${mes}-${dia}`;
}

function formatarRotuloDia(dataDia) {
  if (dataDia === dataLocalISO(0)) return "Hoje";
  if (dataDia === dataLocalISO(-1)) return "Ontem";
  const [ano, mes, dia] = dataDia.split("-");
  return `${dia}/${mes}/${ano}`;
}

async function carregarHistoricoConversas() {
  const resp = await fetch("/api/v1/conversas");
  if (!resp.ok) return;
  const conversas = await resp.json();

  if (!conversas.length) {
    historyList.innerHTML = `<p class="empty-state">Nenhuma conversa salva ainda.</p>`;
    return;
  }

  const porDia = new Map();
  conversas.forEach((c) => {
    if (!porDia.has(c.data_dia)) porDia.set(c.data_dia, []);
    porDia.get(c.data_dia).push(c);
  });

  historyList.innerHTML = Array.from(porDia.entries())
    .map(([dia, itens]) => {
      const botoes = itens
        .map(
          (c) => `
          <div class="history-row">
            <button type="button" class="history-item ${c.id === conversaAtualId ? "active" : ""}" data-conv-id="${c.id}">
              <span class="history-item-title">${escapeHtml(c.titulo)}</span>
              <span class="history-item-count num">${c.total_mensagens} msg</span>
            </button>
            <button type="button" class="history-del-btn" data-del-conv="${c.id}" aria-label="Excluir conversa" title="Excluir conversa">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M3 6h18"></path>
                <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path>
                <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path>
              </svg>
            </button>
          </div>`
        )
        .join("");
      return `
        <div class="history-day-group">
          <span class="history-day-label">${escapeHtml(formatarRotuloDia(dia))}</span>
          ${botoes}
        </div>`;
    })
    .join("");
}

async function abrirConversa(conversaId) {
  conversaAtualId = conversaId;
  const resp = await fetch(`/api/v1/conversas/${conversaId}/mensagens`);
  if (!resp.ok) return;
  const msgs = await resp.json();
  chatFeed.innerHTML = "";
  if (!msgs.length) {
    renderEmptyChat();
  } else {
    msgs.forEach((m) => {
      appendUserMessage(m.mensagem_usuario);
      appendAssistantMessage({
        resposta: m.resposta_assistente,
        acoes: m.acoes || [],
        usou_ia: false,
        latencia_ms: m.latencia_ms,
      });
    });
  }
  historyBackdrop.classList.add("hidden");
  irParaAba("chat");
}

function iniciarNovaConversa() {
  conversaAtualId = null;
  renderEmptyChat();
  historyBackdrop.classList.add("hidden");
  irParaAba("chat");
  inboxInput.focus();
}

async function enviarMensagem(texto) {
  const clean = texto.trim();
  if (!clean) return;

  appendUserMessage(clean);
  inboxInput.value = "";
  sendBtn.disabled = true;

  try {
    const resp = await fetch("/api/v1/inbox", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mensagem: clean, conversa_id: conversaAtualId }),
    });
    if (!resp.ok) throw new Error("Falha ao processar.");
    const data = await resp.json();
    conversaAtualId = data.conversa_id;
    appendAssistantMessage(data);
    await carregarBriefing();
  } catch (err) {
    appendAssistantMessage({
      resposta: `Erro: ${err.message}`,
      acoes: [],
      usou_ia: false,
      latencia_ms: 0,
    });
  } finally {
    sendBtn.disabled = false;
  }
}

function atualizarVisaoIA(conectado, modelos = [], modeloAtual = "") {
  const connectedBox = document.getElementById("ia-connected-box");
  const form = document.getElementById("gemini-config-form");
  const cancelBtn = document.getElementById("ia-cancel-change-btn");
  const activeModelEl = document.getElementById("cfg-ia-active-model");
  const select = document.getElementById("gemini-model-select");
  if (!connectedBox || !form || !select) return;

  if (conectado) {
    connectedBox.classList.remove("hidden");
    form.classList.add("hidden");
    cancelBtn.classList.remove("hidden");
    if (activeModelEl) activeModelEl.textContent = modeloAtual || "—";

    const lista = modelos.length ? modelos : modeloAtual ? [modeloAtual] : [];
    select.innerHTML =
      `<option value="" disabled>Selecione um modelo</option>` +
      lista
        .map(
          (m) =>
            `<option value="${escapeHtml(m)}" ${m === modeloAtual ? "selected" : ""}>${escapeHtml(m)}</option>`
        )
        .join("");
  } else {
    connectedBox.classList.add("hidden");
    form.classList.remove("hidden");
    cancelBtn.classList.add("hidden");
    select.innerHTML = "";
  }
}

async function carregarStatus() {
  try {
    const resp = await fetch("/api/v1/health");
    const data = await resp.json();
    const cfgIa = document.getElementById("cfg-ia-status");
    const cfgGcal = document.getElementById("cfg-gcal-status");
    const cfgTz = document.getElementById("cfg-tz");

    if (cfgIa) {
      cfgIa.textContent = data.ia_ativa ? "CONECTADO" : "LOCAL";
      cfgIa.className = `sync-badge ${data.ia_ativa ? "SINCRONIZADO" : "PENDENTE"}`;
    }
    if (data.ia_ativa) {
      const modResp = await fetch("/api/v1/config/ia/modelos");
      if (modResp.ok) {
        const modData = await modResp.json();
        atualizarVisaoIA(true, modData.modelos, modData.modelo_atual);
      } else {
        atualizarVisaoIA(true, [], data.modelo_ia);
      }
    } else {
      atualizarVisaoIA(false);
    }
    if (cfgGcal) {
      cfgGcal.textContent = data.google_calendar_ativo ? "SINCRONIZADO" : "PENDENTE";
      cfgGcal.className = `sync-badge ${data.google_calendar_ativo ? "SINCRONIZADO" : "PENDENTE"}`;
    }
    if (cfgTz) {
      cfgTz.textContent = data.timezone;
    }
  } catch {
    // mantém estado padrão offline
  }
}

async function carregarFinancas() {
  const params = new URLSearchParams({ mes: finMesAtual, limite: "50" });
  if (finTipoFiltro) params.set("tipo", finTipoFiltro);
  if (finCategoriaFiltro) params.set("categoria", finCategoriaFiltro);

  const [resumoResp, transResp, catsResp] = await Promise.all([
    fetch(`/api/v1/financas/resumo?mes=${encodeURIComponent(finMesAtual)}`),
    fetch(`/api/v1/financas/transacoes?${params.toString()}`),
    fetch("/api/v1/financas/categorias"),
  ]);

  if (catsResp.ok) {
    categoriasCache = await catsResp.json();
    preencherSelectCategorias();
  }

  if (resumoResp.ok) {
    const fin = await resumoResp.json();
    document.getElementById("financas-periodo").textContent = fin.periodo;
    document.getElementById("fin-receitas").textContent = brl.format(fin.total_receitas);
    document.getElementById("fin-despesas").textContent = brl.format(fin.total_despesas);
    document.getElementById("fin-saldo").textContent = brl.format(fin.saldo);

    const clearCatBtn = document.getElementById("clear-cat-filter-btn");
    if (clearCatBtn) clearCatBtn.classList.toggle("hidden", !finCategoriaFiltro);

    const catsEl = document.getElementById("financas-categorias");
    catsEl.innerHTML = !fin.despesas_por_categoria.length
      ? `<p class="empty-state">Sem despesas neste mês.</p>`
      : fin.despesas_por_categoria
          .map(
            (c) => `
            <button type="button" class="cat-bar-item ${finCategoriaFiltro === c.categoria ? "active" : ""}" data-filter-cat="${escapeHtml(c.categoria)}">
              <div class="cat-bar-head">
                <span class="cat-label-wrap">
                  <span class="cat-dot" style="background: ${escapeHtml(c.cor || "#615d59")}"></span>
                  <span>${escapeHtml(c.categoria)}</span>
                </span>
                <span class="num"><strong>${brl.format(c.total)}</strong> · ${c.percentual}%</span>
              </div>
              <div class="progress-track">
                <div class="progress-fill" style="width: ${c.percentual}%; background: ${escapeHtml(c.cor || "#0075de")}"></div>
              </div>
            </button>`
          )
          .join("");
  }

  if (transResp.ok) {
    transacoesCache = await transResp.json();
    const transEl = document.getElementById("transacoes-list");
    transEl.innerHTML = !transacoesCache.length
      ? `<p class="empty-state">Nenhum lançamento encontrado.</p>`
      : transacoesCache
          .map(
            (tr) => `
            <button type="button" class="row-card tx-clickable" data-tx-id="${tr.id}">
              <div>
                <p class="row-title">${escapeHtml(tr.descricao)}</p>
                <div class="tx-meta-line">
                  <span class="cat-dot" style="background: ${escapeHtml(tr.categoria_cor || "#615d59")}"></span>
                  <span>${escapeHtml(tr.categoria)} · ${escapeHtml(tr.data_transacao)}</span>
                  ${tr.conversa_id ? `<span class="chat-origin-tag">Chat</span>` : ""}
                </div>
              </div>
              <strong class="num ${tr.tipo === "RECEITA" ? "positive" : "negative"}">
                ${tr.tipo === "RECEITA" ? "+" : "-"}${brl.format(tr.valor)}
              </strong>
            </button>`
          )
          .join("");
  }
}

function preencherSelectCategorias(selecionada = "OUTROS") {
  const select = document.getElementById("tx-cat-select");
  if (!select) return;
  select.innerHTML = categoriasCache
    .map(
      (c) =>
        `<option value="${escapeHtml(c.nome)}" ${c.nome === selecionada ? "selected" : ""}>${escapeHtml(c.nome)}</option>`
    )
    .join("");
}

function renderListaGerenciarCategorias() {
  const el = document.getElementById("cat-manage-list");
  if (!el) return;
  el.innerHTML = categoriasCache
    .map(
      (c) => `
      <div class="row-card">
        <span class="cat-label-wrap">
          <span class="cat-dot" style="background: ${escapeHtml(c.cor)}"></span>
          <span>${escapeHtml(c.nome)}</span>
        </span>
        ${
          c.padrao
            ? `<span class="muted">Padrão</span>`
            : `<button type="button" class="link-action" data-del-cat="${c.id}">Excluir</button>`
        }
      </div>`
    )
    .join("");
}

function abrirSheetTransacao(tx = null) {
  const backdrop = document.getElementById("tx-sheet-backdrop");
  const title = document.getElementById("tx-sheet-title");
  const goChatBtn = document.getElementById("tx-go-chat-btn");
  const delBtn = document.getElementById("tx-delete-btn");

  document.getElementById("tx-id-input").value = tx ? String(tx.id) : "";
  document.getElementById("tx-tipo-select").value = tx ? tx.tipo : "DESPESA";
  document.getElementById("tx-valor-input").value = tx ? String(tx.valor) : "";
  document.getElementById("tx-desc-input").value = tx ? tx.descricao : "";
  preencherSelectCategorias(tx ? tx.categoria : "OUTROS");
  document.getElementById("tx-data-input").value = tx ? tx.data_transacao : dataLocalISO(0);

  txConversaOrigemId = tx && tx.conversa_id ? tx.conversa_id : null;
  title.textContent = tx ? "Editar lançamento" : "Novo lançamento";
  goChatBtn.classList.toggle("hidden", !txConversaOrigemId);
  delBtn.classList.toggle("hidden", !tx);
  backdrop.classList.remove("hidden");
}

function mudarMes(delta) {
  const [ano, mes] = finMesAtual.split("-").map(Number);
  const d = new Date(ano, mes - 1 + delta, 1);
  finMesAtual = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  finCategoriaFiltro = "";
  carregarFinancas();
}

async function carregarTarefas() {
  const resp = await fetch(`/api/v1/tarefas?status=${encodeURIComponent(taskStatusFiltro)}`);
  if (!resp.ok) return;
  tarefasCache = await resp.json();
  document.getElementById("tarefas-count").textContent = String(tarefasCache.length);
  const tarefasEl = document.getElementById("tarefas-list");
  tarefasEl.innerHTML = !tarefasCache.length
    ? `<p class="empty-state">${taskStatusFiltro === "PENDENTE" ? "Nenhuma tarefa pendente." : "Nenhuma tarefa concluída."}</p>`
    : tarefasCache
        .map(
          (t) => `
          <div class="task-row">
            <input type="checkbox" data-task-toggle="${t.id}" ${t.status === "CONCLUIDA" ? "checked" : ""} />
            <button type="button" class="tx-clickable" style="border:none;background:none;padding:0;flex:1" data-task-edit="${t.id}">
              <span class="task-title" style="${t.status === "CONCLUIDA" ? "text-decoration:line-through;color:var(--ink-muted)" : ""}">${escapeHtml(t.titulo)}</span>
              <div class="tx-meta-line">
                ${t.prazo ? `<span>Prazo ${escapeHtml(String(t.prazo).slice(0, 10))}</span>` : ""}
                ${t.conversa_id ? `<span class="chat-origin-tag">Chat</span>` : ""}
              </div>
            </button>
            <span class="prio-dot ${escapeHtml(t.prioridade)}">${escapeHtml(t.prioridade)}</span>
          </div>`
        )
        .join("");
}

async function carregarCheckinsHoje() {
  const resp = await fetch("/api/v1/saude/checkins");
  if (!resp.ok) return;
  const checkins = await resp.json();
  const el = document.getElementById("checkins-list");
  if (!el) return;
  el.innerHTML = !checkins.length
    ? `<p class="empty-state">Nenhum registro hoje ainda.</p>`
    : checkins
        .map(
          (c) => `
          <div class="row-card">
            <div>
              <p class="row-title">${escapeHtml(c.habito_nome)} · +${c.quantidade} ${escapeHtml(c.unidade)}</p>
              <div class="tx-meta-line">
                <span class="num">${escapeHtml(String(c.registrado_em).slice(11, 16))}</span>
                ${c.conversa_id ? `<button type="button" class="link-action" data-checkin-chat="${c.conversa_id}">Ver chat</button>` : ""}
              </div>
            </div>
            <button type="button" class="link-action" data-del-checkin="${c.id}">Desfazer</button>
          </div>`
        )
        .join("");
}

function renderCalendarioEAgenda() {
  const label = document.getElementById("cal-month-label");
  const grid = document.getElementById("cal-grid");
  const agendaEl = document.getElementById("agenda-list");
  const selLabel = document.getElementById("cal-selected-label");
  const showAllBtn = document.getElementById("cal-show-all-btn");
  if (!grid || !label) return;

  label.textContent = `${MESES_PT[calMes]} ${calAno}`;
  const hojeStr = dataLocalISO(0);

  // Mapa de dias com eventos e dias com prazo de tarefas
  const diasComEvento = new Set(eventosCache.map((ev) => String(ev.inicio).slice(0, 10)));
  const diasComTarefa = new Set(
    tarefasCache.filter((t) => t.prazo).map((t) => String(t.prazo).slice(0, 10))
  );

  const primeiroDiaSemana = new Date(calAno, calMes, 1).getDay();
  const totalDias = new Date(calAno, calMes + 1, 0).getDate();

  let html = "";
  for (let i = 0; i < primeiroDiaSemana; i++) {
    html += `<span class="cal-day is-empty"></span>`;
  }
  for (let dia = 1; dia <= totalDias; dia++) {
    const iso = `${calAno}-${String(calMes + 1).padStart(2, "0")}-${String(dia).padStart(2, "0")}`;
    const temEvento = diasComEvento.has(iso);
    const temTarefa = diasComTarefa.has(iso);
    const classes = ["cal-day"];
    if (temEvento || temTarefa) classes.push("has-items");
    if (iso === hojeStr) classes.push("is-today");
    if (iso === calDiaSelecionado) classes.push("is-selected");
    const dots =
      temEvento || temTarefa
        ? `<span class="cal-dots">${temEvento ? `<span class="cal-dot"></span>` : ""}${temTarefa ? `<span class="cal-dot task-dot"></span>` : ""}</span>`
        : "";
    html += `
      <button type="button" class="${classes.join(" ")}" data-cal-day="${iso}">
        <span>${dia}</span>
        ${dots}
      </button>`;
  }
  grid.innerHTML = html;

  const filtrados = calDiaSelecionado
    ? eventosCache.filter((ev) => String(ev.inicio).slice(0, 10) === calDiaSelecionado)
    : eventosCache;
  const tarefasDoDia = calDiaSelecionado
    ? tarefasCache.filter((t) => t.prazo && String(t.prazo).slice(0, 10) === calDiaSelecionado)
    : [];

  document.getElementById("agenda-count").textContent = String(eventosCache.length);
  if (calDiaSelecionado) {
    const [a, m, d] = calDiaSelecionado.split("-");
    selLabel.textContent = `Itens em ${d}/${m}/${a}`;
    showAllBtn.classList.remove("hidden");
  } else {
    selLabel.textContent = "Próximos compromissos";
    showAllBtn.classList.add("hidden");
  }

  const htmlEventos = filtrados
    .slice(0, 12)
    .map(
      (ev) => `
      <button type="button" class="row-card tx-clickable" data-event-edit="${ev.id}">
        <div>
          <p class="row-title">${escapeHtml(ev.titulo)}</p>
          <div class="tx-meta-line">
            <span class="num">${escapeHtml(ev.inicio.replace("T", " ").slice(0, 16))}</span>
            ${ev.conversa_id ? `<span class="chat-origin-tag">Chat</span>` : ""}
          </div>
        </div>
        <span class="sync-badge ${escapeHtml(ev.sync_status)}">${escapeHtml(ev.sync_status)}</span>
      </button>`
    )
    .join("");

  const htmlTarefasDia = tarefasDoDia
    .map(
      (t) => `
      <button type="button" class="row-card tx-clickable" data-task-edit="${t.id}">
        <div>
          <p class="row-title">${escapeHtml(t.titulo)}</p>
          <div class="tx-meta-line">
            <span>Prazo de tarefa</span>
            ${t.conversa_id ? `<span class="chat-origin-tag">Chat</span>` : ""}
          </div>
        </div>
        <span class="prio-dot ${escapeHtml(t.prioridade)}">${escapeHtml(t.prioridade)}</span>
      </button>`
    )
    .join("");

  agendaEl.innerHTML =
    !htmlEventos && !htmlTarefasDia
      ? `<p class="empty-state">${calDiaSelecionado ? "Nada agendado neste dia. Toque em + Evento." : "Nenhum compromisso agendado."}</p>`
      : htmlEventos + htmlTarefasDia;
}

async function carregarBriefing() {
  const briefResp = await fetch("/api/v1/briefing");
  if (!briefResp.ok) return;
  const b = await briefResp.json();

  document.getElementById("briefing-date").textContent = `Hoje · ${b.data_referencia}`;
  document.getElementById("briefing-meta").textContent = `Atualizado às ${b.hora_atual}`;

  // Tarefas (carrega antes do calendário para pintar os prazos no mês!)
  await carregarTarefas();

  // Agenda + Calendário Mensal
  eventosCache = b.proximos_eventos || [];
  renderCalendarioEAgenda();

  // Saúde (clicável para editar hábito + histórico de check-ins)
  habitosCache = b.saude_hoje || [];
  const saudeEl = document.getElementById("saude-list");
  saudeEl.innerHTML = !habitosCache.length
    ? `<p class="empty-state">Nenhum hábito ativo.</p>`
    : habitosCache
        .map(
          (h) => `
          <button type="button" class="cat-bar-item" data-habit-edit="${h.id}">
            <div class="habit-top">
              <span class="habit-name">${escapeHtml(h.nome)}</span>
              <span class="habit-val num">${h.total_hoje} / ${h.meta_diaria} ${escapeHtml(h.unidade)} (${h.percentual}%)</span>
            </div>
            <div class="progress-track">
              <div class="progress-fill ${h.concluido ? "done" : ""}" style="width: ${h.percentual}%"></div>
            </div>
          </button>`
        )
        .join("");

  await carregarCheckinsHoje();

  // Finanças (carregamento completo com filtros, cores e categorias)
  await carregarFinancas();

  // Notificações
  const notifs = b.notificacoes_pendentes || [];
  notifBadge.textContent = String(notifs.length);
  notifBadge.classList.toggle("hidden", notifs.length === 0);

  const notifsEl = document.getElementById("notificacoes-list");
  notifsEl.innerHTML = !notifs.length
    ? `<p class="empty-state">Nenhum lembrete pendente.</p>`
    : notifs
        .map(
          (n) => `
          <div class="row-card">
            <div>
              <p class="row-title">${escapeHtml(n.titulo)}</p>
              <p class="row-sub">${escapeHtml(n.mensagem)}</p>
            </div>
            <button type="button" class="link-action" data-read-notif="${n.id}">OK</button>
          </div>`
        )
        .join("");
}

// Eventos
inboxForm.addEventListener("submit", (e) => {
  e.preventDefault();
  enviarMensagem(inboxInput.value);
});

// Histórico de conversas e Nova conversa
document.getElementById("history-toggle-btn").addEventListener("click", async () => {
  await carregarHistoricoConversas();
  historyBackdrop.classList.remove("hidden");
});
document.getElementById("close-history-btn").addEventListener("click", () => {
  historyBackdrop.classList.add("hidden");
});
historyBackdrop.addEventListener("click", (e) => {
  if (e.target === historyBackdrop) historyBackdrop.classList.add("hidden");
});
document.getElementById("new-chat-btn").addEventListener("click", iniciarNovaConversa);
document.getElementById("sheet-new-chat-btn").addEventListener("click", iniciarNovaConversa);
historyList.addEventListener("click", async (e) => {
  const delBtn = e.target.closest("button[data-del-conv]");
  if (delBtn) {
    const id = Number(delBtn.dataset.delConv);
    const resp = await fetch(`/api/v1/conversas/${id}`, { method: "DELETE" });
    if (resp.ok) {
      if (conversaAtualId === id) {
        conversaAtualId = null;
        renderEmptyChat();
      }
      await carregarHistoricoConversas();
    }
    return;
  }

  const btn = e.target.closest("button[data-conv-id]");
  if (btn) {
    abrirConversa(Number(btn.dataset.convId));
  }
});

// Botões rápidos de Saúde
document.querySelectorAll(".quick-tile").forEach((tile) => {
  tile.addEventListener("click", async () => {
    await fetch("/api/v1/saude/checkins", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        nome_habito: tile.dataset.health,
        quantidade: Number(tile.dataset.qty),
        observacao: "Atalho mobile",
      }),
    });
    await carregarBriefing();
  });
});

// Eventos de Finanças (mês, filtros, edição manual, categorias e ir para conversa)
document.getElementById("fin-prev-month").addEventListener("click", () => mudarMes(-1));
document.getElementById("fin-next-month").addEventListener("click", () => mudarMes(1));

document.getElementById("fin-type-filters").addEventListener("click", (e) => {
  const pill = e.target.closest("button[data-type]");
  if (!pill) return;
  finTipoFiltro = pill.dataset.type;
  document.querySelectorAll("#fin-type-filters .filter-pill").forEach((b) =>
    b.classList.toggle("active", b === pill)
  );
  carregarFinancas();
});

document.getElementById("financas-categorias").addEventListener("click", (e) => {
  const item = e.target.closest("button[data-filter-cat]");
  if (!item) return;
  const cat = item.dataset.filterCat;
  finCategoriaFiltro = finCategoriaFiltro === cat ? "" : cat;
  carregarFinancas();
});

document.getElementById("clear-cat-filter-btn").addEventListener("click", () => {
  finCategoriaFiltro = "";
  carregarFinancas();
});

document.getElementById("open-new-tx-btn").addEventListener("click", () => abrirSheetTransacao(null));

document.getElementById("transacoes-list").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-tx-id]");
  if (!btn) return;
  const tx = transacoesCache.find((t) => t.id === Number(btn.dataset.txId));
  if (tx) abrirSheetTransacao(tx);
});

const txBackdrop = document.getElementById("tx-sheet-backdrop");
document.getElementById("close-tx-sheet-btn").addEventListener("click", () => txBackdrop.classList.add("hidden"));
txBackdrop.addEventListener("click", (e) => {
  if (e.target === txBackdrop) txBackdrop.classList.add("hidden");
});

document.getElementById("tx-go-chat-btn").addEventListener("click", async () => {
  if (!txConversaOrigemId) return;
  txBackdrop.classList.add("hidden");
  await abrirConversa(txConversaOrigemId);
});

document.getElementById("tx-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = document.getElementById("tx-id-input").value;
  const payload = {
    tipo: document.getElementById("tx-tipo-select").value,
    valor: Number(document.getElementById("tx-valor-input").value),
    descricao: document.getElementById("tx-desc-input").value.trim(),
    categoria: document.getElementById("tx-cat-select").value,
    data_transacao: document.getElementById("tx-data-input").value,
  };

  const url = id ? `/api/v1/financas/transacoes/${id}` : "/api/v1/financas/transacoes";
  const method = id ? "PATCH" : "POST";
  const resp = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (resp.ok) {
    txBackdrop.classList.add("hidden");
    await carregarFinancas();
  }
});

document.getElementById("tx-delete-btn").addEventListener("click", async () => {
  const id = document.getElementById("tx-id-input").value;
  if (!id) return;
  const resp = await fetch(`/api/v1/financas/transacoes/${id}`, { method: "DELETE" });
  if (resp.ok) {
    txBackdrop.classList.add("hidden");
    await carregarFinancas();
  }
});

const catBackdrop = document.getElementById("cat-sheet-backdrop");
document.getElementById("open-categories-btn").addEventListener("click", async () => {
  await carregarFinancas();
  renderListaGerenciarCategorias();
  catBackdrop.classList.remove("hidden");
});
document.getElementById("close-cat-sheet-btn").addEventListener("click", () => catBackdrop.classList.add("hidden"));
catBackdrop.addEventListener("click", (e) => {
  if (e.target === catBackdrop) catBackdrop.classList.add("hidden");
});

document.getElementById("cat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const nameInput = document.getElementById("cat-name-input");
  const colorInput = document.getElementById("cat-color-input");
  const resp = await fetch("/api/v1/financas/categorias", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nome: nameInput.value.trim(), cor: colorInput.value }),
  });
  if (resp.ok) {
    nameInput.value = "";
    await carregarFinancas();
    renderListaGerenciarCategorias();
  }
});

document.getElementById("cat-manage-list").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-del-cat]");
  if (!btn) return;
  const resp = await fetch(`/api/v1/financas/categorias/${btn.dataset.delCat}`, { method: "DELETE" });
  if (resp.ok) {
    await carregarFinancas();
    renderListaGerenciarCategorias();
  }
});

// --- Eventos de Hoje (Tarefas & Agenda) e Saúde ---
const taskBackdrop = document.getElementById("task-sheet-backdrop");
const eventBackdrop = document.getElementById("event-sheet-backdrop");
const habitBackdrop = document.getElementById("habit-sheet-backdrop");

function abrirSheetTarefa(t = null) {
  document.getElementById("task-id-input").value = t ? String(t.id) : "";
  document.getElementById("task-title-input").value = t ? t.titulo : "";
  document.getElementById("task-prio-select").value = t ? t.prioridade : "MEDIA";
  document.getElementById("task-prazo-input").value = t && t.prazo ? String(t.prazo).slice(0, 10) : "";
  taskConversaOrigemId = t && t.conversa_id ? t.conversa_id : null;
  document.getElementById("task-sheet-title").textContent = t ? "Editar tarefa" : "Nova tarefa";
  document.getElementById("task-go-chat-btn").classList.toggle("hidden", !taskConversaOrigemId);
  document.getElementById("task-delete-btn").classList.toggle("hidden", !t);
  taskBackdrop.classList.remove("hidden");
}

function abrirSheetEvento(ev = null) {
  const agora = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const baseDate = calDiaSelecionado || dataLocalISO(0);
  const defaultStart = `${baseDate}T${pad(agora.getHours())}:00`;
  const defaultEnd = `${baseDate}T${pad(Math.min(agora.getHours() + 1, 23))}:00`;

  document.getElementById("event-id-input").value = ev ? String(ev.id) : "";
  document.getElementById("event-title-input").value = ev ? ev.titulo : "";
  document.getElementById("event-start-input").value = ev ? ev.inicio.slice(0, 16) : defaultStart;
  document.getElementById("event-end-input").value = ev ? ev.fim.slice(0, 16) : defaultEnd;
  document.getElementById("event-desc-input").value = ev ? ev.descricao || "" : "";
  eventConversaOrigemId = ev && ev.conversa_id ? ev.conversa_id : null;
  document.getElementById("event-sheet-title").textContent = ev ? "Editar compromisso" : "Novo compromisso";
  document.getElementById("event-go-chat-btn").classList.toggle("hidden", !eventConversaOrigemId);
  document.getElementById("event-delete-btn").classList.toggle("hidden", !ev);
  eventBackdrop.classList.remove("hidden");
}

function abrirSheetHabito(h = null) {
  document.getElementById("habit-id-input").value = h ? String(h.id) : "";
  document.getElementById("habit-name-input").value = h ? h.nome : "";
  document.getElementById("habit-meta-input").value = h ? String(h.meta_diaria) : "1";
  document.getElementById("habit-unit-input").value = h ? h.unidade : "unidade";
  document.getElementById("habit-time-input").value = h && h.horario_lembrete ? h.horario_lembrete : "";
  document.getElementById("habit-sheet-title").textContent = h ? "Editar hábito" : "Novo hábito";
  document.getElementById("habit-delete-btn").classList.toggle("hidden", !h);
  habitBackdrop.classList.remove("hidden");
}

// Calendário Mensal (navegação e seleção de dia)
document.getElementById("cal-prev-month").addEventListener("click", () => {
  calMes -= 1;
  if (calMes < 0) { calMes = 11; calAno -= 1; }
  renderCalendarioEAgenda();
});
document.getElementById("cal-next-month").addEventListener("click", () => {
  calMes += 1;
  if (calMes > 11) { calMes = 0; calAno += 1; }
  renderCalendarioEAgenda();
});
document.getElementById("cal-grid").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-cal-day]");
  if (!btn) return;
  const dia = btn.dataset.calDay;
  calDiaSelecionado = calDiaSelecionado === dia ? null : dia;
  renderCalendarioEAgenda();
});
document.getElementById("cal-show-all-btn").addEventListener("click", () => {
  calDiaSelecionado = null;
  renderCalendarioEAgenda();
});

document.getElementById("open-new-task-btn").addEventListener("click", () => abrirSheetTarefa(null));
document.getElementById("open-new-event-btn").addEventListener("click", () => abrirSheetEvento(null));
document.getElementById("open-new-habit-btn").addEventListener("click", () => abrirSheetHabito(null));

document.getElementById("close-task-sheet-btn").addEventListener("click", () => taskBackdrop.classList.add("hidden"));
taskBackdrop.addEventListener("click", (e) => { if (e.target === taskBackdrop) taskBackdrop.classList.add("hidden"); });

document.getElementById("close-event-sheet-btn").addEventListener("click", () => eventBackdrop.classList.add("hidden"));
eventBackdrop.addEventListener("click", (e) => { if (e.target === eventBackdrop) eventBackdrop.classList.add("hidden"); });

document.getElementById("close-habit-sheet-btn").addEventListener("click", () => habitBackdrop.classList.add("hidden"));
habitBackdrop.addEventListener("click", (e) => { if (e.target === habitBackdrop) habitBackdrop.classList.add("hidden"); });

document.getElementById("task-status-filters").addEventListener("click", (e) => {
  const pill = e.target.closest("button[data-status]");
  if (!pill) return;
  taskStatusFiltro = pill.dataset.status;
  document.querySelectorAll("#task-status-filters .filter-pill").forEach((b) => b.classList.toggle("active", b === pill));
  carregarTarefas();
});

document.getElementById("tarefas-list").addEventListener("change", async (e) => {
  if (e.target.matches("input[data-task-toggle]")) {
    const id = e.target.dataset.taskToggle;
    const novoStatus = e.target.checked ? "CONCLUIDA" : "PENDENTE";
    await fetch(`/api/v1/tarefas/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: novoStatus }),
    });
    await carregarTarefas();
  }
});

document.getElementById("tarefas-list").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-task-edit]");
  if (!btn) return;
  const t = tarefasCache.find((item) => item.id === Number(btn.dataset.taskEdit));
  if (t) abrirSheetTarefa(t);
});

document.getElementById("task-go-chat-btn").addEventListener("click", async () => {
  if (!taskConversaOrigemId) return;
  taskBackdrop.classList.add("hidden");
  await abrirConversa(taskConversaOrigemId);
});

document.getElementById("task-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = document.getElementById("task-id-input").value;
  const prazoVal = document.getElementById("task-prazo-input").value;
  const payload = {
    titulo: document.getElementById("task-title-input").value.trim(),
    prioridade: document.getElementById("task-prio-select").value,
    prazo: prazoVal || null,
  };
  const resp = await fetch(id ? `/api/v1/tarefas/${id}` : "/api/v1/tarefas", {
    method: id ? "PATCH" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (resp.ok) {
    taskBackdrop.classList.add("hidden");
    await carregarTarefas();
  }
});

document.getElementById("task-delete-btn").addEventListener("click", async () => {
  const id = document.getElementById("task-id-input").value;
  if (!id) return;
  if ((await fetch(`/api/v1/tarefas/${id}`, { method: "DELETE" })).ok) {
    taskBackdrop.classList.add("hidden");
    await carregarTarefas();
  }
});

document.getElementById("agenda-list").addEventListener("click", (e) => {
  const evBtn = e.target.closest("button[data-event-edit]");
  if (evBtn) {
    const ev = eventosCache.find((item) => item.id === Number(evBtn.dataset.eventEdit));
    if (ev) abrirSheetEvento(ev);
    return;
  }
  const tBtn = e.target.closest("button[data-task-edit]");
  if (tBtn) {
    const t = tarefasCache.find((item) => item.id === Number(tBtn.dataset.taskEdit));
    if (t) abrirSheetTarefa(t);
  }
});

document.getElementById("event-go-chat-btn").addEventListener("click", async () => {
  if (!eventConversaOrigemId) return;
  eventBackdrop.classList.add("hidden");
  await abrirConversa(eventConversaOrigemId);
});

document.getElementById("event-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = document.getElementById("event-id-input").value;
  const payload = {
    titulo: document.getElementById("event-title-input").value.trim(),
    inicio: document.getElementById("event-start-input").value + ":00",
    fim: document.getElementById("event-end-input").value + ":00",
    descricao: document.getElementById("event-desc-input").value.trim(),
  };
  const resp = await fetch(id ? `/api/v1/agenda/${id}` : "/api/v1/agenda", {
    method: id ? "PATCH" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (resp.ok) {
    eventBackdrop.classList.add("hidden");
    await carregarBriefing();
  }
});

document.getElementById("event-delete-btn").addEventListener("click", async () => {
  const id = document.getElementById("event-id-input").value;
  if (!id) return;
  if ((await fetch(`/api/v1/agenda/${id}`, { method: "DELETE" })).ok) {
    eventBackdrop.classList.add("hidden");
    await carregarBriefing();
  }
});

document.getElementById("saude-list").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-habit-edit]");
  if (!btn) return;
  const h = habitosCache.find((item) => item.id === Number(btn.dataset.habitEdit));
  if (h) abrirSheetHabito(h);
});

document.getElementById("habit-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    nome: document.getElementById("habit-name-input").value.trim(),
    meta_diaria: Number(document.getElementById("habit-meta-input").value),
    unidade: document.getElementById("habit-unit-input").value.trim(),
    horario_lembrete: document.getElementById("habit-time-input").value || null,
  };
  const resp = await fetch("/api/v1/saude/habitos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (resp.ok) {
    habitBackdrop.classList.add("hidden");
    await carregarBriefing();
  }
});

document.getElementById("habit-delete-btn").addEventListener("click", async () => {
  const id = document.getElementById("habit-id-input").value;
  if (!id) return;
  if ((await fetch(`/api/v1/saude/habitos/${id}`, { method: "DELETE" })).ok) {
    habitBackdrop.classList.add("hidden");
    await carregarBriefing();
  }
});

document.getElementById("checkins-list").addEventListener("click", async (e) => {
  const delBtn = e.target.closest("button[data-del-checkin]");
  if (delBtn) {
    if ((await fetch(`/api/v1/saude/checkins/${delBtn.dataset.delCheckin}`, { method: "DELETE" })).ok) {
      await carregarBriefing();
    }
    return;
  }
  const chatBtn = e.target.closest("button[data-checkin-chat]");
  if (chatBtn) {
    await abrirConversa(Number(chatBtn.dataset.checkinChat));
  }
});

// Bottom sheet de notificações
document.getElementById("notif-toggle-btn").addEventListener("click", () => {
  notifBackdrop.classList.remove("hidden");
});
document.getElementById("close-sheet-btn").addEventListener("click", () => {
  notifBackdrop.classList.add("hidden");
});
notifBackdrop.addEventListener("click", (e) => {
  if (e.target === notifBackdrop) notifBackdrop.classList.add("hidden");
});

document.getElementById("notificacoes-list").addEventListener("click", async (e) => {
  if (e.target.matches("button[data-read-notif]")) {
    await fetch(`/api/v1/notificacoes/${e.target.dataset.readNotif}/lida`, { method: "PATCH" });
    await carregarBriefing();
  }
});

async function ativarNotificacoesCelular() {
  if (!("Notification" in window)) return;
  const perm = await Notification.requestPermission();
  if (perm === "granted") {
    new Notification("Synapse", { body: "Alertas no celular ativados com sucesso!" });
  }
}

document.getElementById("enable-push-btn").addEventListener("click", ativarNotificacoesCelular);
document.getElementById("cfg-enable-push-btn").addEventListener("click", ativarNotificacoesCelular);

// Conectar / Trocar chave / Desconectar IA em Ajustes
document.getElementById("ia-change-key-btn").addEventListener("click", () => {
  document.getElementById("ia-connected-box").classList.add("hidden");
  document.getElementById("gemini-config-form").classList.remove("hidden");
  document.getElementById("gemini-config-feedback").classList.add("hidden");
  document.getElementById("gemini-key-input").focus();
});

document.getElementById("ia-cancel-change-btn").addEventListener("click", () => {
  document.getElementById("gemini-config-form").classList.add("hidden");
  document.getElementById("ia-connected-box").classList.remove("hidden");
});

document.getElementById("gemini-config-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const keyInput = document.getElementById("gemini-key-input");
  const connectBtn = document.getElementById("gemini-connect-btn");
  const feedback = document.getElementById("gemini-config-feedback");

  const apiKey = keyInput.value.trim();
  if (!apiKey) {
    feedback.textContent = "Cole sua chave API para conectar.";
    feedback.className = "form-feedback error";
    return;
  }

  connectBtn.disabled = true;
  connectBtn.textContent = "Validando...";
  feedback.classList.add("hidden");

  try {
    const resp = await fetch("/api/v1/config/ia", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey }),
    });
    const data = await resp.json();

    if (!resp.ok) {
      feedback.textContent = data.detail || "Chave inválida. Verifique e tente novamente.";
      feedback.className = "form-feedback error";
      return;
    }

    keyInput.value = "";
    atualizarVisaoIA(true, data.modelos_disponiveis, data.modelo);
    const connFeedback = document.getElementById("ia-connected-feedback");
    connFeedback.textContent = `Conectado! ${data.modelos_disponiveis.length} modelos disponíveis.`;
    connFeedback.className = "form-feedback";
    setTimeout(() => connFeedback.classList.add("hidden"), 3500);
    await carregarStatus();
  } catch {
    feedback.textContent = "Erro de conexão ao validar a chave.";
    feedback.className = "form-feedback error";
  } finally {
    connectBtn.disabled = false;
    connectBtn.textContent = "Conectar";
  }
});

document.getElementById("gemini-model-select").addEventListener("change", async (e) => {
  const feedback = document.getElementById("ia-connected-feedback");
  const activeModelEl = document.getElementById("cfg-ia-active-model");
  const model = e.target.value;
  if (!model) return;
  const resp = await fetch("/api/v1/config/ia/modelo", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model }),
  });
  if (resp.ok) {
    if (activeModelEl) activeModelEl.textContent = model;
    feedback.textContent = `Modelo ativo alterado para ${model}.`;
    feedback.className = "form-feedback";
    setTimeout(() => feedback.classList.add("hidden"), 3000);
  }
});

document.getElementById("gemini-disconnect-btn").addEventListener("click", async () => {
  const feedback = document.getElementById("gemini-config-feedback");
  const resp = await fetch("/api/v1/config/ia", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: "" }),
  });
  if (resp.ok) {
    atualizarVisaoIA(false);
    feedback.textContent = "Desconectado. Voltando para o modo local.";
    feedback.className = "form-feedback";
    await carregarStatus();
    setTimeout(() => feedback.classList.add("hidden"), 3000);
  }
});

// Salvar meta de água nas Configurações
document.getElementById("water-goal-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const meta = Number(document.getElementById("water-goal-input").value);
  const horario = document.getElementById("water-time-input").value || null;
  const feedback = document.getElementById("water-goal-feedback");

  const resp = await fetch("/api/v1/saude/habitos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nome: "Agua", meta_diaria: meta, unidade: "ml", horario_lembrete: horario }),
  });

  if (resp.ok) {
    feedback.textContent = `Meta atualizada para ${meta} ml/dia.`;
    feedback.classList.remove("hidden");
    await carregarBriefing();
    setTimeout(() => feedback.classList.add("hidden"), 3000);
  }
});

document.getElementById("dispatch-btn").addEventListener("click", async () => {
  const resp = await fetch("/api/v1/notificacoes/disparar", { method: "POST" });
  const data = await resp.json();
  if (data.total_disparadas > 0 && "Notification" in window && Notification.permission === "granted") {
    data.itens.forEach((item) => new Notification(item.titulo, { body: item.detalhe }));
  }
  await carregarBriefing();
});

// Comando de Voz (Web Speech API — pt-BR)
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SpeechRecognition) {
  const recognition = new SpeechRecognition();
  recognition.lang = "pt-BR";
  recognition.interimResults = false;

  micBtn.addEventListener("click", () => {
    micBtn.classList.add("recording");
    recognition.start();
  });

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    inboxInput.value = transcript;
    micBtn.classList.remove("recording");
    enviarMensagem(transcript);
  };

  recognition.onerror = () => micBtn.classList.remove("recording");
  recognition.onend = () => micBtn.classList.remove("recording");
} else {
  micBtn.title = "Ditado por voz não suportado neste navegador";
  micBtn.style.opacity = "0.45";
}

carregarStatus();
carregarBriefing();
