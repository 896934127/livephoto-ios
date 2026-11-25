# -*- coding: utf-8 -*-
"""视频转实况图 —— Flask 后端。"""

import json
import os
import shutil
import socket
import threading
import time
import traceback
import uuid as uuidlib

from flask import Flask, jsonify, request, send_file, send_from_directory, abort

from livephoto import builder, ffmpeg_util

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
UP_DIR = os.path.join(DATA_DIR, "uploads")
OUT_DIR = os.path.join(DATA_DIR, "outputs")
TMP_DIR = os.path.join(DATA_DIR, "tmp")
STATIC_DIR = os.path.join(BASE_DIR, "static")

for d in (UP_DIR, OUT_DIR, TMP_DIR):
    os.makedirs(d, exist_ok=True)

ALLOWED_EXT = {"mp4", "mov", "m4v", "avi", "mkv", "webm", "flv", "wmv",
               "3gp", "mpg", "mpeg", "ts", "mts", "m2ts"}

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024 * 1024  # 4G


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------

def _video_path(vid):
    for ext in ALLOWED_EXT:
        p = os.path.join(UP_DIR, vid + "." + ext)
        if os.path.isfile(p):
            return p
    return None


def _meta_path(vid):
    return os.path.join(UP_DIR, vid + ".json")


def _save_meta(vid, meta):
    with open(_meta_path(vid), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)


def _load_meta(vid):
    p = _meta_path(vid)
    if not os.path.isfile(p):
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _sweep():
    """清掉超过 12 小时的临时素材，别让目录无限长。"""
    cutoff = time.time() - 12 * 3600
    for d in (UP_DIR, OUT_DIR, TMP_DIR):
        for name in os.listdir(d):
            p = os.path.join(d, name)
            try:
                if os.path.getmtime(p) < cutoff:
                    if os.path.isdir(p):
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        os.remove(p)
            except OSError:
                pass


_sweep()


# --------------------------------------------------------------------------
# 页面
# --------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/static/<path:name>")
def static_files(name):
    return send_from_directory(STATIC_DIR, name)


@app.route("/sw.js")
def service_worker():
    """Service Worker 放根路径，才能拿到全站 scope。"""
    resp = send_from_directory(STATIC_DIR, "sw.js", mimetype="application/javascript")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


# --------------------------------------------------------------------------
# 接口
# --------------------------------------------------------------------------

@app.route("/api/status")
def api_status():
    ok = ffmpeg_util.available()
    return jsonify({
        "ffmpeg": ok,
        "version": ffmpeg_util.version() if ok else None,
    })


@app.route("/api/upload", methods=["POST"])
def api_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "没有收到文件"}), 400

    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in ALLOWED_EXT:
        return jsonify({"error": "不支持的格式：%s" % ext}), 400

    vid = uuidlib.uuid4().hex
    path = os.path.join(UP_DIR, vid + "." + ext)
    f.save(path)

    try:
        info = ffmpeg_util.probe(path)
    except Exception as exc:
        try:
            os.remove(path)
        except OSError:
            pass
        return jsonify({"error": "读不出视频信息：%s" % exc}), 400

    if info["duration"] <= 0:
        return jsonify({"error": "这个视频时长读不出来，可能文件损坏"}), 400

    meta = {
        "vid": vid,
        "ext": ext,
        "original": f.filename,
        "info": info,
        "uploaded": time.time(),
    }
    _save_meta(vid, meta)
    meta["url"] = "/api/media/" + vid
    return jsonify(meta)


@app.route("/api/media/<vid>")
def api_media(vid):
    p = _video_path(vid)
    if not p:
        abort(404)
    return send_file(p, conditional=True)


@app.route("/api/filmstrip/<vid>")
def api_filmstrip(vid):
    p = _video_path(vid)
    if not p:
        abort(404)
    out = os.path.join(TMP_DIR, vid + "_strip.png")
    if not os.path.isfile(out):
        try:
            ffmpeg_util.make_filmstrip(p, out, count=14, height=88)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
    return send_file(out, mimetype="image/png", max_age=3600)


