// NLA Activation Inspector
//
// Every value rendered here comes from the running server -- there is no mock
// data and no fallback path. If the backend is down the UI says so rather than
// showing plausible numbers, because a fabricated FVE is worse than a blank one.
//
// Backend contract (server/main.py):
//   GET  /api/health   -> {status, model, probe_layer, d_model, dtype, device,
//                          checkpoint_av, checkpoint_ar, fve_baseline}
//   POST /api/chat     -> {messages, tokens, token_ids, is_special,
//                          assistant_token_start, assistant_text}
//   POST /api/analyze  -> {position, explanation, reconstruction, fve}

const $ = (sel) => document.querySelector(sel);

// ---------------------------------------------------------------- state
let state = {
  messages:       [],    // [{role, content}]
  tokens:         [],    // string[]
  tokenIds:       [],    // number[]
  isSpecial:      [],    // bool[]
  assistantStart: 0,     // index of the first assistant token
  selectedIndex:  null,  // currently-selected token index
  history:        [],    // [{index, token, cosine, fve}] most-recent-first
  health:         null,  // last /api/health payload
  source:         "chat",// "chat" | "traces" -- what populated the context
};

const HISTORY_MAX = 12;

// ---------------------------------------------------------------- api
async function apiPost(path, body) {
  const res = await fetch(path, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "request failed");
  }
  return res.json();
}

function readSettings() {
  return {
    max_new_tokens: parseInt($("#max-tokens").value, 10),
    temperature:    parseFloat($("#temperature").value),
    top_p:          parseFloat($("#top-p").value),
  };
}

// ---------------------------------------------------------------- health
async function loadHealth() {
  try {
    const res = await fetch("/api/health");
    if (!res.ok) throw new Error(res.statusText);
    state.health = await res.json();
  } catch {
    state.health = null;
  }
  renderHealth();
}

function renderHealth() {
  const h        = state.health;
  const dot      = $("#status-dot");
  const statusEl = $("#status-text");
  const pill     = $("#probe-pill");

  if (!h) {
    $("#model-name").textContent = "server unreachable";
    pill.textContent = "probe: —";
    pill.classList.remove("live");
    dot.className    = "dot error";
    statusEl.textContent = "offline";
    renderConfig();
    return;
  }

  const ok = h.status === "ok";
  $("#model-name").textContent = h.model || "unknown model";
  pill.textContent = `L${h.probe_layer}`;
  pill.classList.toggle("live", ok);
  dot.className        = ok ? "dot live" : "dot";
  statusEl.textContent = ok ? "live" : h.status;

  // The help text names the probe layer rather than hardcoding "layer 16".
  const helpLayer = $("#help-layer");
  if (helpLayer && h.probe_layer != null) helpLayer.textContent = h.probe_layer;

  // FVE is only meaningful against the corpus-mean baseline; say so when the
  // activations dataset is absent rather than silently reporting nothing.
  $("#m-fve-hint").textContent =
    h.fve_baseline === "corpus mean"
      ? "vs corpus-mean baseline"
      : "baseline unavailable — run Stage 0";

  renderConfig();
}

function renderConfig() {
  const dl = $("#config-list");
  dl.innerHTML = "";
  const h = state.health;
  if (!h) {
    dl.innerHTML = `<dt>status</dt><dd>server unreachable</dd>`;
    return;
  }
  const rows = [
    ["status",       h.status],
    ["backbone",     h.model],
    ["probe layer",  h.probe_layer],
    ["d_model",      h.d_model ?? "—"],
    ["dtype",        h.dtype],
    ["device",       h.device],
    ["AV",           h.checkpoint_av],
    ["AR",           h.checkpoint_ar],
    ["FVE baseline", h.fve_baseline],
  ];
  for (const [k, v] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = k;
    const dd = document.createElement("dd");
    dd.textContent = v == null ? "—" : String(v);
    dl.append(dt, dd);
  }
}

