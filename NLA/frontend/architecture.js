// POLARIS + NLA architecture — structural reference diagram, plus whatever the
// dashboard bridge is reporting live.
//
// The diagram itself is documentation: the boxes and edges are how the system
// is wired, not a measurement. The only live parts are the metric strip, the
// per-node status dots, the activity log and the goal readouts — all of which
// go blank when the bridge is down rather than showing anything invented.

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
    maps: `<code>adapters/verification.py</code>, against the constraints in
<code>config/swim_optimized_config.yaml</code> — the ones listed under Stakeholders →
System Goals. In TAS the invariants would be a cost ceiling and unbroken alarm
coverage.`,
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

// ---------------------------------------------------------------- goals
// Read off POLARIS's runtime config so this panel documents what the system is
// actually started with. `swim_targets` are what the Reasoner optimises for;
// `swim_verification.constraints` are hard invariants the Verifier rejects
// actions against. Nothing here is a knob this page can turn — see GOALS_NOTE.
const GOALS_SOURCE = "POLARIS/polaris_poc/config/swim_optimized_config.yaml";

const GOAL_GROUPS = [
  {
    title: "Non-functional targets",
    note: "swim_targets — what the Reasoner optimises for",
    items: [
      {
        name: "basic_response_time", op: "<", value: 1000, unit: "ms",
        why: "SLA for essential content. The pressure behind most adaptations.",
        metric: "average_response_time", report: true,
      },
      {
        name: "optional_response_time", op: "<", value: 2000, unit: "ms",
        why: "Optional content may lag; the dimmer trades it away first.",
      },
      {
        name: "server_utilization", op: "≈", value: 0.75,
        why: "Utilisation sweet spot — headroom without idle servers.",
        metric: "server_utilization",
      },
      {
        name: "server_utilization_max", op: "≤", value: 0.90,
        why: "Above this, scale out rather than dim.",
        metric: "server_utilization", test: (v) => v <= 0.90,
      },
      {
        name: "dimmer_optimal", op: "≥", value: 0.70,
        why: "Prefer full fidelity; dim only under load.",
        metric: "dimmer", test: (v) => v >= 0.70,
      },
    ],
  },
  {
    title: "Invariants · enforced by the Verifier",
    note: "swim_verification.constraints — an action violating one is rejected",
    items: [
      {
        name: "min_servers", op: "≥", value: 1, sev: "critical",
        why: "Never remove the last server.",
        metric: "active_servers", test: (v) => v >= 1,
      },
      {
        name: "max_servers", op: "≤", dynamic: "max_servers", sev: "high",
        why: "Capacity ceiling, reported by SWIM itself.",
        metric: "active_servers",
        test: (v, m) => !m.max_servers || v <= m.max_servers.value,
      },
      {
        name: "dimmer_bounds", op: "∈", value: "0.1 – 1.0", sev: "high",
        why: "Outside this range SWIM is not stable.",
        metric: "dimmer", test: (v) => v >= 0.1 && v <= 1.0,
      },
      {
        name: "predicted_response_time", op: "<", value: 5000, unit: "ms", sev: "medium",
        why: "Block actions the world model expects to blow past this.",
      },
      {
        name: "server_scaling_interval", op: "≥", value: 10, unit: "s", sev: "medium",
        why: "Let a scaling action settle before the next one.",
      },
      {
        name: "adaptation_interval", op: "≥", value: 5, unit: "s", sev: "low",
        why: "Minimum pause between adaptations of any kind.",
      },
    ],
  },
];

const GOALS_NOTE =
  `Read from <code>${GOALS_SOURCE}</code>. Read-only here on purpose: changing a ` +
  `goal means editing that file and restarting the Verifier, and this page is ` +
  `strictly an observer of the running system.`;

