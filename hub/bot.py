"""
비서실 봇 — 5분마다 깨어나 텔레그램에서 눌린 버튼과 보낸 글을 처리합니다.

할 일:
  · 승인 버튼 → 결과 기록(state/decisions.json), 메시지에 결과 표시, 연결된 워크플로 실행
  · 실패 알림의 '🔁 지금 다시' → 해당 워크플로 다시 실행
  · 아래 고정 버튼: 📋 현황 / ⏳ 승인 대기 / 📊 성적표
  · 📚 판매 입력 → 숫자 버튼으로 이번 주 KDP 판매 권수 기록 (일요일 저녁엔 자동으로 물어봄)
  · 24시간 동안 답이 없는 승인 요청은 한 번만 다시 알림
보안: TELEGRAM_CHAT_ID 의 주인(Jacob)이 누른 것만 처리합니다.

AI 를 전혀 쓰지 않습니다 (토큰·비용 0).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import secretary as s  # noqa: E402

KST = timezone(timedelta(hours=9))
DAYS = "월화수목금토일"
MENU = {"keyboard": [[{"text": "📋 현황"}, {"text": "⏳ 승인 대기"}],
                     [{"text": "📊 성적표"}, {"text": "📚 판매 입력"}]],
        "resize_keyboard": True, "is_persistent": True}
OWNER_REPO = s.HUB_REPO.split("/")[0]


def kst(ts) -> str:
    d = (datetime.fromtimestamp(ts, KST) if isinstance(ts, (int, float))
         else datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(KST))
    return f"{d:%m/%d}({DAYS[d.weekday()]}) {d:%H:%M}"


def agents_config() -> list[dict]:
    return json.loads((Path(__file__).parent / "agents.json").read_text())["agents"]


def repo_token(repo: str) -> str:
    """같은 저장소는 기본 GITHUB_TOKEN, 다른 저장소(stock-agent)는 STOCK_ACTIONS_TOKEN."""
    if repo.split("/")[-1] == s.HUB_REPO.split("/")[-1]:
        return os.environ.get("GITHUB_TOKEN", "")
    return os.environ.get("STOCK_ACTIONS_TOKEN", "")


def dispatch(repo: str, workflow: str, inputs: dict | None = None) -> tuple[bool, str]:
    full = repo if "/" in repo else f"{OWNER_REPO}/{repo}"
    token = repo_token(full)
    if not token:
        return False, "이 저장소를 실행할 열쇠(STOCK_ACTIONS_TOKEN)가 아직 없어요"
    code, j = s._gh("POST", f"/repos/{full}/actions/workflows/{workflow}/dispatches",
                    {"ref": "main", "inputs": inputs or {}}, token=token)
    if code == 204:
        return True, "실행했어요"
    return False, f"실행 실패 ({code}): {str(j.get('message', j))[:120]}"


# ---------------------------------------------------------------- 현황
def latest_runs(repo: str, workflow: str, n: int = 1) -> list[dict]:
    full = repo if "/" in repo else f"{OWNER_REPO}/{repo}"
    token = repo_token(full)
    code, j = s._gh("GET", f"/repos/{full}/actions/workflows/{workflow}/runs?per_page={n}", token=token)
    return j.get("workflow_runs", []) if code == 200 else []


def status_text() -> str:
    now = datetime.now(KST)
    lines = [f"📋 <b>{now:%m/%d}({DAYS[now.weekday()]}) {now:%H:%M} 현황</b>"]
    group = None
    problems = 0
    for a in agents_config():
        if a.get("group") != group:
            group = a.get("group")
            lines.append(f"\n<b>{s.esc(group)}</b>")
        if a.get("paused"):
            lines.append(f"⏸ {s.esc(a['name'])} · 잠시 멈춤")
            continue
        if a.get("manual"):
            lines.append(f"✍️ {s.esc(a['name'])} · {s.esc(a['manual'])}")
            continue
        runs = latest_runs(a["repo"], a["workflow"])
        if not runs:
            note = "아직 기록 없음" if repo_token(a["repo"]) or "stock" not in a["repo"] else "열쇠 필요"
            lines.append(f"▫️ {s.esc(a['name'])} · {note}")
            continue
        r = runs[0]
        if r["status"] != "completed":
            icon, when = "⏳", "실행 중"
        else:
            icon = {"success": "✅", "failure": "🔴", "cancelled": "⚪️"}.get(r["conclusion"], "⚪️")
            when = kst(r["updated_at"])
            problems += r["conclusion"] == "failure"
        lines.append(f'{icon} <a href="{r["html_url"]}">{s.esc(a["name"])}</a> · {when}')
    pend = pending_items()
    lines.append(f"\n⏳ 승인 대기 {len(pend)}건 · {'🔴 문제 ' + str(problems) + '건' if problems else '🟢 모두 정상'}")
    lines.append("💸 쓴 돈 0원 (모두 무료 한도 안)")
    return "\n".join(lines)


def pending_items() -> list[dict]:
    code, j = s._gh("GET", f"/repos/{s.HUB_REPO}/contents/hub/state/pending?ref={s.HUB_BRANCH}")
    if code != 200 or not isinstance(j, list):
        return []
    out = []
    for f in j:
        if f["name"].endswith(".json"):
            data, sha = s.state_get(f"pending/{f['name'][:-5]}")
            if data:
                data["_sha"] = sha
                out.append(data)
    return sorted(out, key=lambda x: x.get("asked", 0))


def pending_text(items) -> str:
    if not items:
        return "⏳ 승인 대기 없음. 할 일이 없어요 🙌"
    lines = [f"⏳ <b>승인 대기 {len(items)}건</b>"]
    for it in items:
        lines.append(f"· {s._tag(it['agent'])} {s.esc(it['title'])} ({kst(it['asked'])})")
    lines.append("\n원래 메시지의 버튼을 누르거나, 아래 버튼으로 바로 처리하세요.")
    return "\n".join(lines)


# ---------------------------------------------------------------- 버튼 처리
def owner_ok(user_id) -> bool:
    _, chat = s._auth()
    return str(user_id) == chat


def mark_message(cb: dict, result_line: str) -> None:
    """누른 버튼을 없애고 메시지 끝에 결과를 붙임."""
    msg = cb.get("message") or {}
    chat, mid = msg.get("chat", {}).get("id"), msg.get("message_id")
    if not chat or not mid:
        return
    old = msg.get("text") if "text" in msg else msg.get("caption", "")
    # 원래 굵게 표시는 텔레그램이 돌려주지 않으므로, 결과 줄만 굵게
    new = s.esc(old or "") + f"\n\n<b>{s.esc(result_line)}</b>"
    try:
        if "text" in msg:
            s.tg("editMessageText", {"chat_id": chat, "message_id": mid, "text": new[:4000],
                                     "parse_mode": "HTML", "disable_web_page_preview": "true"})
        else:
            s.tg("editMessageCaption", {"chat_id": chat, "message_id": mid, "caption": new[:1000],
                                        "parse_mode": "HTML"})
    except RuntimeError as e:
        print(f"(메시지 수정 실패: {e})")


def record_decision(key: str, choice: str) -> dict | None:
    decisions, sha = s.state_get("decisions", {})
    decisions = decisions or {}
    decisions[key] = {"choice": choice, "time": time.time()}
    # 오래된 결정은 60일 뒤 정리
    cut = time.time() - 60 * 86400
    decisions = {k: v for k, v in decisions.items() if v.get("time", 0) > cut}
    s.state_put("decisions", decisions, sha, f"결정: {key} → {choice}")
    item, psha = s.state_get(f"pending/{key}")
    if item and psha:
        s.state_delete(f"pending/{key}", psha)
    return item


def answer(cb: dict, text: str) -> None:
    """버튼 누른 곳에 잠깐 뜨는 안내. 텔레그램은 몇 초 안에만 받아 주므로,
    5분마다 확인하는 방식에선 대부분 시간이 지나 거절돼요. 그래도 처리는 계속합니다."""
    try:
        s.tg("answerCallbackQuery", {"callback_query_id": cb["id"], "text": text[:190]})
    except RuntimeError:
        pass


def handle_callback(cb: dict) -> None:
    data = cb.get("data", "")
    if not owner_ok(cb.get("from", {}).get("id")):
        answer(cb, "주인만 누를 수 있어요")
        return
    parts = data.split("|")
    toast, result = "처리했어요", None
    if parts[0] == "a" and len(parts) == 3:
        key, choice = parts[1], parts[2]
        label = s.CHOICE_LABEL.get(choice, choice)
        if s.decision(key):
            toast = "이미 처리된 요청이에요"
        else:
            answer(cb, f"{label} 접수됐어요")
            toast = None
            item = record_decision(key, choice)
            result = f"{label} · {kst(time.time())}"
            oc = (item or {}).get("on_choice")
            if oc and oc.get("workflow"):
                ok, why = dispatch(oc.get("repo") or item.get("repo") or s.HUB_REPO, oc["workflow"],
                                   {**(oc.get("inputs") or {}), "choice": choice})
                result += " · 다음 단계 시작" if ok else f" · ⚠️ {why}"
    elif parts[0] == "r" and len(parts) == 3:
        answer(cb, "🔁 접수됐어요. 다시 실행할게요")
        toast = None
        ok, why = dispatch(parts[1], parts[2])
        result = ("🔁 다시 실행 시작 · " if ok else f"⚠️ {why} · ") + kst(time.time())
    elif parts[0] == "k" and len(parts) == 3:
        week, val = parts[1], parts[2]
        if val == "more":
            msg = cb.get("message") or {}
            s.tg("editMessageReplyMarkup", {"chat_id": msg.get("chat", {}).get("id"),
                                            "message_id": msg.get("message_id"),
                                            "reply_markup": {"inline_keyboard": kdp_keyboard(week, big=True)}})
            toast = "20권 이상"
        else:
            answer(cb, f"📚 {val}권 접수됐어요")
            toast = None
            save_kdp(week, int(val))
            result = f"📚 {week[5:].replace('-', '/')}~ 주 KDP {val}권 기록 완료"
    elif parts[0] == "x":
        result = "🔕 알겠어요. 오늘은 그대로 둘게요."
        toast = "오늘은 쉬어요"
    elif parts[0] == "p":  # 승인 대기 목록에서 바로 처리
        return handle_callback({**cb, "data": "a|" + "|".join(parts[1:])})
    if toast:
        answer(cb, toast)
    if result:
        mark_message(cb, result)


# ---------------------------------------------------------------- KDP 판매 (버튼으로)
def week_key(d: datetime | None = None) -> str:
    d = d or datetime.now(KST)
    return (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")


def kdp_keyboard(week: str, big: bool = False) -> list:
    nums = list(range(20, 100, 5)) + [100] if big else list(range(0, 20))
    rows = [[{"text": f"{n}" + ("+" if big and n == 100 else ""), "callback_data": f"k|{week}|{n}"}
             for n in nums[i:i + 5]] for i in range(0, len(nums), 5)]
    if not big:
        rows.append([{"text": "20권 이상 ▸", "callback_data": f"k|{week}|more"}])
    return rows


def ask_kdp(week: str | None = None) -> None:
    week = week or week_key()
    reply(f"📚 <b>이번 주({week[5:].replace('-', '/')}~) KDP 몇 권 팔렸나요?</b>\n"
          "KDP 앱이나 사이트의 '보고서'에서 확인하고 숫자를 눌러 주세요.", buttons=kdp_keyboard(week))


def save_kdp(week: str, books: int) -> None:
    kdp, sha = s.state_get("kdp_sales", {})
    kdp = kdp or {}
    kdp[week] = {"books": books, "time": time.time()}
    s.state_put("kdp_sales", kdp, sha, f"KDP 판매 기록 {week}")


# ---------------------------------------------------------------- 글 처리
SALES = re.compile(r"^\s*판매\s*(\d+)\s*(?:권)?\s*(?:\$?\s*([\d.]+)\s*(?:달러|\$)?)?\s*$")


def reply(text: str, buttons=None, menu: bool = False) -> None:
    _, chat = s._auth()
    p = {"chat_id": chat, "text": text[:4000], "parse_mode": "HTML", "disable_web_page_preview": "true"}
    if buttons:
        p["reply_markup"] = {"inline_keyboard": buttons}
    elif menu:
        p["reply_markup"] = MENU
    s.tg("sendMessage", p)


def handle_text(msg: dict) -> None:
    if not owner_ok(msg.get("from", {}).get("id")):
        return
    if "voice" in msg or "audio" in msg:  # 🎤 음성 → 자비스
        import voice
        voice.handle(msg, sys.modules[__name__])
        return
    t = (msg.get("text") or "").strip()
    if t in ("/start", "/menu", "메뉴"):
        reply("🗂 <b>비서실</b>이에요. 모든 에이전트의 보고와 결재가 여기로 와요.\n"
              "글을 칠 필요 없이 아래 버튼만 누르면 돼요.", menu=True)
    elif "현황" in t:
        reply(status_text(), menu=True)
    elif "승인" in t:
        items = pending_items()
        kb = []
        for it in items[:8]:
            btns = it.get("buttons") or s.APPROVE_BUTTONS
            kb.append([{"text": f"{lab} · {it['title'][:14]}", "callback_data": f"p|{it['key']}|{ch}"}
                       for lab, ch in btns[:2]])
        reply(pending_text(items), buttons=kb or None)
    elif "판매" in t and not SALES.match(t):
        ask_kdp()
    elif "성적표" in t:
        ok, why = dispatch(s.HUB_REPO, "weekly-report.yml", {"mode": "now"})
        reply("📊 성적표를 만들고 있어요. 2~3분 뒤에 도착해요." if ok else f"⚠️ {why}")
    elif m := SALES.match(t):
        books, usd = int(m.group(1)), float(m.group(2)) if m.group(2) else None
        kdp, sha = s.state_get("kdp_sales", {})
        kdp = kdp or {}
        week = (datetime.now(KST) - timedelta(days=datetime.now(KST).weekday())).strftime("%Y-%m-%d")
        kdp[week] = {"books": books, "usd": usd, "time": time.time()}
        s.state_put("kdp_sales", kdp, sha, f"KDP 판매 기록 {week}")
        reply(f"📚 이번 주 KDP 판매 {books}권" + (f", ${usd:g}" if usd is not None else "") + " 기록했어요.")
    elif len(t) >= 2:  # 메뉴에 없는 말 → 자비스가 알아듣고 답 (말로 하는 것과 같음)
        import voice
        voice.handle(msg, sys.modules[__name__])
    else:
        reply("아래 버튼을 눌러 주세요 👇", menu=True)


# ---------------------------------------------------------------- 24시간 리마인드
def remind_pending() -> None:
    for it in pending_items():
        if it.get("reminded") or time.time() - it.get("asked", 0) < 24 * 3600:
            continue
        btns = it.get("buttons") or s.APPROVE_BUTTONS
        reply(f"⏰ 하루 동안 답이 없어서 한 번만 다시 여쭤요.\n{s._tag(it['agent'])} <b>{s.esc(it['title'])}</b>\n"
              "누르기 전까지는 다음 단계를 멈춰 둘게요.",
              buttons=[[{"text": lab, "callback_data": f"a|{it['key']}|{ch}"} for lab, ch in btns]])
        sha = it.pop("_sha")
        it["reminded"] = True
        s.state_put(f"pending/{it['key']}", it, sha, f"리마인드: {it['title'][:40]}")


# ---------------------------------------------------------------- 메인
def main() -> None:
    if "--hello" in sys.argv:  # 설치 확인용: 메뉴 버튼 + 시험 승인 요청
        reply("🗂 <b>비서실</b> 연결 완료!\n이제 모든 에이전트의 보고와 결재가 여기로 와요. 아래 버튼만 누르면 돼요.", menu=True)
        s.ask("hub", f"hello-{int(time.time())}", "시험 승인 요청이에요", "아무 버튼이나 눌러 보세요. 바로 '접수됐어요'가 뜨고 결과가 이 메시지에 붙어요.",
              buttons=[("👍 잘 보여요", "approve"), ("👎 이상해요", "drop")])
        return
    if "--voice-test" in sys.argv:  # 자비스 시험: 시세 + 목소리 (AI 없이)
        import voice
        line = voice.quote("SOXL")
        reply(f"🎙 <b>자비스 시험</b>\n{s.esc(line)}\n\n이 아래에 목소리 답이 오면 성공이에요."
              + ("" if voice._key() else "\n(GEMINI_API_KEY 열쇠는 아직 없어요)"))
        ogg = voice.speak("안녕하세요 제이콥님, 자비스예요. " + line.split(" (")[0].replace("$", "") + " 달러예요.")
        if ogg:
            _, chat = s._auth()
            s.tg("sendVoice", {"chat_id": chat}, file=("voice", ogg))
        else:
            sys.exit("목소리 만들기 실패")
        return
    if "--ask-kdp" in sys.argv:
        ask_kdp()
        return
    token, chat = s._auth()
    if not token or not chat:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 비밀값이 아직 없어요. 설정 전이라 조용히 끝냅니다.")
        return
    # 웹훅(예: Cloudflare Worker)이 텔레그램 소식 하나를 넘겨준 경우: 그것만 처리
    raw = (os.environ.get("UPDATE_JSON") or "").strip()
    if raw:
        u = json.loads(raw)
        if "callback_query" in u:
            handle_callback(u["callback_query"])
        elif "message" in u:
            handle_text(u["message"])
        print("넘겨받은 소식 1개 처리")
        return
    # 듣기 모드: 그 시간 동안은 버튼을 누르자마자 바로 반응 (텔레그램 '롱폴링')
    listen = 0.0
    for a in sys.argv:
        if a.startswith("--listen="):
            listen = float(a.split("=")[1] or 0)
    start = time.time()
    deadline = start + listen * 60
    cap = start + 25 * 60  # 한 번에 최대 25분
    off, sha = s.state_get("offset", {"offset": 0})
    offset = (off or {}).get("offset", 0)
    total = 0
    while True:
        wait = int(max(0, min(50, deadline - time.time())))
        try:
            res = s.tg("getUpdates", {"offset": offset, "timeout": wait,
                                      "allowed_updates": ["message", "callback_query"]}, timeout=wait + 20)
        except RuntimeError as e:
            if "409" in str(e):
                print("(다른 확인 작업이 같은 봇을 읽는 중이라 이번엔 건너뜀)")
                break
            raise
        updates = res.get("result", [])
        for u in updates:
            try:
                if "callback_query" in u:
                    handle_callback(u["callback_query"])
                elif "message" in u:
                    handle_text(u["message"])
            except Exception as e:  # 하나가 실패해도 나머지는 처리
                print(f"(처리 실패 {u.get('update_id')}: {type(e).__name__}: {e})")
        if updates:
            total += len(updates)
            offset = updates[-1]["update_id"] + 1
            s.state_put("offset", {"offset": offset}, sha, "비서실: 읽은 위치")
            _, sha = s.state_get("offset")
            # Jacob 이 지금 쓰고 있으니 10분 더 바로바로 반응
            deadline = min(cap, max(deadline, time.time() + 10 * 60))
        if time.time() >= deadline:
            break
    print(f"새 소식 {total}개 처리 · {round((time.time() - start) / 60, 1)}분 대기")
    remind_pending()

if __name__ == "__main__":
    main()
