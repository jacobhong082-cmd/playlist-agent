"""완성된 회차를 텔레그램으로 미리보기 + 승인 버튼."""
import json, sys
sys.path.insert(0, "hub_main/hub")
import secretary as s

out = sys.argv[1]
meta = json.load(open(f"{out}/meta.json"))
rel = sys.argv[2] if len(sys.argv) > 2 else ""
run_id = sys.argv[3] if len(sys.argv) > 3 else ""
_, chat = s._auth()
mins = meta["duration"] // 60
r = s.tg("sendVideo", {"chat_id": chat, "caption": f"🎬 미리보기 (곡이 바뀌는 장면 위주) · 전체 {mins}분 · {len(meta['tracks'])}곡",
                       "supports_streaming": "true", "disable_notification": "true"},
         file=("video", f"{out}/preview.mp4"), timeout=180)
assert r.get("ok"), r
print("sent preview message_id", r["result"]["message_id"])
tracks = "\n".join(f"{t['start'] // 60}:{t['start'] % 60:02d} {t['title']}" for t in meta["tracks"])
body = f"{meta['title']}\n\n{tracks}"
if meta.get("check_note"):
    body = meta["check_note"] + "\n\n" + body
if meta.get("missing"):
    body += f"\n\n⚠️ 빠진 곡: {', '.join(meta['missing'])}"
if rel:
    body += f"\n\n전체 영상: {rel}"
checks = [(meta.get("ai") is True, "AI 표시"), (meta.get("made_for_kids") is False, "아동용 아님"),
          (len(meta["tracks"]) >= 3, "챕터"), (mins >= 55, "1시간 분량")]
k = s.ask("playlist", f"pl-{meta['id']}" + (f"-{run_id[-6:]}" if run_id else ""), "새 플레이리스트 영상 어때요?", body[:900],
          photo=f"{out}/thumb.jpg", checks=checks)
print("asked key", k)
