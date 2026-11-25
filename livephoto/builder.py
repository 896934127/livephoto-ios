# -*- coding: utf-8 -*-
"""把「一段视频 + 一张封面帧」加工成各种实况图产物。"""

import os
import shutil
import time
import uuid as uuidlib
import zipfile

from . import exifutil, ffmpeg_util


def _fmt(name, ext):
    return "%s.%s" % (name, ext)


def _stamp():
    return time.strftime("%Y%m%d_%H%M%S")


def build_motion_photo(src, start, duration, cover, workdir, outpath, max_edge, crf):
    """单文件实况图：JPEG 末尾内嵌 MP4，靠 XMP 告诉相册视频在哪。

    兼容 Google 相册、小米/OPPO/vivo 相册、部分图库。
    """
    mp4 = os.path.join(workdir, "_clip.mp4")
    ffmpeg_util.clip(src, start, duration, mp4, max_edge=max_edge, crf=crf)
    video_len = os.path.getsize(mp4)

    jpg = os.path.join(workdir, "_cover.jpg")
    size = ffmpeg_util.extract_frame(src, cover, jpg, max_edge=max_edge)

    with open(jpg, "rb") as f:
        raw = f.read()
    raw = exifutil.strip_app_segments(raw)

    ts_us = int(max(cover - start, 0) * 1_000_000)
    dt = time.strftime("%Y:%m:%d %H:%M:%S")
    ident = str(uuidlib.uuid4()).upper()

    exif_seg = exifutil.build_exif_segment(
        size[0] if size else 0, size[1] if size else 0, ident, dt)
    xmp_seg = exifutil.build_xmp_segment(video_len, ts_us)

    with open(mp4, "rb") as f:
        video = f.read()

    body = exifutil.inject_segments(raw, [exif_seg, xmp_seg])
    with open(outpath, "wb") as f:
        f.write(body)
        f.write(video)

    return {
        "path": outpath,
        "video_len": video_len,
        "cover": size,
        "uuid": ident,
    }


