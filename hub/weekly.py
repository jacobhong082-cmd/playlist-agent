"""
📊 주간 성적표 — 매주 월요일 아침 7시(한국시간), 한 장짜리 카드로 텔레그램에 보냅니다.

모으는 숫자 (모두 무료, AI 안 씀):
  · 유튜브 조회수·구독자 (YOUTUBE_API_KEY + YOUTUBE_CHANNEL_ID 가 있을 때)
  · 유튜브 시청 시간 (GOOGLE_* 업로드 열쇠에 분석 권한이 있을 때, 없으면 '—')
  · KDP 판매 (일요일 저녁 비서실이 숫자 버튼으로 물어본 값 — KDP 는 자동으로 숫자를 가져올 방법이 없음)
  · 에이전트 성공률 (GitHub 실행 기록)
판정(키울 것 / 접을 것 / 내 할 일)은 정해진 규칙으로 계산합니다.

python weekly.py            → 진짜 숫자로 만들어 보냄
python weekly.py --sample   → 예시 숫자로 카드만 만들어 봄 (보내지 않음)
"""
from __future__ import annotations

import html
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import secretary as s  # noqa: E402
import bot  # noqa: E402

KST = timezone(timedelta(hours=9))
YT = "https://www.googleapis.com/youtube/v3"


