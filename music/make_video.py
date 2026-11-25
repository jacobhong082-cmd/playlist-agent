"""곡들을 이어 붙여 1시간 플레이리스트 영상 + 썸네일 + 설명(곡 목록·챕터)을 만듭니다.
사용: python music/make_video.py music/episodes/ep01.json <곡 폴더> <출력 폴더>
곡 폴더에는 <slug>.mp3 가 있어야 합니다. 없는 곡은 건너뛰고 기록합니다.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scene import LOOP, Scene, thumbnail  # noqa: E402

FPS = 24
FONT = str(Path(__file__).parent / "fonts" / "DMSerifDisplay-italic.ttf")


def run(cmd):
    print("$", " ".join(str(c) for c in cmd)[:300], flush=True)
    subprocess.run(cmd, check=True)


def duration(path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def ts(sec: float) -> str:
    sec = int(round(sec))
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def main(ep_path, songs_dir, out_dir, clips_dir="clips"):
    ep = json.loads(Path(ep_path).read_text())
    songs_dir, out = Path(songs_dir), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cf = float(ep.get("crossfade", 3))

    tracks, missing = [], []
    for s in ep["songs"]:
        p = songs_dir / f"{s['slug']}.mp3"
        (tracks if p.exists() else missing).append({**s, "path": p} if p.exists() else s["slug"])
    print(f"tracks {len(tracks)}, missing {missing}", flush=True)
    if len(tracks) < max(3, len(ep["songs"]) - 3):
        raise SystemExit(f"곡이 너무 많이 빠졌어요: {missing}")

    # 1) 오디오: 크로스페이드로 이어 붙이고 소리 크기 맞추기
    starts, t = [], 0.0
    for i, tr in enumerate(tracks):
        tr["dur"] = duration(tr["path"])
        starts.append(t)
        t += tr["dur"] - (cf if i < len(tracks) - 1 else 0)
    total = t
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for tr in tracks:
        cmd += ["-i", str(tr["path"])]
    chain, last = [], "[0:a]"
    for i in range(1, len(tracks)):
        lab = f"[x{i}]"
        chain.append(f"{last}[{i}:a]acrossfade=d={cf}:c1=tri:c2=tri{lab}")
        last = lab
    chain.append(f"{last}loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=in:d=2,afade=t=out:st={total - 4:.2f}:d=4[aout]")
    run(cmd + ["-filter_complex", ";".join(chain), "-map", "[aout]", "-c:a", "aac", "-b:a", "192k",
               "-ar", "48000", str(out / "audio.m4a")])

    if ep.get("visual") == "real":  # 곡마다 실사 장면
        sys.path.insert(0, str(Path(__file__).parent / "real"))
        import real_video
        real_video.build(ep, tracks, starts, total, out, Path(clips_dir), cf)
    else:
        paint(ep, tracks, starts, total, out)
    write_meta(ep, tracks, starts, total, missing, out)


def paint(ep, tracks, starts, total, out):
    # 2) 8초 반복 배경 영상
    scene = Scene(seed=sum(map(ord, ep["id"])))
    frames = out / "frames"
    frames.mkdir(exist_ok=True)
    t0 = time.time()
    n = int(LOOP * FPS)
    for i in range(n):
        scene.frame(i / FPS).save(frames / f"{i:04d}.png")
    print(f"rendered {n} frames in {time.time() - t0:.0f}s", flush=True)
    run(["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS), "-i", str(frames / "%04d.png"),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(out / "loop.mp4")])

    # 3) 곡 제목 표시 + 합치기
    txt = out / "titles"
    txt.mkdir(exist_ok=True)
    draws = []
    for i, (tr, st) in enumerate(zip(tracks, starts)):
        end = starts[i + 1] if i + 1 < len(tracks) else total + 1
        f = txt / f"{i:02d}.txt"
        f.write_text(f"{i + 1:02d}  ·  {tr['title']}")
        g = txt / f"{i:02d}n.txt"
        g.write_text(f"{i + 1} / {len(tracks)}")
        en = f"between(t\\,{st:.2f}\\,{end:.2f})"
        draws.append(f"drawtext=fontfile={FONT}:textfile={f}:fontsize=34:fontcolor=white@0.92:"
                     f"shadowcolor=black@0.5:shadowx=2:shadowy=2:x=(w-text_w)/2:y=612:enable='{en}'")
        draws.append(f"drawtext=fontfile={FONT}:textfile={g}:fontsize=18:fontcolor=white@0.6:"
                     f"x=w-150:y=664:enable='{en}'")
    t0 = time.time()
    run(["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", str(out / "loop.mp4"),
         "-i", str(out / "audio.m4a"), "-filter_complex", "[0:v]" + ",".join(draws) + "[v]",
         "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
         "-r", str(FPS), "-pix_fmt", "yuv420p", "-c:a", "copy", "-t", f"{total:.2f}",
         "-movflags", "+faststart", str(out / "video.mp4")])
    print(f"encoded video in {time.time() - t0:.0f}s", flush=True)

    # 4) 미리보기 (텔레그램용 60초, 작게)
    run(["ffmpeg", "-y", "-v", "error", "-ss", "5", "-i", str(out / "video.mp4"), "-t", "60",
         "-vf", "scale=854:480", "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
         "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(out / "preview.mp4")])

    # 5) 썸네일 + 설명
    thumbnail(scene, ep["thumb_line1"], ep["thumb_line2"], str(out / "thumb.jpg"))


def write_meta(ep, tracks, starts, total, missing, out):
    lines = [f"{ts(st)} {tr['title']}" for tr, st in zip(tracks, starts)]
    desc = (ep.get("story") or "Pour something warm, dim the lights, and let the river do the talking.") + \
        "\n\nTracklist\n" + "\n".join(lines) + \
        "\n\nAll music in this video is original and was created with AI (ACE-Step), " \
        "then selected and arranged by Window Seat Tapes. " + \
        ("Footage: Pexels (free license), edited and color graded for this mix." if ep.get("visual") == "real"
         else "The scene is an original illustration.")
    (out / "description.txt").write_text(desc)
    meta = {"id": ep["id"], "title": ep["title"], "description": desc, "duration": round(total),
            "tracks": [{"title": tr["title"], "start": round(st), "slug": tr["slug"]} for tr, st in zip(tracks, starts)],
            "missing": missing, "check_note": ep.get("check_note", ""), "ai": True, "made_for_kids": False}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    for p in ["video.mp4", "preview.mp4", "thumb.jpg"]:
        print(p, f"{(out / p).stat().st_size / 1e6:.1f} MB", flush=True)
    print(f"TOTAL {ts(total)} with {len(tracks)} tracks", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:5])
