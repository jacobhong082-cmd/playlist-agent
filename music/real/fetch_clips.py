"""회차에 필요한 Pexels 영상을 받습니다. 사용: python music/real/fetch_clips.py <회차.json> <폴더>"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from make_samples import download  # noqa: E402

ep = json.load(open(sys.argv[1]))
out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
bad = []
for cid in dict.fromkeys(s["clip"] for s in ep["songs"] if s.get("clip")):
    p = out / f"{cid}.mp4"
    if p.exists() and p.stat().st_size > 100000:
        continue
    if not download(cid, p):
        bad.append(cid)
print("missing clips:", bad)
