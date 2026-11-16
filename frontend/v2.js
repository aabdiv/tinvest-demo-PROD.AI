"use strict";
// Пошаговый интерфейс: 1) пожелания и паутина, 2) бумаги, 3) итог и агент. Тот же API, что у подробного вида.
const AX = ["growth", "trend", "dividends", "stability", "quality"];
const NEUTRAL = Object.fromEntries(AX.map((a) => [a, 5]));
const DEFAULT_LINES = [
  { id: "def_maxpos", label: "Не больше 12% в одной бумаге", source: "по умолчанию", active: true },
  { id: "def_nomargin", label: "Без заёмных денег", source: "по умолчанию", active: true },
];
const WISH_HINTS = ["Хочу стабильный доход, дивиденды", "Хочу, чтобы деньги росли", "Боюсь больших просадок",
  "Коплю на покупку через 2 года", "Верю в российский IT", "Без нефти и газа"];
const RL_HINTS = ["Без нефти и газа", "Без банков", "Не больше 10% в одной бумаге", "Просадка не больше 50 тыс. ₽"];
const THEME_HINTS = ["Кто выиграет от снижения ставки", "Золото", "Импортозамещение", "Экспортёры"];
const SECTOR_COLORS = ["#FFDD2D", "#333333", "#888888", "#C4C4C4", "#A89100", "#575757", "#DED6A8", "#E5E5E5", "#999999", "#4A410E", "#A6A6A6", "#6F6F6F", "#C4B85C", "#BBBBBB"];
const LOCK = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>`;

let META = null, S = {}, P = null, HIST = [], GHOST = null, SEL = null, TAB = "holdings", PROPOSAL = null, STEP = 1;
let CHAT = [], USED_RL = new Set(), NEW_IDS = new Set(), RSEQ = 0, MSEQ = 0, mandateTimer = null, dragTimer = null, DRAG = null, UNI_OK = false, MANDATE = "";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (v, d = 1) => Number(v).toFixed(d).replace(".", ",");
const rub = (v) => Math.round(v).toLocaleString("ru-RU") + " ₽";
const krub = (v) => Math.round(v / 1000).toLocaleString("ru-RU") + " тыс. ₽";
const years = (n) => n + " " + (n % 10 === 1 && n % 100 !== 11 ? "год" : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? "года" : "лет");
const pct = (v, d = 1) => (v >= 0 ? "+" : "") + num(v * 100, d) + "%";
const ok = () => P && !P.error;

// ---------------------------------------------------------------- сервис
async function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  const j = await r.json().catch(() => ({}));
  if (j.llm) j.llm.forEach((m) => { $("lastcall").innerHTML = `${Cabinet.icon('clock',14)} <b>${num(m.ms / 1000)} с</b> · ${esc(m.what || "")} · ${esc(String(m.model || "").split("/").pop())}`; });
  if (!r.ok) throw new Error(j.detail || r.statusText);
  return j;
}
function toast(t, ms = 3500) { const el = $("toast"); el.textContent = t; el.classList.remove("hidden"); clearTimeout(toast.t); toast.t = setTimeout(() => el.classList.add("hidden"), ms); }
function fail(e) { console.error(e); toast("Ошибка: " + e.message, 6000); }
function pushHist() { HIST.push(JSON.stringify(S)); if (HIST.length > 60) HIST.shift(); }
async function busy(btn, fn) { if (btn) { btn.disabled = true; btn.setAttribute('aria-busy', 'true'); } try { await fn(); } catch (e) { fail(e); } finally { if (btn) { btn.disabled = false; btn.removeAttribute('aria-busy'); } } }

// ---------------------------------------------------------------- геометрия
const G = { cx: 290, cy: 205, R: 150 };
function pt(i, v, g = G) { const a = (-90 + i * 72) * Math.PI / 180; return [g.cx + g.R * v / 10 * Math.cos(a), g.cy + g.R * v / 10 * Math.sin(a)]; }
const poly = (vals, g = G) => AX.map((a, i) => pt(i, vals[a] ?? 0, g).map((n) => n.toFixed(1)).join(",")).join(" ");
function gridSvg(g = G) {
  let s = "";
  for (const r of [2.5, 5, 7.5, 10]) s += `<polygon points="${poly(Object.fromEntries(AX.map((a) => [a, r])), g)}" fill="none" stroke="var(--chart-grid)"/>`;
  AX.forEach((a, i) => { const [x, y] = pt(i, 10, g); s += `<line x1="${g.cx}" y1="${g.cy}" x2="${x}" y2="${y}" stroke="var(--chart-grid)"/>`; });
  return s;
}
function labelPos(i, g = G, k = 11.6) {
  const [x, y] = pt(i, k, g); const c = Math.cos((-90 + i * 72) * Math.PI / 180);
  return { x, y, anchor: c > 0.3 ? "start" : c < -0.3 ? "end" : "middle" };
}
function mini(axes, target, size = 64) {
  const g = { cx: size / 2, cy: size / 2, R: size / 2 - 3 };
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true">
    <polygon points="${poly(Object.fromEntries(AX.map((a) => [a, 10])), g)}" fill="none" stroke="var(--chart-grid)"/>
    ${target ? `<polygon points="${poly(target, g)}" fill="#FFDD2D" fill-opacity="0.2" stroke="#FFDD2D" stroke-width="1"/>` : ""}
    ${axes ? `<polygon points="${poly(axes, g)}" fill="none" stroke="var(--chart-comparison)" stroke-width="1.6"/>` : ""}</svg>`;
}
const target = () => ({ ...(ok() ? P.target : NEUTRAL), ...(S.manual_axes || {}) });