def build_ios_live(src, start, duration, cover, workdir, outdir, basename,
                   max_edge, crf):
    """iOS 实况照片：同名 JPG + MOV，两边都写同一个 ContentIdentifier。

    产出三份：
      IMG_xxx.livp   —— 苹果官方的实况照片打包格式（本质是 zip 改后缀），
                        手机上打开可以直接「存储到照片」
      IMG_xxx.JPG    —— 独立主图
      IMG_xxx.MOV    —— 独立视频
    后两个是给爱思助手 / 照片 App / 第三方合成工具用的，
    那些工具要的是两个独立文件，不是压缩包。
    """
    tmp_mp4 = os.path.join(workdir, "_ios.mp4")
    ffmpeg_util.clip(src, start, duration, tmp_mp4, max_edge=max_edge, crf=crf)

    ident = str(uuidlib.uuid4()).upper()
    mov = os.path.join(outdir, basename + ".MOV")
    ffmpeg_util.write_mov_metadata(tmp_mp4, mov, ident)

    ok = ffmpeg_util.has_metadata_string(mov, ident)

    jpg = os.path.join(outdir, basename + ".JPG")
    size = ffmpeg_util.extract_frame(src, cover, jpg, max_edge=max_edge)

    with open(jpg, "rb") as f:
        raw = f.read()
    raw = exifutil.strip_app_segments(raw)
    dt = time.strftime("%Y:%m:%d %H:%M:%S")
    exif_seg = exifutil.build_exif_segment(
        size[0] if size else 0, size[1] if size else 0, ident, dt)
    jpg_bytes = exifutil.inject_segments(raw, [exif_seg])

    with open(jpg, "wb") as f:
        f.write(jpg_bytes)

    verified = exifutil.read_makernote_uuid(jpg_bytes) == ident

    # .livp = 一个只装两件东西的 zip，条目在根目录、同名不同扩展名
    livp = os.path.join(outdir, basename + ".livp")
    with zipfile.ZipFile(livp, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(jpg, basename + ".JPG")
        z.write(mov, basename + ".MOV")

    return {
        "path": livp,
        "uuid": ident,
        "jpg": jpg,
        "mov": mov,
        "livp": livp,
        "mov_meta_ok": ok,
        "jpg_meta_ok": verified,
        "cover": size,
    }


def build_all(src, params, workdir, outdir):
    """按前端勾选的格式批量产出。返回成果列表。"""
    start = float(params.get("start", 0))
    duration = float(params.get("duration", 3))
    cover = float(params.get("cover", start + duration / 2.0))
    formats = params.get("formats") or ["motion"]
    max_edge = int(params.get("max_edge", 1440))
    crf = int(params.get("crf", 20))

    basename = "live_" + _stamp() + "_" + uuidlib.uuid4().hex[:6]
    results = []

    if "motion" in formats:
        p = os.path.join(outdir, _fmt(basename, "jpg"))
        info = build_motion_photo(src, start, duration, cover, workdir, p,
                                  max_edge, crf)
        results.append({
            "kind": "motion",
            "path": p,
            "name": os.path.basename(p),
            "label": "实况图（单文件 Motion Photo）",
            "hint": "JPEG 内嵌视频，安卓相册 / Google 相册可直接识别",
            "size": os.path.getsize(p),
            "uuid": info["uuid"],
        })

    if "ios" in formats:
        ios_name = "IMG_" + _stamp() + "_" + uuidlib.uuid4().hex[:4]
        info = build_ios_live(src, start, duration, cover, workdir, outdir,
                              ios_name, max_edge, crf)
        files = [
            {
                "name": os.path.basename(info["livp"]),
                "size": os.path.getsize(info["livp"]),
                "tag": "推荐",
                "note": "苹果官方打包格式，手机上打开直接存进相册",
            },
            {
                "name": os.path.basename(info["jpg"]),
                "size": os.path.getsize(info["jpg"]),
                "tag": "图片",
                "note": "配对用的主图，单下没用，要和 MOV 一起",
            },
            {
                "name": os.path.basename(info["mov"]),
                "size": os.path.getsize(info["mov"]),
                "tag": "视频",
                "note": "配对用的视频，数据线导入时两个都要",
            },
        ]
        results.append({
            "kind": "ios",
            "path": info["livp"],
            "name": os.path.basename(info["livp"]),
            "label": "iOS 实况照片",
            "hint": "苹果底层就是「图 + 视频」两个文件配对，.livp 把俩装一块",
            "size": os.path.getsize(info["livp"]),
            "uuid": info["uuid"],
            "verified": bool(info["mov_meta_ok"] and info["jpg_meta_ok"]),
            "files": files,
        })

    if "gif" in formats:
        p = os.path.join(outdir, _fmt(basename, "gif"))
        ffmpeg_util.make_gif(src, start, duration, p,
                             width=int(params.get("gif_width", 480)),
                             fps=int(params.get("gif_fps", 12)))
        results.append({
            "kind": "gif",
            "path": p,
            "name": os.path.basename(p),
            "label": "动图 GIF",
            "hint": "通用格式，微信 / 网页都能直接发",
            "size": os.path.getsize(p),
        })

    if "mp4" in formats:
        p = os.path.join(outdir, _fmt(basename, "mp4"))
        ffmpeg_util.clip(src, start, duration, p, max_edge=max_edge, crf=crf)
        results.append({
            "kind": "mp4",
            "path": p,
            "name": os.path.basename(p),
            "label": "视频片段 MP4",
            "hint": "H.264 无声/有声均可，留着发短视频平台",
            "size": os.path.getsize(p),
        })

    if "still" in formats:
        p = os.path.join(outdir, basename + "_still.jpg")
        ffmpeg_util.extract_frame(src, cover, p, max_edge=max_edge)
        results.append({
            "kind": "still",
            "path": p,
            "name": os.path.basename(p),
            "label": "封面静帧 JPG",
            "hint": "只要一张图的话拿这个",
            "size": os.path.getsize(p),
        })

    return results
