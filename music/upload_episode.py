"""승인 버튼을 누르면 실행: 만들어 둔 회차 영상을 유튜브에 올리고 텔레그램으로 알려 줍니다.
사용: python music/upload_episode.py <영상 폴더> <choice>
비밀값 GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN 이 없으면 '연결 필요'라고 알려 줍니다."""
import json, os, sys
sys.path.insert(0, "hub_main/hub")
import secretary as s  # noqa: E402

folder, choice = sys.argv[1], sys.argv[2]
if choice == "drop":
    s.notify("playlist", "이번 영상은 버렸어요", "다음 회차를 기다려 주세요.")
    sys.exit(0)
if choice == "redo":
    s.notify("playlist", "다시 만들기 접수", "Claude가 곡과 장면을 바꿔 새로 만들어 보낼게요.")
    sys.exit(0)
if not all(os.environ.get(k, "").strip() for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN")):
    s.notify("playlist", "승인 접수 · 유튜브 연결이 아직 필요해요",
             "영상은 보관함에 잘 있어요. 유튜브 연결 설정을 마치면 바로 올릴게요.", level="urgent")
    sys.exit(0)
import youtube  # noqa: E402
meta = json.load(open(f"{folder}/meta.json"))
assert meta.get("ai") is True and meta.get("made_for_kids") is False, "AI 표시/아동용 설정 확인 실패"
vid = youtube.upload(f"{folder}/video.mp4", title=meta["title"], description=meta["description"],
                     tags=["late night jazz", "jazz playlist", "whiskey jazz", "city night", "Seoul night",
                           "relaxing jazz", "work music"],
                     thumbnail=f"{folder}/thumb.jpg", category="10", language="en")
s.notify("playlist", "유튜브에 올렸어요 🎉", f"https://youtu.be/{vid}\n고정 댓글(곡 목록)과 하트는 유튜브 앱에서 직접 눌러 주세요.")
print("uploaded", vid)
