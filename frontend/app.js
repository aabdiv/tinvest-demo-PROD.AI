"use strict";
const AX = ["growth", "trend", "dividends", "stability", "quality"];
let META = null, S = {}, P = null, HIST = [], GHOST = null, SEL = null, TAB = "holdings", PROPOSAL = null;
let NEW_IDS = new Set(), RSEQ = 0, MSEQ = 0, mandateTimer = null, dragTimer = null, DRAG = null, UNI_OK = false;
const NEUTRAL = Object.fromEntries(AX.map((a) => [a, 5]));
const DEFAULT_LINES = [
  { id: "def_maxpos", label: "Не больше 12% в одной бумаге", source: "по умолчанию", active: true },
  { id: "def_nomargin", label: "Без заёмных денег", source: "по умолчанию", active: true },
];
const LOCK = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>`;

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (v, d = 1) => Number(v).toFixed(d).replace(".", ",");
const rub = (v) => Math.round(v).toLocaleString("ru-RU") + " ₽";
const krub = (v) => Math.round(v / 1000).toLocaleString("ru-RU") + " тыс. ₽";
const years = (n) => n + " " + (n % 10 === 1 && n % 100 !== 11 ? "год" : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? "года" : "лет");
const pct = (v, d = 1) => (v >= 0 ? "+" : "") + num(v * 100, d) + "%";
const SECTOR_COLORS = ["#FFDD2D", "#333333", "#888888", "#C4C4C4", "#A89100", "#575757", "#DED6A8", "#E5E5E5", "#999999", "#4A410E", "#A6A6A6", "#6F6F6F", "#C4B85C", "#BBBBBB"];

// ---------------------------------------------------------------- API
async function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  const j = await r.json().catch(() => ({}));
  if (j.llm) j.llm.forEach(logCall);
  if (!r.ok) throw new Error(j.detail || r.statusText);
  return j;
}
function logCall(m) {
  const d = document.createElement("span");
  d.className = "call";
  d.innerHTML = `<b>${num(m.ms / 1000)} с</b> ${esc(m.what || "")} · ${esc(String(m.model || "").split("/").pop())}`;
  $("calls").prepend(d);
  while ($("calls").children.length > 12) $("calls").lastChild.remove();
}
function toast(t, ms = 3500) {
  const el = $("toast"); el.textContent = t; el.classList.remove("hidden");
  clearTimeout(toast.t); toast.t = setTimeout(() => el.classList.add("hidden"), ms);
}
function fail(e) { console.error(e); toast("Ошибка: " + e.message, 6000); }
function pushHist() { HIST.push(JSON.stringify(S)); if (HIST.length > 60) HIST.shift(); }
async function busy(btn, fn) {
  if (btn) btn.disabled = true;
  try { await fn(); } catch (e) { fail(e); } finally { if (btn) btn.disabled = false; }
}

// ---------------------------------------------------------------- геометрия паутины
const G = { cx: 290, cy: 205, R: 150 };
function pt(i, v, g = G) {
  const a = (-90 + i * 72) * Math.PI / 180;
  return [g.cx + g.R * v / 10 * Math.cos(a), g.cy + g.R * v / 10 * Math.sin(a)];
}
const poly = (vals, g = G) => AX.map((a, i) => pt(i, vals[a] ?? 0, g).map((n) => n.toFixed(1)).join(",")).join(" ");
function gridSvg(g = G, labels = false) {
  let s = "";
  for (const r of [2.5, 5, 7.5, 10]) s += `<polygon points="${poly(Object.fromEntries(AX.map((a) => [a, r])), g)}" fill="none" stroke="var(--chart-grid)"/>`;
  AX.forEach((a, i) => { const [x, y] = pt(i, 10, g); s += `<line x1="${g.cx}" y1="${g.cy}" x2="${x}" y2="${y}" stroke="var(--chart-grid)"/>`; });
  return s;
}
function labelPos(i, g = G) {
  const [x, y] = pt(i, 11.6, g);
  const c = Math.cos((-90 + i * 72) * Math.PI / 180);
  return { x, y, anchor: c > 0.3 ? "start" : c < -0.3 ? "end" : "middle" };
}
function mini(axes, target, size = 54) {
  const g = { cx: size / 2, cy: size / 2, R: size / 2 - 3 };
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true">
    <polygon points="${poly(Object.fromEntries(AX.map((a) => [a, 10])), g)}" fill="none" stroke="var(--chart-grid)"/>
    ${target ? `<polygon points="${poly(target, g)}" fill="#FFDD2D" fill-opacity="0.18" stroke="#FFDD2D" stroke-width="1"/>` : ""}
    <polygon points="${poly(axes, g)}" fill="none" stroke="var(--chart-comparison)" stroke-width="1.5"/></svg>`;
}

