/* Compass — 전 연령 영어 학습 콘텐츠 추천 AI (바닐라 JS) */
const API = typeof API_BASE_URL !== "undefined" && API_BASE_URL ? API_BASE_URL : "";

const SKILL_KO = { listening: "듣기", reading: "읽기", speaking: "말하기", vocabulary: "어휘", overall: "종합" };
const REACTION_KO = { easy: "쉬움", just_right: "적정", hard: "어려움" };
const LEVEL_KO = {
  L1: "L1 초입문", L2: "L2 기본 듣기", L3: "L3 짧은 문장",
  L4: "L4 기초 읽기", L5: "L5 쉬운 텍스트", L6: "L6 실제 자료",
};

const WELCOME = [
  "안녕하세요, Compass입니다. 🧭",
  "나에게 맞는 영어 학습을 찾아주는 비서예요.",
  "",
  "· “리딩 잘하고 싶어”, “오늘 뭘 할지 추천해줘”처럼 자연스럽게 물어보세요",
  "· 수준이 아직 안 잡혀 있으면 짧은 질문으로 함께 파악할게요",
  "",
  "영어는 결국 **스스로 집중해서 들인 시간**이 쌓여 자랍니다. 학습 후에는 「기록」 탭에서 1분만 남겨주세요. 💪",
].join("\n");

