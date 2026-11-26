"""로컬(규칙 기반) 응답 — API 키가 없거나 LLM 호출이 실패할 때.

Bloomy의 "키가 없으면 같은 규칙을 따르는 규칙 기반으로 동작" 원칙을 계승한다.
카탈로그 검색 결과·학습 요약·고정 템플릿만으로 답하므로 비용·네트워크 없이 재현 가능하다.
"""
from typing import Optional

from services.catalog import AGE_BAND_KO, COST_KO, LEVELS, SKILL_KO, TYPE_KO, level_label, level_num

FOCUS_REMINDER = "🌱 좋은 콘텐츠는 출발점일 뿐, 영어를 자라게 하는 건 스스로 집중해서 들인 시간이에요."
RECORD_HINT = "학습이 끝나면 「기록」 탭에 시간·내용·느낌(쉬움/적정/어려움)을 1분만 남겨 주세요."

# 연령대별 자기 점검 체크리스트: 마지막으로 "그렇다"인 단계가 출발 레벨
PLACEMENT_CHECKS = {
    "3-6": [
        (1, "영어 노래가 나오면 관심을 보이거나 몸을 움직인다"),
        (2, "\"Clap your hands\" 같은 짧은 영어 지시를 듣고 따라 한다"),
        (3, "\"I like apples\"처럼 짧은 문장을 따라 말하거나 혼자 말한다"),
        (4, "그림책의 쉬운 단어나 문장을 소리 내어 읽으려 한다"),
    ],
    "7-12": [
        (2, "쉬운 영어 영상(동요·애니메이션)의 상황을 대략 이해한다"),
        (3, "자기소개 등 짧은 문장을 영어로 말할 수 있다"),
        (4, "그림이 있는 쉬운 영어책을 혼자 읽을 수 있다"),
        (5, "챕터북(그림이 거의 없는 짧은 원서)을 사전 없이 읽는다"),
        (6, "어린이용 과학 기사·팟캐스트를 원어민 속도로 이해한다"),
    ],
    "13-17": [
        (3, "기본 인사·자기소개를 영어로 할 수 있다 (≈A1)"),
        (4, "쉬운 지문을 사전을 가끔 찾으며 읽을 수 있다 (≈A1~A2)"),
        (5, "짧은 기사나 일상 대화를 대부분 이해한다 (≈A2~B1)"),
        (6, "TED 강연·원서·뉴스를 자막 없이 대부분 따라간다 (≈B1~B2+)"),
    ],
    "18+": [
        (3, "기본 인사·자기소개를 영어로 할 수 있다 (≈A1)"),
        (4, "쉬운 지문을 사전을 가끔 찾으며 읽을 수 있다 (≈A1~A2)"),
        (5, "짧은 뉴스 기사나 일상 대화를 대부분 이해한다 (≈A2~B1)"),
        (6, "원서·뉴스·미드를 자막 없이 대부분 따라간다 (≈B1~B2+)"),
    ],
}

METHOD_TIPS = {
    "child": {
        "listening": ["같은 노래·영상을 일주일 반복해 소리에 익숙해지기", "보고 난 뒤 나온 단어 하나를 생활 속에서 함께 말하기", "하루 10~15분, 짧고 즐겁게 끝내기"],
        "reading": ["오디오를 먼저 듣고 그림을 보며 이야기 파악하기", "아는 단어를 손가락으로 짚으며 함께 소리 내어 읽기", "같은 책을 여러 번 — 익숙함이 자신감이 돼요"],
        "speaking": ["노래 후렴·짧은 문장 따라 말하기", "역할 놀이로 그날의 표현 한 문장 써 보기", "틀려도 고치기보다 말한 것 자체를 칭찬하기"],
        "vocabulary": ["주제(동물·음식)별로 그림과 함께 익히기", "노래·이야기에서 만난 단어 위주로 반복", "하루 3~5개면 충분해요"],
        "writing": ["알파벳 따라 쓰기부터", "그림에 단어 이름표 붙이기", "짧은 문장 베껴 쓰기"],
    },
    "adult": {
        "listening": ["스크립트 있는 짧은 자료(5~10분)로 1회 그냥 듣기 → 스크립트 보며 듣기 → 다시 듣기", "못 들은 문장만 골라 쉐도잉(따라 말하기)", "흘려듣기보다 집중듣기 시간을 먼저 확보하기"],
        "reading": ["모르는 단어가 한 쪽에 2~3개 이하인 쉬운 자료로 '많이' 읽기(다독)", "사전은 흐름이 막힐 때만 찾기", "읽은 뒤 한두 문장으로 요약해 보기"],
        "speaking": ["들은 자료의 문장을 쉐도잉해 '말할 재료' 만들기", "하루 1분 혼잣말 녹음 후 다시 들어 보기", "입력이 쌓이면 화상 영어·튜터로 실전 연습"],
        "vocabulary": ["읽고 들은 자료에서 나온 단어만 모으기", "간격 반복(Anki·Quizlet)으로 하루 10~20개", "예문째로 외우기"],
        "writing": ["읽은 글을 3~5문장으로 요약하기", "자동 첨삭 도구로 고쳐 쓰기 2~3회", "같은 주제로 꾸준히 일기 쓰기"],
    },
}


