# -*- coding: utf-8 -*-
"""
纯 Python 的 JPEG EXIF / XMP 写入，专门为 Live Photo 配对服务。

为什么要自己写：
  iOS 的实况照片靠一对元数据把「静态图」和「短视频」绑在一起 ——
  JPEG 的 Apple MakerNote(tag 17) 和 MOV 的 com.apple.quicktime.content.identifier
  必须写同一个 UUID，iPhone 相册才认。本机没有 exiftool，所以手搓 TIFF 结构。

参考：Apple MakerNote 布局
  0..9   'Apple iOS\\0'
  10..11 version \\x00\\x01
  12..13 字节序 'MM'
  14..   标准 TIFF IFD（偏移相对 MakerNote 起点，不是相对整个 APP1）
"""

import struct

TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}


# --------------------------------------------------------------------------
# 通用 TIFF / IFD 构造
# --------------------------------------------------------------------------

def _build_ifd(entries, ifd_offset, data_offset):
    """返回 (ifd_bytes, data_bytes)。

    entries: [(tag, type, count, payload_bytes)]
    ifd_offset: 本 IFD 在 TIFF 里的绝对起点（用来把内联值算成绝对偏移）
    data_offset: 溢出数据区起始的绝对偏移
    """
    out = struct.pack(">H", len(entries))
    blob = b""
    for tag, typ, count, payload in entries:
        n = TYPE_SIZE[typ] * count
        out += struct.pack(">HHI", tag, typ, count)
        if n <= 4:
            # 值直接内联，左对齐补零
            out += payload.ljust(4, b"\x00")[:4]
        else:
            out += struct.pack(">I", data_offset + len(blob))
            blob += payload
            if len(blob) % 2:      # TIFF 要求 word 对齐
                blob += b"\x00"
    out += struct.pack(">I", 0)    # 无下一个 IFD
    return out, blob


def build_tiff(ifd0_entries, exif_entries):
    """构造完整 TIFF 块（不含 Exif\\0\\0 前缀）。"""
    ifd0_size = 2 + 12 * len(ifd0_entries) + 4
    ifd0_offset = 8
    ifd0_data_offset = ifd0_offset + ifd0_size

    # 先量 IFD0 溢出数据长度，才能知道 Exif IFD 落在哪
    ifd0_blob_len = 0
    for tag, typ, count, payload in ifd0_entries:
        n = TYPE_SIZE[typ] * count
        if n > 4:
            ifd0_blob_len += n + (n % 2)

    exif_offset = ifd0_data_offset + ifd0_blob_len
    exif_size = 2 + 12 * len(exif_entries) + 4
    exif_data_offset = exif_offset + exif_size

    # 回填 0x8769 的 Exif IFD 指针
    fixed0 = []
    for tag, typ, count, payload in ifd0_entries:
        if tag == 0x8769:
            fixed0.append((tag, 4, 1, struct.pack(">I", exif_offset)))
        else:
            fixed0.append((tag, typ, count, payload))

    ifd0, blob0 = _build_ifd(fixed0, ifd0_offset, ifd0_data_offset)
    exif, blob1 = _build_ifd(exif_entries, exif_offset, exif_data_offset)

    header = b"MM\x00\x2a" + struct.pack(">I", 8)
    return header + ifd0 + blob0 + exif + blob1


def build_apple_makernote(uuid_str):
    """Apple MakerNote，里面只有一个 tag 17 = ContentIdentifier。"""
    s = uuid_str.encode("ascii") + b"\x00"
    header = b"Apple iOS\x00" + b"\x00\x01" + b"MM"      # 14 字节
    data_offset = 14 + 2 + 12 + 4                        # 32
    entry = struct.pack(">HHI", 0x0011, 2, len(s)) + struct.pack(">I", data_offset)
    ifd = struct.pack(">H", 1) + entry + struct.pack(">I", 0)
    return header + ifd + s


def build_exif_segment(width, height, uuid_str, dt_text,
                       make="Apple", model="iPhone 15 Pro"):
    """返回可直接插进 JPEG 的 APP1 段（含 FFE1 头）。"""
    dt = dt_text.encode("ascii") + b"\x00"
    mnote = build_apple_makernote(uuid_str)

    # tag 必须升序
    ifd0 = [
        (0x010F, 2, len(make) + 1, make.encode("ascii") + b"\x00"),
        (0x0110, 2, len(model) + 1, model.encode("ascii") + b"\x00"),
        (0x0132, 2, len(dt), dt),
        (0x8769, 4, 1, b"\x00\x00\x00\x00"),          # 占位，build_tiff 里回填
    ]
    exif = [
        (0x9003, 2, len(dt), dt),                      # DateTimeOriginal
        (0x9004, 2, len(dt), dt),                      # DateTimeDigitized
        (0x927C, 7, len(mnote), mnote),                # MakerNote
        (0xA002, 4, 1, struct.pack(">I", width)),      # PixelXDimension
        (0xA003, 4, 1, struct.pack(">I", height)),     # PixelYDimension
    ]

    tiff = build_tiff(ifd0, exif)
    payload = b"Exif\x00\x00" + tiff
    if len(payload) + 2 > 0xFFFF:
        raise ValueError("EXIF payload too large")
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


# --------------------------------------------------------------------------
# XMP（Motion Photo / Google 标准）
# --------------------------------------------------------------------------