// ---------------------------------------------------------------- шаги
function go(n) {
  if (window.PortfolioWorkspace?.active && n !== 1) {
    document.getElementById("pf-holdings")?.scrollIntoView({ behavior: "smooth" });
    return;
  }
  STEP = n;
  [1, 2, 3].forEach((k) => $("step" + k).classList.toggle("hidden", k !== n));
  $("summary").classList.toggle("hidden", n === 3);
  $("summary").classList.toggle("wide", n === 1);
  document.querySelectorAll(".st").forEach((b) => { const k = +b.dataset.go; b.classList.toggle("on", k === n); b.classList.toggle("done", k < n); });
  $("back").classList.toggle("hidden", n === 1);
  $("next").classList.toggle("hidden", n === 3);
  $("next").textContent = n === 1 ? "Дальше: подобрать бумаги →" : "Дальше: итог →";
  window.scrollTo({ top: 0, behavior: "smooth" });
  renderAll();
}

// ---------------------------------------------------------------- рендер
function renderAll() {
  renderSummary(); renderChat(); renderParams(); renderRedLines(); renderRadar(); renderNotes();
  if (STEP === 2) { renderThemes(); renderSecGrid(); if (SEL) renderDetail(false); }
  if (STEP === 3) { renderFinal(); renderMetrics(); renderAgent(); }
  window.PortfolioWorkspace?.sync();
}

function renderSummary() {
  $("sum-radar").innerHTML = (() => {
    const g = { cx: 26, cy: 26, R: 23 };
    let s = `<polygon points="${poly(Object.fromEntries(AX.map((a) => [a, 10])), g)}" fill="none" stroke="var(--chart-grid)"/>`;
    s += `<polygon points="${poly(ok() ? P.achieved : target(), g)}" fill="#FFDD2D" fill-opacity="0.3" stroke="#FFDD2D" stroke-width="1.2"/>`;
    return s;
  })();
  const empty = !(S.wishes || []).length && !Object.keys(S.manual_axes || {}).length;
  $("sum-mandate").textContent = MANDATE && !empty ? MANDATE : "Портфель пока нейтральный. Расскажите о себе или потяните паутину.";
  if (ok()) {
    const m = P.metrics;
    $("sum-metrics").textContent = `За 3 года: ${pct(m.ann_return)} в год · худший момент −${krub(m.max_dd_rub)} · ${m.n} бумаг · совпадение ${P.fit}%`;
  } else $("sum-metrics").textContent = UNI_OK ? "" : "Цифры появятся после сборки базы бумаг";
}

