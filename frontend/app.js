const chatFeed = document.getElementById("chat-feed");
const inboxForm = document.getElementById("inbox-form");
const inboxInput = document.getElementById("inbox-input");
const sendBtn = document.getElementById("send-btn");
const micBtn = document.getElementById("mic-btn");
const engineStatus = document.getElementById("engine-status");
const screenTitle = document.getElementById("screen-title");
const notifBadge = document.getElementById("notif-badge");
const notifBackdrop = document.getElementById("notif-sheet-backdrop");

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

// Navegação por Bottom Tab Bar
document.querySelectorAll(".tab-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    const tab = btn.dataset.tab;
    document.querySelectorAll(".tab-item").forEach((b) => b.classList.toggle("active", b === btn));
    document.querySelectorAll(".screen").forEach((s) => {
      const isTarget = s.id === `screen-${tab}`;
      s.classList.toggle("active", isTarget);
      if (isTarget) {
        screenTitle.textContent = s.dataset.title || "Synapse";
      }
    });
    if (tab !== "chat") {
      carregarBriefing();
    }
  });
});

// Mensagens no Inbox
function appendUserMessage(text) {
  const el = document.createElement("div");
  el.className = "msg user";
  el.innerHTML = `<div class="msg-bubble">${escapeHtml(text)}</div>`;
  chatFeed.appendChild(el);
  chatFeed.scrollTop = chatFeed.scrollHeight;
}

function appendAssistantMessage(data) {
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
  el.innerHTML = `
    <div class="msg-bubble">${escapeHtml(data.resposta)}</div>
    ${tags ? `<div class="action-list">${tags}</div>` : ""}
    <div class="msg-meta">${modo} · ${data.latencia_ms}ms</div>
  `;
  chatFeed.appendChild(el);
  chatFeed.scrollTop = chatFeed.scrollHeight;
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
      body: JSON.stringify({ mensagem: clean }),
    });
    if (!resp.ok) throw new Error("Falha ao processar.");
    const data = await resp.json();
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

async function carregarStatus() {
  try {
    const resp = await fetch("/api/v1/health");
    const data = await resp.json();
    const cfgIa = document.getElementById("cfg-ia-status");
    const cfgGcal = document.getElementById("cfg-gcal-status");
    const cfgTz = document.getElementById("cfg-tz");

    if (data.ia_ativa) {
      engineStatus.textContent = "Gemini IA Ativo";
      engineStatus.classList.add("ai-on");
      if (cfgIa) {
        cfgIa.textContent = "ATIVO";
        cfgIa.className = "sync-badge SINCRONIZADO";
      }
    } else {
      engineStatus.textContent = "Modo Local · PWA";
      if (cfgIa) {
        cfgIa.textContent = "LOCAL";
        cfgIa.className = "sync-badge PENDENTE";
      }
    }

    if (cfgGcal) {
      cfgGcal.textContent = data.google_calendar_ativo ? "SINCRONIZADO" : "PENDENTE";
      cfgGcal.className = `sync-badge ${data.google_calendar_ativo ? "SINCRONIZADO" : "PENDENTE"}`;
    }
    if (cfgTz) {
      cfgTz.textContent = data.timezone;
    }
  } catch {
    engineStatus.textContent = "Offline";
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

document.querySelectorAll(".prompt-chip").forEach((btn) => {
  btn.addEventListener("click", () => enviarMensagem(btn.dataset.prompt || ""));
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