MOTION_XMP_TMPL = """<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 5.6-c140 79.160451">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:GCamera="http://ns.google.com/photos/1.0/camera/"
    xmlns:Container="http://ns.google.com/photos/1.0/container/"
    xmlns:Item="http://ns.google.com/photos/1.0/container/item/"
    GCamera:MicroVideo="1"
    GCamera:MicroVideoVersion="1"
    GCamera:MicroVideoOffset="{offset}"
    GCamera:MicroVideoPresentationTimestampUs="{ts_us}">
   <Container:Directory>
    <rdf:Seq>
     <rdf:li rdf:parseType="Resource">
      <Container:Item
       Item:Mime="image/jpeg"
       Item:Semantic="Primary"
       Item:Length="0"
       Item:Padding="0"/>
     </rdf:li>
     <rdf:li rdf:parseType="Resource">
      <Container:Item
       Item:Mime="video/mp4"
       Item:Semantic="MotionPhoto"
       Item:Length="{video_len}"
       Item:Padding="0"/>
     </rdf:li>
    </rdf:Seq>
   </Container:Directory>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>{pad}"""


def build_xmp_segment(video_len, ts_us=0, padding=2048):
    """扩展 XMP 段（含 FFE1 头），padding 是规范建议的空白填充。"""
    xmp = MOTION_XMP_TMPL.format(
        offset=video_len, video_len=video_len, ts_us=ts_us,
        pad=" " * padding,
    ).encode("utf-8")
    # XMP 里 begin 后面那个 \xef\xbb\xbf 是 BOM 字节，按 utf-8 编码会变成 6 字节，
    # 这里做一次还原，保证输出的是真 BOM。
    xmp = xmp.replace(b"\xc3\xaf\xc2\xbb\xc2\xbf", b"\xef\xbb\xbf")
    payload = b"http://ns.adobe.com/xap/1.0/\x00" + xmp
    if len(payload) + 2 > 0xFFFF:
        # 填充过头了，砍掉
        overflow = len(payload) + 2 - 0xFFFF
        payload = payload[: len(payload) - overflow - 2] + b'  <?xpacket end="w"?>'
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


# --------------------------------------------------------------------------
# JPEG 拼装
# --------------------------------------------------------------------------

def strip_app_segments(jpeg_bytes):
    """去掉原有的 APP1（EXIF/XMP），保留其它段，返回 SOI + 后续。"""
    if jpeg_bytes[:2] != b"\xff\xd8":
        raise ValueError("not a jpeg")
    out = b"\xff\xd8"
    i = 2
    while i < len(jpeg_bytes) - 1:
        if jpeg_bytes[i] != 0xFF:
            break
        marker = jpeg_bytes[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker == 0xDA:                      # SOS，后面是压缩数据
            out += jpeg_bytes[i:]
            return out
        seg_len = struct.unpack(">H", jpeg_bytes[i + 2:i + 4])[0]
        if marker == 0xE1:                      # 丢掉 APP1
            i += 2 + seg_len
            continue
        out += jpeg_bytes[i:i + 2 + seg_len]
        i += 2 + seg_len
    out += jpeg_bytes[i:]
    return out


def inject_segments(jpeg_bytes, segments):
    """把若干 APP 段插到 SOI 之后。"""
    if jpeg_bytes[:2] != b"\xff\xd8":
        raise ValueError("not a jpeg")
    return jpeg_bytes[:2] + b"".join(segments) + jpeg_bytes[2:]


# --------------------------------------------------------------------------
# 回读校验（写完自己验一遍，别信“应该没问题”）
# --------------------------------------------------------------------------

def read_makernote_uuid(jpeg_bytes):
    """从 JPEG 里把 Apple MakerNote tag 17 抠出来，验证写入是否成功。"""
    if jpeg_bytes[:2] != b"\xff\xd8":
        return None
    i = 2
    tiff = None
    while i < len(jpeg_bytes) - 4:
        if jpeg_bytes[i] != 0xFF:
            return None
        marker = jpeg_bytes[i + 1]
        if marker == 0xDA:
            return None
        seg_len = struct.unpack(">H", jpeg_bytes[i + 2:i + 4])[0]
        body = jpeg_bytes[i + 4:i + 2 + seg_len]
        if marker == 0xE1 and body[:6] == b"Exif\x00\x00":
            tiff = body[6:]
            break
        i += 2 + seg_len
    if not tiff:
        return None

    bo = ">" if tiff[:2] == b"MM" else "<"
    ifd0 = struct.unpack(bo + "I", tiff[4:8])[0]

    def find_ifd_entry(offset, want):
        cnt = struct.unpack(bo + "H", tiff[offset:offset + 2])[0]
        for k in range(cnt):
            p = offset + 2 + 12 * k
            tag, typ, count = struct.unpack(bo + "HHI", tiff[p:p + 8])
            if tag == want:
                raw = tiff[p + 8:p + 12]
                if TYPE_SIZE.get(typ, 1) * count <= 4:
                    return raw[:TYPE_SIZE.get(typ, 1) * count]
                off = struct.unpack(bo + "I", raw)[0]
                return tiff[off:off + TYPE_SIZE.get(typ, 1) * count]
        return None

    exif_ptr = find_ifd_entry(ifd0, 0x8769)
    if not exif_ptr:
        return None
    exif_off = struct.unpack(bo + "I", exif_ptr)[0]
    mnote = find_ifd_entry(exif_off, 0x927C)
    if not mnote:
        return None
    if not mnote.startswith(b"Apple iOS"):
        return None

    sub = mnote[14:]
    cnt = struct.unpack(bo + "H", sub[:2])[0]
    for k in range(cnt):
        p = 2 + 12 * k
        tag, typ, count = struct.unpack(bo + "HHI", sub[p:p + 8])
        if tag == 0x0011:
            # 注意：offset 是相对 MakerNote 起点的，不是相对 sub 的
            off = struct.unpack(bo + "I", sub[p + 8:p + 12])[0]
            return mnote[off:off + count].rstrip(b"\x00").decode("ascii", "ignore")
    return None
