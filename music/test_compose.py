"""시험 작곡: 감성 곡 2개 (보컬 1, 연주 1) 를 만들고 걸린 시간을 기록.
사용: python music/test_compose.py <ACE-Step 폴더> <출력 폴더> <곡 길이(초)>
"""
import json, os, sys, time, traceback
from pathlib import Path

ace, out, dur = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), float(sys.argv[3])
only = sys.argv[4] if len(sys.argv) > 4 else ""
songs_file = str(Path(sys.argv[5]).resolve()) if len(sys.argv) > 5 else ""
out.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("ACESTEP_INIT_LLM", "false")
os.chdir(ace)
sys.path.insert(0, str(ace))

from acestep.handler import AceStepHandler            # noqa: E402
from acestep.llm_inference import LLMHandler          # noqa: E402
from acestep.inference import GenerationParams, GenerationConfig, generate_music  # noqa: E402

SONGS = [
    {
        "slug": "01_rain_on_the_window",
        "caption": "warm emotional acoustic pop ballad, soft breathy female vocal, gentle electric piano, "
                   "nylon guitar, brushed drums, light vinyl crackle, rainy evening cafe mood, calm and steady, "
                   "no sudden drops",
        "lyrics": "[Verse]\nRain on the window, the city slows down\nCoffee gone cold in this quiet part of town\n"
                  "I keep your name in the fog on the glass\nWaiting for the evening rain to pass\n\n"
                  "[Chorus]\nStay a little longer, the lights are soft and low\n"
                  "Seoul is humming something only we know",
        "bpm": 84, "keyscale": "D major", "instrumental": False,
    },
    {
        "slug": "02_last_bus_home",
        "caption": "lofi jazz instrumental, mellow rhodes piano chords, warm upright bass, soft boom bap drums, "
                   "tape hiss, late night bus ride through city lights, cozy and nostalgic, steady volume",
        "lyrics": "[Instrumental]",
        "bpm": 78, "keyscale": "A minor", "instrumental": True,
    },
]

if songs_file:
    SONGS = json.loads(Path(songs_file).read_text())
    if isinstance(SONGS, dict):
        SONGS = SONGS["songs"]

log = {"device": "cpu", "duration_s": dur, "songs": []}
t0 = time.time()
dit = AceStepHandler()
init = dit.initialize_service(project_root=str(ace), config_path="acestep-v15-turbo", device="cpu")
log["init_result"] = str(init)[:500]
log["load_seconds"] = round(time.time() - t0, 1)
print("model loaded in", log["load_seconds"], "s:", log["init_result"], flush=True)
llm = LLMHandler()  # 작사 도우미는 끔 (CPU 절약)

for s in SONGS:
    if only and s["slug"] != only:
        continue
    t = time.time()
    entry = {"slug": s["slug"]}
    try:
        params = GenerationParams(caption=s["caption"], lyrics=s["lyrics"], instrumental=s["instrumental"],
                                  bpm=s["bpm"], keyscale=s["keyscale"], duration=dur, vocal_language="en",
                                  inference_steps=8, shift=3.0, thinking=False,
                                  use_cot_metas=False, use_cot_caption=False, use_cot_language=False)
        cfg = GenerationConfig(batch_size=1, audio_format="mp3")
        res = generate_music(dit, llm, params, cfg, save_dir=str(out / s["slug"]))
        entry["success"] = bool(res.success)
        entry["error"] = None if res.success else str(res.error)
        if res.success:
            entry["files"] = [a["path"] for a in res.audios]
    except Exception:
        entry["success"] = False
        entry["error"] = traceback.format_exc()[-2000:]
    entry["seconds"] = round(time.time() - t, 1)
    print(json.dumps(entry, ensure_ascii=False), flush=True)
    log["songs"].append(entry)

(out / "result.json").write_text(json.dumps(log, ensure_ascii=False, indent=2))
ok = [x for x in log["songs"] if x["success"]]
if ok:
    per_min = sum(x["seconds"] for x in ok) / len(ok) / (dur / 60)
    print(f"SPEED: {per_min:.0f} s of compute per 1 min of music -> "
          f"1-hour playlist ~ {per_min * 60 / 3600:.1f} h", flush=True)
sys.exit(0 if ok else 1)
