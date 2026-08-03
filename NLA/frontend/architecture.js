// POLARIS + NLA architecture — static reference diagram.
//
// Deliberately has no backend calls. Everything here is structural
// documentation of how the pieces fit together; nothing is a measurement.
// The route buttons are a view filter, not system state.
//
// When the POLARIS feed is wired, this is where per-agent activity and live
// routing would attach — see the `status` field on each component below for
// what is already running.

// ---------------------------------------------------------------- components

const COMPONENTS = {
  kernel: {
    title: "Kernel",
    kind: "orch", kindLabel: "Orchestrator",
    role: `Triages every incoming telemetry snapshot and decides which loop handles
it. Below a criticality threshold the situation goes to the Reasoner for
deliberation; above it, the Fast Controller reacts immediately without waiting
on an LLM.`,
    maps: `POLARIS's dispatch layer. In TAS this becomes the split between
panic-button events (straight to the reactive path) and everything else.`,
    status: { live: false, note: "runs in POLARIS/polaris_poc; not surfaced here yet" },
  },

  reasoner: {
    title: "Reasoner",
    kind: "llm", kindLabel: "LLM agent",
    role: `The deliberative core. Given telemetry plus tool access, it proposes an
adaptation action and a justification. This is the component whose activations
the whole interpretability question is about — it is the only place in the
system where an opaque model makes a consequential choice.`,
    maps: `<code>agents/agentic_reasoner.py</code>. Its LLM backend is provider-agnostic
(<code>llm_clients.py</code>), which is what allows a locally-served model with an
activation hook to be dropped in.`,
    nla: `The activation trace comes from here. Each token of the Reasoner's decision
has a residual-stream vector at the probe layer, and the AV turns any of those
into prose — that is exactly what the
<a href="/">Activation Inspector</a> does today, on a stand-in model.`,
    status: { live: false, note: "live against OpenRouter; local activation-hooked backend is the next step" },
  },

  reactive: {
    title: "Fast Controller",
    kind: "rule", kindLabel: "Rule-based",
    role: `Deterministic fallback policy for situations too urgent or too
safety-critical to route through an LLM. No model in the loop, so its behaviour
is inspectable by construction.`,
    maps: `POLARIS's fast controller. Useful as the interpretability contrast case:
it is the baseline for what "already explainable" looks like.`,
    status: { live: false, note: "runs in POLARIS/polaris_poc" },
  },

  meta: {
    title: "Meta-Learner",
    kind: "llm", kindLabel: "LLM agent",
    role: `Reflects over accumulated episodes on a slower cycle and revises the
Reasoner's prompt and thresholds. Adapts the adaptation policy itself rather
than the managed system.`,
    maps: `<code>agents/meta_learner.py</code>. Currently Gemini-only — it is skipped when
the stack runs against an OpenAI-compatible provider.`,
    status: { live: false, note: "not yet generalised past the Gemini backend" },
  },

  "metric-collector": {
    title: "Metric Collector",
    kind: "adapter", kindLabel: "Adapter",
    role: `Samples the managed system and publishes telemetry onto the bus. The
entry point of the control loop.`,
    maps: `<code>adapters/monitor.py</code>, talking to SWIM over its TCP control
interface on port 4242. In TAS this is the existing <code>WorkflowProbe</code>.`,
    status: { live: false, note: "runs in POLARIS/polaris_poc" },
  },

  verifier: {
    title: "Verifier",
    kind: "adapter", kindLabel: "Adapter",
    role: `Safety backstop. Checks a proposed action against invariants before it
can reach the actuator, so an LLM proposal is never enacted unchecked.`,
    maps: `<code>adapters/verification.py</code>. In TAS the invariants would be a cost
ceiling and unbroken alarm coverage.`,
    status: { live: false, note: "runs in POLARIS/polaris_poc" },
  },

  "execution-adapter": {
    title: "Execution Adapter",
    kind: "adapter", kindLabel: "Adapter",
    role: `Translates a verified action into a concrete effect on the managed
system.`,
    maps: `<code>adapters/execution.py</code>. In TAS this is the existing
<code>WorkflowEffector</code>.`,
    status: { live: false, note: "runs in POLARIS/polaris_poc" },
  },

  system: {
    title: "Managed System · SWIM",
    kind: "managed", kindLabel: "Managed system",
    role: `The thing being adapted. SWIM is a simulated web infrastructure with two
knobs: how many servers are running, and a "dimmer" trading response fidelity
against latency.`,
    maps: `<code>SWIM/</code>, run inside the <code>gabrielmoreno/swim</code> container.
It is fully decoupled — it speaks raw TCP and knows nothing about POLARIS.`,
    status: { live: false, note: "started separately via SWIM/start_swim.sh" },
  },

  kb: {
    title: "Knowledge Base",
    kind: "tool", kindLabel: "Reasoner tool",
    role: `Episodic memory. Lets the Reasoner retrieve what happened last time a
similar situation arose.`,
    maps: `POLARIS's knowledge-base component, queried as a tool during reasoning.`,
    status: { live: false, note: "runs in POLARIS/polaris_poc" },
  },

  wm: {
    title: "World Model",
    kind: "tool", kindLabel: "Reasoner tool",
    role: `What-if simulation. The Reasoner can ask for the predicted effect of a
candidate action before committing to it.`,
    maps: `The Bayesian world model behind the Digital Twin service
(<code>models/bayesian_world_model.py</code>), reached over gRPC.`,
    status: { live: false, note: "runs in POLARIS/polaris_poc" },
  },

  nla: {
    title: "Natural Language Autoencoder",
    kind: "tool", kindLabel: "Interpretability",
    role: `Turns a single activation vector from the Reasoner into a natural-language
description, and scores how much of that activation the description alone
recovers. Unlike the logit lens or an SAE, its output needs no expert
labelling — which is what makes it the candidate for explanations a
non-technical stakeholder could act on, and also why its faithfulness has to be
measured rather than assumed.`,
    maps: `This repository. <code>src/av.py</code> (verbalizer), <code>src/ar.py</code>
(reconstructor), <code>server/</code> (resident-model HTTP service).`,
    nla: `The <a href="/">Activation Inspector</a> is this component, running now
against Qwen2.5-0.5B as a stand-in for the eventual Reasoner backbone.`,
    status: { live: true, note: "live — this server" },
  },
};

