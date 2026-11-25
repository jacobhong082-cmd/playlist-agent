"""실사 샘플을 텔레그램으로 보내고 고르는 버튼을 붙입니다."""
import json, sys
sys.path.insert(0, "hub_main/hub")
import secretary as s

out = sys.argv[1]
made = json.load(open(f"{out}/made.json"))
_, chat = s._auth()
for m in made:
    r = s.tg("sendVideo", {"chat_id": chat, "caption": f"🎬 실사 샘플 {m['n']} · {m['label']}",
                           "supports_streaming": "true", "width": "1280", "height": "720",
                           "disable_notification": "true"},
             file=("video", f"{out}/{m['file']}"), timeout=180)
    assert r.get("ok"), r
    print("sent video", m["n"], "message_id", r["result"]["message_id"])
buttons = [(f"{m['n']}번" if m["n"] != "mix" else "🔀 섞기", f"real{m['n']}") for m in made]
buttons.append(("🤖 AI 실사 영상도 볼래", "ai"))
k = s.ask("playlist", "pl-scene-real-1", "어떤 실사 영상이 좋아요?",
          "무료 실사 영상(Pexels, 상업적 사용 가능)에 승인곡을 입혔어요. 골라 주시면 영상을 이 느낌으로 바꿀게요.",
          buttons=buttons)
print("asked key", k)
