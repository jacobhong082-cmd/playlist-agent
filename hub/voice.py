"""
자비스 (음성 비서) — 비서실 봇에 보낸 음성 메시지·자유로운 글을 알아듣고 답합니다.

흐름:
  🎤 음성 → Gemini(무료)가 듣고 + 지금 상황(현황·승인 대기·SOXL)을 보고 한 번에 답 정리
  → 텔레그램에 "이렇게 들었어요" + 답 글 + 🔊 목소리 답(무료 음성) 보내기

안전 규칙 (가장 중요):
  · 조회(현황, 승인 대기, 시세, 할 일)와 성적표 만들기만 바로 해요.
  · 승인·버리기·다시 실행처럼 무언가를 바꾸는 일은 절대 바로 하지 않고,
    '✅ 네 / ✋ 아니요' 확인 버튼만 보내요. 버튼은 기존 비서실 버튼과 같은 방식이라
    Jacob 이 눌러야만 실행돼요.

필요한 비밀값: GEMINI_API_KEY (없으면 "열쇠가 필요해요"라고 답하고 끝)
Claude 토큰은 쓰지 않아요.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import secretary as s

KST = timezone(timedelta(hours=9))
API = "https://generativelanguage.googleapis.com/v1beta"
VOICE = os.environ.get("JARVIS_VOICE", "ko-KR-InJoonNeural")  # 남자 목소리. 여자: ko-KR-SunHiNeural


# ---------------------------------------------------------------- Gemini (무료)
def _key() -> str:
    return (os.environ.get("GEMINI_API_KEY") or "").strip()


def _post(url: str, body: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def models() -> list[str]:
    """내 키로 쓸 수 있는 무료 Flash 모델, 최신 순 (Flash 먼저, 막히면 Flash-Lite)."""
    fixed = (os.environ.get("GEMINI_MODEL") or "").strip()
    if fixed:
        return [fixed]
    with urllib.request.urlopen(f"{API}/models?pageSize=200&key={_key()}", timeout=30) as r:
        data = json.loads(r.read())
    skip = ("image", "tts", "live", "audio", "embedding", "exp", "native", "computer", "omni", "robotics")
    flash, lite = [], []
    for m in data.get("models", []):
        name = m["name"].removeprefix("models/")
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        if "flash" not in name or any(x in name for x in skip):
            continue
        (lite if "lite" in name else flash).append(name)

    def rank(n):
        v = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
        return (-(float(v.group(1)) if v else 0), "preview" in n, len(n))

    return sorted(flash, key=rank)[:2] + sorted(lite, key=rank)[:2]


def ask_gemini(parts: list[dict]) -> dict:
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3}}
    last = None
    for m in models():
        try:
            j = _post(f"{API}/models/{m}:generateContent?key={_key()}", body)
            text = j["candidates"][0]["content"]["parts"][0]["text"]
            print(f"(Gemini {m})")
            return json.loads(text)
        except Exception as e:  # 한도 초과 등 → 다음 모델
            last = e
            print(f"(Gemini {m} 실패: {type(e).__name__}: {str(e)[:120]})")
    raise RuntimeError(f"Gemini 응답 없음: {last}")


# ---------------------------------------------------------------- 지금 상황 모으기
def quote(sym: str) -> str:
    try:
        req = urllib.request.Request(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5d&interval=1d",
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            meta = json.loads(r.read())["chart"]["result"][0]["meta"]
        p, prev = meta["regularMarketPrice"], meta.get("chartPreviousClose") or meta.get("previousClose")
        t = datetime.fromtimestamp(meta["regularMarketTime"], KST)
        ch = f"{(p / prev - 1) * 100:+.1f}%" if prev else ""
        return f"{sym} ${p:.2f} (전일 대비 {ch}, 한국시간 {t:%m/%d %H:%M} 기준)"
    except Exception as e:
        return f"{sym} 시세 불러오기 실패 ({type(e).__name__})"


def context(bot) -> tuple[str, list[dict], list[dict]]:
    """(상황 설명 글, 승인 대기 목록, 실패한 작업 목록)"""
    now = datetime.now(KST)
    lines, failed = [], []
    for a in bot.agents_config():
        if a.get("paused") or a.get("manual"):
            continue
        runs = bot.latest_runs(a["repo"], a["workflow"])
        if not runs:
            lines.append(f"- {a['name']}: 기록 없음")
            continue
        r = runs[0]
        st = "실행 중" if r["status"] != "completed" else {"success": "정상", "failure": "실패"}.get(
            r["conclusion"], r["conclusion"] or "?")
        lines.append(f"- {a['name']}: {st} ({bot.kst(r['updated_at'])})")
        if r.get("conclusion") == "failure":
            failed.append({"name": a["name"], "repo": a["repo"], "workflow": a["workflow"]})
    pend = bot.pending_items()
    plines = [f"- key={p['key']} · {s.AGENTS.get(p['agent'], p['agent'])} · {p['title']}" for p in pend]
    txt = (f"지금 한국시간: {now:%Y-%m-%d (%a) %H:%M}\n\n[에이전트 상태]\n" + "\n".join(lines) +
           f"\n\n[승인 대기 {len(pend)}건]\n" + ("\n".join(plines) or "- 없음") +
           "\n\n[시세]\n" + quote("SOXL") + "\n" + quote("^SOX") + "\n" + quote("^IXIC"))
    return txt, pend, failed


PROMPT = """너는 Jacob의 음성 비서 '자비스'야. Jacob은 개발자가 아니고 한국어로 말해.
Jacob의 에이전트: 주식(시황 브리핑·급등락 알림·모의매매), AI 플레이리스트 유튜브, 아마존 KDP 주간 책, 비서실(텔레그램 봇).

