# -*- coding: utf-8 -*-
"""生成 PWA / iOS 主屏幕图标。

设计语言跟页面 logo 保持一致：深底 + 蓝色同心圆（实况 = 光圈）。
不自己加圆角，iOS 会自动裁。
"""
import os
import sys
import sysconfig

sys.path.append(sysconfig.get_path("purelib"))

from PIL import Image, ImageDraw

BG = (13, 15, 19)
ACCENT = (76, 141, 255)
ACCENT_DIM = (46, 88, 168)

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "static", "icons")


def draw(size, ss=4):
    n = size * ss
    im = Image.new("RGB", (n, n), BG)
    d = ImageDraw.Draw(im)

    c = n / 2.0
    ring = n * 0.335
    ring_w = max(int(n * 0.028), ss * 2)

    # 外圈细环
    d.ellipse([c - ring, c - ring, c + ring, c + ring],
              outline=ACCENT_DIM, width=ring_w)

    # 主环
    r2 = n * 0.245
    d.ellipse([c - r2, c - r2, c + r2, c + r2],
              outline=ACCENT, width=max(int(n * 0.042), ss * 2))

    # 中心实点
    r3 = n * 0.083
    d.ellipse([c - r3, c - r3, c + r3, c + r3], fill=ACCENT)

    # 四向刻度（呼应 logo 的十字）
    tick = n * 0.052
    tw = max(int(n * 0.018), ss * 2)
    for (dx, dy) in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        x0 = c + dx * (ring + tick * 0.9)
        y0 = c + dy * (ring + tick * 0.9)
        x1 = c + dx * (ring + tick * 1.9)
        y1 = c + dy * (ring + tick * 1.9)
        d.line([x0, y0, x1, y1], fill=ACCENT_DIM, width=tw)

    return im.resize((size, size), Image.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    targets = [
        ("icon-192.png", 192),
        ("icon-512.png", 512),
        ("apple-touch-icon.png", 180),
        ("favicon-64.png", 64),
        ("icon-ios-1024.png", 1024),
    ]
    for name, size in targets:
        im = draw(size)
        p = os.path.join(OUT, name)
        im.save(p, "PNG", optimize=True)
        print("%-24s %d bytes" % (name, os.path.getsize(p)))

    # 512 遮罩版（Android 自适应图标用，留 10% 安全边距）
    im = draw(512)
    safe = Image.new("RGB", (512, 512), BG)
    inner = im.resize((410, 410), Image.LANCZOS)
    safe.paste(inner, (51, 51))
    p = os.path.join(OUT, "icon-maskable-512.png")
    safe.save(p, "PNG", optimize=True)
    print("%-24s %d bytes" % ("icon-maskable-512.png", os.path.getsize(p)))


if __name__ == "__main__":
    main()