function chipHtml(w) {
  const cls = ["chip", w.red_line ? "red" : w.theme ? "theme" : "", w.status === "rejected" ? "off" : "", NEW_IDS.has(w.id) ? "new" : ""].join(" ");
  const btn = w.status === "rejected" ? `<button data-wish="${w.id}" aria-label="Вернуть">↺</button>` : `<button data-wish="${w.id}" aria-label="Не согласен">✕</button>`;
  return `<span class="${cls}" title="«${esc(w.span)}»">${esc(w.label)}${btn}</span>`;
}
function renderChat() {
  const byW = Object.fromEntries((S.wishes || []).map((w) => [w.id, w]));
  const byC = Object.fromEntries((S.conflicts || []).map((c) => [c.id, c]));
  let h = `<div class="msg agent">Расскажите, чего вы хотите от этих денег: цель, срок, чего боитесь. Можно коротко.</div>`;
  for (const m of CHAT) {
    if (m.role === "user") { h += `<div class="msg user">${esc(m.text)}</div>`; continue; }
    if (m.role === "wait") { h += `<div class="msg agent"><span><span class="spin"></span> разбираю…</span></div>`; continue; }
    const ws = (m.ids || []).map((id) => byW[id]).filter(Boolean);
    const cs = (m.conflicts || []).map((id) => byC[id]).filter((c) => c && !c.resolved);
    h += `<div class="msg agent">${ws.length ? `<span>Понял так${ws.some((w) => w.status !== "rejected") ? " — не согласны, нажмите ✕" : ""}:</span><div class="chips">${ws.map(chipHtml).join("")}</div>` : `<span>${esc(m.text || "Принял.")}</span>`}
      ${cs.map((c) => `<div class="q"><div>${esc(c.text)}</div><div class="opts">${c.options.map((o, k) => `<button class="${k === 0 ? "primary" : "secondary"}" data-conflict="${c.id}" data-opt="${esc(o)}">${esc(o)}</button>`).join("")}</div></div>`).join("")}</div>`;
  }
  if (Cabinet.setHTML($("chat"), h)) $("chat").scrollTop = $("chat").scrollHeight;
}

function renderParams() {
  $("amount").value = S.amount_rub ?? 500000; $("amount-v").textContent = rub(S.amount_rub ?? 500000);
  $("horizon").value = S.horizon_years ?? 5; $("horizon-v").textContent = years(S.horizon_years ?? 5);
}

function renderRedLines() {
  const lines = (P?.red_lines || DEFAULT_LINES.filter((l) => !(S.disabled_defaults || []).includes(l.id))).filter((l) => l.active);
  Cabinet.setHTML($("redlines"), lines.map((l) => `<div class="rl"><div class="ico">${LOCK}</div>
    <div class="txt"><div>${esc(l.label)}</div><div class="src">${esc(l.source)}</div></div>
    <button data-rl="${l.id}" aria-label="Убрать запрет">✕</button></div>`).join(""));
  Cabinet.setHTML($("rl-hints"), RL_HINTS.filter((h) => !USED_RL.has(h)).map((h) => `<button class="hint red" data-rlhint="${esc(h)}">+ ${esc(h)}</button>`).join(""));
}

function radarSvg({ interactive }) {
  const t = target();
  const pinned = new Set(Object.keys(S.manual_axes || {}));
  let s = gridSvg();
  if (interactive && GHOST) s += `<polygon points="${poly(GHOST)}" fill="none" stroke="var(--chart-ghost)" stroke-width="1.5" stroke-dasharray="5 5"/>`;
  s += ok() ? `<polygon points="${poly(P.achieved)}" fill="#FFDD2D" fill-opacity="0.24" stroke="#FFDD2D" stroke-opacity="0.35"/>`
            : `<polygon points="${poly(t)}" fill="#FFDD2D" fill-opacity="0.12"/>`;
  s += `<polygon points="${poly(t)}" fill="none" stroke="#FFDD2D" stroke-width="2.5"/>`;
  AX.forEach((a, i) => {
    const [x, y] = pt(i, t[a]);
    if (interactive) s += `<circle class="handle" data-i="${i}" cx="${x}" cy="${y}" r="11" fill="#FFDD2D" stroke="${pinned.has(a) ? "var(--chart-text)" : "none"}" stroke-width="3"/>`;
    const L = labelPos(i);
    s += `<text class="axis-label" data-axis="${a}" x="${L.x}" y="${L.y - 4}" text-anchor="${L.anchor}" fill="var(--chart-text)" font-size="18" font-weight="700">${esc(META.axis_ru[a])}<title>${esc(META.axis_method[a])}</title></text>`;
    if (interactive && pinned.has(a)) s += Cabinet.pin(L.x, L.y + 32);
    const val = ok() ? P.achieved[a] : t[a];
    const col = !ok() ? "var(--chart-muted)" : Math.abs(P.achieved[a] - t[a]) < 1 ? "var(--green)" : Math.abs(P.achieved[a] - t[a]) < 2 ? "var(--orange)" : "var(--red)";
    s += `<text x="${L.x}" y="${L.y + 14}" text-anchor="${L.anchor}" font-size="18" font-weight="700" fill="${col}">${num(val)}</text>`;
  });
  if (ok()) {
    s += `<text x="${G.cx}" y="${G.cy + 8}" text-anchor="middle" font-size="42" font-weight="700" fill="var(--chart-text)">${P.fit}%</text>`;
    s += `<text x="${G.cx}" y="${G.cy + 28}" text-anchor="middle" font-size="14" fill="var(--chart-muted)">совпадение</text>`;
  }
  return s;
}
function renderRadar() { if (META) $("radar").innerHTML = radarSvg({ interactive: true }); }
function renderFinal() { if (META) $("radar3").innerHTML = radarSvg({ interactive: false }); $("mandate").textContent = MANDATE || "Появятся, как только агент поймёт ваши пожелания."; }
function renderNotes() { $("notes").innerHTML = (P?.error ? [P.error] : (P?.notes || [])).map((n) => `<div class="note">${esc(n)}</div>`).join(""); }

