# -*- coding: utf-8 -*-
"""把 tools 下的 .gz 解成 ffmpeg.exe / ffprobe.exe，只跑一次。"""

import gzip
import os
import shutil
import sys

TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools")
BIN = os.path.join(TOOLS, "ffmpeg", "bin")
os.makedirs(BIN, exist_ok=True)

PAIRS = [
    ("ffmpeg-win64.gz", "ffmpeg.exe"),
    ("ffprobe-win64.gz", "ffprobe.exe"),
]

for src_name, dst_name in PAIRS:
    src = os.path.join(TOOLS, src_name)
    dst = os.path.join(BIN, dst_name)
    if not os.path.isfile(src):
        print("skip, missing:", src_name)
        continue
    if os.path.isfile(dst) and os.path.getsize(dst) > 1024:
        print("already:", dst_name)
        continue
    with gzip.open(src, "rb") as f, open(dst, "wb") as o:
        shutil.copyfileobj(f, o)
    print("extracted:", dst_name, os.path.getsize(dst))

# 顺手清掉下载的 zip 残骸
for junk in ("ffmpeg.zip",):
    p = os.path.join(TOOLS, junk)
    if os.path.isfile(p):
        try:
            os.remove(p)
        except OSError:
            pass
print("done")