const state = {
  history: [],       // {role, content}[] — 현재 세션 대화
  conversationId: null,
  records: [],
  profile: {},
  summary: null,
  editingId: null,
  busy: false,
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
    throw new Error("서버에 연결할 수 없습니다. (배포/실행 상태를 확인해 주세요)");
  }
  if (!res.ok) {
    let detail = `${res.status} 오류`;
    try {
      const j = await res.json();
      if (typeof j.detail === "string") detail = j.detail;
      else if (Array.isArray(j.detail)) detail = j.detail.map((d) => d.msg).join(", ");
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

/* ── 렌더링 유틸 ─────────────────────────────────────── */
function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function md(text) {
  let h = esc(text);
  h = h.replace(/\*(.+?)\*/g, "<b>$1</b>");
  h = h.replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
  h = h.replace(/\n/g, "<br>");
  return h;
}
function fmtTime(min) {
  return min >= 60 ? `${Math.floor(min / 60)}시간 ${min % 60}분` : `${min}분`;
}

function addMsg(role, content, sources = null, isError = false) {
  const box = $("#messages");
  const div = document.createElement("div");
  div.className = "msg " + role + (isError ? " error" : "");
  div.innerHTML = md(content);
  if (sources && sources.length) {
    const s = document.createElement("div");
    s.className = "sources";
    s.innerHTML =
      "<b>참고 출처</b><ul>" +
      sources.map((x) => `<li><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a></li>`).join("") +
      "</ul>";
    div.appendChild(s);
  }
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

function setLoading(on) {
  state.busy = on;
  $("#typing").hidden = !on;
  $("#send-btn").disabled = on;
}

/* ── 화면 전환 ───────────────────────────────────────── */
function switchView(v) {
  document.querySelectorAll(".view").forEach((s) => (s.hidden = s.id !== "view-" + v));
  document.querySelectorAll(".tabbar button").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
  if (v === "records") loadRecords();
  if (v === "history") loadConversations();
  if (v === "summary") loadSummary();
}

/* ── 채팅 ────────────────────────────────────────────── */
async function sendMessage() {
  const input = $("#chat-input");
  const text = input.value.trim();
  if (!text || state.busy) return;
  input.value = "";

  addMsg("user", text);
  state.history.push({ role: "user", content: text });
  setLoading(true);
  try {
    const r = await api("/api/chat", "POST", {
      message: text,
      conversation_id: state.conversationId,
      history: state.history.slice(0, -1),
    });
    state.conversationId = r.conversation_id;
    state.history.push({ role: "assistant", content: r.reply });
    addMsg("assistant", r.reply, r.sources);
  } catch (err) {
    state.history.pop(); // 실패한 사용자 메시지 제거(재시도 시 일관성)
    addMsg("assistant", `⚠️ ${err.message}`, null, true);
  } finally {
    setLoading(false);
  }
}

/* ── 학습 기록 (CRUD) ────────────────────────────────── */
async function loadRecords() {
  state.records = await api("/api/data");
  renderRecords();
}

function renderRecords() {
  const list = $("#record-list");
  if (!state.records.length) {
    list.innerHTML = '<p class="hint">아직 기록이 없어요. 첫 학습이 끝나면 바로 남겨보세요 — 1분이면 됩니다.</p>';
    return;
  }
  list.innerHTML = "";
  for (const r of state.records) {
    const el = document.createElement("div");
    el.className = "item";
    el.innerHTML = `
      <div class="item-main">
        <span class="item-title">${esc(r.memo)}</span>
        <span class="item-sub">${r.date} · ${r.value}분${r.skill ? " · " + SKILL_KO[r.skill] : ""}${r.reaction ? " · " + REACTION_KO[r.reaction] : ""}</span>
      </div>
      <div class="item-actions">
        <button class="ghost edit" type="button">수정</button>
        <button class="ghost del" type="button">삭제</button>
      </div>`;
    el.querySelector(".edit").onclick = () => startEdit(r);
    el.querySelector(".del").onclick = async () => {
      if (!confirm("이 기록을 삭제할까요?")) return;
      await api("/api/data/" + r.id, "DELETE");
      loadRecords();
      loadSummary();
    };
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
  $("#record-save").textContent = "수정 저장";
  $("#record-cancel").hidden = false;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function resetRecordForm() {
  state.editingId = null;
  $("#record-form").reset();
  $("#r-date").value = new Date().toISOString().slice(0, 10);
  $("#record-save").textContent = "추가";
  $("#record-cancel").hidden = true;
}

/* ── 대화 기록 ───────────────────────────────────────── */
async function loadConversations() {
  const rows = await api("/api/conversations");
  const list = $("#conversation-list");
  if (!rows.length) {
    list.innerHTML = "<p class="hint">아직 저장된 대화가 없어요. 채팅을 시작하면 자동 저장됩니다.</p>";
    return;
  }
  list.innerHTML = "";
  for (const c of rows) {
    const el = document.createElement("div");
    el.className = "item";
    const d = c.created_at ? new Date(c.created_at) : null;
    el.innerHTML = `
      <div class="item-main">
        <span class="item-title">${esc(c.title)}</span>
        <span class="item-sub">${d ? d.toLocaleString("ko-KR") : ""}</span>
      </div>
      <div class="item-actions">
        <button class="ghost load" type="button">불러오기</button>
        <button class="ghost del" type="button">삭제</button>
      </div>`;
    el.querySelector(".load").onclick = () => openConversation(c.id);
    el.querySelector(".del").onclick = async () => {
      if (!confirm("이 대화를 삭제할까요?")) return;
      await api("/api/conversations/" + c.id, "DELETE");
      loadConversations();
    };
    list.appendChild(el);
  }
}

async function openConversation(id) {
  const c = await api("/api/conversations/" + id);
  state.conversationId = c.id;
  state.history = (c.messages || [])
    .filter((m) => (m.role === "user" || m.role === "assistant") && m.content)
    .map((m) => ({ role: m.role, content: m.content }));
  $("#messages").innerHTML = "";
  for (const m of state.history) addMsg(m.role, m.content);
  switchView("chat");
}

/* ── 요약 ────────────────────────────────────────────── */
async function loadSummary() {
  state.summary = await api("/api/data/summary");
  renderSummary();
}

function renderSummary() {
  const s = state.summary;
  const badge = $("#level-badge");
  if (s.level) {
    badge.hidden = false;
    badge.textContent = LEVEL_KO[s.level] || s.level;
  } else {
    badge.hidden = true;
  }

  const b = $("#summary-body");
  if (!s.count) {
    b.innerHTML = '<p class="hint">아직 학습 기록이 없어요. 첫 기록이 들어가면 요약이 여기에 표시됩니다.</p>';
    renderChart([]);
    return;
  }
  const m = s.metrics;
  const rows = [
    ["기간", s.period],
    ["기록 수", `${s.count}개`],
    ["총 학습량", fmtTime(m.total)],
    ["일평균", `${m.average}분`],
    ["최대 / 최소", `${m.max}분 / ${m.min}분`],
    ["최근 추세", s.trend],
    ["연속 기록", `${s.streak}일`],
  ];
  let html = '<dl class="stats">' + rows.map(([k, v]) => `<div class="stat"><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join("") + "</dl>";

  if (Object.keys(s.skill_distribution).length) {
    const total = m.total || 1;
    html += "<h3 style="margin: 12px 0 4px; font-size: 14px;">스킬 분포</h3>" +
      Object.entries(s.skill_distribution).map(([k, v]) => {
        const pct = Math.round((v / total) * 100);
        return `<div class="bar-row"><span class="bar-label">${SKILL_KO[k] || k}</span><div class="bar"><div class="bar-fill" style="width:${pct}%"></div></div><span class="bar-val">${pct}%</span></div>`;
      }).join("");
  }
  const r = s.reaction;
  const warn = r.easy >= 7 || r.hard >= 7
    ? " — 「채팅」에서 레벨 재점검을 요청해 보세요."
    : "";
  html += `<p class="hint" style="margin-top:10px;">반응: 쉬움 ${r.easy} · 적정 ${r.just_right} · 어려움 ${r.hard}${warn}</p>`;
  b.innerHTML = html;
  renderChart(s.recent_days);
}

function renderChart(days) {
  const c = $("#chart");
  if (!days || !days.length) {
    c.innerHTML = '<p class="hint">데이터 없음</p>';
    return;
  }
  const max = Math.max(...days.map((d) => d.minutes), 1);
  c.innerHTML = days
    .map((d) => {
      const h = d.minutes > 0 ? Math.max(Math.round((d.minutes / max) * 100), 3) : 0;
      return `<div class="bar-col" title="${d.date}: ${d.minutes}분"><div class="bar-col-fill" style="height:${h}%"></div><span>${d.date.slice(5)}</span></div>`;
    })
    .join("");
}

/* ── 프로필 ──────────────────────────────────────────── */
async function loadProfile() {
  state.profile = await api("/api/profile");
  const p = state.profile;
  $("#p-age").value = p.age_band || "";
  $("#p-level").value = p.level || "";
  $("#p-goals").value = p.goals || "";
  $("#p-minutes").value = p.daily_minutes || "";
}

/* ── 초기화 ──────────────────────────────────────────── */
window.addEventListener("DOMContentLoaded", () => {
  // 탭바
  document.querySelectorAll(".tabbar button").forEach((btn) => {
    btn.onclick = () => switchView(btn.dataset.view);
  });

  // 다크 모드
  const savedTheme = localStorage.getItem("theme");
  if (savedTheme === "dark") {
    document.documentElement.dataset.theme = "dark";
    $("#dark-toggle").textContent = "☀️";
  }
  $("#dark-toggle").onclick = () => {
    const root = document.documentElement;
    const isDark = root.dataset.theme === "dark";
    if (isDark) delete root.dataset.theme;
    else root.dataset.theme = "dark";
    localStorage.setItem("theme", isDark ? "" : "dark");
    $("#dark-toggle").textContent = isDark ? "🌙" : "☀️";
  };

  // 채팅
  $("#r-date").value = new Date().toISOString().slice(0, 10);
  $("#chat-form").onsubmit = (e) => {
    e.preventDefault();
    sendMessage();
  };
  $("#chat-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      $("#chat-form").requestSubmit();
    }
  });
  $("#recheck-level").onclick = () => {
    $("#chat-input").value = "레벨을 다시 확인해 주세요. 최근 학습 기록도 함께 봐줄래요?";
    $("#chat-form").requestSubmit();
  };

  // 학습 기록 폼
  $("#record-form").onsubmit = async (e) => {
    e.preventDefault();
    const body = {
      date: $("#r-date").value,
      value: parseInt($("#r-value").value, 10),
      memo: $("#r-memo").value.trim(),
      skill: $("#r-skill").value || null,
      reaction: $("#r-reaction").value || null,
    };
    if (!body.date || !body.value || !body.memo) return;
    try {
      if (state.editingId) await api("/api/data/" + state.editingId, "PUT", body);
      else await api("/api/data", "POST", body);
    } catch (err) {
      alert(err.message);
      return;
    }
    resetRecordForm();
    loadRecords();
    loadSummary();
  };
  $("#record-cancel").onclick = resetRecordForm;

  // 프로필 폼
  $("#profile-form").onsubmit = async (e) => {
    e.preventDefault();
    const body = {
      age_band: $("#p-age").value || null,
      level: $("#p-level").value || null,
      goals: $("#p-goals").value.trim() || null,
      daily_minutes: $("#p-minutes").value ? parseInt($("#p-minutes").value, 10) : null,
    };
    try {
      state.profile = await api("/api/profile", "PUT", body);
      renderSummary();
      alert("프로필을 저장했어요. 이제 채팅 추천에 이 정보가 반영됩니다.");
    } catch (err) {
      alert(err.message);
    }
  };

  // 첫 화면
  addMsg("assistant", WELCOME);
  loadProfile();
  loadSummary();
});