function renderMetrics() {
  if (!ok()) {
    ["m-ret", "m-dd", "m-inc"].forEach((id) => { $(id).textContent = "—"; $(id).className = ""; });
    $("spark").innerHTML = `<text x="300" y="60" text-anchor="middle" font-size="13" fill="var(--chart-muted)">${UNI_OK ? "" : "Появится после сборки базы бумаг"}</text>`;
    $("sectors").innerHTML = ""; $("sector-legend").innerHTML = ""; return;
  }
  const m = P.metrics, amt = S.amount_rub ?? 500000;
  $("m-ret").textContent = pct(m.ann_return); $("m-ret").className = m.ann_return >= 0 ? "good" : "bad";
  $("m-dd").textContent = "−" + krub(m.max_dd_rub); $("m-dd").className = m.dd_ok ? "" : "bad";
  $("m-inc").textContent = "≈ " + krub(m.income_year_rub);
  const v = P.backtest.values;
  if (v.length > 1) {
    const lo = Math.min(...v, amt), hi = Math.max(...v, amt);
    const X = (i) => (i / (v.length - 1)) * 600, Y = (y) => 110 - ((y - lo) / (hi - lo || 1)) * 100;
    $("spark").innerHTML = `<line x1="0" x2="600" y1="${Y(amt)}" y2="${Y(amt)}" stroke="var(--chart-grid)" stroke-dasharray="4 4"/>
      <polyline points="${v.map((y, i) => `${X(i).toFixed(1)},${Y(y).toFixed(1)}`).join(" ")}" fill="none" stroke="#FFDD2D" stroke-width="2" vector-effect="non-scaling-stroke"/>
      <title>Было ${rub(amt)}, стало бы ${rub(v[v.length - 1])}</title>`;
  }
  $("sectors").innerHTML = P.sectors.map((s, k) => `<div style="flex:${s.weight};background:${SECTOR_COLORS[k % SECTOR_COLORS.length]}"></div>`).join("");
  $("sector-legend").innerHTML = P.sectors.map((s, k) => `<span><i class="sw" style="background:${SECTOR_COLORS[k % SECTOR_COLORS.length]}"></i>${esc(s.name)} ${Math.round(s.weight * 100)}%</span>`).join("");
}

function renderThemes() {
  const ts = (P?.themes || []).filter((t) => t.active);
  $("themes").innerHTML = ts.map((t) => `<span class="chip theme">Ищу: ${esc(t.query)} · ${t.matches.length} бумаг<button data-theme="${t.id}" aria-label="Убрать">✕</button></span>`).join("");
  const have = new Set(ts.map((t) => t.query.toLowerCase()));
  $("theme-hints").innerHTML = THEME_HINTS.filter((h) => !have.has(h.toLowerCase())).map((h) => `<button class="hint" data-themehint="${esc(h)}">${esc(h)}</button>`).join("");
}

function badge(fit) { return `<span class="badge ${fit >= 80 ? "good" : fit >= 65 ? "warn" : "bad"}">${fit}%</span>`; }

function renderSecGrid() {
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === TAB));
  if (!ok()) { $("sec-grid").innerHTML = `<div class="muted">${UNI_OK ? "Не удалось собрать портфель." : "Бумаги появятся после сборки базы."}</div>`; return; }
  $("cnt-h").textContent = P.holdings.length; $("cnt-c").textContent = P.candidates.length; $("cnt-b").textContent = P.blocked.length;
  const list = P[TAB] || [], t = target();
  $("sec-grid").innerHTML = list.length ? list.map((h) => `<button class="sec ${SEL === h.secid ? "sel" : ""}" data-sec="${h.secid}">
      <div class="top-line"><div><div class="nm">${esc(h.shortname)}</div><div class="sub2">${esc(h.sector_ru)}</div></div>${h.blocked ? "" : badge(h.fit)}</div>
      <div class="mid">${mini(h.axes, t)}<div class="sub2">${h.blocked ? `${Cabinet.icon("lock",14)} ${esc(h.blocked)}` : TAB === "holdings" ? `<b style="color:var(--text);font-size:18px">${Math.round(h.weight * 100)}%</b><br>${krub(h.rub)}` : "можно добавить"}</div></div>
    </button>`).join("") : `<div class="muted">Пусто.</div>`;
}

