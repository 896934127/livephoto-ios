# -*- coding: utf-8 -*-
"""自检脚本：不依赖 ffmpeg，验证元数据写入与 JPEG 拼装的正确性。

跑法： python -S selftest.py
"""

import io
import os
import struct
import sys
import sysconfig
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_sp = sysconfig.get_path("purelib")
if _sp not in sys.path:
    sys.path.append(_sp)

from PIL import Image

from livephoto import exifutil

FAIL = []


def check(name, cond, extra=""):
    if cond:
        print("  [OK]   %s" % name)
    else:
        print("  [FAIL] %s  %s" % (name, extra))
        FAIL.append(name)


def make_jpeg(w=640, h=480):
    im = Image.new("RGB", (w, h), (40, 80, 140))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return buf.getvalue()


print("== 1. Apple MakerNote 往返 ==")
ident = str(uuid.uuid4()).upper()
jpg = make_jpeg()
raw = exifutil.strip_app_segments(jpg)
seg = exifutil.build_exif_segment(640, 480, ident, "2026:11:25 21:00:00")
out = exifutil.inject_segments(raw, [seg])
back = exifutil.read_makernote_uuid(out)
check("UUID 写进去能读回来", back == ident, "读到 %r" % back)
check("UUID 是 36 位", len(ident) == 36)

print("== 2. JPEG 仍然可解码 ==")
try:
    im2 = Image.open(io.BytesIO(out))
    im2.load()
    check("注入 EXIF 后 PIL 能打开", True)
    check("尺寸没变", im2.size == (640, 480), str(im2.size))
except Exception as exc:
    check("注入 EXIF 后 PIL 能打开", False, str(exc))

print("== 3. Motion Photo 结构 ==")
fake_video = b"\x00\x00\x00\x20ftypisom" + b"\x00" * 5000
xmp_seg = exifutil.build_xmp_segment(len(fake_video), 1500000)
mp = exifutil.inject_segments(raw, [seg, xmp_seg]) + fake_video

check("文件头是 SOI", mp[:2] == b"\xff\xd8")
check("XMP 里有 MicroVideoOffset", b"MicroVideoOffset=\"%d\"" % len(fake_video) in mp)
check("XMP 里有 MotionPhoto 语义", b'Semantic="MotionPhoto"' in mp)
check("尾部就是视频数据", mp.endswith(fake_video))

# 校验 IFD 里的 Item:Length 和真实长度一致
check("Item:Length 正确",
      b'Item:Length="%d"' % len(fake_video) in mp)

try:
    im3 = Image.open(io.BytesIO(mp))
    im3.load()
    check("内嵌视频后 PIL 仍能打开（相册同理）", True)
    check("内嵌后尺寸正确", im3.size == (640, 480), str(im3.size))
except Exception as exc:
    check("内嵌视频后 PIL 仍能打开（相册同理）", False, str(exc))

print("== 4. EXIF 结构合法性 ==")
i = 2
segments = []
while i < len(mp) - 4:
    if mp[i] != 0xFF:
        break
    if mp[i + 1] == 0xDA:
        break
    ln = struct.unpack(">H", mp[i + 2:i + 4])[0]
    segments.append((hex(mp[i + 1]), ln))
    i += 2 + ln
check("APP 段长度合法", all(0 < ln < 65535 for _, ln in segments), str(segments))
check("有一个 APP1（EXIF）", segments.count(("0xe1", segments[0][1] if segments else 0)) >= 1)

# 用 PIL 读回 EXIF 里的 Make / 尺寸
im4 = Image.open(io.BytesIO(mp))
ex = im4.getexif()
check("PIL 能读到 Make=Apple", ex.get(0x010F) == "Apple", str(ex.get(0x010F)))
exif_ifd = ex.get_ifd(0x8769)
check("PIL 能读到 PixelXDimension", exif_ifd.get(0xA002) == 640, str(exif_ifd.get(0xA002)))
check("PIL 能读到 MakerNote", bool(exif_ifd.get(0x927C)), "missing")

print("")
if FAIL:
    print("失败 %d 项：%s" % (len(FAIL), ", ".join(FAIL)))
    sys.exit(1)
print("全部通过")