// ---------------------------------------------------------------- рендер
function renderAll() {
  renderWishes(); renderConflicts(); renderParams(); renderRedLines(); renderRadar();
  renderNotes(); renderMetrics(); renderThemes(); renderSecList(); renderAgent();
  if (SEL) renderDetail(false);
}

function renderWishes() {
  const ws = S.wishes || [];
  if (!ws.length) { $("wishes").innerHTML = `<span class="muted small">Пока пусто. Напишите пару фраз выше.</span>`; return; }
  $("wishes").innerHTML = ws.map((w) => {
    const cls = ["chip", w.red_line ? "red" : w.theme ? "theme" : "", w.status === "rejected" ? "off" : "", NEW_IDS.has(w.id) ? "new" : ""].join(" ");
    const eff = Object.entries(w.effects || {}).map(([a, v]) => `${META.axis_ru[a]} ${v > 0 ? "+" : ""}${v}`).join(", ");
    const tip = [w.span && `«${w.span}»`, eff].filter(Boolean).join(" → ");
    const btn = w.status === "rejected" ? `<button data-wish="${w.id}" aria-label="Вернуть трактовку" title="Вернуть">↺</button>`
                                         : `<button data-wish="${w.id}" aria-label="Отменить трактовку" title="Отменить">✕</button>`;
    return `<span class="${cls}" title="${esc(tip)}"><span class="span">«${esc(w.span)}»</span><span>→ ${esc(w.label)}</span>${btn}</span>`;
  }).join("");
}

function renderConflicts() {
  const cs = (S.conflicts || []).filter((c) => !c.resolved);
  $("conflicts").innerHTML = cs.map((c) => `<div class="conflict"><div>${Cabinet.icon("warning",16)} ${esc(c.text)}</div>
    <div class="opts">${c.options.map((o, k) => `<button class="${k === 0 ? "primary" : "secondary"}" data-conflict="${c.id}" data-opt="${esc(o)}">${esc(o)}</button>`).join("")}</div></div>`).join("");
}

function renderParams() {
  $("amount").value = S.amount_rub ?? 500000; $("amount-v").textContent = rub(S.amount_rub ?? 500000);
  $("horizon").value = S.horizon_years ?? 5; $("horizon-v").textContent = years(S.horizon_years ?? 5);
}

function renderRedLines() {
  const lines = (P?.red_lines || DEFAULT_LINES.filter((l) => !(S.disabled_defaults || []).includes(l.id))).filter((l) => l.active);
  $("redlines").innerHTML = lines.length ? lines.map((l) => `<div class="rl"><div class="ico">${LOCK}</div>
    <div class="txt"><div>${esc(l.label)}</div><div class="src">${esc(l.source)}</div></div>
    <button data-rl="${l.id}" aria-label="Убрать запрет">✕</button></div>`).join("") : `<span class="muted small">Запретов нет.</span>`;
}

