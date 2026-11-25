# -*- coding: utf-8 -*-
"""ffmpeg 定位与封装。所有视频处理都走这里，别在业务层直接拼命令。"""

import json
import os
import shutil
import struct
import subprocess

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_DIR = os.path.join(BASE_DIR, "tools")

_CREATE_NO_WINDOW = 0x08000000
_cache = {}

FFMPEG = None
FFPROBE = None


def _walk_find(root, filename, depth=0):
    if depth > 4 or not os.path.isdir(root):
        return None
    direct = os.path.join(root, filename)
    if os.path.isfile(direct):
        return direct
    try:
        for name in os.listdir(root):
            p = os.path.join(root, name)
            if os.path.isdir(p):
                found = _walk_find(p, filename, depth + 1)
                if found:
                    return found
    except OSError:
        pass
    return None


def _locate():
    """按 环境变量 → 项目 tools → PATH 的顺序找 ffmpeg。"""
    global FFMPEG, FFPROBE
    if FFMPEG:
        return FFMPEG, FFPROBE

    candidates = []
    env = os.environ.get("FFMPEG_PATH")
    if env and os.path.isfile(env):
        candidates.append(env)

    found = _walk_find(TOOLS_DIR, "ffmpeg.exe")
    if found:
        candidates.append(found)

    which = shutil.which("ffmpeg")
    if which:
        candidates.append(which)

    for c in candidates:
        if c and os.path.isfile(c):
            FFMPEG = c
            probe = os.path.join(os.path.dirname(c), "ffprobe.exe")
            FFPROBE = probe if os.path.isfile(probe) else None
            break

    if not FFMPEG:
        raise RuntimeError("找不到 ffmpeg，请把 ffmpeg.exe 放到 tools 目录，或设置 FFMPEG_PATH")
    return FFMPEG, FFPROBE


def available():
    try:
        _locate()
        return True
    except RuntimeError:
        return False


def run(args, timeout=300):
    _locate()
    cmd = [FFMPEG] + args
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        creationflags=_CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace")[-1500:]
        raise RuntimeError("ffmpeg 失败: %s" % tail)
    return proc.stdout


def version():
    if "v" in _cache:
        return _cache["v"]
    _locate()
    out = subprocess.run(
        [FFMPEG, "-version"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
        creationflags=_CREATE_NO_WINDOW if os.name == "nt" else 0,
    ).stdout.decode("utf-8", "replace")
    line = out.splitlines()[0] if out else "unknown"
    _cache["v"] = line.strip()
    return _cache["v"]


# --------------------------------------------------------------------------
# 探测
# --------------------------------------------------------------------------

def probe(path):
    _locate()
    if not FFPROBE:
        raise RuntimeError("缺少 ffprobe.exe")
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
        creationflags=_CREATE_NO_WINDOW if os.name == "nt" else 0,
    ).stdout.decode("utf-8", "replace")
    data = json.loads(out)

    vs = None
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            vs = s
            break
    if not vs:
        raise RuntimeError("这个文件里没有视频轨道")

    w = int(vs.get("width") or 0)
    h = int(vs.get("height") or 0)

    # 手机竖屏视频靠 rotation 标记，ffmpeg 解码时自动转正，这里同步交换宽高
    rot = 0
    for sd in vs.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    if rot == 0 and vs.get("tags", {}).get("rotate"):
        try:
            rot = int(vs["tags"]["rotate"])
        except ValueError:
            rot = 0
    if abs(rot) % 180 == 90:
        w, h = h, w

    fps = 0.0
    for key in ("avg_frame_rate", "r_frame_rate"):
        v = vs.get(key) or "0/0"
        try:
            num, den = v.split("/")
            if float(den) > 0:
                fps = float(num) / float(den)
                if fps > 0:
                    break
        except (ValueError, ZeroDivisionError):
            pass

    dur = 0.0
    try:
        dur = float(data.get("format", {}).get("duration") or vs.get("duration") or 0)
    except ValueError:
        dur = 0.0

    has_audio = any(s.get("codec_type") == "audio" for s in data.get("streams", []))

    return {
        "duration": dur,
        "width": w,
        "height": h,
        "fps": round(fps, 3),
        "rotation": rot,
        "has_audio": has_audio,
        "codec": vs.get("codec_name"),
    }