// ---------------------------------------------------------------- pipeline
// Drives the status dots from the real request lifecycle. `stages` is the set
// currently working; everything else resets to idle (or stays done).
function setPipeline(working, done = []) {
  document.querySelectorAll(".pipeline .node").forEach((node) => {
    const stage = node.dataset.stage;
    const dot   = node.querySelector(".node-status");
    if (working.includes(stage)) {
      dot.dataset.status = "working";
      node.classList.add("active");
    } else if (done.includes(stage)) {
      dot.dataset.status = "done";
      node.classList.remove("active");
    } else {
      dot.dataset.status = "idle";
      node.classList.remove("active");
    }
  });
}

function pipelineError(stage) {
  const node = document.querySelector(`.pipeline .node[data-stage="${stage}"]`);
  if (node) node.querySelector(".node-status").dataset.status = "error";
}

// ---------------------------------------------------------------- chat flow
async function sendMessage() {
  const text = $("#chat-input").value.trim();
  if (!text) return;

  const settings = readSettings();
  $("#send-btn").disabled = true;
  $("#chat-input").value  = "";

  // Sending replaces the context with this chat, so leave trace-browsing mode
  // rather than showing a trace picker that no longer matches what is displayed.
  if (state.source !== "chat") setSource("chat");

  // Optimistic: show the user message plus an assistant placeholder.
  state.messages.push({ role: "user", content: text });
  renderMessages({ withPlaceholder: true });
  setPipeline(["target"]);

  try {
    const res = await apiPost("/api/chat", { messages: state.messages, ...settings });
    state.messages       = res.messages;
    state.tokens         = res.tokens;
    state.tokenIds       = res.token_ids;
    state.isSpecial      = res.is_special;
    state.assistantStart = res.assistant_token_start;
    state.selectedIndex  = null;
    state.history        = [];

    renderMessages();
    renderTokens();
    renderHistory();
    resetExplanation();
    setPipeline([], ["target"]);
  } catch (e) {
    state.messages.pop();          // undo the optimistic user message
    renderMessages();
    pipelineError("target");
    explanationError(`Chat failed: ${e.message}`);
  } finally {
    $("#send-btn").disabled = false;
    $("#chat-input").focus();
  }
}

function newChat() {
  state = {
    ...state,
    messages: [], tokens: [], tokenIds: [], isSpecial: [],
    assistantStart: 0, selectedIndex: null, history: [],
  };
  $("#chat-input").value = "";
  renderMessages();
  renderTokens();
  renderHistory();
  resetExplanation();
  resetMetrics();
  setPipeline([]);
  $("#chat-input").focus();
}

// ---------------------------------------------------------------- rendering
function renderMessages({ withPlaceholder = false } = {}) {
  const div = $("#messages");
  div.innerHTML = "";

  if (state.messages.length === 0 && !withPlaceholder) {
    div.innerHTML = `<div class="placeholder">No messages yet. Type something and press Enter.</div>`;
    return;
  }

  for (const m of state.messages) {
    const el = document.createElement("div");
    el.className   = `message ${m.role}`;
    el.textContent = m.content;
    div.appendChild(el);
  }

  if (withPlaceholder) {
    const el = document.createElement("div");
    el.className   = "message assistant loading";
    el.textContent = "generating…";
    div.appendChild(el);
  }

  div.scrollTop = div.scrollHeight;
}

function renderTokens() {
  const div = $("#tokens");
  div.innerHTML = "";
  $("#token-count").textContent =
    `${state.tokens.length} token${state.tokens.length === 1 ? "" : "s"}`;

  if (state.tokens.length === 0) {
    div.innerHTML = `<div class="placeholder">Send a message to populate the model context.</div>`;
    return;
  }

  state.tokens.forEach((t, i) => {
    const span = document.createElement("span");
    span.className = "token";
    if (state.isSpecial[i])        span.classList.add("special");
    if (i >= state.assistantStart) span.classList.add("in-assistant");
    span.textContent   = displayToken(t);
    span.dataset.index = i;
    span.title         = `token ${i}${state.isSpecial[i] ? " (special)" : ""}`;
    span.addEventListener("click", () => analyzeToken(i));
    div.appendChild(span);
  });
}

// Newlines would collapse the inline token layout; show a visible glyph and
// keep the real string in the tooltip.
function displayToken(t) {
  return t.replace(/\n/g, "⏎");
}