function renderRadar() {
  if (!META) return;
  const ok = P && !P.error;
  const target = { ...(ok ? P.target : NEUTRAL), ...(S.manual_axes || {}) };
  const pinned = new Set(Object.keys(S.manual_axes || {}));
  let s = gridSvg();
  if (GHOST) s += `<polygon points="${poly(GHOST)}" fill="none" stroke="var(--chart-ghost)" stroke-width="1.5" stroke-dasharray="5 5"/>`;
  if (ok) s += `<polygon points="${poly(P.achieved)}" fill="#FFDD2D" fill-opacity="0.22" stroke="#FFDD2D" stroke-opacity="0.35"/>`;
  else s += `<polygon points="${poly(target)}" fill="#FFDD2D" fill-opacity="0.12"/>`;
  s += `<polygon points="${poly(target)}" fill="none" stroke="#FFDD2D" stroke-width="2.5"/>`;
  AX.forEach((a, i) => {
    const [x, y] = pt(i, target[a]);
    s += `<circle class="handle" data-i="${i}" cx="${x}" cy="${y}" r="10" fill="#FFDD2D" stroke="${pinned.has(a) ? "var(--chart-text)" : "none"}" stroke-width="3"/>`;
    const L = labelPos(i);
    const diff = ok ? Math.abs(P.achieved[a] - target[a]) : 0;
    const col = diff < 1 ? "var(--green)" : diff < 2 ? "var(--orange)" : "var(--red)";
    s += `<text class="axis-label" data-axis="${a}" x="${L.x}" y="${L.y - 6}" text-anchor="${L.anchor}" fill="var(--chart-text)" font-size="18" font-weight="700">${esc(META.axis_ru[a])}<title>${esc(META.axis_method[a])}${pinned.has(a) ? ". Нажмите, чтобы открепить." : ""}</title></text>`;
    if (pinned.has(a)) s += Cabinet.pin(L.x, L.y + 32);
    s += ok ? `<text x="${L.x}" y="${L.y + 12}" text-anchor="${L.anchor}" font-size="14" fill="var(--chart-muted)">цель ${num(target[a])} · <tspan fill="${col}" font-weight="600">есть ${num(P.achieved[a])}</tspan></text>`
            : `<text x="${L.x}" y="${L.y + 12}" text-anchor="${L.anchor}" font-size="14" fill="var(--chart-muted)">цель ${num(target[a])}</text>`;
  });
  if (ok) {
    s += `<text x="${G.cx}" y="${G.cy + 8}" text-anchor="middle" font-size="42" font-weight="700" fill="var(--chart-text)">${P.fit}%</text>`;
    s += `<text x="${G.cx}" y="${G.cy + 28}" text-anchor="middle" font-size="14" fill="var(--chart-muted)">совпадение</text>`;
  } else {
    s += `<text x="${G.cx}" y="${G.cy + 6}" text-anchor="middle" font-size="16" font-weight="600" fill="var(--chart-text)">старт</text>`;
    s += `<text x="${G.cx}" y="${G.cy + 26}" text-anchor="middle" font-size="14" fill="var(--chart-muted)">${Object.keys(S.manual_axes || {}).length || (S.wishes || []).length ? "портфель — после сборки базы" : "все оси на 5"}</text>`;
  }
  $("radar").innerHTML = s;
}

function renderNotes() {
  const notes = P?.error ? [P.error] : (P?.notes || []);
  $("notes").innerHTML = notes.map((n) => `<div class="note">${esc(n)}</div>`).join("");
}

function renderMetrics() {
  if (!P || P.error) {
    ["m-ret", "m-dd", "m-inc", "m-fit"].forEach((id) => { $(id).textContent = "—"; $(id).className = ""; });
    $("spark").innerHTML = `<line x1="0" x2="600" y1="60" y2="60" stroke="var(--chart-grid)" stroke-dasharray="4 4"/>
      <text x="300" y="52" text-anchor="middle" font-size="13" fill="var(--chart-muted)">${UNI_OK ? "Не удалось посчитать портфель" : "Цифры появятся, как только будет собрана база бумаг"}</text>`;
    $("sectors").innerHTML = "";
    return;
  }
  const m = P.metrics;
  $("m-ret").textContent = pct(m.ann_return);
  $("m-ret").className = m.ann_return >= 0 ? "good" : "bad";
  $("m-dd").textContent = "−" + krub(m.max_dd_rub);
  $("m-dd").className = m.dd_ok ? "" : "bad";
  $("m-inc").textContent = "≈ " + krub(m.income_year_rub);
  $("m-fit").textContent = P.fit + "%";
  $("m-fit").className = P.fit >= 85 ? "good" : P.fit >= 70 ? "warn" : "bad";
  const v = P.backtest.values;
  if (v.length > 1) {
    const amt = S.amount_rub ?? 500000;
    const lo = Math.min(...v, amt), hi = Math.max(...v, amt);
    const X = (i) => (i / (v.length - 1)) * 600, Y = (y) => 110 - ((y - lo) / (hi - lo || 1)) * 100;
    const line = v.map((y, i) => `${X(i).toFixed(1)},${Y(y).toFixed(1)}`).join(" ");
    $("spark").innerHTML = `<line x1="0" x2="600" y1="${Y(amt)}" y2="${Y(amt)}" stroke="var(--chart-grid)" stroke-dasharray="4 4"/>
      <polyline points="${line}" fill="none" stroke="#FFDD2D" stroke-width="2" vector-effect="non-scaling-stroke"/>
      <title>Было ${rub(amt)}, стало бы ${rub(v[v.length - 1])}</title>`;
  }
  $("sectors").innerHTML = P.sectors.map((s, k) => `<div style="flex:${s.weight};background:${SECTOR_COLORS[k % SECTOR_COLORS.length]}" title="${esc(s.name)} ${Math.round(s.weight * 100)}%"></div>`).join("");
  let leg = $("sector-legend");
  if (!leg) { leg = document.createElement("div"); leg.id = "sector-legend"; leg.className = "sector-legend"; $("sectors").after(leg); }
  leg.innerHTML = P.sectors.map((s, k) => `<span><i class="sw" style="background:${SECTOR_COLORS[k % SECTOR_COLORS.length]}"></i>${esc(s.name)} ${Math.round(s.weight * 100)}%</span>`).join("");
}

