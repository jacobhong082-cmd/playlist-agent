"""실사 영상 모드: 곡마다 어울리는 실사 장면을 깔고, 곡이 바뀔 때 오디오와 같이 3초 동안 부드럽게 넘어갑니다.
각 장면은 끝과 시작을 겹쳐 이어 붙인 '끊김 없는 반복'으로 곡 길이만큼 돕니다. 1920x1080.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = Path(__file__).parent.parent / "fonts"
W, H, FPS = 1920, 1080, 24
GRADE = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1,"
         "eq=saturation=0.9:gamma=0.96,colorbalance=rs=0.05:bs=-0.04:rm=0.03:bm=-0.03,format=yuv420p")


def run(cmd):
    print("$", " ".join(str(c) for c in cmd)[:300], flush=True)
    subprocess.run(cmd, check=True)


def duration(path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def make_loop(src: Path, dst: Path, max_len: float = 24.0, fade: float = 1.5):
    """끝 1.5초를 처음과 겹쳐서 이음새 없이 반복되는 짧은 영상을 만듭니다."""
    L = min(duration(src), max_len)
    if L < 4 * fade:  # 너무 짧으면 앞뒤로 왕복
        fc = f"[0:v]trim=0:{L:.2f},setpts=PTS-STARTPTS,{GRADE},split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1:a=0[v]"
    else:
        fc = (f"[0:v]{GRADE},split[s1][s2];"
              f"[s1]trim={fade}:{L:.2f},setpts=PTS-STARTPTS[a];[s2]trim=0:{fade},setpts=PTS-STARTPTS[b];"
              f"[a][b]xfade=transition=fade:duration={fade}:offset={L - 2 * fade:.2f}[v]")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-filter_complex", fc, "-map", "[v]", "-an",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(dst)])


def ui_layer(path: Path, channel: str):
    """화면 위 글자 영역: 위쪽 채널 이름, 아래쪽 은은한 그림자."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for y in range(H - 300, H):
        d.line([(0, y), (W, y)], fill=(5, 5, 10, int(175 * ((y - (H - 300)) / 300) ** 1.4)))
    for y in range(0, 140):
        d.line([(0, y), (W, y)], fill=(5, 5, 10, int(90 * (1 - y / 140))))
    f = ImageFont.truetype(str(FONTS / "DMSerifDisplay-normal.ttf"), 32)
    d.text((W / 2, 54), channel, font=f, fill=(255, 236, 210, 190), anchor="mm")
    img.save(path)


def thumbnail(frame_png: Path, line1: str, line2: str, out: Path):
    img = Image.open(frame_png).convert("RGBA").resize((1280, 720))
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for y in range(0, 320):
        d.line([(0, y), (1280, y)], fill=(0, 0, 0, int(160 * (1 - y / 320))))
    d.text((70, 70), line1, font=ImageFont.truetype(str(FONTS / "DMSerifDisplay-italic.ttf"), 66), fill=(255, 238, 214, 255))
    d.text((74, 164), line2, font=ImageFont.truetype(str(FONTS / "DMSerifDisplay-normal.ttf"), 36), fill=(240, 200, 150, 235))
    Image.alpha_composite(img, ov).convert("RGB").save(out, quality=92)


