"""
유튜브 업로드 공통 부품 — AI 표시를 빠뜨릴 수 없게 만든 업로드 함수.

필요: pip install requests
비밀값: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN
  (만들 때 권한: youtube.upload, youtube.force-ssl, 성적표용 yt-analytics.readonly)

    import youtube
    vid = youtube.upload("video.mp4", title="Late Night Seoul · Lofi Jazz", description="...",
                         tags=["lofi"], thumbnail="thumb.png", captions={"en": "en.srt"},
                         publish_at="2026-11-25T12:00:00Z")

규칙 (유튜브 정책 · 수익화 대비):
  · 'AI로 만든 콘텐츠' 표시(containsSyntheticMedia)를 항상 켭니다. 끌 수 없습니다.
  · 설명 맨 끝에 AI 사용 안내 문장을 자동으로 붙입니다.
  · 아동용 아님(selfDeclaredMadeForKids=False) 으로 올립니다.
  · publish_at 을 주면 비공개로 올린 뒤 그 시각에 자동 공개됩니다.
"""
from __future__ import annotations

import json
import os
import time

import requests

YT = "https://www.googleapis.com/youtube/v3"
YT_UP = "https://www.googleapis.com/upload/youtube/v3"
AI_NOTE = "\n\n—\nMusic and visuals in this video were created with the help of AI tools."
_tok = {"v": None, "exp": 0}


def token() -> str:
    if _tok["v"] and time.time() < _tok["exp"] - 60:
        return _tok["v"]
    r = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "client_id": os.environ["GOOGLE_CLIENT_ID"].strip(),
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"].strip(),
        "refresh_token": os.environ["GOOGLE_REFRESH_TOKEN"].strip(),
        "grant_type": "refresh_token"})
    if r.status_code != 200:
        raise RuntimeError(f"구글 로그인 실패 ({r.status_code}): {r.text[:300]}")
    j = r.json()
    _tok.update(v=j["access_token"], exp=time.time() + j.get("expires_in", 3600))
    return _tok["v"]


def _h(extra: dict | None = None) -> dict:
    return {"Authorization": f"Bearer {token()}", **(extra or {})}


def _check(r, what):
    if r.status_code >= 300:
        raise RuntimeError(f"{what} 실패 ({r.status_code}): {r.text[:400]}")
    return r


def upload(video: str, *, title: str, description: str, tags: list[str] | None = None,
           category: str = "10", thumbnail: str | None = None, captions: dict | None = None,
           publish_at: str | None = None, language: str = "en", playlist_id: str | None = None) -> str:
    """영상을 올리고 영상 ID 를 돌려줍니다. category 10 = 음악."""
    if AI_NOTE.strip() not in description:
        description = description.rstrip() + AI_NOTE
    status = {"privacyStatus": "private" if publish_at else "public",
              "selfDeclaredMadeForKids": False,
              "containsSyntheticMedia": True}  # ← AI 표시 (항상 켬)
    if publish_at:
        status["publishAt"] = publish_at
    body = {"snippet": {"title": title[:100], "description": description[:5000], "tags": tags or [],
                        "categoryId": category, "defaultLanguage": language,
                        "defaultAudioLanguage": language},
            "status": status}
    size = os.path.getsize(video)
    r = _check(requests.post(f"{YT_UP}/videos", timeout=60,
                             params={"uploadType": "resumable", "part": "snippet,status"},
                             headers=_h({"X-Upload-Content-Type": "video/mp4",
                                         "X-Upload-Content-Length": str(size)}),
                             json=body), "업로드 시작")
    url, vid = r.headers["Location"], None
    for attempt in range(5):
        try:
            with open(video, "rb") as fh:
                r = requests.put(url, data=fh, timeout=3600, headers=_h({"Content-Type": "video/mp4"}))
            if r.status_code in (200, 201):
                vid = r.json()["id"]
                break
            if r.status_code not in (500, 502, 503, 504):
                _check(r, "영상 업로드")
        except requests.RequestException as e:
            print(f"(업로드 끊김, 다시 시도: {e})")
        time.sleep(15 * (attempt + 1))
    if not vid:
        raise RuntimeError("영상 업로드가 계속 실패했어요")
    if thumbnail:
        with open(thumbnail, "rb") as fh:
            _check(requests.post(f"{YT_UP}/thumbnails/set", params={"videoId": vid}, data=fh,
                                 headers=_h({"Content-Type": "image/png"}), timeout=120), "썸네일")
    for lang, path in (captions or {}).items():
        meta = {"snippet": {"videoId": vid, "language": lang, "name": lang.upper()}}
        with open(path, "rb") as fh:
            _check(requests.post(f"{YT_UP}/captions", headers=_h(), timeout=120,
                                 params={"uploadType": "multipart", "part": "snippet"},
                                 files={"metadata": ("m", json.dumps(meta), "application/json"),
                                        "file": ("c.srt", fh, "application/octet-stream")}), "자막")
    if playlist_id:
        _check(requests.post(f"{YT}/playlistItems", params={"part": "snippet"}, headers=_h(), timeout=30,
                             json={"snippet": {"playlistId": playlist_id,
                                               "resourceId": {"kind": "youtube#video", "videoId": vid}}}),
               "재생목록 추가")
    return vid
