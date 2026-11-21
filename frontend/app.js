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

async function carregarBriefing() {
  const [briefResp, transResp] = await Promise.all([
    fetch("/api/v1/briefing"),
    fetch("/api/v1/financas/transacoes?limite=10"),
  ]);
  if (!briefResp.ok) return;
  const b = await briefResp.json();
  const transacoes = transResp.ok ? await transResp.json() : [];

  document.getElementById("briefing-date").textContent = `Hoje · ${b.data_referencia}`;
  document.getElementById("briefing-meta").textContent = `Atualizado às ${b.hora_atual}`;

  // Agenda
  const eventos = b.proximos_eventos || [];
  document.getElementById("agenda-count").textContent = String(eventos.length);
  const agendaEl = document.getElementById("agenda-list");
  agendaEl.innerHTML = !eventos.length
    ? `<p class="empty-state">Nenhum compromisso agendado.</p>`
    : eventos
        .slice(0, 8)
        .map(
          (ev) => `
          <div class="row-card">
            <div>
              <p class="row-title">${escapeHtml(ev.titulo)}</p>
              <p class="row-sub num">${escapeHtml(ev.inicio.replace("T", " ").slice(0, 16))}</p>
            </div>
            <span class="sync-badge ${escapeHtml(ev.sync_status)}">${escapeHtml(ev.sync_status)}</span>
          </div>`
        )
        .join("");

  // Tarefas
  const tarefas = b.tarefas_pendentes || [];
  document.getElementById("tarefas-count").textContent = String(tarefas.length);
  const tarefasEl = document.getElementById("tarefas-list");
  tarefasEl.innerHTML = !tarefas.length
    ? `<p class="empty-state">Nenhuma tarefa pendente.</p>`
    : tarefas
        .map(
          (t) => `
          <label class="task-row">
            <input type="checkbox" data-task-id="${t.id}" />
            <span class="task-title">${escapeHtml(t.titulo)}</span>
            <span class="prio-dot ${escapeHtml(t.prioridade)}">${escapeHtml(t.prioridade)}</span>
          </label>`
        )
        .join("");

  // Saúde
  const saudeEl = document.getElementById("saude-list");
  saudeEl.innerHTML = !b.saude_hoje.length
    ? `<p class="empty-state">Nenhum hábito ativo.</p>`
    : b.saude_hoje
        .map(
          (h) => `
          <div class="habit-row">
            <div class="habit-top">
              <span class="habit-name">${escapeHtml(h.nome)}</span>
              <span class="habit-val num">${h.total_hoje} / ${h.meta_diaria} ${escapeHtml(h.unidade)} (${h.percentual}%)</span>
            </div>
            <div class="progress-track">
              <div class="progress-fill ${h.concluido ? "done" : ""}" style="width: ${h.percentual}%"></div>
            </div>
          </div>`
        )
        .join("");

  // Finanças
  const fin = b.resumo_financeiro;
  document.getElementById("financas-periodo").textContent = `Período ${fin.periodo}`;
  document.getElementById("fin-receitas").textContent = brl.format(fin.total_receitas);
  document.getElementById("fin-despesas").textContent = brl.format(fin.total_despesas);
  document.getElementById("fin-saldo").textContent = brl.format(fin.saldo);

  const catsEl = document.getElementById("financas-categorias");
  catsEl.innerHTML = !fin.despesas_por_categoria.length
    ? `<p class="empty-state">Sem despesas neste mês.</p>`
    : fin.despesas_por_categoria
        .map(
          (c) => `
          <div class="cat-row">
            <span>${escapeHtml(c.categoria)}</span>
            <strong class="num">${brl.format(c.total)}</strong>
          </div>`
        )
        .join("");

  const transEl = document.getElementById("transacoes-list");
  transEl.innerHTML = !transacoes.length
    ? `<p class="empty-state">Nenhum lançamento ainda.</p>`
    : transacoes
        .map(
          (tr) => `
          <div class="row-card">
            <div>
              <p class="row-title">${escapeHtml(tr.descricao)}</p>
              <p class="row-sub">${escapeHtml(tr.categoria)} · ${escapeHtml(tr.data_transacao)}</p>
            </div>
            <strong class="num ${tr.tipo === "RECEITA" ? "positive" : "negative"}">
              ${tr.tipo === "RECEITA" ? "+" : "-"}${brl.format(tr.valor)}
            </strong>
          </div>`
        )
        .join("");

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

// Concluir tarefa
document.getElementById("tarefas-list").addEventListener("change", async (e) => {
  if (e.target.matches("input[data-task-id]")) {
    await fetch(`/api/v1/tarefas/${e.target.dataset.taskId}/concluir`, { method: "PATCH" });
    await carregarBriefing();
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