# --------------------------------------------------------------------------
# 工具函数
# --------------------------------------------------------------------------

def fit_size(src_w, src_h, max_edge):
    """等比缩放到长边不超过 max_edge，且宽高都是偶数（yuv420p 的硬要求）。"""
    if not src_w or not src_h:
        return None
    scale = min(1.0, float(max_edge) / float(max(src_w, src_h)))
    w = int(round(src_w * scale / 2.0)) * 2
    h = int(round(src_h * scale / 2.0)) * 2
    return max(w, 2), max(h, 2)


def make_filmstrip(src, out_png, count=12, height=88):
    """生成一条横向缩略图带，前端拿来做时间轴背景。"""
    info = probe(src)
    dur = max(info["duration"], 0.1)
    fps = max(count / dur, 0.02)
    w = int(round(info["width"] * height / max(info["height"], 1) / 2.0)) * 2
    w = max(w, 2)
    vf = "fps={:.6f},scale={}:{},tile={}x1".format(fps, w, height, count)
    run(["-y", "-ss", "0", "-i", src, "-vf", vf,
         "-frames:v", "1", "-update", "1", out_png], timeout=120)


def extract_frame(src, t, out_jpg, max_edge=1440, quality=2):
    info = probe(src)
    size = fit_size(info["width"], info["height"], max_edge)
    args = ["-y", "-ss", "%.3f" % max(t, 0), "-i", src, "-frames:v", "1"]
    if size:
        args += ["-vf", "scale={}:{}".format(*size)]
    args += ["-q:v", str(quality), out_jpg]
    run(args, timeout=120)
    return size


def clip(src, start, duration, out_path, max_edge=1440,
         with_audio=True, crf=20, preset="medium"):
    """切一段出来，重编码成 H.264，确保 iOS / 安卓都能播。"""
    info = probe(src)
    size = fit_size(info["width"], info["height"], max_edge)
    args = ["-y",
            "-ss", "%.3f" % max(start, 0),
            "-i", src,
            "-t", "%.3f" % max(duration, 0.1)]
    if size:
        args += ["-vf", "scale={}:{}".format(*size)]
    args += [
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-profile:v", "high",
        "-level", "4.0",
    ]
    if with_audio and info["has_audio"]:
        args += ["-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2"]
    else:
        args += ["-an"]
    args += ["-movflags", "+faststart", "-f", "mp4", out_path]
    run(args, timeout=600)
    return size


def make_gif(src, start, duration, out_path, width=480, fps=12):
    vf = (
        "fps={fps},scale={w}:-2:flags=lanczos,split[a][b];"
        "[a]palettegen=stats_mode=diff[p];"
        "[b][p]paletteuse=dither=bayer:bayer_scale=5"
    ).format(fps=fps, w=width)
    run(["-y", "-ss", "%.3f" % max(start, 0), "-i", src,
         "-t", "%.3f" % max(duration, 0.1),
         "-vf", vf, "-loop", "0", out_path], timeout=300)


def write_mov_metadata(src_mp4, out_mov, identifier):
    """把 mp4 转成 mov 并塞进 iOS 的 ContentIdentifier（Live Photo 配对必需）。

    ffmpeg 用 use_metadata_tags 才会写进 Apple 的 keys/ilst 结构，
    直接 -metadata 会被丢进 udta 的 © 标签里，相册读不到。
    """
    args = ["-y", "-i", src_mp4, "-c", "copy",
            "-movflags", "use_metadata_tags",
            "-metadata", "com.apple.quicktime.content.identifier=" + identifier,
            "-metadata", "com.apple.quicktime.still-image-time=0",
            out_mov]
    run(args, timeout=300)
    return os.path.getsize(out_mov)


def has_metadata_string(path, needle):
    """暴力校验元数据字符串真的写进文件了。"""
    blob = needle.encode("ascii")
    with open(path, "rb") as f:
        data = f.read()
    return blob in data