// ---------------------------------------------------------------- edges
// Direction matters for arrowheads. The loop reads:
//   MS → MC → Kernel → {Fast Controller / Reasoner} → Verifier → EA → MS
// with the Meta-Learner editing policy on a slower cycle above.
//
// `kind` drives colour/marker: tel (blue), act (amber), meta (dashed violet).
// `route` marks the two internal Kernel dispatch paths, highlighted on demand.
//
// Every edge is routed orthogonally (see orthoRoute): it leaves a box square to
// the side it names and enters the next one square too, so the picture is made
// of straight runs and right angles rather than curves. `fromT`/`toT` slide the
// anchor along that side (0 = left/top end, 1 = right/bottom end) to keep the
// two rails from sharing a lane; where a run has to jog sideways, the turn is
// placed in the empty gutter between the two boxes (gapCross).
const EDGES = [
  // LEFT rail — telemetry up out of the managed system
  { from: "system", to: "metric-collector", kind: "tel",
    fromSide: "left", toSide: "left", label: "telemetry" },
  { from: "metric-collector", to: "kernel", kind: "tel",
    fromSide: "right", toSide: "left" },

  // RIGHT rail — actions down into it
  { from: "kernel", to: "verifier", kind: "act",
    fromSide: "right", toSide: "left", label: "actions" },
  { from: "verifier", to: "execution-adapter", kind: "act",
    fromSide: "bottom", toSide: "right" },
  { from: "execution-adapter", to: "system", kind: "act",
    fromSide: "bottom", toSide: "top", toT: 0.7 },

  // Kernel ↔ Reasoner (slow loop · strategic) — dead-straight verticals
  { from: "kernel",   to: "reasoner", route: "strategic",
    fromSide: "top",    toSide: "bottom", label: "plan" },
  { from: "reasoner", to: "kernel",   route: "strategic",
    fromSide: "bottom", toSide: "top" },

  // Kernel ↔ Fast Controller (fast loop · reflex) — off the kernel's right
  { from: "kernel",   to: "reactive", route: "stabilization",
    fromSide: "top", fromT: 0.82, toSide: "bottom", label: "stabilize" },
  { from: "reactive", to: "kernel",   route: "stabilization",
    fromSide: "bottom", toSide: "top", toT: 0.82 },

  // Reasoner ↔ Meta-Learner
  { from: "reasoner", to: "meta",     kind: "meta",
    fromSide: "top",    toSide: "bottom", label: "record" },
  { from: "meta",     to: "reasoner", kind: "meta",
    fromSide: "bottom", toSide: "top",    label: "evolve" },
];

// Edges that have a mirror image get nudged onto their own lane so the two
// directions do not draw on top of each other.
const PAIRED = new Set();
for (const e of EDGES) {
  if (EDGES.some((o) => o.from === e.to && o.to === e.from)) {
    PAIRED.add(`${e.from}->${e.to}`);
  }
}

// "auto" follows the route POLARIS actually dispatched on (reported by the
// bridge); the others pin it manually for reading the diagram offline.
let routeMode   = "auto";
let activeRoute = "strategic";
let liveState   = null;

// ---------------------------------------------------------------- geometry
const SIDE_DIR = {
  top:    { x:  0, y: -1 },
  bottom: { x:  0, y:  1 },
  left:   { x: -1, y:  0 },
  right:  { x:  1, y:  0 },
};

const STUB = 14;   // how far an edge runs square out of a box before turning
const RADIUS = 9;  // corner rounding

function isVertical(side) { return side === "top" || side === "bottom"; }

// Box of `el` in diagram coordinates.
function relRect(el, diag) {
  const d = diag.getBoundingClientRect();
  const r = el.getBoundingClientRect();
  return {
    top:    r.top    - d.top,
    bottom: r.bottom - d.top,
    left:   r.left   - d.left,
    right:  r.right  - d.left,
  };
}

// Point on `side` of `el`, `t` of the way along that side (0.5 = centre).
function anchorPoint(el, side, t = 0.5) {
  const diag = document.getElementById("diagram").getBoundingClientRect();
  const r    = el.getBoundingClientRect();
  const left = r.left - diag.left, top = r.top - diag.top;
  if (isVertical(side)) {
    return {
      x: left + r.width * t,
      y: side === "top" ? top : top + r.height,
    };
  }
  return {
    x: side === "left" ? left : left + r.width,
    y: top + r.height * t,
  };
}