아래 [지금 상황]만 근거로 짧게 답해. 모르는 건 지어내지 말고 모른다고 해.
말로 읽어 줄 답이니 2~4문장, 쉬운 존댓말, 기호·표·이모지 없이.
투자 판단(사라/팔아라)은 하지 말고 사실만 말해.

할 수 있는 행동(action) — 반드시 이 중 하나:
- none: 대답만
- report: 이번 주 성적표 카드 만들어 보내기 (바로 실행해도 되는 안전한 일)
- kdp_sales: KDP 판매 권수 입력 버튼 보내기 (안전)
- decide: 승인 대기 항목 하나를 승인(approve)/다시 만들기(redo)/버리기(drop) — key는 [승인 대기]의 key 그대로
- retry: 실패한 작업 다시 실행 — name은 [에이전트 상태]의 이름 그대로
decide·retry는 바로 실행되지 않고 Jacob에게 확인 버튼이 가. 그러니 say에서 "확인 버튼 보냈어요, 눌러 주세요"라고 말해.
업로드·주문·삭제·돈이 드는 일·목록에 없는 일은 action none으로 하고, 텔레그램 버튼이나 직접 해야 한다고 말해.

JSON 하나로만 답해:
{"heard": "Jacob이 한 말을 그대로 받아쓴 것", "say": "답", "action": "none|report|kdp_sales|decide|retry", "key": "", "choice": "", "name": ""}

