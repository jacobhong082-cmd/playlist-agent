"""한 라운드의 시험곡을 텔레그램 오디오로 보내고 느낌 버튼을 붙임.
사용: python music/send_round.py music/round2.json samples pl-sample-feel-2"""
import json, sys
sys.path.insert(0, "hub_main/hub")
import secretary as s

songs = json.load(open(sys.argv[1]))
folder, key = sys.argv[2], sys.argv[3]
_, chat = s._auth()
for i, song in enumerate(songs, 1):
    r = s.send("playlist", "sendAudio", {"title": song["title"], "performer": "AI 시험곡",
                           "caption": f"🎵 시험곡 {i} · {song['desc']}", "disable_notification": "true"},
             file=("audio", f"{folder}/{song['slug']}.mp3"), timeout=120)
    assert r.get("ok"), r
    print("sent audio", i, "message_id", r["result"]["message_id"], "duration", r["result"]["audio"].get("duration"))
k = s.ask("playlist", key, "이번 연주곡들은 어땠어요?", "한강 야경 · 노란 조명 · 위스키 느낌으로 만들었어요.",
          buttons=[("👍 좋아", "good"), ("🌙 더 잔잔하게", "calmer"), ("🎷 재즈 더 진하게", "jazzier")])
print("asked key", k)
