"""KDP 책 공장 — 코드로만 그려서(그림 AI 없음, 비용 0원) 인쇄용 PDF를 만듭니다.

만드는 것 (책 1권마다):
  interior.pdf  속지 (8.5x11인치, 흑백, 여백 없음 no-bleed, 300dpi)
  cover.pdf     감싸는 표지 (뒤표지 + 책등 + 앞표지, 사방 0.125인치 bleed)
  preview.png   텔레그램 승인 카드용 미리보기 (표지 + 속지 2쪽)
  listing.json  아마존 등록 문구 (제목·부제·설명·키워드 7개·카테고리·가격·AI 질문 답)

책 종류:
  wordsearch  큰 글씨 단어 찾기 (낱말 묶음 kdp/wordbanks/<id>.json 에서)
  coloring    한국 문양 컬러링 (조각보·꽃살·단청 무늬, 씨앗 번호로 매번 다른 그림)
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
FONTS = HERE / "fonts"
F_BOLD = str(FONTS / "NanumGothic-Bold.ttf")
F_REG = str(FONTS / "NanumGothic-Regular.ttf")
F_SERIF = str(FONTS / "DMSerifDisplay-normal.ttf")
F_MJ = str(FONTS / "NanumMyeongjoExtraBold.ttf")

DPI = 300
TRIM_W, TRIM_H = 8.5, 11.0
PW, PH = int(TRIM_W * DPI), int(TRIM_H * DPI)
MARGIN = int(0.6 * DPI)          # KDP 최소: 안쪽 0.375", 바깥 0.25" → 사방 0.6"로 넉넉히
BLEED = 0.125
PAPER_IN_PER_PAGE = 0.002252     # KDP 흰 종이(흑백) 책등 두께
INK, GRAY, LIGHT = 0, 110, 205
MINT, APRICOT, CREAM, INK_RGB = (127, 196, 170), (244, 176, 132), (252, 248, 240), (40, 44, 52)
_BRAND = json.loads((HERE / "brand.json").read_text())
BRAND, BRAND_KO = _BRAND["en"], _BRAND["ko"]
_fonts: dict = {}


def font(path, px):
    k = (path, px)
    if k not in _fonts:
        _fonts[k] = ImageFont.truetype(path, px)
    return _fonts[k]


def page(mode="L"):
    return Image.new(mode, (PW, PH), 255 if mode == "L" else "white")


def ctext(d, xy, s, f, fill=INK):
    d.text(xy, s, font=f, fill=fill, anchor="mm")


def page_number(d, n):
    ctext(d, (PW / 2, PH - MARGIN / 2), str(n), font(F_REG, 34), GRAY)


# =========================================================== 단어 찾기
N = 15
DIRS = [(0, 1), (1, 0), (1, 1), (-1, 1)]       # 큰 글씨판: 거꾸로 읽기 없음


def _occurrences(g, w):
    """격자에서 단어가 나오는 모든 자리. 이 책은 '거꾸로 없음'이라 읽는 방향(DIRS)만 셈."""
    found = set()
    for r in range(N):
        for k in range(N):
            for dr, dc in DIRS:
                er, ec = r + dr * (len(w) - 1), k + dc * (len(w) - 1)
                if 0 <= er < N and 0 <= ec < N and all(g[r + dr * i][k + dc * i] == w[i] for i in range(len(w))):
                    found.add(frozenset((r + dr * i, k + dc * i) for i in range(len(w))))
    return found


def _count(g, w):
    return len(_occurrences(g, w))


def build_grid(words: list[str], seed: int):
    """단어를 숨긴 15x15 격자. 모든 단어가 '정확히 한 번'만 나오도록 검사까지 통과한 것만 돌려줌."""
    rnd = random.Random(seed)
    fill_letters = "".join(words)
    for _ in range(300):
        g = [[None] * N for _ in range(N)]
        place = {}
        for w in sorted(words, key=len, reverse=True):
            for _ in range(500):
                dr, dc = rnd.choice(DIRS)
                r, c = rnd.randrange(N), rnd.randrange(N)
                er, ec = r + dr * (len(w) - 1), c + dc * (len(w) - 1)
                if not (0 <= er < N and 0 <= ec < N):
                    continue
                cells = [(r + dr * i, c + dc * i) for i in range(len(w))]
                if all(g[a][b] in (None, w[i]) for i, (a, b) in enumerate(cells)):
                    for i, (a, b) in enumerate(cells):
                        g[a][b] = w[i]
                    place[w] = cells
                    break
            else:
                break
        if len(place) != len(words):
            continue
        used = {cell for cells in place.values() for cell in cells}
        for a in range(N):
            for b in range(N):
                if g[a][b] is None:
                    g[a][b] = rnd.choice(fill_letters)
        # 빈칸 글자 때문에 단어가 우연히 한 번 더 생기면 그 칸만 바꿔서 고침
        for _ in range(400):
            extra = [occ for w in words for occ in _occurrences(g, w) if occ != frozenset(place[w])]
            if not extra:
                return g, place
            free = [c for c in extra[0] if c not in used]
            if not free:
                break
            a, b = rnd.choice(free)
            g[a][b] = rnd.choice(fill_letters)
    raise RuntimeError(f"격자를 만들지 못했어요: {words}")


def _draw_grid(d, g, place, x, y, cell, size, solution, show_letters=True):
    if solution:
        for cells in place.values():
            (r0, c0), (r1, c1) = cells[0], cells[-1]
            p0 = (x + c0 * cell + cell / 2, y + r0 * cell + cell / 2)
            p1 = (x + c1 * cell + cell / 2, y + r1 * cell + cell / 2)
            wdt = int(cell * 0.72)
            d.line([p0, p1], fill=LIGHT, width=wdt)
            for px, py in (p0, p1):
                d.ellipse([px - wdt / 2, py - wdt / 2, px + wdt / 2, py + wdt / 2], fill=LIGHT)
    f = font(F_BOLD, size)
    for r in range(N):
        for c in range(N):
            ctext(d, (x + c * cell + cell / 2, y + r * cell + cell / 2), g[r][c], f)


def puzzle_page(no, theme, g, place):
    im = page()
    d = ImageDraw.Draw(im)
    ctext(d, (PW / 2, MARGIN + 60), f"Puzzle {no} · {theme['title']}", font(F_SERIF, 110))
    ctext(d, (PW / 2, MARGIN + 165), theme["ko"], font(F_MJ, 62), GRAY)
    cell = 128
    gx, gy = (PW - cell * N) / 2, MARGIN + 250
    _draw_grid(d, g, place, gx, gy, cell, 82, False)
    d.rounded_rectangle([gx - 26, gy - 26, gx + cell * N + 26, gy + cell * N + 26], 36, outline=90, width=7)
    ly = gy + cell * N + 95
    cols, colw = 3, (PW - 2 * MARGIN) / 3
    for i, (w, k) in enumerate(theme["words"]):
        x = MARGIN + 40 + (i % cols) * colw
        y = ly + (i // cols) * 128
        d.rectangle([x, y + 12, x + 34, y + 46], outline=INK, width=4)     # 찾으면 체크하는 칸
        d.text((x + 58, y), w, font=font(F_BOLD, 54), fill=INK)
        d.text((x + 58, y + 64), k, font=font(F_REG, 44), fill=GRAY)
    return im


def solutions_page(start_no, items):
    im = page()
    d = ImageDraw.Draw(im)
    ctext(d, (PW / 2, MARGIN + 50), "Solutions", font(F_SERIF, 100))
    cell = 62
    box = cell * N
    gapx = (PW - 2 * MARGIN - 2 * box) / 1
    for i, (theme, g, place) in enumerate(items):
        x = MARGIN + (i % 2) * (box + gapx)
        y = MARGIN + 200 + (i // 2) * (box + 170)
        ctext(d, (x + box / 2, y - 50), f"{start_no + i}. {theme['title']}", font(F_BOLD, 46))
        _draw_grid(d, g, place, x, y, cell, 40, True)
        d.rectangle([x - 8, y - 8, x + box + 8, y + box + 8], outline=120, width=4)
    return im


def text_page(lines, top=None):
    """lines: (글, 글꼴, 크기, 색) 목록. 가운데 정렬로 차례로 씀."""
    im = page()
    d = ImageDraw.Draw(im)
    y = top or MARGIN + 300
    for s, f, px, col, gap in lines:
        if s:
            ctext(d, (PW / 2, y), s, font(f, px), col)
        y += gap
    return im


def build_wordsearch(spec: dict, seed: int):
    themes = spec["themes"]
    grids = [build_grid([w for w, _ in t["words"]], seed * 1000 + i) for i, t in enumerate(themes)]
    pages = []
    pages.append(text_page([
        (spec["title"], F_SERIF, 150, INK, 190), ("LARGE PRINT", F_BOLD, 64, 90, 140),
        (spec["cover_korean"], F_MJ, 76, GRAY, 260), (BRAND, F_BOLD, 52, GRAY, 0)], top=MARGIN + 700))
    pages.append(text_page([
        (f"{spec['title']} — {BRAND}", F_REG, 44, INK, 80), ("Copyright © 2026 " + BRAND + ". All rights reserved.", F_REG, 40, GRAY, 80),
        ("No part of this book may be reproduced without permission.", F_REG, 40, GRAY, 80),
        ("Puzzles were generated by computer and checked so every word appears exactly once.", F_REG, 40, GRAY, 80)],
        top=PH - MARGIN - 500))
    pages.append(text_page([
        ("How to Play", F_SERIF, 120, INK, 220),
        ("Find each word hidden in the grid.", F_REG, 58, INK, 95),
        ("Words run left to right, top to bottom, or diagonally.", F_REG, 58, INK, 95),
        ("No words are written backwards.", F_REG, 58, INK, 95),
        ("Tick the box next to each word when you find it.", F_REG, 58, INK, 220),
        ("Bonus: every word comes with its Korean spelling (Hangul).", F_BOLD, 54, 70, 95),
        ("Say it out loud and you are already speaking a little Korean!", F_REG, 52, GRAY, 0)]))
    for i, (t, (g, pl)) in enumerate(zip(themes, grids)):
        pages.append(puzzle_page(i + 1, t, g, pl))
    for s in range(0, len(themes), 4):
        items = [(themes[j], *grids[j]) for j in range(s, min(s + 4, len(themes)))]
        pages.append(solutions_page(s + 1, items))
    pages.append(text_page([
        ("Thank you!", F_SERIF, 130, INK, 200), ("감사합니다 · gamsahamnida", F_MJ, 64, GRAY, 200),
        ("If you enjoyed these puzzles, a short honest review on Amazon", F_REG, 52, INK, 85),
        ("helps a small publisher more than you might think.", F_REG, 52, INK, 0)]))
    if len(pages) % 2:
        pages.append(page())
    for n, im in enumerate(pages[3:], start=4):
        page_number(ImageDraw.Draw(im), n)
    sample = pages[3]
    words = sorted({w for t in themes for w, _ in t["words"]})
    return pages, sample, {"puzzles": len(themes), "words": len(words), "fingerprint": _fp(words)}


# =========================================================== 컬러링 (한국 문양)
def _split(rnd, x0, y0, x1, y1, depth, out, minsz):
    w, h = x1 - x0, y1 - y0
    if depth == 0 or (w < minsz and h < minsz) or (depth < 3 and rnd.random() < 0.18):
        out.append((x0, y0, x1, y1))
        return
    if w > h * 1.2 or (h <= w * 1.2 and rnd.random() < 0.5):
        t = x0 + w * rnd.uniform(0.35, 0.65)
        _split(rnd, x0, y0, t, y1, depth - 1, out, minsz)
        _split(rnd, t, y0, x1, y1, depth - 1, out, minsz)
    else:
        t = y0 + h * rnd.uniform(0.35, 0.65)
        _split(rnd, x0, y0, x1, t, depth - 1, out, minsz)
        _split(rnd, x0, t, x1, y1, depth - 1, out, minsz)


def _flower(d, cx, cy, r, lw, petals=5, rot=90, fill=None):
    center = fill if fill is not None else ("white" if d.im.mode == "RGB" else 255)
    for i in range(petals):
        a = math.radians(rot + i * 360 / petals)
        px, py = cx + math.cos(a) * r * 0.55, cy - math.sin(a) * r * 0.55
        d.ellipse([px - r * 0.48, py - r * 0.48, px + r * 0.48, py + r * 0.48], outline=INK, width=lw, fill=fill)
    d.ellipse([cx - r * 0.25, cy - r * 0.25, cx + r * 0.25, cy + r * 0.25], outline=INK, width=lw, fill=center)


def _motif(d, rect, kind, lw):
    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    r = min(x1 - x0, y1 - y0) * 0.32
    if r < 70:
        return
    if kind == "flower":
        _flower(d, cx, cy, r, lw)
    elif kind == "circle":
        for k in (1, 0.62, 0.28):
            d.ellipse([cx - r * k, cy - r * k, cx + r * k, cy + r * k], outline=INK, width=lw)
    elif kind == "diamond":
        for k in (1, 0.5):
            d.polygon([(cx, cy - r * k), (cx + r * k, cy), (cx, cy + r * k), (cx - r * k, cy)], outline=INK, width=lw)
    elif kind == "stripes":
        n = 3 if (y1 - y0) < 500 else 5
        for i in range(1, n + 1):
            yy = y0 + (y1 - y0) * i / (n + 1)
            d.line([(x0 + 40, yy), (x1 - 40, yy)], fill=INK, width=lw)
    elif kind == "cloud":   # 구름무늬 (간단한 소용돌이)
        for k in (1, 0.66, 0.33):
            d.arc([cx - r * k, cy - r * k, cx + r * k, cy + r * k], 180, 450 - 60 * k, fill=INK, width=lw)


def draw_jogakbo(rnd, w, h, lw=14, colored=False):
    im = Image.new("RGB" if colored else "L", (w, h), "white" if colored else 255)
    d = ImageDraw.Draw(im)
    rects = []
    _split(rnd, 0, 0, w, h, rnd.choice([5, 6]), rects, rnd.choice([420, 520, 620]))
    pal = [MINT, APRICOT, (250, 226, 160), (203, 226, 240), (240, 200, 210), (232, 236, 214), CREAM]
    for rc in rects:
        d.rectangle(rc, fill=rnd.choice(pal) if colored else None, outline=INK_RGB if colored else INK, width=lw)
        x0, y0, x1, y1 = rc
        if min(x1 - x0, y1 - y0) > 600:
            d.rectangle([x0 + 60, y0 + 60, x1 - 60, y1 - 60], outline=INK_RGB if colored else INK, width=lw - 5)
        _motif(d, rc, rnd.choice(["flower", "circle", "diamond", "stripes", "cloud", "flower"]), lw - 4)
    d.rectangle([0, 0, w - 1, h - 1], outline=INK_RGB if colored else INK, width=lw + 6)
    return im


def draw_rosette(rnd, w, h, lw=12):
    """단청 꽃무늬 느낌의 둥근 문양. 바깥 고리부터 안쪽으로 겹겹이 (안쪽이 위를 덮어 선이 깔끔함)."""
    im = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(im)
    cx, cy = w / 2, h / 2
    r = min(w, h) / 2 - 30
    k = 0
    while r > min(w, h) * 0.09:
        n = rnd.choice([8, 10, 12, 16]) if k else rnd.choice([12, 16, 20])
        pr = min(r * 0.24, r * math.sin(math.pi / n) * 1.05)
        if pr < 55:          # 너무 작은 고리는 색칠하기 어려우니 그만
            break
        rot = rnd.uniform(0, 360 / n)
        shape = rnd.choice(["round", "leaf", "round"])
        for j in range(n):
            a = math.radians(rot + j * 360 / n)
            px, py = cx + math.cos(a) * (r - pr), cy + math.sin(a) * (r - pr)
            if shape == "round":
                d.ellipse([px - pr, py - pr, px + pr, py + pr], outline=INK, width=lw, fill=255)
                d.ellipse([px - pr * 0.4, py - pr * 0.4, px + pr * 0.4, py + pr * 0.4], outline=INK, width=lw - 4)
            else:
                tip = (cx + math.cos(a) * r, cy + math.sin(a) * r)
                base = r - 2.2 * pr
                l = (cx + math.cos(a - math.pi / n) * base, cy + math.sin(a - math.pi / n) * base)
                rr = (cx + math.cos(a + math.pi / n) * base, cy + math.sin(a + math.pi / n) * base)
                d.polygon([tip, l, rr], outline=INK, width=lw, fill=255)
        r = r - 2 * pr * 0.92
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=INK, width=lw, fill=255)
        r -= lw * 2.5
        k += 1
    _flower(d, cx, cy, r * 0.95, lw, petals=rnd.choice([5, 6, 8]))
    for qx, qy in ((0.09, 0.07), (0.91, 0.07), (0.09, 0.93), (0.91, 0.93)):
        _flower(d, w * qx, h * qy, min(w, h) * 0.07, lw - 2, petals=5)
    return im


def draw_lattice(rnd, w, h, lw=12):
    """꽃살문 격자 (문살 사이사이 꽃)."""
    im = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(im)
    n = rnd.choice([3, 4])
    s = w / n
    rows = int(h // s)
    oy = (h - rows * s) / 2
    for r in range(rows):
        for c in range(n):
            x0, y0 = c * s, oy + r * s
            d.rectangle([x0, y0, x0 + s, y0 + s], outline=INK, width=lw + 2)
            m = s * 0.08
            d.rectangle([x0 + m, y0 + m, x0 + s - m, y0 + s - m], outline=INK, width=lw - 4)
            for (ax, ay) in ((x0 + m, y0 + m), (x0 + s - m, y0 + m), (x0 + m, y0 + s - m), (x0 + s - m, y0 + s - m)):
                d.line([(ax, ay), (x0 + s / 2, y0 + s / 2)], fill=INK, width=lw - 4)
            _flower(d, x0 + s / 2, y0 + s / 2, s * 0.34, lw - 2, petals=rnd.choice([4, 5, 6, 8]),
                    rot=rnd.choice([90, 45]), fill=255)
    d.rectangle([0, oy, w - 1, oy + rows * s], outline=INK, width=lw + 4)
    return im


PATTERNS = {
    "jogakbo": ("Jogakbo · patchwork wrapping cloth", "조각보",
                "Korean families stitched leftover fabric into bright wrapping cloths."),
    "rosette": ("Dancheong Flower", "단청 꽃무늬",
                "Palaces and temples are painted with these colorful flower rings."),
    "lattice": ("Kkotsal Door · flower lattice", "꽃살문",
                "Temple doors are carved with flowers so light falls through in patterns."),
}


def coloring_art(kind, rnd):
    w, h = PW - 2 * MARGIN, PH - 2 * MARGIN - 330
    if kind == "jogakbo":
        return draw_jogakbo(rnd, w, h)
    if kind == "rosette":
        return draw_rosette(rnd, w, h)
    return draw_lattice(rnd, w, h)


def coloring_page(no, kind, rnd):
    im = page()
    art = coloring_art(kind, rnd)
    im.paste(art, (MARGIN, MARGIN))
    d = ImageDraw.Draw(im)
    en, ko, note = PATTERNS[kind]
    y = PH - MARGIN - 250
    ctext(d, (PW / 2, y), f"{no}. {en}", font(F_SERIF, 80))
    ctext(d, (PW / 2, y + 100), ko, font(F_MJ, 58), GRAY)
    ctext(d, (PW / 2, y + 185), note, font(F_REG, 44), GRAY)
    return im, art


def build_coloring(spec: dict, seed: int):
    rnd = random.Random(seed)
    kinds = spec.get("patterns", ["jogakbo", "rosette", "lattice"])
    pages = []
    pages.append(text_page([
        (spec["title"], F_SERIF, 140, INK, 180), ("BOLD & EASY", F_BOLD, 64, 90, 140),
        (spec["cover_korean"], F_MJ, 76, GRAY, 260), (BRAND, F_BOLD, 52, GRAY, 0)], top=MARGIN + 700))
    pages.append(text_page([
        (f"{spec['title']} — {BRAND}", F_REG, 44, INK, 80),
        ("Copyright © 2026 " + BRAND + ". All rights reserved.", F_REG, 40, GRAY, 80),
        ("Patterns were drawn by computer code, inspired by traditional Korean design.", F_REG, 40, GRAY, 80),
        ("Each design is printed on one side so markers will not ruin the next page.", F_REG, 40, GRAY, 80)],
        top=PH - MARGIN - 500))
    test = text_page([("Color Test Page", F_SERIF, 110, INK, 160),
                      ("Try your pens, pencils and markers here first.", F_REG, 54, GRAY, 0)], top=MARGIN + 120)
    td = ImageDraw.Draw(test)
    for i in range(20):
        x = MARGIN + 60 + (i % 5) * 420
        y = MARGIN + 450 + (i // 5) * 520
        td.ellipse([x, y, x + 330, y + 330], outline=INK, width=10)
    pages += [test, page()]
    sample_art = None
    fps = []
    for i in range(spec["designs"]):
        kind = kinds[i % len(kinds)]
        im, art = coloring_page(i + 1, kind, rnd)
        if sample_art is None and kind == "jogakbo":
            sample_art = im
        fps.append(hashlib.sha1(art.resize((64, 64)).tobytes()).hexdigest()[:12])
        pages += [im, page()]       # 뒷면은 비움 (번짐 방지)
    pages.append(text_page([
        ("Thank you!", F_SERIF, 130, INK, 200), ("감사합니다 · gamsahamnida", F_MJ, 64, GRAY, 200),
        ("If you enjoyed coloring these patterns, a short honest review on Amazon", F_REG, 50, INK, 85),
        ("helps a small publisher more than you might think.", F_REG, 50, INK, 0)]))
    if len(pages) % 2:
        pages.append(page())
    return pages, sample_art, {"designs": spec["designs"], "fingerprint": _fp(fps)}


# =========================================================== 표지
def spine_in(pages: int) -> float:
    return pages * PAPER_IN_PER_PAGE


def build_cover(spec: dict, kind: str, pages: int, seed: int, back_sample: Image.Image):
    """감싸는 표지 한 장 (RGB, 300dpi). 바코드 자리(뒤표지 오른쪽 아래 2x1.2인치)는 비워 둠."""
    sp = spine_in(pages)
    W = int((BLEED * 2 + TRIM_W * 2 + sp) * DPI)
    H = int((BLEED * 2 + TRIM_H) * DPI)
    b, s = int(BLEED * DPI), int(sp * DPI)
    fx = b + PW + s                      # 앞표지 시작 x
    im = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(im)
    rnd = random.Random(seed + 7)
    if kind == "coloring":
        art = draw_jogakbo(rnd, PW + b + 4, H, lw=16, colored=True)
        im.paste(art, (fx - 2, 0))
        box = [fx + 260, 760, fx + PW - 260, 1950]
    else:
        f = font(F_BOLD, 120)
        letters = "".join(w for t in spec["themes"] for w, _ in t["words"])
        cell = 205
        for r in range(H // cell + 1):
            for c in range(PW // cell + 1):
                ch = letters[(r * 13 + c * 7) % len(letters)]
                ctext(d, (fx + c * cell + 100, r * cell + 100), ch, f, (226, 220, 206))
        for (r, c, word, col) in ((2, 1, "KIMCHI", APRICOT), (12, 3, "HANGUL", MINT)):
            for i, ch in enumerate(word):
                x, y = fx + (c + i) * cell + 100, r * cell + 100
                d.ellipse([x - 88, y - 88, x + 88, y + 88], fill=col)
                ctext(d, (x, y), ch, f, "white")
        box = [fx + 230, 760, fx + PW - 230, 2050]
    d.rounded_rectangle(box, 90, fill="white", outline=MINT if kind != "coloring" else INK_RGB, width=14)
    cx = (box[0] + box[2]) / 2
    top = box[1]
    ctext(d, (cx, top + 170), "LARGE PRINT" if kind == "wordsearch" else "BOLD & EASY", font(F_BOLD, 96), (200, 120, 80))
    title = spec["title"].split(" ")
    if kind == "wordsearch":
        ctext(d, (cx, top + 410), " ".join(title[:-2]) or spec["title"], font(F_SERIF, 270), INK_RGB)
        ctext(d, (cx, top + 680), " ".join(title[-2:]), font(F_SERIF, 210), (60, 120, 100))
    else:
        ctext(d, (cx, top + 400), " ".join(title[:2]), font(F_SERIF, 230), INK_RGB)
        ctext(d, (cx, top + 650), " ".join(title[2:]), font(F_SERIF, 200), (60, 120, 100))
    ctext(d, (cx, top + 880), spec["cover_line"], font(F_REG, 78), (90, 90, 90))
    ctext(d, (cx, top + 1030), spec["cover_korean"], font(F_MJ, 84), (130, 130, 130))
    d.rounded_rectangle([cx - 560, H - b - 320, cx + 560, H - b - 150], 40, fill="white")
    ctext(d, (cx, H - b - 235), f"{BRAND.upper()} · {BRAND_KO}", font(F_BOLD, 74), (110, 110, 110))
    # 책등 (100쪽 이상일 때만 글씨)
    d.rectangle([b + PW, 0, fx, H], fill=MINT)
    if pages >= 100:
        sp_img = Image.new("RGB", (H - 2 * b - 400, max(s - 40, 10)), MINT)
        sd = ImageDraw.Draw(sp_img)
        ctext(sd, (sp_img.width / 2, sp_img.height / 2), f"{spec['title']}  ·  {BRAND}",
              font(F_BOLD, int(min(70, s * 0.5))), "white")
        im.paste(sp_img.rotate(-90, expand=True), (b + PW + 20, b + 200))
    # 뒤표지
    bx0 = b
    ctext(d, (bx0 + PW / 2, b + 420), spec["back_title"], font(F_SERIF, 150), INK_RGB)
    y = b + 640
    for line in spec["back_lines"]:
        ctext(d, (bx0 + PW / 2, y), line, font(F_REG, 66), (70, 70, 70))
        y += 110
    if back_sample is not None:
        th = back_sample.convert("RGB").resize((int(PW * 0.42), int(PH * 0.42)))
        tx, ty = int(bx0 + PW / 2 - th.width / 2), y + 60
        d.rectangle([tx - 12, ty - 12, tx + th.width + 12, ty + th.height + 12], fill=(220, 214, 200))
        im.paste(th, (tx, ty))
    # 바코드 자리 표시 없이 비워 두기만 함 (KDP가 흰 상자를 넣음)
    return im, {"width_in": round(W / DPI, 3), "height_in": round(H / DPI, 3), "spine_in": round(sp, 4)}


# =========================================================== 저장 · 검사
def _fp(items) -> str:
    return hashlib.sha1("|".join(items).encode()).hexdigest()[:16]


def save_pdf(pages: list[Image.Image], path: Path):
    first, rest = pages[0], pages[1:]
    first.save(path, "PDF", resolution=DPI, save_all=True, append_images=rest)


def check_book(pages, cover_img, cover_info, kind) -> list[tuple[bool, str]]:
    n = len(pages)
    ok_size = all(p.size == (PW, PH) for p in pages)
    exp_w = round(BLEED * 2 + TRIM_W * 2 + spine_in(n), 3)
    return [
        (ok_size, "속지 8.5x11"),
        (24 <= n <= 828 and n % 2 == 0, f"{n}쪽"),
        (abs(cover_info["width_in"] - exp_w) < 0.01 and abs(cover_info["height_in"] - 11.25) < 0.01, "표지 크기"),
        (MARGIN >= 0.375 * DPI, "여백"),
    ]


def preview(cover_img, samples, out: Path):
    W, H = cover_img.size
    b = int(BLEED * DPI)
    front = cover_img.crop((W - b - PW, b, W - b, b + PH))
    tiles = [front] + [s.convert("RGB") for s in samples if s is not None]
    tw, th = 700, int(700 * PH / PW)
    sheet = Image.new("RGB", (len(tiles) * (tw + 30) + 30, th + 60), (236, 236, 236))
    for i, t in enumerate(tiles):
        sheet.paste(t.resize((tw, th)), (30 + i * (tw + 30), 30))
    sheet.save(out)


def listing(spec: dict, kind: str, pages: int) -> dict:
    ai = ("AI 질문: 'Did you use AI tools…?' → Yes. 글(Text): 'AI-generated' 를 고르고 도구 이름에 'Claude' "
          "(낱말 목록·문구를 AI가 함께 만듦). 그림(Images): 'None' (코드로 그린 격자·무늬). 번역: None.")
    if kind == "coloring":
        ai = ("AI 질문: 'Did you use AI tools…?' → Yes. 글(Text): 'AI-generated', 도구 이름 'Claude' "
              "(설명 문구). 그림(Images): 'None' (AI 그림 도구가 아니라 코드로 그린 무늬). 번역: None.")
    # 8.5x11은 KDP '큰 판형'(large trim). 흑백 24~108쪽은 정액, 그 이상은 쪽당 (2025년 KDP 표 기준, 추정치)
    printing = 2.84 if pages <= 108 else round(1.00 + 0.017 * pages, 2)
    return {
        "title": spec["title"],
        "subtitle": spec["subtitle"],
        "series": spec["series"],
        "author": BRAND,
        "description": spec["description"],
        "keywords": spec["keywords"],
        "categories": spec["categories"],
        "trim": "8.5 x 11 in · Black & white interior · White paper · No bleed · Matte cover",
        "pages": pages,
        "price_usd": spec["price"],
        "royalty_estimate_usd": round(spec["price"] * 0.6 - printing, 2),
        "ai_answer": ai,
        "low_content": "No (ISBN: Get a free KDP ISBN)",
        "adult_content": "No",
        "expanded_distribution": "Off",
    }


def make_book(spec: dict, out: Path, seed: int | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    seed = seed if seed is not None else int(hashlib.sha1(spec["id"].encode()).hexdigest()[:6], 16)
    kind = spec["kind"]
    if kind == "wordsearch":
        pages, sample, info = build_wordsearch(spec, seed)
        samples = [pages[3], pages[-3] if len(pages) > 6 else None]
    else:
        pages, sample, info = build_coloring(spec, seed)
        samples = [pages[4], pages[6]]
    cover_img, cinfo = build_cover(spec, kind, len(pages), seed, sample)
    checks = check_book(pages, cover_img, cinfo, kind)
    save_pdf(pages, out / "interior.pdf")
    cover_img.save(out / "cover.pdf", "PDF", resolution=DPI)
    preview(cover_img, samples, out / "preview.png")
    lst = listing(spec, kind, len(pages))
    (out / "listing.json").write_text(json.dumps(lst, ensure_ascii=False, indent=1))
    return {"id": spec["id"], "kind": kind, "seed": seed, "pages": len(pages), "cover": cinfo,
            "checks": checks, **info}