def build(ep: dict, tracks: list, starts: list, total: float, out: Path, clips_dir: Path, cf: float,
          channel: str = "Window Seat Tapes"):
    loops = out / "loops"
    loops.mkdir(exist_ok=True)
    t0 = time.time()
    for tr in tracks:
        cid = tr["clip"]
        dst = loops / f"{cid}.mp4"
        if not dst.exists():
            make_loop(clips_dir / f"{cid}.mp4", dst)
    print(f"made loops in {time.time() - t0:.0f}s", flush=True)
    ui = out / "ui.png"
    ui_layer(ui, channel)

    # 곡마다 장면 하나: 곡 길이만큼 반복 → 곡 바뀌는 지점에서 3초 크로스페이드
    ins, parts = [], []
    for i, tr in enumerate(tracks):
        ins += ["-stream_loop", "-1", "-i", str(loops / f"{tr['clip']}.mp4")]
        parts.append(f"[{i}:v]trim=0:{tr['dur']:.3f},setpts=PTS-STARTPTS[s{i}]")
    chain, last = [], "[s0]"
    for i in range(1, len(tracks)):
        chain.append(f"{last}[s{i}]xfade=transition=fade:duration={cf}:offset={starts[i]:.3f}[x{i}]")
        last = f"[x{i}]"
    n = len(tracks)
    font_i = str(FONTS / "DMSerifDisplay-italic.ttf")
    txt = out / "titles"
    txt.mkdir(exist_ok=True)
    draws = []
    for i, (tr, st) in enumerate(zip(tracks, starts)):
        end = starts[i + 1] if i + 1 < n else total + 1
        f = txt / f"{i:02d}.txt"
        f.write_text(f"{i + 1:02d}  ·  {tr['title']}")
        g = txt / f"{i:02d}n.txt"
        g.write_text(f"{i + 1} / {n}")
        en = f"between(t\\,{st:.2f}\\,{end:.2f})"
        draws.append(f"drawtext=fontfile={font_i}:textfile={f}:fontsize=50:fontcolor=white@0.93:"
                     f"shadowcolor=black@0.55:shadowx=2:shadowy=2:x=(w-text_w)/2:y=930:enable='{en}'")
        draws.append(f"drawtext=fontfile={font_i}:textfile={g}:fontsize=26:fontcolor=white@0.62:"
                     f"x=w-200:y=1002:enable='{en}'")
    fc = ";".join(parts + chain) + f";{last}[{n}:v]overlay=0:0," + ",".join(draws) + "[v]"
    t0 = time.time()
    run(["ffmpeg", "-y", "-v", "error", *ins, "-loop", "1", "-framerate", str(FPS), "-i", str(ui),
         "-i", str(out / "audio.m4a"), "-filter_complex", fc, "-map", "[v]", "-map", f"{n + 1}:a",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-maxrate", "3500k", "-bufsize", "7M",
         "-r", str(FPS), "-pix_fmt", "yuv420p", "-c:a", "copy", "-t", f"{total:.2f}",
         "-movflags", "+faststart", str(out / "video.mp4")])
    print(f"encoded video in {time.time() - t0:.0f}s", flush=True)

    # 미리보기: 곡이 바뀌는 순간 3군데를 20초씩 (장면 전환이 보이게)
    picks = [starts[i] for i in (1, max(2, n // 3), max(3, 2 * n // 3)) if i < n][:3] or [5]
    ins, cat = [], []
    for j, st in enumerate(picks):
        ins += ["-ss", f"{max(0, st - 10):.2f}", "-t", "20", "-i", str(out / "video.mp4")]
        cat.append(f"[{j}:v]scale=854:480,setsar=1[v{j}];[{j}:a]afade=t=in:d=0.5,afade=t=out:st=19.4:d=0.6[a{j}]")
    fc = ";".join(cat) + ";" + "".join(f"[v{j}][a{j}]" for j in range(len(picks))) + \
        f"concat=n={len(picks)}:v=1:a=1[v][a]"
    run(["ffmpeg", "-y", "-v", "error", *ins, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-c:a", "aac", "-b:a", "96k",
         "-movflags", "+faststart", str(out / "preview.mp4")])

    # 썸네일: 첫 장면 3초 화면
    fr = out / "thumb_src.png"
    run(["ffmpeg", "-y", "-v", "error", "-ss", "3", "-i", str(loops / f"{tracks[0]['clip']}.mp4"),
         "-frames:v", "1", str(fr)])
    thumbnail(fr, ep["thumb_line1"], ep["thumb_line2"], out / "thumb.jpg")
    # 확인용: 장면 모음 한 장
    sheet = Image.new("RGB", (5 * 384, ((n + 4) // 5) * 216))
    for i, tr in enumerate(tracks):
        p = out / f"sheet_{i}.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "4", "-i", str(loops / f"{tr['clip']}.mp4"),
                        "-frames:v", "1", "-vf", "scale=384:216", str(p)], check=False)
        if p.exists():
            sheet.paste(Image.open(p), ((i % 5) * 384, (i // 5) * 216))
    sheet.save(out / "scenes.jpg", quality=85)