function renderThemes() {
  const ts = (P?.themes || []).filter((t) => t.active);
  $("themes").innerHTML = ts.map((t) => `<span class="chip theme" title="${esc(t.source)}"><span>Тема: ${esc(t.query)} · до ${Math.round(t.max_share * 100)}% · ${t.matches.length} бумаг</span>
    <button data-theme="${t.id}" aria-label="Убрать тему">✕</button></span>`).join("");
}

function renderSecList() {
  if (!P || P.error) { $("sec-list").innerHTML = `<div class="muted small">${UNI_OK ? "" : "Список бумаг появится после сборки базы."}</div>`; return; }
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === TAB));
  const list = P[TAB] || [];
  const target = { ...P.target, ...(S.manual_axes || {}) };
  if (!list.length) { $("sec-list").innerHTML = `<div class="muted small">Пусто.</div>`; return; }
  $("sec-list").innerHTML = list.map((h) => {
    const fitCls = h.fit >= 80 ? "good" : h.fit >= 65 ? "warn" : "bad";
    const sub = h.blocked ? `${Cabinet.icon("lock",14)} ${esc(h.blocked)}` : `${esc(h.sector_ru)}${h.theme ? " · тема" : ""}`;
    const right = TAB === "holdings" ? `<div class="w">${Math.round(h.weight * 100)}% · ${krub(h.rub)}</div>` : "";
    return `<button class="sec ${SEL === h.secid ? "sel" : ""}" data-sec="${h.secid}">${mini(h.axes, target)}
      <div class="mid"><div class="nm">${esc(h.shortname)} <span class="muted small">${esc(h.secid)}</span></div><div class="sub">${sub}</div></div>
      <div><div class="fit ${fitCls}">${h.fit}%</div>${right}</div></button>`;
  }).join("");
}

function findSec(secid) {
  return ["holdings", "candidates", "blocked"].map((k) => (P?.[k] || []).find((h) => h.secid === secid)).find(Boolean);
}