[지금 상황]
"""


# ---------------------------------------------------------------- 목소리 답 (무료)
def speak(text: str) -> str | None:
    """무료 Edge 음성으로 읽어서 텔레그램 음성(ogg) 파일 경로를 돌려줌. 실패하면 None (글 답은 그대로 감)."""
    try:
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "edge-tts"], check=True, timeout=120)
        d = tempfile.mkdtemp()
        mp3, ogg = f"{d}/a.mp3", f"{d}/a.ogg"
        subprocess.run([sys.executable, "-m", "edge_tts", "--voice", VOICE, "--text", text, "--write-media", mp3],
                       check=True, capture_output=True, timeout=60)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-c:a", "libopus", "-b:a", "32k", ogg],
                       check=True, capture_output=True, timeout=60)
        return ogg
    except Exception as e:
        print(f"(목소리 만들기 실패: {type(e).__name__}: {str(e)[:150]})")
        return None


# ---------------------------------------------------------------- 처리
def _download_voice(file_id: str) -> bytes:
    token, _ = s._auth()
    path = s.tg("getFile", {"file_id": file_id})["result"]["file_path"]
    with urllib.request.urlopen(f"https://api.telegram.org/file/bot{token}/{path}", timeout=60) as r:
        return r.read()


def handle(msg: dict, bot) -> None:
    """음성 메시지(voice) 또는 메뉴에 없는 글(text)."""
    _, chat = s._auth()
    if not _key():
        bot.reply("🎤 음성 비서를 쓰려면 GEMINI_API_KEY 열쇠가 필요해요. 설치 안내를 따라 한 번만 넣어 주세요.")
        return
    try:
        s.tg("sendChatAction", {"chat_id": chat, "action": "typing"})
    except RuntimeError:
        pass
    ctx, pend, failed = context(bot)
    parts = [{"text": PROMPT + ctx}]
    is_voice = "voice" in msg or "audio" in msg
    if is_voice:
        v = msg.get("voice") or msg.get("audio")
        audio = _download_voice(v["file_id"])
        parts.append({"inline_data": {"mime_type": v.get("mime_type") or "audio/ogg",
                                      "data": base64.b64encode(audio).decode()}})
        parts.append({"text": "위 음성이 Jacob의 말이야."})
    else:
        parts.append({"text": f"Jacob이 쓴 글: {msg.get('text', '')}"})
    try:
        out = ask_gemini(parts)
    except Exception as e:
        print(f"(Gemini 실패: {e})")
        bot.reply("🎤 지금은 AI 무료 한도가 차서 알아듣지 못했어요. 아래 버튼을 써 주세요 👇", menu=True)
        return

    heard, say = (out.get("heard") or "").strip(), (out.get("say") or "").strip() or "잘 못 알아들었어요. 다시 말씀해 주세요."
    action, buttons, extra = out.get("action") or "none", None, ""

    if action == "decide":
        item = next((p for p in pend if p["key"] == out.get("key")), None)
        choice = out.get("choice") if out.get("choice") in ("approve", "redo", "drop") else None
        if item and choice:
            label = s.CHOICE_LABEL.get(choice, choice)
            extra = f"\n\n<b>{s.esc(item['title'])}</b> → {label}\n이대로 할까요?"
            buttons = [[{"text": "✅ 네", "callback_data": f"a|{item['key']}|{choice}"},
                        {"text": "✋ 아니요", "callback_data": "x"}]]
        else:
            say = "어느 승인 건인지 확실하지 않아요. 승인 대기 버튼으로 골라 주세요."
    elif action == "retry":
        f = next((x for x in failed if x["name"] == out.get("name")), None)
        if f:
            extra = f"\n\n<b>{s.esc(f['name'])}</b> 다시 실행할까요?"
            buttons = [[{"text": "🔁 네, 다시", "callback_data": f"r|{f['repo']}|{f['workflow']}"},
                        {"text": "✋ 아니요", "callback_data": "x"}]]
        else:
            say = "지금 실패한 작업이 없어서 다시 돌릴 게 없어요."
    elif action == "report":
        ok, why = bot.dispatch(s.HUB_REPO, "weekly-report.yml", {"mode": "now"})
        extra = "\n\n📊 성적표 만드는 중 · 2~3분 뒤 도착" if ok else f"\n\n⚠️ {s.esc(why)}"
    elif action == "kdp_sales":
        bot.ask_kdp()

    head = f"📝 <i>이렇게 들었어요: “{s.esc(heard)}”</i>\n\n" if is_voice and heard else ""
    bot.reply(f"🎙 {head}{s.esc(say)}{extra}", buttons=buttons)
    if is_voice:  # 말로 물으면 말로도 답
        ogg = speak(say)
        if ogg:
            s.tg("sendVoice", {"chat_id": chat, "disable_notification": "true"}, file=("voice", ogg))