function findSec(id) { return ["holdings", "candidates", "blocked"].map((k) => (P?.[k] || []).find((h) => h.secid === id)).find(Boolean); }

async function renderDetail(fetchExplain = true) {
  const h = findSec(SEL), box = $("sec-detail");
  if (!h) { box.innerHTML = `<div class="muted">Нажмите на бумагу, чтобы увидеть подробности.</div>`; return; }
  const t = target(), g = { cx: 180, cy: 150, R: 105 };
  let svg = gridSvg(g);
  svg += `<polygon points="${poly(t, g)}" fill="#FFDD2D" fill-opacity="0.18" stroke="#FFDD2D" stroke-width="1.5"/>`;
  svg += `<polygon points="${poly(h.axes, g)}" fill="var(--chart-comparison)" fill-opacity="0.12" stroke="var(--chart-comparison)" stroke-width="2"/>`;
  const gi = AX.indexOf(h.gap_axis), [x1, y1] = pt(gi, t[h.gap_axis], g), [x2, y2] = pt(gi, h.axes[h.gap_axis], g);
  svg += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="var(--orange)" stroke-width="4" stroke-linecap="round"/>`;
  AX.forEach((a, i) => { const L = labelPos(i, g); svg += `<text x="${L.x}" y="${L.y + 4}" text-anchor="${L.anchor}" font-size="14" fill="${a === h.gap_axis ? "var(--orange)" : "var(--chart-text)"}">${esc(META.axis_ru[a])}</text>`; });
  const rows = AX.map((a) => `<span>${esc(META.axis_ru[a])}</span><span class="muted">${num(t[a])}</span><b>${num(h.axes[a])}</b>`).join("");
  const cached = box.dataset.sec === h.secid && box.dataset.text;
  box.innerHTML = `<div class="row"><div><div class="h3">${esc(h.shortname)}</div><div class="muted small">${esc(h.sector_ru)} · ${esc(h.secid)}</div></div>${h.blocked ? "" : badge(h.fit)}</div>
    <svg viewBox="0 0 360 290" role="img" aria-label="Ваш портфель и эта бумага">${svg}</svg>
    <div class="explain" id="explain">${cached ? esc(box.dataset.text) : `<span class="spin"></span> агент объясняет…`}</div>
    <details><summary class="muted small">Подробнее: оси и цена</summary>
      <div class="axes-table"><span class="hd">Ось</span><span class="hd">вам нужно</span><span class="hd">у бумаги</span>${rows}</div>
      <div class="muted small">${h.description ? esc(h.description) + "<br>" : ""}Цена ${rub(h.price)} · лот ${h.lot} · дивиденды/купон ${num((h.div_yield || 0) * 100)}%${h.weight > 0 ? ` · ${h.lots} лот. в портфеле` : ""}</div>
    </details>
    ${h.blocked ? "" : `<button class="secondary" id="exclude">Не хочу эту бумагу</button>`}`;
  if (!fetchExplain || cached) return;
  box.dataset.sec = h.secid; box.dataset.text = "";
  try {
    const j = await api("/api/explain", { state: S, secid: h.secid });
    if (SEL !== h.secid) return; box.dataset.text = j.text; $("explain").textContent = j.text;
  } catch (e) { $("explain").textContent = "Не удалось получить объяснение."; }
}

function renderAgent() {
  document.querySelectorAll(".choice button").forEach((b) => { const on = b.dataset.v === (S.autonomy || "ask"); b.classList.toggle("on", on); b.setAttribute("aria-checked", on); });
  const has = !!S.executed;
  $("trust").textContent = has ? "Пересобрать по новым правилам" : "Доверить портфель агенту";
  $("simulate").classList.toggle("hidden", !has);
  const head = has ? `<div>У агента: <b>${rub(S.executed_value || S.amount_rub)}</b> · ${S.executed.length} бумаг</div>` : "";
  $("agent-log").innerHTML = head + (S.agent_log || []).slice().reverse().map((e) => `<div><span class="muted">${esc(e.at)}</span> ${esc(e.text)}</div>`).join("");
  window.PortfolioWorkspace?.sync();
}

// ---------------------------------------------------------------- действия
async function send(text, conflictId, shown) {
  text = (text || "").trim();
  if (!text) { toast("Напишите хотя бы пару слов или нажмите готовую фразу"); return; }
  pushHist();
  CHAT.push({ role: "user", text: shown || text }, { role: "wait" }); renderChat();
  const before = new Set((S.conflicts || []).map((c) => c.id));
  try {
    const j = await api("/api/interpret", { state: S, text, conflict_id: conflictId || null });
    S = j.state; NEW_IDS = new Set(j.new_ids || []);
    CHAT.pop();
    CHAT.push({ role: "agent", ids: j.new_ids || [], text: j.reply, conflicts: (S.conflicts || []).filter((c) => !before.has(c.id)).map((c) => c.id) });
  } catch (e) { CHAT.pop(); CHAT.push({ role: "agent", text: "Не получилось разобрать, попробуйте ещё раз." }); throw e; }
  finally { renderChat(); }
  renderParams();
  await recompute();
}
function mergeThemes(server) {
  const by = {};
  (server.manual_themes || []).forEach((t) => (by[t.id] = t));
  (server.wishes || []).forEach((w) => { if (w.theme) by[w.theme.id] = w.theme; });
  const upd = (t) => { const s = by[t.id]; if (s && s.resolved) { t.resolved = true; t.matches = s.matches; } };
  (S.manual_themes || []).forEach(upd); (S.wishes || []).forEach((w) => w.theme && upd(w.theme));
}
async function recompute() {
  if (!UNI_OK) { renderAll(); return; }
  const seq = ++RSEQ;
  const j = await api("/api/recompute", { state: window.PortfolioWorkspace?.computeState?.() || S });
  if (seq !== RSEQ) return;
  mergeThemes(j.state); P = j.portfolio;
  renderAll();
  if (!P.error) scheduleMandate();
}
function scheduleMandate() {
  clearTimeout(mandateTimer);
  $("mandate-status").innerHTML = `<span class="spin"></span>`;
  mandateTimer = setTimeout(async () => {
    const seq = ++MSEQ;
    document.querySelector(".mandate").classList.add("loading");
    try {
      const j = await api("/api/mandate", { state: S });
      if (seq !== MSEQ) return;
      MANDATE = j.mandate; $("mandate-status").textContent = ""; renderSummary(); if (STEP === 3) renderFinal();
    } catch (e) { $("mandate-status").textContent = "не обновились"; }
    finally { document.querySelector(".mandate").classList.remove("loading"); }
  }, 900);
}
async function addRedLine(text) {
  pushHist();
  const j = await api("/api/redline", { state: S, text });
  if (!j.added) { toast(j.message); return; }
  S = j.state; await recompute(); toast("Запрет добавлен");
}
async function addTheme(text) {
  pushHist();
  const j = await api("/api/theme", { state: S, text });
  S = j.state; P = j.portfolio; TAB = "holdings"; renderAll(); scheduleMandate();
}
function removeRedLine(id) {
  pushHist();
  if (id.startsWith("def_")) S.disabled_defaults = [...(S.disabled_defaults || []), id];
  else {
    const w = (S.wishes || []).find((w) => w.red_line && w.red_line.id === id); if (w) w.red_line.active = false;
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
  $("modal-title").textContent = prop.kind === "initial" ? "Агент предлагает собрать портфель" : (prop.trades.length ? "Портфель отошёл от ваших правил" : "Всё в порядке");
  $("modal-why").textContent = prop.rationale || "";
  let s = gridSvg();
  s += `<polygon points="${poly(prop.after_axes)}" fill="#FFDD2D" fill-opacity="0.25" stroke="#FFDD2D" stroke-width="2"/>`;
  if (prop.before_axes) s += `<polygon points="${poly(prop.before_axes)}" fill="none" stroke="var(--chart-text)" stroke-width="1.5"/>`;
  s += `<polygon points="${poly(prop.mandate_target)}" fill="none" stroke="var(--chart-ghost)" stroke-width="1.5" stroke-dasharray="5 5"/>`;
  AX.forEach((a, i) => { const L = labelPos(i); s += `<text x="${L.x}" y="${L.y + 4}" text-anchor="${L.anchor}" font-size="14" fill="var(--chart-text)">${esc(META.axis_ru[a])}</text>`; });
  $("modal-radar").innerHTML = s;
  $("fit-before").textContent = prop.fit_before == null ? "деньги на счёте" : prop.fit_before + "%";
  $("fit-after").textContent = prop.fit_after + "%"; $("fit-after").className = "good";
  const before = Object.fromEntries((prop.checks_before || []).map((c) => [c.label, c.ok]));
  $("modal-checks").innerHTML = prop.checks_after.map((c) => `<div class="check"><span class="${c.ok ? "good" : "bad"}">${c.ok ? "✓" : "✕"}</span>${esc(c.label)}${before[c.label] === false ? ` <span class="warn small">сейчас нарушено</span>` : ""}</div>`).join("");
  $("modal-trades").innerHTML = prop.trades.length ? prop.trades.map((t) => `<div class="trade"><div><span class="side ${t.side}">${t.side === "buy" ? "Купить" : "Продать"}</span> ${esc(t.shortname)}
      <div class="muted small">${t.lots} лот. · доля ${Math.round(t.weight_from * 100)}% → ${Math.round(t.weight_to * 100)}%</div></div><b>≈ ${krub(t.rub)}</b></div>`).join("") : `<span class="muted">Сделки не нужны.</span>`;
  $("modal-confirm").disabled = !prop.trades.length;
  $("modal").classList.remove("hidden");
}
const closeModal = () => $("modal").classList.add("hidden");

// ---------------------------------------------------------------- события
function bind() {
  document.querySelectorAll(".st").forEach((b) => (b.onclick = () => go(+b.dataset.go)));
  $("back").onclick = () => go(Math.max(1, STEP - 1));
  $("next").onclick = () => go(Math.min(3, STEP + 1));
  $("hints").innerHTML = WISH_HINTS.map((h) => `<button class="hint" data-hint="${esc(h)}">${esc(h)}</button>`).join("");
  $("hints").onclick = (e) => {
    const b = e.target.closest("[data-hint]"); if (!b) return;
    const cur = $("wish").value.trim();
    $("wish").value = (cur ? cur.replace(/[.!?]?$/, ". ") : "") + b.dataset.hint + ".";
    b.remove(); $("wish").focus();
  };
  $("send").onclick = () => busy($("send"), async () => { await send($("wish").value); $("wish").value = ""; bind.hintsReset(); });
  bind.hintsReset = () => { $("hints").innerHTML = WISH_HINTS.map((h) => `<button class="hint" data-hint="${esc(h)}">${esc(h)}</button>`).join(""); };
  $("wish").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) $("send").click(); });
  $("chat").onclick = (e) => {
    const c = e.target.closest("[data-conflict]");
    if (c) { busy(c, () => send("Выбираю: " + c.dataset.opt, c.dataset.conflict, c.dataset.opt)); return; }
    const b = e.target.closest("[data-wish]"); if (!b) return;
    pushHist(); const w = S.wishes.find((x) => x.id === b.dataset.wish); if (!w) return;
    w.status = w.status === "rejected" ? "accepted" : "rejected"; NEW_IDS.clear(); renderChat(); recompute().catch(fail);
  };
  $("amount").oninput = () => ($("amount-v").textContent = rub(+$("amount").value));
  $("amount").onchange = () => { pushHist(); S.amount_rub = +$("amount").value; recompute().catch(fail); };
  $("horizon").oninput = () => ($("horizon-v").textContent = years(+$("horizon").value));
  $("horizon").onchange = () => { pushHist(); S.horizon_years = +$("horizon").value; recompute().catch(fail); };
  $("redlines").onclick = (e) => { const b = e.target.closest("[data-rl]"); if (b) removeRedLine(b.dataset.rl); };
  $("rl-hints").onclick = (e) => { const b = e.target.closest("[data-rlhint]"); if (b) busy(b, async () => { await addRedLine(b.dataset.rlhint); USED_RL.add(b.dataset.rlhint); renderRedLines(); }); };
  $("rl-form").onsubmit = (e) => { e.preventDefault(); const t = $("rl-input").value.trim(); if (t) busy(e.submitter, async () => { await addRedLine(t); $("rl-input").value = ""; }); };
  $("theme-form").onsubmit = (e) => { e.preventDefault(); const t = $("theme-input").value.trim(); if (t) busy(e.submitter, async () => { await addTheme(t); $("theme-input").value = ""; }); };
  $("theme-hints").onclick = (e) => { const b = e.target.closest("[data-themehint]"); if (b) busy(b, () => addTheme(b.dataset.themehint)); };
  $("themes").onclick = (e) => { const b = e.target.closest("[data-theme]"); if (b) removeTheme(b.dataset.theme); };
  document.querySelector(".tabs").onclick = (e) => { const b = e.target.closest("[data-tab]"); if (b) { TAB = b.dataset.tab; renderSecGrid(); } };
  $("sec-grid").onclick = (e) => { const b = e.target.closest("[data-sec]"); if (!b) return; SEL = b.dataset.sec; $("sec-detail").dataset.text = ""; renderSecGrid(); renderDetail(true); };
  $("sec-detail").onclick = (e) => {
    if (!e.target.closest("#exclude")) return;
    const h = findSec(SEL); pushHist();
    S.manual_red_lines = [...(S.manual_red_lines || []), { id: "rx" + Date.now(), kind: "exclude_security", secid: h.secid, label: `Без ${h.shortname}`, source: "убрано на шаге «Бумаги»", active: true }];
    SEL = null; toast(`${h.shortname} убрана, агент подобрал замену`); recompute().catch(fail);
  };

  const svg = $("radar");
  svg.addEventListener("pointerdown", (e) => {
    const h = e.target.closest(".handle"); if (!h) return;
    pushHist(); DRAG = +h.dataset.i; GHOST = target(); svg.setPointerCapture(e.pointerId); e.preventDefault();
  });
  svg.addEventListener("pointermove", (e) => {
    if (DRAG === null) return;
    const p = svg.createSVGPoint(); p.x = e.clientX; p.y = e.clientY;
    const q = p.matrixTransform(svg.getScreenCTM().inverse()), a = (-90 + DRAG * 72) * Math.PI / 180;
    let v = ((q.x - G.cx) * Math.cos(a) + (q.y - G.cy) * Math.sin(a)) / G.R * 10;
    S.manual_axes = { ...(S.manual_axes || {}), [AX[DRAG]]: Math.round(Math.max(0, Math.min(10, v)) * 10) / 10 };
    renderRadar(); clearTimeout(dragTimer); dragTimer = setTimeout(() => recompute().catch(fail), 140);
  });
  const end = () => { if (DRAG !== null) { DRAG = null; recompute().catch(fail); } };
  svg.addEventListener("pointerup", end); svg.addEventListener("pointercancel", end);
  svg.addEventListener("click", (e) => {
    const t = e.target.closest(".axis-label"); if (!t) return; const a = t.dataset.axis;
    if (S.manual_axes && a in S.manual_axes) { pushHist(); delete S.manual_axes[a]; toast(`«${META.axis_ru[a]}» снова задают ваши слова`); recompute().catch(fail); }
  });

  document.querySelector(".choice").onclick = (e) => { const b = e.target.closest("[data-v]"); if (b) { S.autonomy = b.dataset.v; renderAgent(); } };
  $("trust").onclick = () => busy($("trust"), async () => { const j = await api("/api/agent/propose", { state: S }); mergeThemes(j.state); openModal(j.proposal); });
  $("simulate").onclick = () => busy($("simulate"), async () => {
    const j = await api("/api/agent/simulate", { state: S }); S = j.state; renderAgent();
    if (j.applied) toast("Агент сам поправил портфель в рамках ваших правил", 5000);
    else if (j.proposal.trades.length) openModal(j.proposal);
    else toast(`За квартал ${pct(j.period.portfolio_return)}. Всё в рамках правил, сделки не нужны.`, 5000);
  });
  $("modal-close").onclick = closeModal;
  $("modal-reject").onclick = () => { S.agent_log = [...(S.agent_log || []), { at: new Date().toLocaleTimeString("ru-RU"), type: "rejected", text: "Вы отклонили предложение агента" }]; closeModal(); renderAgent(); };
  $("modal-confirm").onclick = () => busy($("modal-confirm"), async () => { const j = await api("/api/agent/confirm", { state: S, after: PROPOSAL.after }); S = j.state; closeModal(); renderAgent(); toast("Готово, сделки подтверждены"); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
  $("undo").onclick = () => { if (!HIST.length) { toast("Отменять нечего"); return; } S = JSON.parse(HIST.pop()); GHOST = null; recompute().catch(fail); };
  $("reset").onclick = () => {
    if (!confirm("Начать заново?")) return;
    S = {}; HIST = []; GHOST = null; SEL = null; MANDATE = ""; CHAT = []; NEW_IDS.clear(); USED_RL.clear(); go(1); recompute().catch(fail);
  };
}

async function init() {
  META = await api("/api/meta");
  UNI_OK = !!META.universe.ok;
  if (window.PortfolioWorkspace && !(await window.PortfolioWorkspace.load())) return;
  bind();
  if (!UNI_OK) {
    $("uni-error").innerHTML = `Нет базы бумаг: паутину и параметры можно двигать, но бумаги и цифры пока не считаются.<br>
      В папке проекта выполните <code>python scripts/build_universe.py</code> и обновите страницу.`;
    $("uni-error").classList.remove("hidden");
  }
  if (UNI_OK && META.universe.demo) {
    $("uni-error").textContent = "Демо-данные: компании настоящие, но цены, дивиденды и история за 3 года условные.";
    $("uni-error").classList.add("demo"); $("uni-error").classList.remove("hidden");
    $("hist-note").textContent = "Условная история на демо-данных, не реальные котировки";
  }
  go(1);
  await recompute();
}
init().catch(fail);