def _profile_line(profile: dict) -> str:
    parts = [AGE_BAND_KO.get(profile.get("age_band") or "", "연령대 미설정")]
    n = level_num(profile.get("level"))
    parts.append(level_label(n) if n else "레벨 미판정")
    if profile.get("goals"):
        parts.append(f"목표: {profile['goals']}")
    if profile.get("daily_minutes"):
        parts.append(f"하루 {profile['daily_minutes']}분")
    return " · ".join(parts)


def _hits_lines(hits: list[dict]) -> list[str]:
    lines = []
    for i, h in enumerate(hits, 1):
        it = h["item"]
        price = COST_KO[it["cost"]] + (f" — {it['price_note']}" if it.get("price_note") else "")
        lines.append(f"{i}. **{it['title']}** ({TYPE_KO[it['type']]} · {price} · 1회 약 {it['minutes']}분)")
        why = it["why"]
        if h["reasons"]:
            why = f"{why} ({' · '.join(h['reasons'][:2])})"
        lines.append(f"   왜: {why}")
        lines.append(f"   방법: {it['how_to']}")
        lines.append(f"   {it['link']}")
    return lines


def _setup_nudge(profile: dict) -> Optional[str]:
    if not profile.get("age_band"):
        return "더 정확한 추천을 위해 「요약」 탭에서 연령대와 목표를 먼저 저장해 주세요."
    if not profile.get("level"):
        return "레벨이 아직 없어요. \"내 레벨 확인해줘\"라고 물어보면 짧은 체크리스트로 함께 찾아볼게요."
    return None


def recommend(profile: dict, hits: list[dict], summary: dict) -> str:
    out = [f"지금 프로필({_profile_line(profile)}) 기준으로 Compass 카탈로그에서 골랐어요.", ""]
    if hits:
        out += _hits_lines(hits)
    else:
        out.append("조건에 딱 맞는 카탈로그 자료를 찾지 못했어요. 연령대·레벨 설정을 확인하거나, 원하는 스킬(듣기·읽기 등)을 함께 말해 주세요.")
    sig = summary.get("level_signal")
    if sig:
        out += ["", f"💡 {sig['message']} ({sig['basis']})"]
    nudge = _setup_nudge(profile)
    out += ["", FOCUS_REMINDER, RECORD_HINT]
    if nudge:
        out += ["", nudge]
    return "\n".join(out)


def placement(profile: dict, summary: dict) -> str:
    band = profile.get("age_band")
    if not band:
        return "\n".join([
            "레벨을 함께 찾아볼게요! 먼저 연령대를 알려 주세요.",
            "",
            "「요약」 탭 프로필에서 연령대(3~6세 / 7~12세 / 13~17세 / 성인)를 저장한 뒤 다시 \"레벨 확인해줘\"라고 물어봐 주세요.",
            "",
            FOCUS_REMINDER,
        ])
    checks = PLACEMENT_CHECKS[band]
    who = "아이가" if band in ("3-6", "7-12") else "내가"
    out = [f"아래 문장 중 {who} '대체로 그렇다'고 할 수 있는 것에 체크해 보세요.", ""]
    for lv, text in checks:
        code, name, _ = LEVELS[lv]
        out.append(f"□ {text}  → {code} {name}")
    out += [
        "",
        "마지막으로 체크한 단계가 출발 레벨이에요. 애매하면 한 단계 낮게 시작해 기록으로 조정하는 편이 좋아요.",
        "정한 레벨은 「요약」 탭 프로필에 저장해 주세요. 레벨은 평가가 아니라 다음 추천을 고르는 도구예요.",
    ]
    sig = summary.get("level_signal")
    if sig:
        hint = f" → {sig['suggested_level']} 검토" if sig.get("suggested_level") else ""
        out += ["", f"📊 기록 신호: {sig['basis']}{hint}"]
    out += ["", FOCUS_REMINDER]
    return "\n".join(out)


