"""밤 한강 창가 장면 (Pillow, 무료). 8초마다 끊김 없이 반복되는 화면을 그립니다.
- 강물에 비친 불빛이 일렁이고, 다리 불빛이 천천히 반짝이고, 위스키 잔 옆 촛불·조명이 흔들려요.
- frame(t) 는 0 <= t < LOOP 구간에서 1280x720 RGB 이미지를 돌려줍니다.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).parent
FONTS = HERE / "fonts"
W, H = 1280, 720
LOOP = 8.0
TAU = 2 * math.pi


def font(name: str, size: int):
    return ImageFont.truetype(str(FONTS / name), size)


def _w(t, n=1):  # 반복 주기에 맞춘 각속도
    return TAU * n * t / LOOP


def lerp(a, b, k):
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


class Scene:
    def __init__(self, seed: int = 7, channel: str = "Window Seat Tapes"):
        self.rng = random.Random(seed)
        self.channel = channel
        self.bg = self._background()
        r = self.rng
        self.reflect = [(r.uniform(140, 1140), r.uniform(470, 575), r.uniform(6, 26),
                         r.choice([(255, 200, 120), (255, 170, 90), (200, 215, 255), (255, 230, 160)]),
                         r.uniform(0, TAU), r.choice([1, 2, 3])) for _ in range(90)]
        self.bridge = [(150 + i * 33, r.uniform(0, TAU)) for i in range(31)]

    # ---------------------------------------------------------- 정적인 배경
    def _background(self):
        r = self.rng
        img = Image.new("RGB", (W, H))
        d = ImageDraw.Draw(img)
        top, mid, low = (12, 16, 38), (34, 34, 70), (70, 52, 78)
        for y in range(H):
            k = y / H
            c = lerp(top, mid, k / 0.5) if k < 0.5 else lerp(mid, low, min(1, (k - 0.5) / 0.15))
            d.line([(0, y), (W, y)], fill=c)
        # 강 건너 스카이라인
        x = 100
        while x < W - 100:
            w = r.randint(28, 90)
            h = r.randint(60, 230)
            d.rectangle([x, 420 - h, x + w, 440], fill=(20, 20, 40))
            for wy in range(420 - h + 10, 432, 14):
                for wx in range(x + 5, x + w - 6, 11):
                    if r.random() < 0.3:
                        d.rectangle([wx, wy, wx + 4, wy + 6], fill=(255, 208, 140))
            x += w + r.randint(0, 8)
        # 남산 타워 실루엣 (일반적인 전망탑 모양)
        d.polygon([(860, 300), (930, 300), (900, 250)], fill=(18, 18, 36))
        d.rectangle([892, 170, 900, 300], fill=(22, 22, 44))
        d.ellipse([884, 186, 908, 198], fill=(255, 190, 110))
        # 강물
        for y in range(450, 590):
            k = (y - 450) / 140
            d.line([(0, y), (W, y)], fill=lerp((22, 26, 54), (10, 12, 28), k))
        # 다리 상판
        d.rectangle([120, 440, W - 120, 452], fill=(28, 28, 50))
        for px in range(170, W - 120, 120):
            d.rectangle([px, 452, px + 10, 470], fill=(24, 24, 44))
        return img.filter(ImageFilter.GaussianBlur(1.6)).convert("RGBA")

    # ---------------------------------------------------------- 움직이는 층
    def _lights(self, t):
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        for (x, ph) in self.bridge:  # 다리 불빛 반짝임
            a = int(150 + 90 * math.sin(_w(t) + ph))
            d.ellipse([x - 3, 437, x + 3, 443], fill=(255, 214, 150, a))
        for (x, y, ln, c, ph, n) in self.reflect:  # 강물 반사 일렁임
            dx = 6 * math.sin(_w(t, n) + ph)
            a = int(70 + 60 * math.sin(_w(t, n) + ph * 1.7))
            d.line([(x + dx - ln / 2, y), (x + dx + ln / 2, y)], fill=c + (a,), width=2)
        return lay.filter(ImageFilter.GaussianBlur(1.2))

    def _interior(self, t):
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        wood, wood_d = (62, 40, 30, 255), (40, 26, 20, 255)
        d.rectangle([0, 0, W, 64], fill=wood_d)
        d.rectangle([0, 0, 112, H], fill=wood_d)
        d.rectangle([W - 112, 0, W, H], fill=wood_d)
        d.rectangle([104, 56, W - 104, 76], fill=wood)
        d.rectangle([622, 64, 656, 590], fill=wood)
        d.rectangle([0, 588, W, 614], fill=(86, 58, 40, 255))
        d.rectangle([0, 614, W, H], fill=(50, 34, 26, 255))
        # 따뜻한 노란 조명 (스탠드)
        lx = 1040
        d.rectangle([lx - 4, 470, lx + 4, 590], fill=(30, 22, 16, 255))
        d.ellipse([lx - 40, 584, lx + 40, 596], fill=(30, 22, 16, 255))
        d.polygon([(lx - 70, 470), (lx + 70, 470), (lx + 40, 400), (lx - 40, 400)], fill=(236, 196, 120, 255))
        # 위스키 잔 + 얼음
        gx, gy = 820, 590
        d.polygon([(gx - 46, gy - 90), (gx + 46, gy - 90), (gx + 40, gy), (gx - 40, gy)],
                  fill=(255, 255, 255, 40), outline=(255, 255, 255, 110))
        d.polygon([(gx - 43, gy - 48), (gx + 43, gy - 48), (gx + 40, gy - 4), (gx - 40, gy - 4)],
                  fill=(196, 112, 36, 210))
        bob = 2 * math.sin(_w(t))
        d.rounded_rectangle([gx - 26, gy - 62 + bob, gx + 2, gy - 36 + bob], 5,
                            fill=(255, 255, 255, 80), outline=(255, 255, 255, 140))
        d.rectangle([gx - 40, gy - 4, gx + 40, gy], fill=(255, 255, 255, 90))
        # 작은 책 두 권
        d.rectangle([230, 566, 420, 590], fill=(92, 60, 48, 255))
        d.rectangle([248, 546, 404, 566], fill=(54, 68, 70, 255))
        # 조명 빛 번짐 (살짝 숨쉬듯)
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        g = ImageDraw.Draw(glow)
        a = int(70 + 12 * math.sin(_w(t)))
        g.ellipse([lx - 330, 300, lx + 300, 820], fill=(255, 176, 80, a))
        g.ellipse([gx - 90, gy - 70, gx + 90, gy + 30], fill=(255, 150, 60, 40))
        glow = glow.filter(ImageFilter.GaussianBlur(70))
        return Image.alpha_composite(lay, glow)

    def _ui(self, t, wave: bool = True):
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        for y in range(H - 200, H):
            d.line([(0, y), (W, y)], fill=(6, 6, 12, int(170 * (y - (H - 200)) / 200)))
        d.text((W / 2, 36), self.channel, font=font("DMSerifDisplay-normal.ttf", 22),
               fill=(255, 236, 210, 170), anchor="mm")
        if wave:
            for i in range(36):
                hgt = 5 + 20 * abs(math.sin(i * 0.7 + _w(t, 3)) * math.sin(i * 0.23 + _w(t, 1)))
                x = 60 + i * 7
                d.line([(x, 676 - hgt / 2), (x, 676 + hgt / 2)], fill=(255, 230, 200, 150), width=3)
        return ov

    def frame(self, t: float, ui: bool = True) -> Image.Image:
        img = Image.alpha_composite(self.bg, self._lights(t))
        img = Image.alpha_composite(img, self._interior(t))
        if ui:
            img = Image.alpha_composite(img, self._ui(t))
        return img.convert("RGB")


def thumbnail(scene: Scene, line1: str, line2: str, out: str):
    img = scene.frame(1.5, ui=False).convert("RGBA")
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for y in range(0, 300):
        d.line([(0, y), (W, y)], fill=(0, 0, 0, int(140 * (1 - y / 300))))
    d.text((70, 70), line1, font=font("DMSerifDisplay-italic.ttf", 64), fill=(255, 238, 214, 255))
    d.text((74, 160), line2, font=font("DMSerifDisplay-normal.ttf", 34), fill=(240, 200, 150, 230))
    Image.alpha_composite(img, ov).convert("RGB").save(out, quality=92)


if __name__ == "__main__":
    import sys
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    s = Scene()
    s.frame(1.0).save(out / "scene_frame.png")
    thumbnail(s, "whiskey, han river, 2 a.m.", "1 hour of late night jazz", str(out / "thumb.png"))
