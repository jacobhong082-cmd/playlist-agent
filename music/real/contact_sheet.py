"""장면 점검용: 각 실사 영상에서 3장면(처음·가운데·끝)을 뽑아 번호와 함께 한 장에 붙입니다.
사용: python music/real/contact_sheet.py <회차.json> <clips 폴더> <출력 폴더>"""
import json, subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw

ep = json.load(open(sys.argv[1]))
clips, out = Path(sys.argv[2]), Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
rows = []
for i, s in enumerate(ep["songs"], 1):
    src = clips / f"{s['clip']}.mp4"
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
                             capture_output=True, text=True).stdout.strip() or 0)
    row = Image.new("RGB", (3 * 480, 270 + 30), (20, 20, 20))
    for j, t in enumerate([0.5, d / 2, max(0.5, min(d, 24) - 1)]):
        p = out / f"f_{i}_{j}.jpg"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1",
                        "-vf", "scale=480:270:force_original_aspect_ratio=increase,crop=480:270", str(p)])
        if p.exists():
            row.paste(Image.open(p), (j * 480, 30))
            p.unlink()
    ImageDraw.Draw(row).text((8, 6), f"{i:02d} {s['title']}  | clip {s['clip']}  | {d:.1f}s", fill=(255, 230, 160))
    rows.append(row)
for k in range(0, len(rows), 5):
    part = rows[k:k + 5]
    sheet = Image.new("RGB", (1440, 300 * len(part)))
    for n, r in enumerate(part):
        sheet.paste(r, (0, n * 300))
    sheet.save(out / f"sheet_{k // 5 + 1}.jpg", quality=80)
print("sheets", len(rows))