def progress(profile: dict, summary: dict, hits: list[dict]) -> str:
    if not summary["count"]:
        return "\n".join([
            "아직 학습 기록이 없어서 점검할 내용이 없어요.",
            "",
            "오늘 학습이 끝나면 「기록」 탭에 ①날짜 ②시간 ③한 것 ④느낌을 남겨 주세요. 일주일만 쌓여도 흐름이 보여요.",
            "",
            FOCUS_REMINDER,
        ])
    m = summary["metrics"]
    out = [
        "기록을 바탕으로 정리해 봤어요.",
        "",
        f"· 지금까지 {m['active_days']}일 동안 총 {m['total']}분 (학습한 날 평균 {m['per_active_day']}분)",
        f"· 최근 7일 {summary['last_7_days']}분 · 추세: {summary['trend']} · 현재 {summary['streak']}일 연속",
    ]
    goal = summary.get("goal")
    if goal:
        out.append(f"· 주간 목표 {goal['weekly_target']}분 중 {goal['last_7_days']}분 ({goal['percent']}%)")
    dist = summary["skill_distribution"]
    if dist:
        total = sum(dist.values()) or 1
        top = sorted(dist.items(), key=lambda x: -x[1])
        out.append("· 스킬 비중: " + " / ".join(f"{SKILL_KO.get(k, k)} {round(v / total * 100)}%" for k, v in top))
        weakest = [s for s in ("listening", "reading", "speaking", "vocabulary") if s not in dist]
    else:
        weakest = []
    r = summary["reaction"]
    out.append(f"· 느낌: 쉬움 {r['easy']} · 적정 {r['just_right']} · 어려움 {r['hard']}")

    out.append("")
    if summary["streak"] >= 3:
        out.append(f"👍 {summary['streak']}일 연속으로 이어 가고 있어요. 이 리듬이 가장 큰 자산이에요.")
    elif summary["last_7_days"] > 0:
        out.append("👍 이번 주에도 시간을 들였어요. 짧게라도 매일 이어 가는 것을 목표로 해 보세요.")
    sig = summary.get("level_signal")
    if sig:
        out.append(f"💡 {sig['message']} ({sig['basis']})")
    elif weakest:
        out.append(f"💡 {SKILL_KO[weakest[0]]} 기록이 아직 없어요. 다음 주에 한 번 시도해 보면 균형이 좋아져요.")
    if hits:
        it = hits[0]["item"]
        out.append(f"➡️ 다음 학습 제안: **{it['title']}** — {it['how_to']}")
    out += ["", FOCUS_REMINDER]
    return "\n".join(out)


def method(profile: dict, skill: Optional[str], hits: list[dict]) -> str:
    group = "child" if profile.get("age_band") in ("3-6", "7-12") else "adult"
    skill = skill or profile.get("focus_skill") or "listening"
    tips = METHOD_TIPS[group].get(skill, METHOD_TIPS[group]["listening"])
    out = [f"{SKILL_KO.get(skill, skill)} 학습은 이렇게 해 보세요.", ""]
    out += [f"{i}. {t}" for i, t in enumerate(tips, 1)]
    if hits:
        out += ["", "바로 써 볼 자료:"]
        for h in hits[:2]:
            it = h["item"]
            out.append(f"· **{it['title']}** ({COST_KO[it['cost']]}) — {it['how_to']} {it['link']}")
    out += ["", FOCUS_REMINDER, RECORD_HINT]
    return "\n".join(out)


def general(profile: dict) -> str:
    out = [
        "Compass는 지금 나에게 맞는 영어 콘텐츠를 찾아 드려요. 이렇게 물어보세요:",
        "",
        "· \"오늘 뭘 공부할지 추천해줘\" — 레벨·목표에 맞는 콘텐츠 2~3개",
        "· \"리스닝은 어떻게 하는 게 좋아?\" — 수준에 맞는 학습 방법",
        "· \"내 레벨 확인해줘\" — 짧은 체크리스트로 출발점 찾기",
        "· \"요즘 내 학습은 어때?\" — 기록 기반 점검",
    ]
    nudge = _setup_nudge(profile)
    if nudge:
        out += ["", nudge]
    out += ["", FOCUS_REMINDER]
    return "\n".join(out)