// ---------------------------------------------------------------- edges
// Direction matters for arrowheads. The loop reads:
//   MS → MC → Kernel → {Fast Controller / Reasoner} → Verifier → EA → MS
// with the Meta-Learner editing policy on a slower cycle above.
//
// `kind` drives colour/marker: tel (blue), act (amber), meta (dashed violet).
// `route` marks the two internal Kernel dispatch paths, highlighted on demand.
const EDGES = [
  // LEFT rail — telemetry up
  { from: "system",           to: "metric-collector", kind: "tel", fromSide: "left", toSide: "bottom", label: "telemetry" },
  { from: "metric-collector", to: "kernel",           kind: "tel", fromSide: "top",  toSide: "left" },

  // RIGHT rail — actions down
  { from: "kernel",            to: "verifier",          kind: "act", fromSide: "right",  toSide: "top", label: "actions" },
  { from: "verifier",          to: "execution-adapter", kind: "act", fromSide: "bottom", toSide: "top" },
  { from: "execution-adapter", to: "system",            kind: "act", fromSide: "bottom", toSide: "right" },

  // Kernel ↔ Reasoner (slow loop · strategic)
  { from: "kernel",   to: "reasoner", route: "strategic", fromSide: "top",    toSide: "bottom", label: "plan" },
  { from: "reasoner", to: "kernel",   route: "strategic", fromSide: "bottom", toSide: "top" },

  // Kernel ↔ Fast Controller (fast loop · reactive)
  { from: "kernel",   to: "reactive", route: "stabilization", fromSide: "top",    toSide: "bottom", label: "stabilize" },
  { from: "reactive", to: "kernel",   route: "stabilization", fromSide: "bottom", toSide: "top" },

  // Reasoner ↔ Meta-Learner
  { from: "reasoner", to: "meta",     kind: "meta", fromSide: "top",    toSide: "bottom", label: "record" },
  { from: "meta",     to: "reasoner", kind: "meta", fromSide: "bottom", toSide: "top",    label: "evolve" },
];

let activeRoute = "strategic";

// ---------------------------------------------------------------- geometry
function anchorPoint(el, side) {
  const diag = document.getElementById("diagram").getBoundingClientRect();
  const r    = el.getBoundingClientRect();
  const xMid = r.left - diag.left + r.width / 2;
  const yMid = r.top  - diag.top  + r.height / 2;
  if (side === "top")    return { x: xMid, y: r.top    - diag.top };
  if (side === "bottom") return { x: xMid, y: r.bottom - diag.top };
  if (side === "left")   return { x: r.left  - diag.left, y: yMid };
  if (side === "right")  return { x: r.right - diag.left, y: yMid };
  return { x: xMid, y: yMid };
}

// Nudge the two directions of a bidirectional pair onto opposite sides of the
// centre line so they do not overdraw each other.
function perpOffset(a, b, dist, edge) {
  const dx = b.x - a.x, dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  const h = (edge.from + "->" + edge.to).split("")
    .reduce((acc, c) => (acc * 31 + c.charCodeAt(0)) | 0, 0);
  const sign = (h & 1) ? 1 : -1;
  return { x: sign * (-dy / len) * dist, y: sign * (dx / len) * dist };
}

