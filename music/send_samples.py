"""시험 곡을 텔레그램 오디오로 보내고, 느낌을 고르는 버튼을 붙임."""
import glob, os, sys
sys.path.insert(0, "hub_main/hub")
import secretary as s

_, chat = s._auth()
songs = [("samples/01_rain_on_the_window.mp3", "Rain on the Window", "감성 보컬 · 비 오는 창가 · 84 BPM"),
         ("samples/02_last_bus_home.mp3", "Last Bus Home", "로파이 재즈 연주곡 · 막차 버스 · 78 BPM")]
ids = []
for i, (path, title, desc) in enumerate(songs, 1):
    r = s.tg("sendAudio", {"chat_id": chat, "title": title, "performer": "AI 시험곡",
                           "caption": f"🎵 시험곡 {i} · {desc}", "disable_notification": "true"},
             file=("audio", path), timeout=120)
    assert r.get("ok"), r
    ids.append(r["result"]["message_id"])
    print("sent audio", i, "message_id", r["result"]["message_id"], "duration", r["result"]["audio"].get("duration"))
key = s.ask("playlist", "pl-sample-feel-1", "시험곡 2개 어땠어요?",
            "들어보시고 눌러 주세요. 다음 곡들 만들 때 반영해요.",
            buttons=[("👍 좋아", "good"), ("🌙 더 잔잔하게", "calmer"), ("🎹 보컬 빼고", "novocal")])
print("asked key", key)