def get_json(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


# ---------------------------------------------------------------- 유튜브
def youtube_now() -> dict | None:
    key = (os.environ.get("YOUTUBE_API_KEY") or "").strip()
    ch = (os.environ.get("YOUTUBE_CHANNEL_ID") or "").strip()
    if not key or not ch:
        return None
    j = get_json(f"{YT}/channels?part=statistics,contentDetails&id={ch}&key={key}")
    if not j.get("items"):
        return None
    it = j["items"][0]
    st = it["statistics"]
    uploads = it["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, page = [], ""
    while len(ids) < 200:
        p = get_json(f"{YT}/playlistItems?part=contentDetails&maxResults=50&playlistId={uploads}&key={key}"
                     + (f"&pageToken={page}" if page else ""))
        ids += [x["contentDetails"]["videoId"] for x in p.get("items", [])]
        page = p.get("nextPageToken")
        if not page:
            break
    videos = {}
    for i in range(0, len(ids), 50):
        v = get_json(f"{YT}/videos?part=statistics,snippet&id={','.join(ids[i:i+50])}&key={key}")
        for x in v.get("items", []):
            videos[x["id"]] = {"title": x["snippet"]["title"], "published": x["snippet"]["publishedAt"],
                               "views": int(x["statistics"].get("viewCount", 0))}
    return {"views": int(st.get("viewCount", 0)), "subs": int(st.get("subscriberCount", 0)), "videos": videos}


def watch_hours_total() -> float | None:
    """채널 전체 누적 시청 시간(시간). 수익화 조건은 최근 12개월 4,000시간이라 365일로 셉니다."""
    if not all(os.environ.get(k) for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN")):
        return None
    try:
        data = urllib.parse.urlencode({
            "client_id": os.environ["GOOGLE_CLIENT_ID"].strip(),
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"].strip(),
            "refresh_token": os.environ["GOOGLE_REFRESH_TOKEN"].strip(),
            "grant_type": "refresh_token"}).encode()
        with urllib.request.urlopen("https://oauth2.googleapis.com/token", data, timeout=30) as r:
            tok = json.loads(r.read())["access_token"]
        end = datetime.now(KST).date()
        q = urllib.parse.urlencode({"ids": "channel==MINE", "metrics": "estimatedMinutesWatched",
                                    "startDate": str(end - timedelta(days=365)), "endDate": str(end)})
        j = get_json(f"https://youtubeanalytics.googleapis.com/v2/reports?{q}",
                     {"Authorization": f"Bearer {tok}"})
        return round(j["rows"][0][0] / 60, 1) if j.get("rows") else 0.0
    except Exception as e:  # 분석 권한이 없으면 그냥 '—'
        print(f"(시청 시간 못 가져옴: {e})")
        return None


# ---------------------------------------------------------------- 에이전트 성공률
def agent_health(since: datetime) -> tuple[int, int]:
    ok = bad = 0
    seen = set()
    for a in bot.agents_config():
        if not a.get("workflow") or a.get("paused") or (a["repo"], a["workflow"]) in seen:
            continue
        seen.add((a["repo"], a["workflow"]))
        for r in bot.latest_runs(a["repo"], a["workflow"], n=100):
            if r["status"] != "completed":
                continue
            if datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00")) < since:
                break
            ok += r["conclusion"] == "success"
            bad += r["conclusion"] == "failure"
    return ok, bad


# ---------------------------------------------------------------- 숫자 모으기
def fmt(n) -> str:
    return "—" if n is None else f"{n:,}"


def delta(now, before, pct=False) -> str:
    if now is None or before is None:
        return ""
    d = now - before
    if pct and before:
        return f"{'+' if d >= 0 else ''}{d / before * 100:.0f}%"
    return f"{'+' if d >= 0 else ''}{d:,}"


def collect() -> dict:
    now = datetime.now(KST)
    start = (now - timedelta(days=now.weekday() + 7)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=6)
    snap, snap_sha = s.state_get("yt_snapshot", None)
    yt = None
    try:
        yt = youtube_now()
    except Exception as e:
        print(f"(유튜브 숫자 못 가져옴: {e})")
    d = {"range": f"{start:%m.%d} — {end:%m.%d}", "yt": yt is not None}
    verdict = {"grow": None, "drop": None}
    if yt:
        prev = snap or {}
        d["views"], d["subs"] = yt["views"], yt["subs"]
        d["views_d"] = delta(yt["views"], prev.get("views"), pct=True) if prev else "첫 주"
        d["subs_d"] = delta(yt["subs"], prev.get("subs")) if prev else "첫 주"
        pv = prev.get("videos", {})
        week = []
        for vid, v in yt["videos"].items():
            gained = v["views"] - pv.get(vid, {}).get("views", 0)
            age = (now - datetime.fromisoformat(v["published"].replace("Z", "+00:00"))).days
            week.append((gained, age, v["title"]))
        week.sort(reverse=True)
        if week and week[0][0] > 0:
            verdict["grow"] = f"{week[0][2][:28]} · 이번 주 조회 {week[0][0]:,} → 비슷한 영상 더"
        weak = [w for w in week if w[1] >= 21 and w[0] < 50]
        if weak:
            verdict["drop"] = f"{weak[-1][2][:28]} 외 {len(weak) - 1}편 · 3주 넘게 주간 조회 50 미만" \
                if len(weak) > 1 else f"{weak[-1][2][:28]} · 3주 넘게 주간 조회 50 미만"
        s.state_put("yt_snapshot", {"date": now.isoformat(), "views": yt["views"], "subs": yt["subs"],
                                    "videos": {k: {"views": v["views"]} for k, v in yt["videos"].items()}},
                    snap_sha, "성적표: 유튜브 숫자 저장")
    d["hours"] = watch_hours_total()

    kdp, _ = s.state_get("kdp_sales", {})
    kdp = kdp or {}
    wk, cur = f"{start:%Y-%m-%d}", f"{start + timedelta(days=7):%Y-%m-%d}"
    entry = kdp.get(wk) or kdp.get(cur)
    prev_entry = kdp.get(f"{start - timedelta(days=7):%Y-%m-%d}")
    d["kdp"] = entry["books"] if entry else None
    d["kdp_d"] = delta(d["kdp"], prev_entry["books"] if prev_entry else None) if entry else "입력 전"
    per = json.loads((HERE / "agents.json").read_text()).get("kdp_royalty_per_book")
    d["royalty"] = round(sum((v.get("usd") if v.get("usd") is not None else v["books"] * (per or 0))
                             for v in kdp.values()), 2) if per or any(v.get("usd") for v in kdp.values()) else None

    ok, bad = agent_health(start)
    d["runs"], d["fails"] = ok + bad, bad
    d["rate"] = f"{ok / (ok + bad) * 100:.0f}%" if ok + bad else "—"

    todo = []
    pend = bot.pending_items()
    if pend:
        todo.append(f"승인 대기 {len(pend)}건")
    if not entry:
        todo.append("KDP 판매 입력 (📚 버튼)")
    if bad:
        todo.append(f"실패 {bad}건 확인")
    d["todo"] = " · ".join(todo) or "없어요. 푹 쉬세요 🙌"
    d["grow"] = verdict["grow"] or ("채널 연결 후 자동 판정" if not yt else "아직 눈에 띄는 영상 없음")
    d["drop"] = verdict["drop"] or ("—" if not yt else "접을 것 없음")
    return d


def sample() -> dict:
    return {"range": "11.17 — 11.23", "yt": True, "views": 3820, "views_d": "+48%", "subs": 146, "subs_d": "+38",
            "kdp": 7, "kdp_d": "+4", "hours": 212, "royalty": 18, "runs": 98, "fails": 2, "rate": "98%",
            "grow": "Rainy Cafe Jazz · 이번 주 조회 1,910 → 비슷한 영상 더",
            "drop": "Morning Classic · 3주 넘게 주간 조회 50 미만", "todo": "KDP 표지 승인 1건"}


# ---------------------------------------------------------------- 카드 그리기
def bar(now, goal) -> str:
    w = 0 if not now else min(100, now / goal * 100)
    return f'<div class="tr"><i style="width:{max(w, 1.5 if now else 0):.1f}%"></i></div>'


def render(d: dict, out: Path) -> Path:
    e = lambda x: html.escape(str(x))  # noqa: E731
    tpl = (HERE / "card.html").read_text()
    body = tpl.format(
        range=e(d["range"]),
        views=e(fmt(d.get("views"))), views_d=e(d.get("views_d", "채널 연결 전")),
        subs=e(fmt(d.get("subs"))), subs_d=e(d.get("subs_d", "")),
        kdp=e(fmt(d.get("kdp"))), kdp_d=e(d.get("kdp_d", "")),
        subs_bar=bar(d.get("subs"), 1000), subs_txt=e(f"{fmt(d.get('subs'))} / 1,000"),
        hours_bar=bar(d.get("hours"), 4000), hours_txt=e(f"{fmt(d.get('hours'))} / 4,000h"),
        roy_bar=bar(d.get("royalty"), 100),
        roy_txt=e(f"${d['royalty']:g} / $100" if d.get("royalty") is not None else "가격 정해지면 자동"),
        rate=e(d["rate"]), runs=e(d["runs"]), fails=e(d["fails"]),
        grow=e(d["grow"]), drop=e(d["drop"]), todo=e(d["todo"]),
    )
    page = HERE / "_card_render.html"
    page.write_text(body)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=os.environ.get("CHROME_PATH") or None)
        pg = b.new_page(viewport={"width": 540, "height": 800}, device_scale_factor=2)
        pg.goto(page.resolve().as_uri())
        pg.wait_for_timeout(400)
        pg.locator(".sheet").screenshot(path=str(out))
        b.close()
    page.unlink()
    return out


def caption(d: dict) -> str:
    lines = [f"📊 <b>주간 성적표</b> · {d['range']}"]
    if d.get("yt"):
        lines.append(f"🎵 조회 {fmt(d.get('views'))} ({d.get('views_d')}) · 구독자 {fmt(d.get('subs'))} ({d.get('subs_d')})")
    else:
        lines.append("🎵 유튜브는 채널을 연결하면 자동으로 채워져요")
    lines.append(f"📚 KDP {fmt(d.get('kdp')) + '권' if d.get('kdp') is not None else '입력 전'}")
    lines.append(f"🛠 에이전트 {d['runs']}번 실행 · 실패 {d['fails']}번 · 쓴 돈 0원")
    lines.append(f"✅ 내 할 일: {d['todo']}")
    return "\n".join(lines)


def main() -> None:
    is_sample = "--sample" in sys.argv
    if not is_sample and not all(s._auth()):
        print("텔레그램 비밀값이 아직 없어 성적표를 건너뜁니다.")
        return
    d = sample() if is_sample else collect()
    out = render(d, HERE / "weekly_card.png")
    print(f"카드 완성: {out}")
    if is_sample:
        return
    s._send(caption(d), silent=False, photo=str(out))
    print("텔레그램 전송 완료")


if __name__ == "__main__":
    main()