function updateContextHighlight() {
  const tokens = document.querySelectorAll("#tokens .token");
  tokens.forEach((el) => el.classList.remove("selected", "in-context", "loading"));
  if (state.selectedIndex == null) return;
  for (let i = 0; i < state.selectedIndex; i++) tokens[i].classList.add("in-context");
  tokens[state.selectedIndex].classList.add("selected");
}

// ---------------------------------------------------------------- analyse
async function analyzeToken(index) {
  state.selectedIndex = index;
  updateContextHighlight();
  selectTab("explanation");

  const tokenEl = document.querySelectorAll("#tokens .token")[index];
  tokenEl.classList.add("loading");

  $("#nla-empty").classList.add("hidden");
  $("#nla-body").classList.remove("hidden");
  $("#nla-token").textContent    = displayToken(state.tokens[index]);
  $("#nla-position").textContent =
    `position ${index}${state.isSpecial[index] ? " · special" : ""}`;
  $("#inspector-sub").textContent = `token ${index}`;

  $("#nla-explanation").textContent = "Generating explanation…";
  $("#nla-explanation").classList.add("muted");
  $("#nla-cosine").textContent = "—";
  $("#nla-fve").textContent    = "—";

  // AV generation then AR reconstruction happen in one request; the target
  // forward pass to get the activation runs first inside the same call.
  setPipeline(["target", "av", "ar"]);

  try {
    const res = await apiPost("/api/analyze", {
      token_ids: state.tokenIds,
      position:  index,
    });

    $("#nla-explanation").textContent = res.explanation || "(empty)";
    $("#nla-explanation").classList.remove("muted");
    $("#nla-cosine").textContent = res.reconstruction.toFixed(3);
    $("#nla-fve").textContent    = res.fve == null ? "n/a" : res.fve.toFixed(3);

    updateMetrics(res.reconstruction, res.fve);
    pushHistory(index, state.tokens[index], res.reconstruction, res.fve);
    setPipeline([], ["target", "av", "ar", "score"]);
  } catch (e) {
    pipelineError("av");
    explanationError(`Analyse failed: ${e.message}`);
  } finally {
    tokenEl.classList.remove("loading");
  }
}

function resetExplanation() {
  $("#nla-empty").classList.remove("hidden");
  $("#nla-body").classList.add("hidden");
  $("#inspector-sub").textContent = "no token selected";
}

function explanationError(msg) {
  $("#nla-empty").classList.add("hidden");
  $("#nla-body").classList.remove("hidden");
  $("#nla-explanation").innerHTML = `<span class="error">${escapeHtml(msg)}</span>`;
  $("#nla-explanation").classList.remove("muted");
}

// ---------------------------------------------------------------- metrics
function updateMetrics(cosine, fve) {
  $("#m-cosine").textContent = cosine.toFixed(3);
  // Cosine is bounded [-1, 1]; map to a 0-100% bar.
  $("#m-cosine-bar").style.width = `${Math.max(0, Math.min(100, ((cosine + 1) / 2) * 100))}%`;

  if (fve == null) {
    $("#m-fve").textContent = "n/a";
    $("#m-fve-bar").style.width = "0%";
  } else {
    $("#m-fve").textContent = fve.toFixed(3);
    // FVE can go negative (worse than predicting the mean); clamp the bar only.
    $("#m-fve-bar").style.width = `${Math.max(0, Math.min(100, fve * 100))}%`;
  }
  paintSparkline();
}

function resetMetrics() {
  $("#m-cosine").textContent = "—";
  $("#m-fve").textContent    = "—";
  $("#m-cosine-bar").style.width = "0%";
  $("#m-fve-bar").style.width    = "0%";
  paintSparkline();
}

// ---------------------------------------------------------------- history
function pushHistory(index, token, cosine, fve) {
  state.history = state.history.filter((h) => h.index !== index);
  state.history.unshift({ index, token, cosine, fve });
  state.history = state.history.slice(0, HISTORY_MAX);
  renderHistory();
}

