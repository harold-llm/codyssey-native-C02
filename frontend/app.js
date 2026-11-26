/* Compass — 전 연령 영어 학습 콘텐츠 추천 AI (바닐라 JS) */
const API = typeof API_BASE_URL !== "undefined" && API_BASE_URL ? API_BASE_URL : "";

const SKILL_KO = { listening: "듣기", reading: "읽기", speaking: "말하기", vocabulary: "어휘", writing: "쓰기", overall: "종합" };
const REACTION_KO = { easy: "쉬움", just_right: "적정", hard: "어려움" };
const LEVEL_KO = {
  L1: "L1 초입문", L2: "L2 기본 듣기", L3: "L3 짧은 문장",
  L4: "L4 기초 읽기", L5: "L5 쉬운 텍스트", L6: "L6 실제 자료",
};
const MODE_KO = {
  claude: "🤖 Claude", openai: "🤖 OpenAI", openrouter: "🤖 OpenRouter", local: "📚 오프라인 추천", guardrail: "🛡 안내",
};

const WELCOME = [
  "안녕하세요, Compass입니다. 🧭",
  "3세 아이부터 성인까지, 지금 나에게 맞는 영어 콘텐츠를 **이유와 함께** 찾아 드려요.",
  "",
  "· “리딩 잘하고 싶어”, “5살 아이랑 볼 영상 추천해줘”처럼 편하게 물어보세요",
  "· 수준이 아직 안 잡혀 있으면 “내 레벨 확인해줘”로 함께 찾아요",
  "",
  "영어는 결국 **스스로 집중해서 들인 시간**이 쌓여 자랍니다. 학습 후에는 「기록」 탭에서 1분만 남겨 주세요. 💪",
].join("\n");

const state = {
  history: [],        // {role, content}[] — 현재 대화 (API로 보내는 부분)
  conversationId: null,
  records: [],
  profile: {},
  summary: null,
  editingId: null,
  busy: false,
  recSkill: "",
};

const $ = (s) => document.querySelector(s);