function drawConnectors() {
  const svg  = document.getElementById("connectors");
  const diag = document.getElementById("diagram");
  if (!svg || !diag) return;

  svg.setAttribute("viewBox", `0 0 ${diag.clientWidth} ${diag.clientHeight}`);
  svg.setAttribute("width",  diag.clientWidth);
  svg.setAttribute("height", diag.clientHeight);

  svg.querySelectorAll("path.connector, text.edge-label").forEach((n) => n.remove());

  for (const edge of EDGES) {
    const fromEl = document.querySelector(`.node[data-agent="${edge.from}"]`);
    const toEl   = document.querySelector(`.node[data-agent="${edge.to}"]`);
    if (!fromEl || !toEl) continue;

    const a = anchorPoint(fromEl, edge.fromSide);
    const b = anchorPoint(toEl,   edge.toSide);

    const perp = perpOffset(a, b, 4, edge);
    const ax = a.x + perp.x, ay = a.y + perp.y;
    const bx = b.x + perp.x, by = b.y + perp.y;

    const mx = (ax + bx) / 2, my = (ay + by) / 2;
    // Gentle curvature on diagonals; the vertical rails stay nearly straight.
    const curveAmt = (Math.abs(bx - ax) > 60 && Math.abs(by - ay) > 60) ? 0.10 : 0.04;
    const cx = mx + (by - ay) * curveAmt;
    const cy = my + (ax - bx) * curveAmt;

    let cls = "connector";
    let marker = "url(#arrow)";
    let labelColor = "#64748b";

    if (edge.kind === "tel") {
      cls += " tel";  marker = "url(#arrow-tel)";  labelColor = "#1d4ed8";
    } else if (edge.kind === "act") {
      cls += " act";  marker = "url(#arrow-act)";  labelColor = "#b45309";
    } else if (edge.kind === "meta") {
      cls += " meta"; marker = "url(#arrow-meta)"; labelColor = "#8b5cf6";
    }

    if (edge.route && edge.route === activeRoute) {
      if (activeRoute === "stabilization") {
        cls += " stabilization"; marker = "url(#arrow-stab)"; labelColor = "#b91c1c";
      } else {
        cls += " active"; marker = "url(#arrow-active)"; labelColor = "#4338ca";
      }
    }

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", `M ${ax} ${ay} Q ${cx} ${cy} ${bx} ${by}`);
    path.setAttribute("class", cls);
    path.setAttribute("marker-end", marker);
    svg.appendChild(path);

    if (edge.label) {
      const dx = bx - ax, dy = by - ay;
      const len = Math.hypot(dx, dy) || 1;
      const lbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
      lbl.setAttribute("x", mx + (-dy / len) * 9);
      lbl.setAttribute("y", my + ( dx / len) * 9);
      lbl.setAttribute("text-anchor", "middle");
      lbl.setAttribute("dominant-baseline", "middle");
      lbl.setAttribute("font-size", "9.5");
      lbl.setAttribute("fill", labelColor);
      lbl.setAttribute("font-family", "ui-monospace, Menlo, monospace");
      lbl.setAttribute("class", "edge-label");
      lbl.textContent = edge.label;
      svg.appendChild(lbl);
    }
  }
}

// ---------------------------------------------------------------- details
function selectComponent(id) {
  const c = COMPONENTS[id];
  if (!c) return;

  document.querySelectorAll("#diagram .node, .tool-chip")
    .forEach((n) => n.classList.remove("selected"));
  const el = document.querySelector(`[data-agent="${id}"]`);
  if (el) el.classList.add("selected");

  document.getElementById("details-title").textContent = c.title;
  document.getElementById("details-sub").textContent   = c.kindLabel.toLowerCase();
  document.getElementById("details-empty").classList.add("hidden");
  document.getElementById("details-body").classList.remove("hidden");

  const kindEl = document.getElementById("detail-kind");
  kindEl.textContent    = c.kindLabel;
  kindEl.dataset.kind   = c.kind;

  document.getElementById("detail-role").textContent = c.role;
  document.getElementById("detail-maps").innerHTML   = c.maps;

  const nlaSection = document.getElementById("detail-nla-section");
  if (c.nla) {
    nlaSection.classList.remove("hidden");
    document.getElementById("detail-nla").innerHTML = c.nla;
  } else {
    nlaSection.classList.add("hidden");
  }

  const status = document.getElementById("detail-status");
  const cls    = c.status.live ? "status-live" : "status-pending";
  const dot    = c.status.live ? "●" : "○";
  status.innerHTML = `<span class="${cls}">${dot} ${escapeHtml(c.status.note)}</span>`;
}

function setRoute(name) {
  activeRoute = name;
  document.querySelectorAll(".route-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.route === name));
  drawConnectors();
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

// ---------------------------------------------------------------- init
document.querySelectorAll("[data-agent]").forEach((el) => {
  const id = el.dataset.agent;
  if (!COMPONENTS[id]) return;
  el.addEventListener("click", () => selectComponent(id));
});

document.querySelectorAll(".route-btn").forEach((b) =>
  b.addEventListener("click", () => setRoute(b.dataset.route)));

drawConnectors();
window.addEventListener("resize", drawConnectors);
// Fonts and the grid settle a frame or two after load; redraw so the anchors
// land on final geometry rather than the initial layout pass.
window.addEventListener("load", () => requestAnimationFrame(drawConnectors));

selectComponent("nla");
