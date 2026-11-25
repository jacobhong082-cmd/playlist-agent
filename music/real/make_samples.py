"""실사(무료 Pexels) 영상으로 20초 샘플을 만듭니다. 음악은 승인곡 앞부분.
사용: python music/real/make_samples.py <clips.json> <음악.mp3> <출력 폴더>
Pexels 라이선스: 상업적 사용·수정 무료, 출처 표기 불필요 (원본 그대로 재판매만 금지). 출처는 clips.json에 기록.
"""
import json, subprocess, sys, time, urllib.request
from pathlib import Path

FONT = str(Path(__file__).parent.parent / "fonts" / "DMSerifDisplay-italic.ttf")
FONT_N = str(Path(__file__).parent.parent / "fonts" / "DMSerifDisplay-normal.ttf")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
GRADE = "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=24,eq=saturation=0.92:gamma=0.97,colorbalance=rs=0.05:bs=-0.04:rm=0.03:bm=-0.03"


def run(cmd):
    print("$", " ".join(cmd)[:240], flush=True)
    subprocess.run(cmd, check=True)


def download(cid, out):
    for url in [f"https://www.pexels.com/download/video/{cid}/?h=720", f"https://www.pexels.com/download/video/{cid}/"]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.pexels.com/"})
            with urllib.request.urlopen(req, timeout=120) as r:
                ct = r.headers.get("Content-Type", "")
                data = r.read()
            print(cid, url, ct, len(data), flush=True)
            if ct.startswith("video") and len(data) > 100000:
                out.write_bytes(data)
                return True
        except Exception as e:
            print("download fail", cid, url, e, flush=True)
    return False


def overlay(title):
    return (f"drawtext=fontfile={FONT_N}:text='Window Seat Tapes':fontsize=22:fontcolor=white@0.7:x=(w-text_w)/2:y=30,"
            f"drawbox=x=0:y=560:w=1280:h=160:color=black@0.25:t=fill,"
            f"drawtext=fontfile={FONT}:text='{title}':fontsize=34:fontcolor=white@0.92:shadowcolor=black@0.5:"
            f"shadowx=2:shadowy=2:x=(w-text_w)/2:y=612")


def main(clips_path, music, out_dir):
    clips = json.loads(Path(clips_path).read_text())
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    raw = out / "raw"; raw.mkdir(exist_ok=True)
    ok = []
    for c in clips:
        p = raw / f"{c['id']}.mp4"
        if download(c["id"], p):
            ok.append(c)
    print("downloaded", [c["n"] for c in ok], flush=True)
    if not ok:
        raise SystemExit("Pexels 다운로드 모두 실패")
    made = []
    for c in ok:
        o = out / f"real_{c['n']}.mp4"
        # 10초 앞으로 + 10초 거꾸로 = 끊김 없는 20초 반복
        fc = (f"[0:v]trim=0:10,setpts=PTS-STARTPTS,{GRADE},split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1:a=0,"
              + overlay("01  ·  Han River Lights") + "[v];"
              "[1:a]atrim=0:20,afade=t=in:d=1.5,afade=t=out:st=18:d=2[aud]")
        try:
            run(["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", str(raw / f"{c['id']}.mp4"), "-i", music, "-filter_complex", fc,
                 "-map", "[v]", "-map", "[aud]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-t", "20", "-movflags", "+faststart", str(o)])
            made.append({**c, "file": o.name})
        except subprocess.CalledProcessError as e:
            print("encode fail", c["n"], e, flush=True)
    # 섞어 쓰기 샘플: 곡이 바뀔 때마다 장면이 바뀌는 느낌
    if len(made) >= 3:
        pick = made[:3]
        ins, parts = [], []
        for i, c in enumerate(pick):
            ins += ["-stream_loop", "-1", "-i", str(raw / f"{c['id']}.mp4")]
            parts.append(f"[{i}:v]trim=0:8,setpts=PTS-STARTPTS,{GRADE},format=yuv420p[c{i}]")
        fc = ";".join(parts) + ";[c0][c1]xfade=transition=fade:duration=1.5:offset=6.5[x1];" \
             "[x1][c2]xfade=transition=fade:duration=1.5:offset=13[x2];[x2]" + overlay("01  ·  Han River Lights") + "[v];" \
             f"[{len(pick)}:a]atrim=0:21,afade=t=in:d=1.5,afade=t=out:st=19:d=2[aud]"
        o = out / "real_mix.mp4"
        try:
            run(["ffmpeg", "-y", "-v", "error", *ins, "-i", music, "-filter_complex", fc, "-map", "[v]", "-map", "[aud]",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac",
                 "-b:a", "128k", "-t", "21", "-movflags", "+faststart", str(o)])
            made.append({"n": "mix", "label": "장면 섞기 (" + " → ".join(str(c["n"]) for c in pick) + ")", "file": o.name})
        except subprocess.CalledProcessError as e:
            print("mix fail", e, flush=True)
    (out / "made.json").write_text(json.dumps(made, ensure_ascii=False, indent=1))
    for m in made:
        print("MADE", m["n"], m["file"], f"{(out / m['file']).stat().st_size / 1e6:.1f} MB", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:4])