@app.route("/api/frame/<vid>")
def api_frame(vid):
    p = _video_path(vid)
    if not p:
        abort(404)
    t = float(request.args.get("t", 0))
    meta = _load_meta(vid)
    edge = int(request.args.get("edge", 720))
    out = os.path.join(TMP_DIR, "%s_f_%d_%d.jpg" % (vid, int(t * 100), edge))
    if not os.path.isfile(out):
        try:
            ffmpeg_util.extract_frame(p, t, out, max_edge=edge, quality=4)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
    resp = send_file(out, mimetype="image/jpeg", conditional=True)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/api/export", methods=["POST"])
def api_export():
    payload = request.get_json(silent=True) or {}
    vid = payload.get("vid")
    src = _video_path(vid) if vid else None
    if not src or not os.path.isfile(src):
        return jsonify({"error": "视频找不到了，请重新上传"}), 400

    meta = _load_meta(vid)
    info = meta.get("info", {})
    total = float(info.get("duration") or 0)

    start = max(float(payload.get("start", 0)), 0.0)
    duration = max(float(payload.get("duration", 3)), 0.2)
    if total and start + duration > total:
        duration = max(total - start, 0.2)
    cover = float(payload.get("cover", start + duration / 2.0))
    cover = min(max(cover, start), start + duration)

    params = {
        "start": start,
        "duration": duration,
        "cover": cover,
        "formats": payload.get("formats") or ["motion"],
        "max_edge": int(payload.get("max_edge", 1440)),
        "crf": int(payload.get("crf", 20)),
        "gif_width": int(payload.get("gif_width", 480)),
        "gif_fps": int(payload.get("gif_fps", 12)),
    }

    workdir = os.path.join(TMP_DIR, "job_" + uuidlib.uuid4().hex[:10])
    os.makedirs(workdir, exist_ok=True)

    t0 = time.time()
    try:
        results = builder.build_all(src, params, workdir, OUT_DIR)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": "生成失败：%s" % exc}), 500
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    for r in results:
        r["download"] = "/api/download/" + r["name"]

    return jsonify({
        "ok": True,
        "elapsed": round(time.time() - t0, 2),
        "items": results,
        "params": params,
    })


@app.route("/api/download/<name>")
def api_download(name):
    if "/" in name or "\\" in name or ".." in name:
        abort(400)
    p = os.path.join(OUT_DIR, name)
    if not os.path.isfile(p):
        abort(404)
    return send_file(p, as_attachment=True, download_name=name)


@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "文件太大，超过 4G 了"}), 413


def _lan_ips():
    """本机所有可用的局域网 IPv4，手机要连的那个就在里面。"""
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.3)
        try:
            s.connect(("223.5.5.5", 80))
            ips.append(s.getsockname()[0])
        finally:
            s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    return ips


def _is_phone_link(ip):
    """iPhone 用 USB 网络共享时，电脑这端一般是 172.20.10.x。"""
    return ip.startswith("172.20.10.")


def main(host="0.0.0.0", port=8770):
    lan = _lan_ips() if host in ("0.0.0.0", "") else []

    print("")
    print("  实况图工厂   已启动")
    print("  " + "-" * 50)
    print("  电脑上打开：  http://127.0.0.1:%d" % port)
    if lan:
        print("  手机上打开（跟电脑同一 WiFi，或用数据线连着）：")
        for ip in lan:
            tail = "   <== USB 连着 iPhone 就用这个" if _is_phone_link(ip) else ""
            print("      http://%s:%d%s" % (ip, port, tail))
    print("  " + "-" * 50)
    print("  手机第一次打开：Safari 底部「分享」->「添加到主屏幕」")
    print("  关掉这个窗口就停止服务")
    print("")

    if not ffmpeg_util.available():
        print("  [警告] 没找到 ffmpeg，视频处理会失败。\n")

    app.run(host=host, port=port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