function renderHistory() {
  const ul = $("#nla-history");
  ul.innerHTML = "";
  if (state.history.length === 0) {
    ul.innerHTML = `<li class="muted" style="cursor:default">nothing analysed yet</li>`;
    return;
  }
  for (const h of state.history) {
    const li = document.createElement("li");
    const score = h.fve == null ? h.cosine.toFixed(2) : h.fve.toFixed(2);
    const label = h.fve == null ? "cos" : "fve";
    li.innerHTML =
      `<span class="nbr-tok">[${h.index}] ${escapeHtml(displayToken(h.token))}</span>` +
      `<span class="nbr-score">${label} ${score}</span>`;
    li.addEventListener("click", () => analyzeToken(h.index));
    ul.appendChild(li);
  }
}

// ---------------------------------------------------------------- sparkline
// Plots FVE (or cosine when no baseline exists) in the order tokens were
// analysed. Purely a record of real measurements -- no synthetic points.
function paintSparkline() {
  const line = $("#sparkline-line");
  const zero = $("#sparkline-zero");
  if (!line) return;

  const w = 220, h = 56;
  const hist = [...state.history].reverse();

  // The series is FVE only when every point has one. Falling back to cosine is
  // fine -- inventing an "FVE" label for it is not, so say which is plotted.
  const usingFve = hist.length > 0 && hist.every((x) => x.fve != null);
  const series = hist.map((x) => (usingFve ? x.fve : x.cosine));

  const label = $("#sparkline-label");
  const hint  = $("#sparkline-hint");
  if (label) {
    label.textContent = hist.length === 0
      ? "across analysed tokens"
      : `${usingFve ? "FVE" : "cosine"} across analysed tokens`;
  }
  if (hint) {
    hint.textContent = hist.length === 0
      ? "no tokens analysed yet"
      : usingFve
        ? "FVE = 0 (corpus-mean baseline)"
        : "cosine = 0 (no FVE baseline — run Stage 0)";
  }

  if (series.length === 0) {
    line.setAttribute("points", "");
    zero.setAttribute("y1", h); zero.setAttribute("y2", h);
    return;
  }

  // Scale to the observed range with a little padding, always including 0 so
  // the baseline line is meaningful.
  const lo = Math.min(0, ...series);
  const hi = Math.max(...series, lo + 0.05);
  const pad = (hi - lo) * 0.1;
  const min = lo - pad, max = hi + pad;
  const y = (v) => h - ((v - min) / (max - min)) * h;

  const pts = series.map((v, i) => {
    const x = series.length === 1 ? w / 2 : (i / (series.length - 1)) * w;
    return `${x.toFixed(1)},${y(v).toFixed(1)}`;
  });
  line.setAttribute("points", pts.join(" "));
  zero.setAttribute("y1", y(0).toFixed(1));
  zero.setAttribute("y2", y(0).toFixed(1));
}

// ------------------------------------------------------------ trace browser
// A trace is one call POLARIS actually made. Loading one replaces the context
// with its tokens; from there everything behaves exactly as for a chat, because
// analyzeToken() already sends token_ids rather than text. Nothing here reads
// the .npz -- activations are re-derived per click -- so a run captured with
// NLA_CAPTURE=text inspects identically to a full one.

async function apiGet(path) {
  const res = await fetch(path);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "request failed");
  }
  return res.json();
}