// Axis-aligned route from `a` (leaving square to aSide) to `b` (entering square
// to bSide). Two boxes facing the same way get a Z whose crossbar sits at
// `cross` (see gapCross — the empty lane between them); boxes facing at right
// angles get a single L.
function orthoRoute(a, aSide, b, bSide, cross) {
  const da = SIDE_DIR[aSide], db = SIDE_DIR[bSide];
  const A = { x: a.x + da.x * STUB, y: a.y + da.y * STUB };
  const B = { x: b.x + db.x * STUB, y: b.y + db.y * STUB };
  const pts = [a, A];

  const av = isVertical(aSide), bv = isVertical(bSide);
  if (av && bv) {
    if (Math.abs(A.x - B.x) > 1.5) {
      const my = between(cross, A.y, B.y);
      pts.push({ x: A.x, y: my }, { x: B.x, y: my });
    }
  } else if (!av && !bv) {
    if (Math.abs(A.y - B.y) > 1.5) {
      const mx = between(cross, A.x, B.x);
      pts.push({ x: mx, y: A.y }, { x: mx, y: B.y });
    }
  } else if (av) {
    pts.push({ x: A.x, y: B.y });
  } else {
    pts.push({ x: B.x, y: A.y });
  }

  pts.push(B, b);
  return dedupe(pts);
}

// Keep the crossbar between the two stub ends; fall back to the midpoint when
// the caller had nothing better to offer or the boxes are too close together.
function between(v, p, q) {
  const lo = Math.min(p, q), hi = Math.max(p, q);
  if (typeof v !== "number" || v < lo || v > hi) return (p + q) / 2;
  return v;
}

// Where a Z-shaped edge should turn: the middle of the empty lane between the
// two boxes, so the crossbar runs down a gutter instead of cutting across a
// layer panel. Returns null when the boxes overlap on that axis.
function gapCross(F, T, vertical, lane) {
  if (vertical) {
    const upper = F.bottom <= T.top ? F : T;
    const lower = upper === F ? T : F;
    if (upper.bottom >= lower.top) return null;
    return (upper.bottom + lower.top) / 2 + lane;
  }
  const left  = F.right <= T.left ? F : T;
  const right = left === F ? T : F;
  if (left.right >= right.left) return null;
  return (left.right + right.left) / 2 + lane;
}

function dedupe(pts) {
  const out = [];
  for (const p of pts) {
    const last = out[out.length - 1];
    if (!last || Math.abs(last.x - p.x) > 0.4 || Math.abs(last.y - p.y) > 0.4) out.push(p);
  }
  return out;
}