/* ── API ─────────────────────────────────────────────── */
async function api(path, method = "GET", body) {
  let res;
  try {
    res = await fetch(API + path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해 주세요.");
  }
  if (!res.ok) {
    let detail = `${res.status} 오류`;
    try {
      const j = await res.json();
      if (typeof j.detail === "string") detail = j.detail;
      else if (Array.isArray(j.detail)) detail = j.detail.map((d) => d.msg.replace(/^Value error, /, "")).join(", ");
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

function toast(msg, isError = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.toggle("error", isError);
  t.hidden = false;
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => (t.hidden = true), 3200);
}

/* 비동기 핸들러 공통 오류 처리 */
function safe(fn) {
  return async (...args) => {
    try {
      return await fn(...args);
    } catch (err) {
      toast(err.message || String(err), true);
    }
  };
}

/* ── 렌더링 유틸 ─────────────────────────────────────── */
function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function safeUrl(u) {
  return /^https?:\/\//i.test(u) ? u : "#";
}
/* 최소 마크다운: **굵게**, [텍스트](링크), 맨 URL, 줄바꿈 */
function md(text) {
  let h = esc(text);
  h = h.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
  h = h.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  h = h.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>');
  h = h.replace(/\n/g, "<br>");
  return h;
}
function fmtTime(min) {
  return min >= 60 ? `${Math.floor(min / 60)}시간 ${min % 60}분` : `${min}분`;
}
/* 로컬 날짜 (toISOString은 UTC라 한국 오전에 전날로 찍힘) */
function today() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/* ── 추천 카드 ───────────────────────────────────────── */
function cardHtml(c, compact = false) {
  const skills = c.skills.map((s) => SKILL_KO[s] || s).join("·");
  const price = c.price_note ? ` title="${esc(c.price_note)}"` : "";
  const reasons = (c.reasons || []).slice(0, compact ? 2 : 3)
    .map((r) => `<li>${esc(r)}</li>`).join("");
  return `
    <div class="rec-card" data-id="${esc(c.id)}">
      <div class="rec-head">
        <a class="rec-title" href="${esc(safeUrl(c.link))}" target="_blank" rel="noopener">${esc(c.title)}</a>
        <span class="tag cost-${esc(c.cost)}"${price}>${esc(c.cost_ko)}</span>
      </div>
      <div class="rec-meta">${esc(c.type_ko)} · ${esc(skills)} · ${esc(c.levels)} · 1회 약 ${c.minutes}분</div>
      <p class="rec-why">${esc(c.why)}</p>
      ${compact ? "" : `<p class="rec-how">👉 ${esc(c.how_to)}</p>`}
      ${c.price_note ? `<p class="rec-price">💳 ${esc(c.price_note)}</p>` : ""}
      ${reasons ? `<ul class="rec-reasons">${reasons}</ul>` : ""}
      <div class="rec-actions">
        <a class="ghost small" href="${esc(safeUrl(c.link))}" target="_blank" rel="noopener">열기</a>
        <button type="button" class="ghost small log-btn">기록하기</button>
      </div>
    </div>`;
}

function bindCardActions(root, cards) {
  root.querySelectorAll(".rec-card").forEach((el) => {
    const c = cards.find((x) => x.id === el.dataset.id);
    if (!c) return;
    el.querySelector(".log-btn").onclick = () => logFromCard(c);
  });
}

function logFromCard(c) {
  resetRecordForm();
  $("#r-memo").value = c.title;
  $("#r-value").value = Math.min(c.minutes, state.profile.daily_minutes || c.minutes);
  const focus = state.profile.focus_skill;
  $("#r-skill").value = focus && c.skills.includes(focus) ? focus : c.skills[0] || "";
  $("#r-content-id").value = c.id;
  const linked = $("#r-linked");
  linked.hidden = false;
  linked.innerHTML = `🔗 카탈로그 연결: <b>${esc(c.title)}</b> — 느낌을 남기면 다음 추천에 반영돼요.`;
  switchView("records");
  $("#r-reaction").focus();
}

/* ── 채팅 메시지 ─────────────────────────────────────── */
function addMsg(role, content, extra = {}) {
  const box = $("#messages");
  const div = document.createElement("div");
  div.className = "msg " + role + (extra.isError ? " error" : "");
  div.innerHTML = md(content);

  if (extra.sources && extra.sources.length) {
    const s = document.createElement("div");
    s.className = "sources";
    s.innerHTML = "<b>참고 출처 (웹 검색)</b><ul>" +
      extra.sources.map((x) => `<li><a href="${esc(safeUrl(x.url))}" target="_blank" rel="noopener">${esc(x.title)}</a></li>`).join("") +
      "</ul>";
    div.appendChild(s);
  }
  if (extra.warnings && extra.warnings.length) {
    const w = document.createElement("div");
    w.className = "msg-warn";
    w.textContent = "ⓘ " + extra.warnings.join(" ");
    div.appendChild(w);
  }
  if (extra.mode && role === "assistant") {
    const m = document.createElement("div");
    m.className = "msg-mode";
    m.textContent = MODE_KO[extra.mode] || extra.mode;
    div.appendChild(m);
  }
  box.appendChild(div);

  if (extra.recommendations && extra.recommendations.length) {
    const wrap = document.createElement("div");
    wrap.className = "msg-cards";
    wrap.innerHTML = '<div class="msg-cards-title">📚 Compass 카탈로그 추천</div>' +
      extra.recommendations.map((c) => cardHtml(c, true)).join("");
    bindCardActions(wrap, extra.recommendations);
    box.appendChild(wrap);
  }
  box.scrollTop = box.scrollHeight;
}

function setLoading(on) {
  state.busy = on;
  $("#typing").hidden = !on;
  $("#send-btn").disabled = on;
  document.querySelectorAll("#quick-chips .chip").forEach((b) => (b.disabled = on));
}

/* ── 화면 전환 ───────────────────────────────────────── */
function switchView(v) {
  document.querySelectorAll(".view").forEach((s) => (s.hidden = s.id !== "view-" + v));
  document.querySelectorAll(".tabbar button").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
  if (v === "recommend") safe(loadRecommendations)();
  if (v === "records") safe(loadRecords)();
  if (v === "history") safe(loadConversations)();
  if (v === "summary") safe(loadSummary)();
  window.scrollTo({ top: 0 });
}

/* ── 채팅 ────────────────────────────────────────────── */
async function sendMessage(text) {
  text = (text ?? $("#chat-input").value).trim();
  if (!text || state.busy) return;
  $("#chat-input").value = "";

  addMsg("user", text);
  setLoading(true);
  try {
    const r = await api("/api/chat", "POST", {
      message: text,
      conversation_id: state.conversationId,
      history: state.history,
    });
    state.conversationId = r.conversation_id;
    state.history.push({ role: "user", content: text }, { role: "assistant", content: r.reply });
    addMsg("assistant", r.reply, r);
    if (r.warnings && r.warnings.length) loadHealth();
  } catch (err) {
    addMsg("assistant", `⚠️ ${err.message}`, { isError: true });
  } finally {
    setLoading(false);
  }
}

function newChat() {
  state.history = [];
  state.conversationId = null;
  $("#messages").innerHTML = "";
  addMsg("assistant", WELCOME);
}

/* ── 추천 탭 ─────────────────────────────────────────── */
async function loadRecommendations() {
  const params = new URLSearchParams({ limit: "8" });
  if (state.recSkill) params.set("skill", state.recSkill);
  if ($("#rec-free").checked) params.set("free_only", "true");
  const list = $("#rec-list");
  list.innerHTML = '<p class="hint">불러오는 중…</p>';
  const r = await api("/api/recommendations?" + params);

  const sig = $("#rec-signal");
  if (r.level_signal) {
    sig.hidden = false;
    sig.textContent = `💡 ${r.level_signal.message} (${r.level_signal.basis}) — 그래서 탐색 범위를 한 칸 옮겨 골랐어요.`;
  } else {
    sig.hidden = true;
  }

  let html = "";
  if (!r.profile_ready) {
    html += '<p class="hint">ⓘ 연령대가 설정되지 않아 전체 연령에서 골랐어요. 「요약」 탭에서 프로필을 저장하면 더 정확해져요.</p>';
  }
  if (!r.items.length) {
    html += '<p class="hint">조건에 맞는 콘텐츠가 없어요. 스킬 필터를 바꾸거나 레벨 설정을 확인해 주세요.</p>';
  }
  list.innerHTML = html + r.items.map((c) => cardHtml(c)).join("");
  bindCardActions(list, r.items);
}

/* ── 학습 기록 (CRUD) ────────────────────────────────── */
async function loadRecords() {
  state.records = await api("/api/data");
  renderRecords();
}

function renderRecords() {
  const list = $("#record-list");
  if (!state.records.length) {
    list.innerHTML = '<p class="hint">아직 기록이 없어요. 첫 학습이 끝나면 바로 남겨 보세요 — 1분이면 됩니다.</p>';
    return;
  }
  list.innerHTML = "";
  for (const r of state.records) {
    const el = document.createElement("div");
    el.className = "item";
    const tags = [
      r.skill ? SKILL_KO[r.skill] : "",
      r.reaction ? REACTION_KO[r.reaction] : "",
      r.content_id ? "🔗 카탈로그" : "",
    ].filter(Boolean).join(" · ");
    el.innerHTML = `
      <div class="item-main">
        <span class="item-title">${esc(r.memo)}</span>
        <span class="item-sub">${esc(r.date)} · ${r.value}분${tags ? " · " + esc(tags) : ""}</span>
      </div>
      <div class="item-actions">
        <button class="ghost edit" type="button">수정</button>
        <button class="ghost del" type="button">삭제</button>
      </div>`;
    el.querySelector(".edit").onclick = () => startEdit(r);
    el.querySelector(".del").onclick = safe(async () => {
      if (!confirm("이 기록을 삭제할까요?")) return;
      await api("/api/data/" + r.id, "DELETE");
      if (state.editingId === r.id) resetRecordForm();
      toast("기록을 삭제했어요");
      await loadRecords();
      await loadSummary();
    });
    list.appendChild(el);
  }
}

function startEdit(r) {
  state.editingId = r.id;
  $("#r-date").value = r.date;
  $("#r-value").value = r.value;
  $("#r-memo").value = r.memo;
  $("#r-skill").value = r.skill || "";
  $("#r-reaction").value = r.reaction || "";
  $("#r-content-id").value = r.content_id || "";
  $("#r-linked").hidden = !r.content_id;
  $("#r-linked").textContent = r.content_id ? "🔗 카탈로그와 연결된 기록이에요." : "";
  $("#record-save").textContent = "수정 저장";
  $("#record-cancel").hidden = false;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function resetRecordForm() {
  state.editingId = null;
  $("#record-form").reset();
  $("#r-date").value = today();
  $("#r-date").max = today();
  $("#r-content-id").value = "";
  $("#r-linked").hidden = true;
  $("#record-save").textContent = "추가";
  $("#record-cancel").hidden = true;
}

async function submitRecord(e) {
  e.preventDefault();
  const body = {
    date: $("#r-date").value,
    value: parseInt($("#r-value").value, 10),
    memo: $("#r-memo").value.trim(),
    skill: $("#r-skill").value || null,
    reaction: $("#r-reaction").value || null,
    content_id: $("#r-content-id").value || null,
  };
  if (!body.date || !body.value || !body.memo) return;
  if (state.editingId) await api("/api/data/" + state.editingId, "PUT", body);
  else await api("/api/data", "POST", body);
  toast(state.editingId ? "기록을 수정했어요" : "기록했어요! 오늘도 시간을 들였네요 👏");
  resetRecordForm();
  await loadRecords();
  await loadSummary();
}

/* ── 대화 기록 ───────────────────────────────────────── */
async function loadConversations() {
  const rows = await api("/api/conversations");
  const list = $("#conversation-list");
  if (!rows.length) {
    list.innerHTML = '<p class="hint">아직 저장된 대화가 없어요. 채팅을 시작하면 자동 저장됩니다.</p>';
    return;
  }
  list.innerHTML = "";
  for (const c of rows) {
    const el = document.createElement("div");
    el.className = "item" + (c.id === state.conversationId ? " current" : "");
    const d = c.updated_at ? new Date(c.updated_at) : null;
    el.innerHTML = `
      <div class="item-main">
        <span class="item-title">${esc(c.title)}</span>
        <span class="item-sub">${d ? esc(d.toLocaleString("ko-KR")) : ""} · 메시지 ${c.message_count || 0}개</span>
      </div>
      <div class="item-actions">
        <button class="ghost load" type="button">불러오기</button>
        <button class="ghost del" type="button">삭제</button>
      </div>`;
    el.querySelector(".load").onclick = safe(() => openConversation(c.id));
    el.querySelector(".del").onclick = safe(async () => {
      if (!confirm("이 대화를 삭제할까요?")) return;
      await api("/api/conversations/" + c.id, "DELETE");
      if (state.conversationId === c.id) newChat();
      toast("대화를 삭제했어요");
      await loadConversations();
    });
    list.appendChild(el);
  }
}

async function openConversation(id) {
  const c = await api("/api/conversations/" + id);
  const msgs = (c.messages || []).filter((m) => (m.role === "user" || m.role === "assistant") && m.content);
  state.conversationId = c.id;
  state.history = msgs.map((m) => ({ role: m.role, content: m.content }));
  $("#messages").innerHTML = "";
  for (const m of msgs) addMsg(m.role, m.content, m);
  switchView("chat");
}

/* ── 요약 ────────────────────────────────────────────── */
async function loadSummary() {
  state.summary = await api("/api/data/summary");
  renderSummary();
}

function renderLevelBadge() {
  const badge = $("#level-badge");
  const level = state.profile.level;
  badge.hidden = !level;
  badge.textContent = level ? LEVEL_KO[level] || level : "";
}

function renderSummary() {
  const s = state.summary;
  renderLevelBadge();

  const sig = $("#level-signal");
  if (s.level_signal) {
    const ls = s.level_signal;
    sig.hidden = false;
    sig.innerHTML = `💡 <b>레벨 재점검 제안</b> — ${esc(ls.message)} <span class="hint">(${esc(ls.basis)}${ls.suggested_level ? ` → ${esc(ls.suggested_level)} 검토` : ""})</span>
      <div><button type="button" class="ghost small" id="signal-chat">채팅으로 재점검하기</button></div>`;
    $("#signal-chat").onclick = () => {
      switchView("chat");
      sendMessage("최근 기록을 보고 내 레벨을 다시 확인해 줘");
    };
  } else {
    sig.hidden = true;
  }

  const b = $("#summary-body");
  if (!s.count) {
    b.innerHTML = '<p class="hint">아직 학습 기록이 없어요. 첫 기록이 들어가면 요약이 여기에 표시됩니다.</p>';
    renderChart(s.recent_days);
    return;
  }
  const m = s.metrics;
  const rows = [
    ["기간", s.period],
    ["총 학습량", fmtTime(m.total)],
    ["학습한 날", `${m.active_days}일 (평균 ${m.per_active_day}분)`],
    ["최근 7일", fmtTime(s.last_7_days)],
    ["최근 추세", s.trend],
    ["연속 기록", `${s.streak}일`],
  ];
  if (s.goal) rows.push(["주간 목표", `${s.goal.last_7_days}/${s.goal.weekly_target}분 (${s.goal.percent}%)`]);
  rows.push(["기록 수", `${s.count}개 (1회 평균 ${m.per_session}분)`]);
  let html = '<dl class="stats">' + rows.map(([k, v]) => `<div class="stat"><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join("") + "</dl>";

  if (Object.keys(s.skill_distribution).length) {
    const total = m.total || 1;
    html += '<h4 class="sub-title">스킬 분포</h4>' +
      Object.entries(s.skill_distribution).sort((a, b) => b[1] - a[1]).map(([k, v]) => {
        const pct = Math.round((v / total) * 100);
        return `<div class="bar-row"><span class="bar-label">${SKILL_KO[k] || esc(k)}</span><div class="bar"><div class="bar-fill" style="width:${pct}%"></div></div><span class="bar-val">${pct}%</span></div>`;
      }).join("");
  }
  const r = s.reaction;
  html += `<p class="hint" style="margin-top:10px;">느낌: 쉬움 ${r.easy} · 적정 ${r.just_right} · 어려움 ${r.hard}</p>`;
  b.innerHTML = html;
  renderChart(s.recent_days);
}

function renderChart(days) {
  const c = $("#chart");
  if (!days || !days.length || !days.some((d) => d.minutes > 0)) {
    c.innerHTML = '<p class="hint">최근 14일 기록 없음</p>';
    return;
  }
  const max = Math.max(...days.map((d) => d.minutes), 1);
  c.innerHTML = days.map((d) => {
    const h = d.minutes > 0 ? Math.max(Math.round((d.minutes / max) * 100), 3) : 0;
    return `<div class="bar-col" title="${d.date}: ${d.minutes}분"><div class="bar-col-fill" style="height:${h}%"></div><span>${d.date.slice(5)}</span></div>`;
  }).join("");
}

/* ── 프로필 ──────────────────────────────────────────── */
async function loadProfile() {
  state.profile = await api("/api/profile");
  const p = state.profile;
  $("#p-age").value = p.age_band || "";
  $("#p-level").value = p.level || "";
  $("#p-confidence").value = p.confidence || "";
  $("#p-focus").value = p.focus_skill || "";
  $("#p-goals").value = p.goals || "";
  $("#p-interests").value = p.interests || "";
  $("#p-minutes").value = p.daily_minutes || "";
  $("#p-free").checked = !!p.prefer_free;
  $("#onboarding").hidden = !!p.age_band;
  renderLevelBadge();
}

async function saveProfile(e) {
  e.preventDefault();
  const minutes = $("#p-minutes").value;
  state.profile = await api("/api/profile", "PUT", {
    age_band: $("#p-age").value || null,
    level: $("#p-level").value || null,
    confidence: $("#p-confidence").value || null,
    focus_skill: $("#p-focus").value || null,
    goals: $("#p-goals").value.trim() || null,
    interests: $("#p-interests").value.trim() || null,
    daily_minutes: minutes ? parseInt(minutes, 10) : null,
    prefer_free: $("#p-free").checked,
  });
  $("#onboarding").hidden = !!state.profile.age_band;
  await loadSummary();
  toast("프로필을 저장했어요. 이제 추천에 반영됩니다.");
}

async function quickSetAge(age) {
  state.profile = await api("/api/profile", "PUT", { age_band: age });
  await loadProfile();
  const who = age === "3-6" ? "아이와 함께 볼" : "나에게 맞는";
  sendMessage(`${who} 영어 콘텐츠를 추천해줘`);
}

async function loadHealth() {
  const badge = $("#mode-badge");
  try {
    const h = await api("/api/health");
    const llm = h.llm || {};
    if (llm.paused_reason) {
      badge.textContent = "⚠️ " + (MODE_KO[llm.provider] || llm.provider).replace("🤖 ", "") + " 일시 중단";
      badge.title = llm.paused_reason + " — 해결 후 서버를 재시작하면 바로 다시 연결돼요 (그 전엔 오프라인 추천).";
      return;
    }
    badge.textContent = MODE_KO[llm.provider] || llm.provider;
    badge.title = llm.provider === "local"
      ? "API 키가 없어 카탈로그 규칙 기반으로 답해요 (.env에 OPENROUTER_API_KEY 등을 설정하면 AI 모드)"
      : `${llm.model} · 웹 검색 ${llm.web_search ? "켜짐" : "꺼짐"} · 저장소 ${h.store}`;
  } catch {
    badge.textContent = "⚠️ 서버 연결 안 됨";
  }
}

/* ── 초기화 ──────────────────────────────────────────── */
window.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".tabbar button").forEach((btn) => {
    btn.onclick = () => switchView(btn.dataset.view);
  });

  // 다크 모드 (저장값 → 없으면 OS 설정)
  const saved = localStorage.getItem("theme");
  const preferDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  if (saved === "dark" || (!saved && preferDark)) {
    document.documentElement.dataset.theme = "dark";
    $("#dark-toggle").textContent = "☀️";
  }
  $("#dark-toggle").onclick = () => {
    const root = document.documentElement;
    const isDark = root.dataset.theme === "dark";
    if (isDark) delete root.dataset.theme;
    else root.dataset.theme = "dark";
    localStorage.setItem("theme", isDark ? "light" : "dark");
    $("#dark-toggle").textContent = isDark ? "🌙" : "☀️";
  };

  // 채팅
  $("#chat-form").onsubmit = (e) => {
    e.preventDefault();
    sendMessage();
  };
  $("#chat-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      $("#chat-form").requestSubmit();
    }
  });
  document.querySelectorAll("#quick-chips .chip").forEach((b) => {
    b.onclick = () => sendMessage(b.dataset.prompt);
  });
  $("#recheck-level").onclick = () => sendMessage("레벨을 다시 확인해 주세요. 최근 학습 기록도 함께 봐줄래요?");
  $("#new-chat").onclick = newChat;
  document.querySelectorAll("#onboarding-age .chip").forEach((b) => {
    b.onclick = safe(() => quickSetAge(b.dataset.age));
  });

  // 추천 탭 필터
  document.querySelectorAll("#rec-skills .chip").forEach((b) => {
    b.onclick = () => {
      state.recSkill = b.dataset.skill;
      document.querySelectorAll("#rec-skills .chip").forEach((x) => x.classList.toggle("active", x === b));
      safe(loadRecommendations)();
    };
  });
  $("#rec-free").onchange = safe(loadRecommendations);

  // 폼
  $("#record-form").onsubmit = safe(submitRecord);
  $("#record-cancel").onclick = resetRecordForm;
  $("#profile-form").onsubmit = safe(saveProfile);
  resetRecordForm();

  // 첫 화면
  addMsg("assistant", WELCOME);
  loadHealth();
  safe(async () => {
    await loadProfile();
    await loadSummary();
  })();
});
