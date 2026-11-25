# -*- coding: utf-8 -*-
"""端到端自检：拿一个真视频跑完整产出流程，逐个验证产物。

跑法： python -S e2e_test.py <视频路径>
"""

import io
import json
import os
import shutil
import struct
import subprocess
import sys
import sysconfig
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_sp = sysconfig.get_path("purelib")
if _sp not in sys.path:
    sys.path.append(_sp)

from PIL import Image

from livephoto import builder, exifutil, ffmpeg_util

FAIL = []


def check(name, cond, extra=""):
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else "  " + str(extra)))
    if not cond:
        FAIL.append(name)


def main(src):
    print("ffmpeg:", ffmpeg_util.version())
    info = ffmpeg_util.probe(src)
    print("源视频:", json.dumps(info, ensure_ascii=False))
    check("探测出时长", info["duration"] > 1, info["duration"])
    check("探测出宽高", info["width"] > 0 and info["height"] > 0)

    work = tempfile.mkdtemp(prefix="lp_e2e_")
    out = tempfile.mkdtemp(prefix="lp_out_")

    params = {
        "start": 2.0,
        "duration": 3.0,
        "cover": 3.2,
        "formats": ["motion", "ios", "gif", "mp4", "still"],
        "max_edge": 1440,
        "crf": 20,
    }

    print("\n== 生成 ==")
    items = builder.build_all(src, params, work, out)
    for it in items:
        print("  %-6s %-42s %8.2f KB" % (it["kind"], it["name"], it["size"] / 1024.0))
    check("产出 5 个文件", len(items) == 5, len(items))

    by_kind = {i["kind"]: i for i in items}

    # ---------------- Motion Photo ----------------
    print("\n== Motion Photo ==")
    p = by_kind["motion"]["path"]
    with open(p, "rb") as f:
        blob = f.read()
    check("文件存在且非空", len(blob) > 10000, len(blob))
    check("头是 JPEG SOI", blob[:2] == b"\xff\xd8")
    check("含 MicroVideo 标记", b'GCamera:MicroVideo="1"' in blob[:200000])
    check("含 MotionPhoto 语义", b'Semantic="MotionPhoto"' in blob[:200000])

    # 从 XMP 里抠 offset，切出视频喂 ffprobe，验证真的能播
    idx = blob.find(b"MicroVideoOffset=\"")
    off_len = 0
    if idx > 0:
        s = idx + len(b"MicroVideoOffset=\"")
        e = blob.find(b'"', s)
        off_len = int(blob[s:e])
    check("解析出视频长度", off_len > 1000, off_len)

    video_part = blob[len(blob) - off_len:]
    check("尾部是 ftyp 盒", video_part[4:8] == b"ftyp", video_part[:12])

    tmp_mp4 = os.path.join(work, "_verify.mp4")
    with open(tmp_mp4, "wb") as f:
        f.write(video_part)
    try:
        vi = ffmpeg_util.probe(tmp_mp4)
        check("内嵌视频可被 ffprobe 解析", vi["duration"] > 1, vi)
        check("内嵌视频时长≈3s", abs(vi["duration"] - 3.0) < 0.6, vi["duration"])
        check("内嵌视频有音轨", vi["has_audio"])
    except Exception as exc:
        check("内嵌视频可被 ffprobe 解析", False, exc)

    try:
        im = Image.open(io.BytesIO(blob))
        im.load()
        check("JPEG 主图仍可解码", True)
        check("主图尺寸被限制到 1440 内", max(im.size) <= 1440, im.size)
    except Exception as exc:
        check("JPEG 主图仍可解码", False, exc)

    # ---------------- iOS 配对包 ----------------
    print("\n== iOS Live Photo ==")
    item = by_kind["ios"]
    zp = item["path"]
    check("主产物后缀是 .livp", zp.lower().endswith(".livp"), zp)
    with zipfile.ZipFile(zp) as z:
        names = z.namelist()
        check("包里有 2 个文件", len(names) == 2, names)
        check("条目在根目录（无子文件夹）",
              all("/" not in n and "\\" not in n for n in names), names)
        jpg_name = [n for n in names if n.upper().endswith(".JPG")]
        mov_name = [n for n in names if n.upper().endswith(".MOV")]
        check("有 JPG", len(jpg_name) == 1, names)
        check("有 MOV", len(mov_name) == 1, names)
        check("同名（配对前提）",
              os.path.splitext(jpg_name[0])[0] == os.path.splitext(mov_name[0])[0],
              (jpg_name, mov_name))
        check("文件名是 IMG_ 开头（像原生的）",
              jpg_name[0].startswith("IMG_"), jpg_name[0])

        jpg_bytes = z.read(jpg_name[0])
        mov_bytes = z.read(mov_name[0])

    # 单独下载的两个文件也得在，且跟包里一致
    files = item.get("files") or []
    check("返回 3 个可下载文件", len(files) == 3, [f["name"] for f in files])
    for f in files:
        p = os.path.join(os.path.dirname(zp), f["name"])
        check("独立文件存在: " + f["name"], os.path.isfile(p), p)

    uuid_in_jpg = exifutil.read_makernote_uuid(jpg_bytes)
    check("JPG 里有 ContentIdentifier", bool(uuid_in_jpg), uuid_in_jpg)
    check("MOV 里有同一个 UUID", bool(uuid_in_jpg) and uuid_in_jpg.encode() in mov_bytes, uuid_in_jpg)
    check("页面报告校验通过", item.get("verified") is True, item.get("verified"))

    tmp_mov = os.path.join(work, "_verify.mov")
    with open(tmp_mov, "wb") as f:
        f.write(mov_bytes)
    try:
        mi = ffmpeg_util.probe(tmp_mov)
        check("MOV 可解析", mi["duration"] > 1, mi)
        check("MOV 时长≈3s", abs(mi["duration"] - 3.0) < 0.6, mi["duration"])
    except Exception as exc:
        check("MOV 可解析", False, exc)

    try:
        Image.open(io.BytesIO(jpg_bytes)).load()
        check("配对 JPG 可解码", True)
    except Exception as exc:
        check("配对 JPG 可解码", False, exc)

    # ---------------- GIF ----------------
    print("\n== GIF ==")
    try:
        g = Image.open(by_kind["gif"]["path"])
        frames = getattr(g, "n_frames", 1)
        check("GIF 多帧", frames > 5, frames)
        check("GIF 有循环标记", g.info.get("loop", None) == 0, g.info.get("loop"))
    except Exception as exc:
        check("GIF 多帧", False, exc)

    # ---------------- MP4 ----------------
    print("\n== MP4 片段 ==")
    try:
        m = ffmpeg_util.probe(by_kind["mp4"]["path"])
        check("MP4 时长≈3s", abs(m["duration"] - 3.0) < 0.6, m["duration"])
        check("MP4 是 h264", m["codec"] == "h264", m["codec"])
    except Exception as exc:
        check("MP4 时长≈3s", False, exc)

    # ---------------- 边缘情况 ----------------
    print("\n== 边缘情况 ==")
    short = builder.build_all(src, {"start": 8.5, "duration": 5, "cover": 9.0,
                                    "formats": ["motion"]}, work, out)
    check("起点靠近尾部不崩", len(short) == 1)
    with open(short[0]["path"], "rb") as f:
        b2 = f.read()
    idx = b2.find(b"MicroVideoOffset=\"")
    s = idx + len(b"MicroVideoOffset=\"")
    ln = int(b2[s:b2.find(b'"', s)])
    vp = b2[len(b2) - ln:]
    check("截断后视频仍完整", vp[4:8] == b"ftyp", vp[:12])

    shutil.rmtree(work, ignore_errors=True)
    shutil.rmtree(out, ignore_errors=True)

    print("")
    if FAIL:
        print("失败 %d 项：%s" % (len(FAIL), "、".join(FAIL)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python -S e2e_test.py <视频路径>")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
