"""
비서실 (Secretary) — 모든 에이전트가 같이 쓰는 텔레그램 공통 부품.

추가 설치 없이 파이썬 기본 기능만 씁니다. 다른 저장소에서는 이 파일 하나만 내려받아 쓰면 됩니다:
    curl -fsSL https://raw.githubusercontent.com/jacobhong082-cmd/playlist-agent/main/hub/secretary.py -o secretary.py

필요한 환경 변수 (GitHub → Settings → Secrets):
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
선택:
    GITHUB_TOKEN   승인 요청을 비서실 '승인 대기' 목록에 올릴 때 (비서실 저장소 안에서는 자동으로 있음)

쓰는 법:
    import secretary as s
    s.notify("playlist", "12곡 작곡 완료", "내일 영상으로 만들어요.")              # 조용히 도착 (소리 없음)
    s.notify("playlist", "업로드 실패", "원인: ...", level="urgent")               # 소리 나는 알림
    s.fail("stock", "시황 브리핑", "Gemini 무료 한도 초과", retry=("stock-agent", "daily-briefing.yml"))
    s.ask("playlist", "pl-1125", "새 영상 올릴까요?", "Late Night Seoul · 12곡",
          photo="thumb.png", checks=s.preflight(meta),
          on_choice={"workflow": "upload.yml", "inputs": {"id": "1125"}})
    s.decision("pl-1125")   # → None(아직) / "approve" / "redo" / "drop"

알림 3단계:
    urgent  소리 나는 알림 (실패, 승인 필요)
    normal  조용히 도착 (완료 보고) — 텔레그램 '무음 메시지' 기능
    log     텔레그램에 보내지 않고 기록만 (주간 성적표 재료)
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HUB_REPO = "jacobhong082-cmd/playlist-agent"
HUB_BRANCH = os.environ.get("HUB_BRANCH", "main")

# 에이전트 이름표 (텔레그램 메시지 맨 앞에 붙는 꼬리표)
AGENTS = {
    "playlist": "🎵 플레이리스트",
    "kdp": "📚 KDP",
    "stock": "📈 주식",
    "hub": "🗂 비서실",
}

# 승인 버튼 기본 세트
APPROVE_BUTTONS = [("✅ 올리기", "approve"), ("🔁 다시 만들기", "redo"), ("❌ 버리기", "drop")]
CHOICE_LABEL = {"approve": "✅ 승인", "redo": "🔁 다시 만들기", "drop": "❌ 버림",
                "retry": "🔁 다시 실행", "skip": "🔕 오늘은 쉬기"}


# ---------------------------------------------------------------- 텔레그램 기본
def _auth():
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if token.lower().startswith("bot"):
        token = token[3:]
    return token, chat


def _multipart(fields: dict, file_field: str, path: str):
    boundary = uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    with open(path, "rb") as f:
        data = f.read()
    name = os.path.basename(path)
    out.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{name}"\r\n'
               f"Content-Type: application/octet-stream\r\n\r\n".encode() + data + b"\r\n")
    out.append(f"--{boundary}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={boundary}"


def tg(method: str, params: dict | None = None, file: tuple[str, str] | None = None,
       timeout: int = 60) -> dict:
    """텔레그램 API 호출. 연결 문제는 10·30·60초 뒤 다시 시도. 실패하면 RuntimeError."""
    token, _ = _auth()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN 이 없어요")
    url = f"https://api.telegram.org/bot{token}/{method}"
    params = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
              for k, v in (params or {}).items() if v is not None}
    last = None
    for wait in (10, 30, 60, None):
        try:
            if file:
                body, ctype = _multipart(params, file[0], file[1])
            else:
                body, ctype = urllib.parse.urlencode(params).encode(), "application/x-www-form-urlencoded"
            req = urllib.request.Request(url, body, {"Content-Type": ctype})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")[:300]
            last = f"{e.code} {text}"
            if e.code < 500 and e.code != 429:
                raise RuntimeError(f"텔레그램이 거절했어요 ({method}): {last}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = str(e)
        if wait is None:
            break
        print(f"(텔레그램 연결 문제, {wait}초 뒤 다시: {last})")
        time.sleep(wait)
    raise RuntimeError(f"텔레그램에 연결하지 못했어요 ({method}): {last}")


def _tag(agent: str) -> str:
    return AGENTS.get(agent, agent)


def _send(text: str, *, silent: bool, buttons=None, photo: str | None = None) -> dict | None:
    token, chat = _auth()
    if not token or not chat:
        print("(텔레그램 설정이 없어 전송 생략)\n" + text)
        return None
    p = {"chat_id": chat, "parse_mode": "HTML", "disable_notification": "true" if silent else "false",
         "disable_web_page_preview": "true"}
    if buttons:
        p["reply_markup"] = {"inline_keyboard": buttons}
    if photo and os.path.exists(photo):
        p["caption"] = text[:1000]
        try:
            return tg("sendPhoto", p, file=("photo", photo))["result"]
        except RuntimeError as e:
            print(f"(사진 전송 실패, 글로만 보냄: {e})")
            p.pop("caption")
    p["text"] = text[:4000]
    return tg("sendMessage", p)["result"]


def esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------- 보고 · 실패
def notify(agent: str, title: str, body: str = "", level: str = "normal",
           photo: str | None = None, link: str | None = None) -> dict | None:
    """진행 보고. level: urgent(소리) / normal(무음) / log(기록만)."""
    text = f"{_tag(agent)}\n<b>{esc(title)}</b>"
    if body:
        text += f"\n{esc(body)}"
    if link:
        text += f'\n<a href="{esc(link)}">자세히 보기</a>'
    if level == "log":
        print("[기록] " + text)
        return None
    return _send(text, silent=(level != "urgent"), photo=photo)


def fail(agent: str, job: str, reason: str, retry: tuple[str, str] | None = None,
         link: str | None = None, auto_retry_note: str | None = None) -> dict | None:
    """실패 알림 (소리 남). retry=(저장소 이름, 워크플로 파일) 을 주면 '🔁 지금 다시' 버튼이 붙습니다."""
    text = f"{_tag(agent)} · 🔴 <b>실패</b>\n<b>{esc(job)}</b> 작업이 멈췄어요\n원인: {esc(reason)[:400]}"
    if auto_retry_note:
        text += f"\n→ {esc(auto_retry_note)}"
    if link:
        text += f'\n<a href="{esc(link)}">기록 보기</a>'
    buttons = None
    if retry:
        repo, wf = retry
        data = f"r|{repo.split('/')[-1]}|{wf}"
        if len(data.encode()) <= 64:
            buttons = [[{"text": "🔁 지금 다시", "callback_data": data},
                        {"text": "🔕 오늘은 쉬기", "callback_data": "x|skip"}]]
    return _send(text, silent=False, buttons=buttons)


# ---------------------------------------------------------------- 승인
def _short_key(key: str) -> str:
    key = "".join(c for c in key if c.isalnum() or c in "-_.")
    return key if len(key) <= 40 else key[:28] + "-" + hashlib.sha1(key.encode()).hexdigest()[:8]


def ask(agent: str, key: str, title: str, body: str = "", *, photo: str | None = None,
        buttons: list[tuple[str, str]] | None = None, checks: list[tuple[bool, str]] | None = None,
        on_choice: dict | None = None, repo: str | None = None) -> str:
    """승인 요청 (소리 남). key 는 이 요청의 고유 이름 (예: 'pl-2026-11-25').
    on_choice = {"workflow": "upload.yml", "inputs": {...}} 을 주면, 버튼을 누를 때
    비서실이 그 워크플로를 바로 실행합니다 (inputs 에 choice 가 함께 들어감).
    돌려주는 값: 실제로 쓴 key."""
    key = _short_key(key)
    buttons = buttons or APPROVE_BUTTONS
    text = f"{_tag(agent)} · 🟡 <b>승인 필요</b>\n<b>{esc(title)}</b>"
    if body:
        text += f"\n{esc(body)}"
    if checks:
        text += "\n" + "  ".join(("✓ " if ok else "✗ ") + esc(label) for ok, label in checks)
        if not all(ok for ok, _ in checks):
            text += "\n⚠️ 확인 안 된 항목이 있어요"
    kb = [[{"text": label, "callback_data": f"a|{key}|{choice}"} for label, choice in buttons]]
    msg = _send(text, silent=False, buttons=kb, photo=photo)
    register_pending({
        "key": key, "agent": agent, "title": title, "asked": time.time(),
        "message_id": (msg or {}).get("message_id"), "reminded": False,
        "buttons": buttons, "on_choice": on_choice,
        "repo": repo or os.environ.get("GITHUB_REPOSITORY", ""),
    })
    return key


# ---------------------------------------------------------------- 비서실 저장소 (상태 파일)
def _gh(method: str, path: str, body: dict | None = None, token: str | None = None):
    token = token if token is not None else (os.environ.get("HUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or "")
    req = urllib.request.Request(f"https://api.github.com{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Accept": "application/vnd.github+json",
                                          "User-Agent": "secretary-bot",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def state_get(name: str, default=None):
    """hub/state/<name>.json 읽기 → (데이터, sha)."""
    code, j = _gh("GET", f"/repos/{HUB_REPO}/contents/hub/state/{name}.json?ref={HUB_BRANCH}")
    if code != 200:
        return default, None
    return json.loads(base64.b64decode(j["content"]).decode()), j["sha"]


def state_put(name: str, data, sha: str | None = None, message: str | None = None) -> bool:
    """기록 저장. 다른 에이전트와 동시에 저장하다 부딪히면(409) 최신 상태로 3번까지 다시 시도."""
    body = {"message": message or f"비서실 기록: {name}", "branch": HUB_BRANCH,
            "content": base64.b64encode(json.dumps(data, ensure_ascii=False, indent=1).encode()).decode()}
    for attempt in range(4):
        if sha:
            body["sha"] = sha
        code, j = _gh("PUT", f"/repos/{HUB_REPO}/contents/hub/state/{name}.json", body)
        if code in (200, 201):
            return True
        if code in (409, 422) and attempt < 3:
            time.sleep(2 + attempt * 3)
            _, sha = state_get(name)
            continue
        break
    print(f"(비서실 기록 실패 {name}: {code} {str(j)[:200]})")
    return False


def state_delete(name: str, sha: str) -> bool:
    code, _ = _gh("DELETE", f"/repos/{HUB_REPO}/contents/hub/state/{name}.json",
                  {"message": f"비서실 정리: {name}", "sha": sha, "branch": HUB_BRANCH})
    return code == 200


def register_pending(item: dict) -> None:
    """승인 대기 목록에 올림 (24시간 리마인드·'⏳ 승인 대기' 버튼용). 실패해도 승인 버튼은 그대로 작동."""
    if not (os.environ.get("HUB_TOKEN") or os.environ.get("GITHUB_TOKEN")):
        print("(GITHUB_TOKEN 이 없어 승인 대기 목록 등록은 건너뜀)")
        return
    _, sha = state_get(f"pending/{item['key']}")
    state_put(f"pending/{item['key']}", item, sha, f"승인 요청: {item['title'][:40]}")


def decision(key: str):
    """버튼 결과: None(아직 안 누름) / 'approve' / 'redo' / 'drop' / ..."""
    data, _ = state_get("decisions", {})
    d = (data or {}).get(_short_key(key))
    return d["choice"] if d else None


def wait_decision(key: str, minutes: int = 20, every: int = 60):
    """워크플로 안에서 잠깐 기다릴 때 (기본 20분). 보통은 on_choice 로 다음 단계를 실행하는 쪽이 무료 시간을 덜 씀."""
    end = time.time() + minutes * 60
    while time.time() < end:
        d = decision(key)
        if d:
            return d
        time.sleep(every)
    return None


# ---------------------------------------------------------------- 업로드 전 자동 검사
def preflight(meta: dict) -> list[tuple[bool, str]]:
    """유튜브 업로드 정보 점검 → 승인 카드에 ✓/✗ 로 표시.
    meta: title, description, ai(bool), captions(파일 경로 또는 목록), thumbnail(경로), made_for_kids(bool)"""
    title = meta.get("title", "")
    caps = meta.get("captions") or []
    caps = [caps] if isinstance(caps, str) else caps
    thumb = meta.get("thumbnail")
    return [
        (meta.get("ai") is True, "AI 표시"),
        (bool(title) and title.isascii() and len(title) <= 100, "영어 제목"),
        (bool(caps) and all(os.path.exists(c) for c in caps), "자막"),
        (bool(thumb) and os.path.exists(thumb), "썸네일"),
        (meta.get("made_for_kids") is False, "아동용 아님 표시"),
        (len(meta.get("description", "")) >= 100, "설명 100자+"),
    ]