function setSource(src) {
  state.source = src;
  document.querySelectorAll(".src-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.src === src));
  $("#trace-pickers").classList.toggle("hidden", src !== "traces");
  $("#trace-meta").classList.toggle("hidden", src !== "traces");
  if (src === "traces") loadRuns();
}

async function loadRuns() {
  const sel = $("#trace-run");
  try {
    const { runs } = await apiGet("/api/traces");
    if (!runs.length) {
      sel.innerHTML = `<option value="">no traces on disk</option>`;
      $("#trace-req").innerHTML = "";
      $("#trace-meta").textContent = "Nothing captured yet — run POLARIS against this server.";
      return;
    }
    const keep = sel.value;
    sel.innerHTML = runs.map((r) =>
      `<option value="${r.run_id}">${r.run_id} · ${r.n_traces} call${r.n_traces === 1 ? "" : "s"}` +
      `${r.current ? " (live)" : ""}${r.has_activations ? "" : " · text-only"}</option>`).join("");
    sel.value = runs.some((r) => r.run_id === keep) ? keep : runs[0].run_id;
    await loadTraceList(sel.value);
  } catch (e) {
    sel.innerHTML = `<option value="">error</option>`;
    $("#trace-meta").textContent = `Could not list traces: ${e.message}`;
  }
}

async function loadTraceList(runId) {
  const sel = $("#trace-req");
  if (!runId) return;
  try {
    const { traces } = await apiGet(`/api/traces/${encodeURIComponent(runId)}`);
    sel.innerHTML = traces.map((t) =>
      `<option value="${t.request_id}">${t.request_id} · ${t.n_tokens} tok — ` +
      `${escapeHtml((t.preview || "").slice(0, 48))}…</option>`).join("");
    if (traces.length) await openTrace(runId, traces[0].request_id);
  } catch (e) {
    sel.innerHTML = `<option value="">error</option>`;
    $("#trace-meta").textContent = `Could not list run: ${e.message}`;
  }
}

async function openTrace(runId, requestId) {
  try {
    const t = await apiGet(
      `/api/traces/${encodeURIComponent(runId)}/${encodeURIComponent(requestId)}`);

    state.tokens         = t.tokens || [];
    state.tokenIds       = t.token_ids || [];
    state.isSpecial      = t.is_special || state.tokens.map(() => false);
    state.assistantStart = t.assistant_token_start ?? state.tokens.length;
    state.selectedIndex  = null;

    renderTokens();
    resetExplanation();
    resetMetrics();

    const cfg = t.config || {};
    const warn = cfg.model && state.health && cfg.model !== state.health.model
      ? ` ⚠ captured with ${cfg.model}, server is running ${state.health.model}`
      : "";
    $("#trace-meta").innerHTML =
      `<strong>${escapeHtml(t.request_id)}</strong> · ${t.n_tokens} tokens · ` +
      `${escapeHtml(t.source || "?")} · layer ${cfg.probe_layer ?? "?"} · ` +
      `${t.has_activations ? "activations on disk" : "text-only (activations re-derived)"}` +
      `<span class="warn">${escapeHtml(warn)}</span>`;
  } catch (e) {
    $("#trace-meta").textContent = `Could not open trace: ${e.message}`;
  }
}

// ---------------------------------------------------------------- tabs
function selectTab(tabId) {
  document.querySelectorAll(".tab-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === tabId));
  document.querySelectorAll(".tab-panel").forEach((p) =>
    p.classList.toggle("hidden", p.dataset.panel !== tabId));
}

// ---------------------------------------------------------------- utilities
function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

// ---------------------------------------------------------------- init
$("#send-btn").addEventListener("click", sendMessage);
$("#new-chat-btn").addEventListener("click", newChat);
$("#settings-toggle").addEventListener("click", () =>
  $("#settings").classList.toggle("hidden"));

document.querySelectorAll(".tab-btn").forEach((b) =>
  b.addEventListener("click", () => selectTab(b.dataset.tab)));

$("#chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// Arrow keys step through tokens once one is selected.
document.addEventListener("keydown", (e) => {
  if (document.activeElement === $("#chat-input")) return;
  if (state.selectedIndex == null) return;
  if (e.key === "ArrowRight" && state.selectedIndex < state.tokens.length - 1) {
    e.preventDefault();
    analyzeToken(state.selectedIndex + 1);
  } else if (e.key === "ArrowLeft" && state.selectedIndex > 0) {
    e.preventDefault();
    analyzeToken(state.selectedIndex - 1);
  }
});

document.querySelectorAll(".src-btn").forEach((b) =>
  b.addEventListener("click", () => setSource(b.dataset.src)));

$("#trace-run").addEventListener("change", (e) => loadTraceList(e.target.value));
$("#trace-req").addEventListener("change", (e) =>
  openTrace($("#trace-run").value, e.target.value));
$("#trace-reload").addEventListener("click", () => loadRuns());

renderHistory();
setPipeline([]);
loadHealth();
$("#chat-input").focus();