async function renderDetail(fetchExplain = true) {
  const h = findSec(SEL);
  const box = $("sec-detail");
  if (!h) { box.classList.add("hidden"); return; }
  box.classList.remove("hidden");
  const target = { ...P.target, ...(S.manual_axes || {}) };
  const g = { cx: 180, cy: 150, R: 105 };
  let svg = gridSvg(g);
  svg += `<polygon points="${poly(target, g)}" fill="#FFDD2D" fill-opacity="0.18" stroke="#FFDD2D" stroke-width="1.5"/>`;
  svg += `<polygon points="${poly(h.axes, g)}" fill="var(--chart-comparison)" fill-opacity="0.12" stroke="var(--chart-comparison)" stroke-width="2"/>`;
  const gi = AX.indexOf(h.gap_axis);
  const [x1, y1] = pt(gi, target[h.gap_axis], g), [x2, y2] = pt(gi, h.axes[h.gap_axis], g);
  svg += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="var(--orange)" stroke-width="4" stroke-linecap="round"/>`;
  AX.forEach((a, i) => { const L = labelPos(i, g); svg += `<text x="${L.x}" y="${L.y + 4}" text-anchor="${L.anchor}" font-size="14" fill="${a === h.gap_axis ? "var(--orange)" : "var(--chart-text)"}">${esc(META.axis_ru[a])}</text>`; });
  const rows = AX.map((a) => `<span>${esc(META.axis_ru[a])}</span><span class="muted">${num(target[a])}</span><b>${num(h.axes[a])}</b>`).join("");
  const inPf = h.weight > 0 ? `${Math.round(h.weight * 100)}% портфеля · ${h.lots} лот. · ${krub(h.rub)}` : (h.blocked ? "исключена красной линией" : "не в портфеле");
  const explainHtml = box.dataset.sec === h.secid && box.dataset.text ? esc(box.dataset.text) : `<span class="spin"></span> агент объясняет…`;
  box.innerHTML = `<div class="row"><div><div class="h3">${esc(h.shortname)} <span class="muted small">${esc(h.secid)}</span></div>
      <div class="muted small">${esc(h.sector_ru)} · ${esc(inPf)}</div></div><button class="ghost" id="detail-close" aria-label="Закрыть">✕</button></div>
    ${h.description ? `<div class="small">${esc(h.description)}</div>` : ""}
    <svg viewBox="0 0 360 290" role="img" aria-label="Наложение вашей формы и формы бумаги">${svg}</svg>
    <div class="axes-table"><span class="hd">Ось</span><span class="hd">вам нужно</span><span class="hd">у бумаги</span>${rows}</div>
    <div class="explain" id="explain">${explainHtml}</div>
    <div class="row gap">${h.blocked ? "" : `<button class="secondary" id="exclude">Исключить бумагу</button>`}
      <span class="muted small">Цена ${rub(h.price)} · лот ${h.lot} · див./купон ${num((h.div_yield || 0) * 100)}%</span></div>`;
  if (!fetchExplain || (box.dataset.sec === h.secid && box.dataset.text)) return;
  box.dataset.sec = h.secid; box.dataset.text = "";
  try {
    const j = await api("/api/explain", { state: S, secid: h.secid });
    if (SEL !== h.secid) return;
    box.dataset.text = j.text; $("explain").textContent = j.text;
  } catch (e) { $("explain").textContent = "Не удалось получить объяснение: " + e.message; }
}

function renderAgent() {
  document.querySelectorAll(".seg button").forEach((b) => { const on = b.dataset.v === (S.autonomy || "ask"); b.classList.toggle("on", on); b.setAttribute("aria-checked", on); });
  const has = !!S.executed;
  $("trust").textContent = has ? "Пересобрать по текущему мандату" : "Доверить портфель агенту";
  $("simulate").classList.toggle("hidden", !has);
  const log = (S.agent_log || []).slice().reverse();
  let head = "";
  if (has) head = `<div>Портфель у агента: <b>${rub(S.executed_value || S.amount_rub)}</b> · ${S.executed.length} бумаг</div>`;
  $("agent-log").innerHTML = head + log.map((e) => `<div><span class="muted">${esc(e.at)}</span> ${esc(e.text)}</div>`).join("");
}

// ---------------------------------------------------------------- действия
async function send(text, conflictId) {
  text = (text || "").trim();
  if (!text) { toast("Напишите хотя бы одну фразу"); return; }
  pushHist();
  const j = await api("/api/interpret", { state: S, text, conflict_id: conflictId || null });
  S = j.state; NEW_IDS = new Set(j.new_ids || []);
  if (j.reply) { $("reply").textContent = j.reply; $("reply").classList.remove("hidden"); }
  renderWishes(); renderConflicts(); renderParams();
  await recompute();
}

function mergeThemes(server) {
  const byId = {};
  (server.manual_themes || []).forEach((t) => (byId[t.id] = t));
  (server.wishes || []).forEach((w) => { if (w.theme) byId[w.theme.id] = w.theme; });
  const upd = (t) => { const s = byId[t.id]; if (s && s.resolved) { t.resolved = true; t.matches = s.matches; } };
  (S.manual_themes || []).forEach(upd);
  (S.wishes || []).forEach((w) => w.theme && upd(w.theme));
}

async function recompute() {
  if (!UNI_OK) { renderAll(); return; }
  const seq = ++RSEQ;
  const j = await api("/api/recompute", { state: S });
  if (seq !== RSEQ) return;
  mergeThemes(j.state);
  P = j.portfolio;
  renderAll();
  if (P.error) return;
  scheduleMandate();
}

function scheduleMandate() {
  clearTimeout(mandateTimer);
  $("mandate-status").innerHTML = `<span class="spin"></span> обновится`;
  mandateTimer = setTimeout(async () => {
    const seq = ++MSEQ;
    document.querySelector(".mandate").classList.add("loading");
    try {
      const j = await api("/api/mandate", { state: S });
      if (seq !== MSEQ) return;
      $("mandate").textContent = j.mandate;
      $("mandate-status").textContent = "обновлён только что";
    } catch (e) { $("mandate-status").textContent = "не удалось обновить"; fail(e); }
    finally { document.querySelector(".mandate").classList.remove("loading"); }
  }, 900);
}

function removeRedLine(id) {
  pushHist();
  if (id.startsWith("def_")) { S.disabled_defaults = [...(S.disabled_defaults || []), id]; }
  else {
    const w = (S.wishes || []).find((w) => w.red_line && w.red_line.id === id);
    if (w) w.red_line.active = false;
    S.manual_red_lines = (S.manual_red_lines || []).filter((l) => l.id !== id);
  }
  recompute().catch(fail);
}

function removeTheme(id) {
  pushHist();
  (S.manual_themes || []).forEach((t) => { if (t.id === id) t.active = false; });
  (S.wishes || []).forEach((w) => { if (w.theme && w.theme.id === id) w.theme.active = false; });
  recompute().catch(fail);
}

function openModal(prop) {
  PROPOSAL = prop;
  const initial = prop.kind === "initial";
  $("modal-title").textContent = initial ? "Агент предлагает собрать портфель" : (prop.trades.length ? "Портфель сместился от мандата" : "Портфель в порядке");
  $("modal-why").textContent = prop.rationale || "";
  let s = gridSvg();
  s += `<polygon points="${poly(prop.after_axes)}" fill="#FFDD2D" fill-opacity="0.25" stroke="#FFDD2D" stroke-width="2"/>`;
  if (prop.before_axes) s += `<polygon points="${poly(prop.before_axes)}" fill="none" stroke="var(--chart-text)" stroke-width="1.5"/>`;
  s += `<polygon points="${poly(prop.mandate_target)}" fill="none" stroke="var(--chart-ghost)" stroke-width="1.5" stroke-dasharray="5 5"/>`;
  AX.forEach((a, i) => { const L = labelPos(i); s += `<text x="${L.x}" y="${L.y + 4}" text-anchor="${L.anchor}" font-size="13" fill="var(--chart-text)">${esc(META.axis_ru[a])}</text>`; });
  $("modal-radar").innerHTML = s;
  $("fit-before").textContent = prop.fit_before == null ? "деньги на счёте" : prop.fit_before + "%";
  $("fit-after").textContent = prop.fit_after + "%";
  $("fit-after").className = "good";
  const before = Object.fromEntries((prop.checks_before || []).map((c) => [c.label, c.ok]));
  $("modal-checks").innerHTML = prop.checks_after.map((c) => {
    const was = before[c.label] === false ? ` <span class="warn small">сейчас нарушено</span>` : "";
    return `<div class="check"><span class="${c.ok ? "good" : "bad"}">${c.ok ? "✓" : "✕"}</span>${esc(c.label)}${was}</div>`;
  }).join("") || `<span class="muted small">Нет красных линий.</span>`;
  $("modal-trades").innerHTML = prop.trades.length ? prop.trades.map((t) => `<div class="trade"><div><span class="side ${t.side}">${t.side === "buy" ? "Купить" : "Продать"}</span> ${esc(t.shortname)}
      <div class="muted small">${t.lots} лот. · доля ${Math.round(t.weight_from * 100)}% → ${Math.round(t.weight_to * 100)}%</div></div><b>≈ ${krub(t.rub)}</b></div>`).join("")
    : `<span class="muted small">Сделки не нужны.</span>`;
  $("modal-confirm").disabled = !prop.trades.length;
  $("modal").classList.remove("hidden");
}
function closeModal() { $("modal").classList.add("hidden"); }

// ---------------------------------------------------------------- события
function bind() {
  $("send").onclick = () => busy($("send"), async () => { await send($("wish").value); $("wish").value = ""; });
  $("wish").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) $("send").click(); });
  const examples = [
    "Хочу стабильные дивиденды, чтобы через 5 лет был дополнительный доход. Нефть не хочу. Боюсь повторения 2022 года. Верю в российский IT.",
    "Готов рисковать ради роста на 10 лет, но без банков и не больше 10% в одной бумаге.",
    "Коплю на первый взнос через 2 года, главное — не потерять деньги.",
  ];
  $("examples").innerHTML = examples.map((t, k) => `<button class="example" data-ex="${k}">${esc(t.slice(0, 52))}…</button>`).join("");
  $("examples").onclick = (e) => { const b = e.target.closest("[data-ex]"); if (b) { $("wish").value = examples[+b.dataset.ex]; $("wish").focus(); } };

  $("wishes").onclick = (e) => {
    const b = e.target.closest("[data-wish]"); if (!b) return;
    pushHist();
    const w = S.wishes.find((x) => x.id === b.dataset.wish);
    w.status = w.status === "rejected" ? "accepted" : "rejected";
    NEW_IDS.clear(); renderWishes(); recompute().catch(fail);
  };
  $("conflicts").onclick = (e) => {
    const b = e.target.closest("[data-conflict]"); if (!b) return;
    busy(b, () => send("Выбираю: " + b.dataset.opt, b.dataset.conflict));
  };
  $("amount").oninput = () => ($("amount-v").textContent = rub(+$("amount").value));
  $("amount").onchange = () => { pushHist(); S.amount_rub = +$("amount").value; recompute().catch(fail); };
  $("horizon").oninput = () => ($("horizon-v").textContent = years(+$("horizon").value));
  $("horizon").onchange = () => { pushHist(); S.horizon_years = +$("horizon").value; recompute().catch(fail); };
  $("redlines").onclick = (e) => { const b = e.target.closest("[data-rl]"); if (b) removeRedLine(b.dataset.rl); };
  $("rl-form").onsubmit = (e) => {
    e.preventDefault();
    const text = $("rl-input").value.trim(); if (!text) return;
    busy(e.submitter, async () => {
      pushHist();
      const j = await api("/api/redline", { state: S, text });
      if (!j.added) { toast(j.message); return; }
      S = j.state; $("rl-input").value = ""; await recompute();
    });
  };
  $("theme-form").onsubmit = (e) => {
    e.preventDefault();
    const text = $("theme-input").value.trim(); if (!text) return;
    busy(e.submitter, async () => {
      pushHist();
      const j = await api("/api/theme", { state: S, text });
      S = j.state; P = j.portfolio; $("theme-input").value = ""; TAB = "holdings"; renderAll(); scheduleMandate();
    });
  };
  $("themes").onclick = (e) => { const b = e.target.closest("[data-theme]"); if (b) removeTheme(b.dataset.theme); };
  document.querySelector(".tabs").onclick = (e) => { const b = e.target.closest("[data-tab]"); if (b) { TAB = b.dataset.tab; renderSecList(); } };
  $("sec-list").onclick = (e) => {
    const b = e.target.closest("[data-sec]"); if (!b) return;
    SEL = b.dataset.sec; $("sec-detail").dataset.text = ""; renderSecList(); renderDetail(true);
  };
  $("sec-detail").onclick = (e) => {
    if (e.target.closest("#detail-close")) { SEL = null; renderSecList(); $("sec-detail").classList.add("hidden"); }
    if (e.target.closest("#exclude")) {
      const h = findSec(SEL); pushHist();
      S.manual_red_lines = [...(S.manual_red_lines || []), { id: "rx" + Date.now(), kind: "exclude_security", secid: h.secid,
        label: `Без ${h.shortname}`, source: "исключено вручную", active: true }];
      SEL = null; $("sec-detail").classList.add("hidden"); toast(`${h.shortname} исключена, агент пересобирает портфель`);
      recompute().catch(fail);
    }
  };

  // паутина: перетаскивание целевых точек
  const svg = $("radar");
  svg.addEventListener("pointerdown", (e) => {
    const h = e.target.closest(".handle");
    if (!h) return;
    pushHist(); DRAG = +h.dataset.i; GHOST = { ...(P && !P.error ? P.target : NEUTRAL), ...(S.manual_axes || {}) };
    svg.setPointerCapture(e.pointerId); e.preventDefault();
  });
  svg.addEventListener("pointermove", (e) => {
    if (DRAG === null) return;
    const p = svg.createSVGPoint(); p.x = e.clientX; p.y = e.clientY;
    const q = p.matrixTransform(svg.getScreenCTM().inverse());
    const a = (-90 + DRAG * 72) * Math.PI / 180;
    let v = ((q.x - G.cx) * Math.cos(a) + (q.y - G.cy) * Math.sin(a)) / G.R * 10;
    v = Math.round(Math.max(0, Math.min(10, v)) * 10) / 10;
    S.manual_axes = { ...(S.manual_axes || {}), [AX[DRAG]]: v };
    renderRadar();
    clearTimeout(dragTimer); dragTimer = setTimeout(() => recompute().catch(fail), 140);
  });
  const end = () => { if (DRAG !== null) { DRAG = null; recompute().catch(fail); } };
  svg.addEventListener("pointerup", end); svg.addEventListener("pointercancel", end);
  svg.addEventListener("click", (e) => {
    const t = e.target.closest(".axis-label"); if (!t) return;
    const a = t.dataset.axis;
    if (S.manual_axes && a in S.manual_axes) { pushHist(); delete S.manual_axes[a]; toast(`Ось «${META.axis_ru[a]}» откреплена: её снова задают ваши слова`); recompute().catch(fail); }
  });

  document.querySelector(".seg").onclick = (e) => { const b = e.target.closest("[data-v]"); if (b) { S.autonomy = b.dataset.v; renderAgent(); } };
  $("trust").onclick = () => busy($("trust"), async () => {
    const j = await api("/api/agent/propose", { state: S });
    mergeThemes(j.state); openModal(j.proposal);
  });
  $("simulate").onclick = () => busy($("simulate"), async () => {
    const j = await api("/api/agent/simulate", { state: S });
    S = j.state; renderAgent();
    if (j.applied) toast("Агент сам провёл ребалансировку в рамках мандата", 5000);
    else if (j.proposal.trades.length) openModal(j.proposal);
    else toast(`Квартал: ${pct(j.period.portfolio_return)}. Портфель в рамках мандата, сделки не нужны.`, 5000);
  });
  $("modal-close").onclick = closeModal;
  $("modal-reject").onclick = () => {
    S.agent_log = [...(S.agent_log || []), { at: new Date().toLocaleTimeString("ru-RU"), type: "rejected", text: "Предложение агента отклонено" }];
    closeModal(); renderAgent();
  };
  $("modal-confirm").onclick = () => busy($("modal-confirm"), async () => {
    const j = await api("/api/agent/confirm", { state: S, after: PROPOSAL.after });
    S = j.state; closeModal(); renderAgent(); toast("Сделки подтверждены");
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

  $("undo").onclick = () => {
    if (!HIST.length) { toast("Отменять нечего"); return; }
    S = JSON.parse(HIST.pop()); GHOST = null; recompute().catch(fail);
  };
  $("reset").onclick = () => {
    if (!confirm("Начать заново? Профиль и портфель агента будут очищены.")) return;
    S = {}; HIST = []; GHOST = null; SEL = null; NEW_IDS.clear();
    $("reply").classList.add("hidden"); $("mandate").textContent = "Появится, как только агент поймёт ваши пожелания.";
    recompute().catch(fail);
  };
}

async function init() {
  META = await api("/api/meta");
  UNI_OK = !!META.universe.ok;
  bind();
  if (!UNI_OK) {
    $("uni-error").innerHTML = `Нет базы бумаг, поэтому портфель и цифры пока не считаются. Паутину и параметры уже можно двигать.<br>
      В отдельном окне терминала, в папке проекта, выполните <code>python scripts/build_universe.py</code>, дождитесь «Готово» и обновите страницу.`;
    $("uni-error").classList.remove("hidden");
  } else {
    if (META.universe.demo) {
      $("uni-error").textContent = "Демо-данные: компании настоящие, но цены, дивиденды и история за 3 года условные.";
      $("uni-error").style.background = "#FFF7C9"; $("uni-error").style.color = "#333333"; $("uni-error").classList.remove("hidden");
    }
  }
  renderParams();
  await recompute();
}
init().catch(fail);