// Polyline → path with the corners rounded off, so right angles read as turns
// rather than as kinks.
function roundedPath(pts, r = RADIUS) {
  if (pts.length < 2) return "";
  let d = `M ${round1(pts[0].x)} ${round1(pts[0].y)}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const p0 = pts[i - 1], p1 = pts[i], p2 = pts[i + 1];
    const l1 = Math.hypot(p1.x - p0.x, p1.y - p0.y);
    const l2 = Math.hypot(p2.x - p1.x, p2.y - p1.y);
    const rr = Math.min(r, l1 / 2, l2 / 2);
    if (rr < 1.5) { d += ` L ${round1(p1.x)} ${round1(p1.y)}`; continue; }
    const inX  = p1.x + ((p0.x - p1.x) / l1) * rr;
    const inY  = p1.y + ((p0.y - p1.y) / l1) * rr;
    const outX = p1.x + ((p2.x - p1.x) / l2) * rr;
    const outY = p1.y + ((p2.y - p1.y) / l2) * rr;
    d += ` L ${round1(inX)} ${round1(inY)}` +
         ` Q ${round1(p1.x)} ${round1(p1.y)} ${round1(outX)} ${round1(outY)}`;
  }
  const last = pts[pts.length - 1];
  return `${d} L ${round1(last.x)} ${round1(last.y)}`;
}

function round1(n) { return Math.round(n * 10) / 10; }

// Which lane a paired edge takes: same offset magnitude, opposite signs, chosen
// deterministically so a redraw never flips them.
function laneSign(edge) {
  const key = `${edge.from}->${edge.to}`;
  const rev = `${edge.to}->${edge.from}`;
  return key < rev ? -1 : 1;
}

// Longest run in the polyline — the only segment with room for a label.
function longestSegment(pts) {
  let best = null, bestLen = -1;
  for (let i = 0; i < pts.length - 1; i++) {
    const len = Math.hypot(pts[i + 1].x - pts[i].x, pts[i + 1].y - pts[i].y);
    if (len > bestLen) { bestLen = len; best = [pts[i], pts[i + 1]]; }
  }
  return { seg: best, len: bestLen };
}

const SVG_NS = "http://www.w3.org/2000/svg";

function drawConnectors() {
  const svg  = document.getElementById("connectors");
  const diag = document.getElementById("diagram");
  if (!svg || !diag) return;

  const w = diag.clientWidth, h = diag.clientHeight;
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.setAttribute("width",  w);
  svg.setAttribute("height", h);

  svg.querySelectorAll(".edge").forEach((n) => n.remove());

  for (const edge of EDGES) {
    const fromEl = document.querySelector(`.node[data-agent="${edge.from}"]`);
    const toEl   = document.querySelector(`.node[data-agent="${edge.to}"]`);
    if (!fromEl || !toEl) continue;

    const paired = PAIRED.has(`${edge.from}->${edge.to}`);
    const lane   = paired ? laneSign(edge) * 7 : 0;

    // Slide the anchor along its side, then shift it into its lane. The lane
    // shift runs along the side itself, which is what keeps the run straight.
    const a = anchorPoint(fromEl, edge.fromSide, edge.fromT ?? 0.5);
    const b = anchorPoint(toEl,   edge.toSide,   edge.toT   ?? 0.5);
    if (isVertical(edge.fromSide)) a.x += lane; else a.y += lane;
    if (isVertical(edge.toSide))   b.x += lane; else b.y += lane;

    const sameAxis = isVertical(edge.fromSide) === isVertical(edge.toSide);
    const cross = sameAxis
      ? gapCross(relRect(fromEl, diag), relRect(toEl, diag), isVertical(edge.fromSide), lane)
      : null;

    const pts = orthoRoute(a, edge.fromSide, b, edge.toSide, cross);

    let cls = "connector edge";
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

    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", roundedPath(pts));
    path.setAttribute("class", cls);
    path.setAttribute("marker-end", marker);
    svg.appendChild(path);

    if (edge.label) drawEdgeLabel(svg, pts, edge, labelColor, lane);
  }
}

function drawEdgeLabel(svg, pts, edge, color, lane) {
  const { seg, len } = longestSegment(pts);
  if (!seg || len < 26) return;

  const mx = (seg[0].x + seg[1].x) / 2;
  const my = (seg[0].y + seg[1].y) / 2;
  const vertical = Math.abs(seg[1].x - seg[0].x) < Math.abs(seg[1].y - seg[0].y);

  // Sit off to the side of the run rather than on top of it; for a paired edge
  // that side is the lane it already took, so the two labels never collide.
  const off = 8;
  const side = lane >= 0 ? 1 : -1;
  const x = vertical ? mx + off * side : mx;
  const y = vertical ? my : my - off;

  const text = document.createElementNS(SVG_NS, "text");
  text.setAttribute("x", round1(x));
  text.setAttribute("y", round1(y));
  text.setAttribute("text-anchor", vertical ? (side > 0 ? "start" : "end") : "middle");
  text.setAttribute("dominant-baseline", "middle");
  text.setAttribute("fill", color);
  text.setAttribute("class", "edge-label edge");
  text.textContent = edge.label;
  svg.appendChild(text);

  // A white plate keeps the label readable where it overlaps a layer panel.
  const box  = text.getBBox();
  const rect = document.createElementNS(SVG_NS, "rect");
  rect.setAttribute("x", round1(box.x - 2.5));
  rect.setAttribute("y", round1(box.y - 1));
  rect.setAttribute("width",  round1(box.width + 5));
  rect.setAttribute("height", round1(box.height + 2));
  rect.setAttribute("rx", "2");
  rect.setAttribute("class", "edge-label-plate edge");
  svg.insertBefore(rect, text);
}

// ---------------------------------------------------------------- goals panel
function renderGoals() {
  const body = document.getElementById("goals-body");
  const foot = document.getElementById("goals-foot");
  if (!body) return;

  const metrics = (liveState && liveState.metrics) || null;
  body.innerHTML = "";

  for (const group of GOAL_GROUPS) {
    const head = document.createElement("div");
    head.className = "goals-group";
    head.textContent = group.title;
    head.title = group.note;
    body.appendChild(head);

    for (const item of group.items) {
      const row = document.createElement("div");
      row.className = "goal-row";

      const target = item.dynamic
        ? (metrics && metrics[item.dynamic] && fmtNum(metrics[item.dynamic].value)) || "—"
        : (typeof item.value === "number" ? fmtNum(item.value) : item.value);

      row.innerHTML =
        `<div>` +
          `<span class="goal-name">${escapeHtml(item.name)}</span>` +
          (item.sev ? `<span class="goal-sev ${item.sev}">${item.sev}</span>` : "") +
          `<div class="goal-why">${escapeHtml(item.why)}</div>` +
          liveChip(item, metrics) +
        `</div>` +
        `<div class="goal-target">` +
          `<span class="goal-op">${escapeHtml(item.op)}</span>${escapeHtml(String(target))}` +
          (item.unit ? ` ${escapeHtml(item.unit)}` : "") +
        `</div>`;
      body.appendChild(row);
    }
  }

  foot.innerHTML = GOALS_NOTE;
}

// The live column of the goals panel. Only says pass/fail where the comparison
// is actually well defined — a goal whose metric is not being reported, or
// whose units do not line up with the feed, is shown as a reading and nothing
// more.
function liveChip(item, metrics) {
  if (!item.metric) return "";
  if (!metrics) return `<span class="goal-live idle">no bridge</span>`;

  const entry = metrics[item.metric];
  if (!entry || typeof entry.value !== "number") {
    return `<span class="goal-live idle">${escapeHtml(item.metric)}: not reported</span>`;
  }

  const reading = `${item.metric} = ${fmtNum(entry.value)}` +
                  (entry.unit ? ` ${entry.unit}` : "");

  // `report: true` means show the number but do not judge it — see the unit
  // caveat on average_response_time in renderLive().
  if (item.report || typeof item.test !== "function") {
    return `<span class="goal-live idle">${escapeHtml(reading)}</span>`;
  }

  const ok = !!item.test(entry.value, metrics);
  return `<span class="goal-live ${ok ? "ok" : "miss"}">` +
         `${ok ? "✓" : "✗"} ${escapeHtml(reading)}</span>`;
}

function toggleGoals(force) {
  const btn   = document.getElementById("stakeholders");
  const panel = document.getElementById("goals-panel");
  if (!btn || !panel) return;
  const open = force !== undefined ? force : panel.classList.contains("hidden");
  panel.classList.toggle("hidden", !open);
  btn.setAttribute("aria-expanded", String(open));
  if (open) renderGoals();
}

// ---------------------------------------------------------------- details
let selectedId = null;

function selectComponent(id) {
  const c = COMPONENTS[id];
  if (!c) return;
  selectedId = id;
  selectTab("component");

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

  renderLiveLine(id);
}

function setRoute(mode) {
  routeMode = mode;
  document.querySelectorAll(".route-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.route === mode));
  resolveRoute();
  drawConnectors();
}

function resolveRoute() {
  if (routeMode === "auto") {
    // Nothing dispatched yet (or no bridge) -> highlight nothing rather than
    // guessing a route the system has not actually taken.
    activeRoute = (liveState && liveState.route) || null;
  } else {
    activeRoute = routeMode === "none" ? null : routeMode;
  }
}

// ---------------------------------------------------------------- live state
const POLL_MS = 2000;

async function pollState() {
  let s = null;
  try {
    const r = await fetch("/api/polaris/state", { cache: "no-store" });
    if (r.ok) s = await r.json();
  } catch {
    s = null;
  }
  liveState = s && s.connected ? s : null;
  renderLive(s);
  resolveRoute();
  drawConnectors();
  if (!document.getElementById("goals-panel").classList.contains("hidden")) {
    renderGoals();
  }
}

function renderLive(s) {
  const connected = !!(s && s.connected);
  const dot   = document.getElementById("bridge-dot");
  const pill  = document.getElementById("bridge-pill");
  const text  = document.getElementById("bridge-text");
  const strip = document.getElementById("metrics-strip");
  const banner = document.getElementById("banner");

  dot.className = connected ? "dot live" : (s && s.bridge && !s.bridge.reachable ? "dot" : "dot error");
  pill.classList.toggle("live", connected);
  strip.classList.toggle("hidden", !connected);
  banner.classList.toggle("hidden", connected);

  if (!connected) {
    pill.textContent = "bridge: —";
    text.textContent = "not connected";
    renderActivity(null);
    setNodeStatuses(null);
    return;
  }

  pill.textContent = `${s.messages} msgs`;
  text.textContent = "live";

  // Response time: printed with the unit the bridge reports and enough digits
  // that a sub-unit reading does not round to zero (SWIM's feed comes through
  // around 0.05 while extern/config.yaml declares the metric in ms — that
  // mismatch is upstream, so the number is shown as fed rather than converted).
  // The bar scales to the largest value seen this run for the same reason.
  const rtHist = (s.history.average_response_time || []).map((p) => p[1]);
  const rtMax  = rtHist.length ? Math.max(...rtHist) : null;
  setMetric("rt", s.metrics.average_response_time, rtMax || 1, fmtNum,
            (s.metrics.average_response_time || {}).unit || "");
  const rtHint = document.getElementById("m-rt-hint");
  if (rtHint) {
    const u = (s.metrics.average_response_time || {}).unit;
    rtHint.textContent = "swim.average_response_time" + (u ? ` · ${u} as reported` : "");
  }

  setMetric("util",    s.metrics.server_utilization, 1, (v) => v.toFixed(2));
  setMetric("dim",     s.metrics.dimmer,             1, (v) => v.toFixed(2));
  setMetric("servers", s.metrics.active_servers,
            (s.metrics.max_servers && s.metrics.max_servers.value) || 3,
            (v) => `${v}`);

  paintSparkline(s.history.average_response_time || []);
  renderActivity(s.activity);
  setNodeStatuses(s.components);

  // Keep an open component panel's live line current.
  if (selectedId) renderLiveLine(selectedId);
}

// Enough significant figures to stay readable whether the feed is in seconds,
// milliseconds or counts — a server count prints as "3", a sub-second reading
// as "0.051" rather than rounding away to "0".
function fmtNum(v) {
  if (typeof v !== "number" || !isFinite(v)) return "—";
  if (Number.isInteger(v)) return String(v);
  const a = Math.abs(v);
  let out;
  if (a >= 100)       out = v.toFixed(0);
  else if (a >= 10)   out = v.toFixed(1);
  else if (a >= 1)    out = v.toFixed(2);
  else if (a >= 0.01) out = v.toFixed(3);
  else                out = v.toPrecision(2);
  return out.includes(".") ? out.replace(/0+$/, "").replace(/\.$/, "") : out;
}

function setMetric(key, entry, max, fmt, unit) {
  const el  = document.getElementById(`m-${key}`);
  const bar = document.getElementById(`m-${key}-bar`);
  if (!el) return;
  if (!entry || typeof entry.value !== "number") {
    el.textContent = "—";
    if (bar) bar.style.width = "0%";
    return;
  }
  el.innerHTML = fmt(entry.value) +
    (unit ? `<span class="mt-unit">${escapeHtml(unit)}</span>` : "");
  if (bar) {
    const pct = Math.max(0, Math.min(100, (entry.value / (max || 1)) * 100));
    bar.style.width = `${pct}%`;
  }
}

function paintSparkline(series) {
  const line = document.getElementById("sparkline-line");
  const hint = document.getElementById("spark-hint");
  if (!line) return;
  const vals = series.map((p) => p[1]);
  if (vals.length < 2) {
    line.setAttribute("points", "");
    hint.textContent = vals.length ? "one sample so far" : "awaiting telemetry";
    return;
  }
  const w = 220, h = 56;
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi - lo) * 0.1 || 1;
  const min = lo - pad, max = hi + pad;
  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * w;
    const y = h - ((v - min) / (max - min)) * h;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  line.setAttribute("points", pts.join(" "));
  hint.textContent = `${vals.length} samples · ${fmtNum(lo)}–${fmtNum(hi)}`;
}

function setNodeStatuses(components) {
  document.querySelectorAll("#diagram .node").forEach((node) => {
    const dot = node.querySelector(".node-status");
    if (!dot) return;
    const c = components && components[node.dataset.agent];
    dot.dataset.status = c ? c.status : "idle";
    dot.title = c
      ? `${c.count} messages, last ${c.age_sec}s ago`
      : "no traffic seen";
  });
}

function renderActivity(activity) {
  const el    = document.getElementById("activity-log");
  const badge = document.getElementById("activity-count");
  if (!activity || activity.length === 0) {
    el.innerHTML = `<div class="placeholder">${
      activity ? "Bridge connected, no messages yet." : "No bridge connection — nothing to show."
    }</div>`;
    badge.classList.add("hidden");
    return;
  }
  badge.textContent = activity.length;
  badge.classList.remove("hidden");

  el.innerHTML = "";
  for (const a of activity) {
    const row = document.createElement("div");
    row.className = "log-row";
    const t = new Date(a.ts * 1000).toISOString().slice(11, 19);
    row.innerHTML =
      `<span class="log-time">${t}</span>` +
      `<span class="log-msg">` +
      (a.component ? `<span class="tag comp">${escapeHtml(a.component)}</span>` : "") +
      `<span class="log-subject">${escapeHtml(a.subject)}</span>` +
      (a.summary ? ` ${escapeHtml(a.summary)}` : "") +
      `</span>`;
    el.appendChild(row);
  }
}

function renderLiveLine(id) {
  const el = document.getElementById("detail-live");
  if (!el) return;
  const c = liveState && liveState.components && liveState.components[id];
  if (!c) {
    el.innerHTML = liveState
      ? `<span class="status-pending">○ no traffic seen this run</span>`
      : "";
    return;
  }
  el.innerHTML =
    `<span class="status-live">● live: ${c.count} messages, ` +
    `last ${c.age_sec}s ago (${c.status})</span>`;
}

// ---------------------------------------------------------------- tabs
function selectTab(tabId) {
  document.querySelectorAll(".tab-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === tabId));
  document.querySelectorAll(".tab-panel").forEach((p) =>
    p.classList.toggle("hidden", p.dataset.panel !== tabId));
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

document.querySelectorAll(".tab-btn").forEach((b) =>
  b.addEventListener("click", () => selectTab(b.dataset.tab)));

document.getElementById("stakeholders").addEventListener("click", (e) => {
  e.stopPropagation();
  toggleGoals();
});
document.getElementById("goals-close").addEventListener("click", () => toggleGoals(false));
document.getElementById("goals-panel").addEventListener("click", (e) => e.stopPropagation());
document.addEventListener("click", () => toggleGoals(false));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") toggleGoals(false);
});

// The diagram reflows on font load, on the metric strip appearing, and on any
// resize; the connectors are absolute pixels, so they have to be redrawn each
// time or they drift off their boxes.
drawConnectors();
window.addEventListener("resize", drawConnectors);
if (window.ResizeObserver) {
  new ResizeObserver(() => drawConnectors()).observe(document.getElementById("diagram"));
}
window.addEventListener("load", () => requestAnimationFrame(drawConnectors));

renderGoals();
selectComponent("nla");
resolveRoute();
pollState();
setInterval(pollState, POLL_MS);
