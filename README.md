# 实况图工厂

把视频里的一小段做成「实况照片」（Live Photo / Motion Photo）。本地跑，不联网，不上传任何素材。

## 启动

双击 `启动.bat`，浏览器会自动打开 `http://127.0.0.1:8770`。

  命令行也行：

```
python -S run.py            # 自动开浏览器
python -S run.py 9000       # 换端口
python -S run.py --no-browser
```

> 必须带 `-S`。本机 `site-packages` 里有个 GBK 编码的 `.pth`（dynamic_skill_agent），
> 不带 `-S` 启动会直接 `Fatal Python error: init_import_size`。
> `run.py` 里已经手动把 `site-packages` 补进 `sys.path`，不影响 Flask 使用。

## 用法

1. 把视频拖进页面（mp4 / mov / mkv / avi / 3gp 等）
2. 在时间轴上拖蓝框选片段 —— 拖两边手柄改起止，拖中间整块平移
3. 黄色小三角是**封面帧**，选中那条实况图点开显示的画面，可拖动
4. 勾要哪些输出，点「生成实况图」，右边下载

时长一般 3 秒（iOS 实况照片的标准长度）。1～5 秒都能用。

## 输出格式

| 格式 | 文件 | 谁能认 |
|---|---|---|
| 实况图（单文件） | `xxx.jpg` | 安卓相册（小米 / OPPO / vivo）、Google 相册、部分图库 |
| iOS 实况照片 | `IMG_xxx.livp` + 同名 `.JPG` / `.MOV` | iOS 相册，见下面的导入方法 |
| GIF 动图 | `xxx.gif` | 哪儿都能发 |
| MP4 片段 | `xxx.mp4` | 短视频平台、微信 |
| 封面静帧 | `xxx_still.jpg` | 只要一张图时用 |

### 单文件实况图（安卓，推荐）

一张 JPEG 文件，视频数据直接追加在文件尾部，靠 XMP 元数据告诉相册「视频有多长、在哪个位置」。

- 安卓：拷到 `DCIM/Camera` 目录，小米 / OPPO / vivo / 荣耀 / 一加相册一般能识别成长按照片
- Google 相册：能识别
- 电脑上：Windows 照片、macOS 预览只显示静态图（正常，只看得到封面）

### iOS 实况照片

**先说清楚：iOS 上根本没有「单文件」实况照片。** 苹果自己拍的照片，底层就是一个
`IMG_0001.HEIC` 加一个 `IMG_0001.MOV`，靠元数据里的同一个 `ContentIdentifier`
（JPG 写在 Apple MakerNote 的 tag 17，MOV 写在
`com.apple.quicktime.content.identifier`）绑成一张。相册里看着是一张，文件系统里就是俩。

苹果唯一的「打包成一个文件」的格式是 **`.livp`** —— 本质就是 zip 改后缀，
里面装那一对文件。这个工具三种都给你：

| 文件 | 干什么用 |
|---|---|
| `IMG_xxx.livp` | 传到手机上点开 → 分享 → 存储到「照片」 |
| `IMG_xxx.JPG` | 配对主图，走数据线/照片 App 时和 MOV 一起导入 |
| `IMG_xxx.MOV` | 配对视频，同上 |

`.livp` 内部就是这两件东西，条目在根目录、同名不同扩展名，跟苹果导出的结构一致。

### 弄到手机上的四条路

**安卓**：下载单文件 `.jpg` → 数据线拷到 `DCIM/Camera` → 相册里长按就动。

**iPhone · 无线（先试这个）**
1. 下载 `.livp`
2. 微信「文件传输助手」发到手机 —— 发送时选**「文件」**，别用图片发送
3. 手机上点开 → 右上角分享 → 存储到「照片」

iOS 部分版本对 `.livp` 认得不稳，存不进去就走下面两条。

**iPhone · 数据线（最稳）**
1. 装爱思助手（免费），手机连电脑
2. 「照片」→「实况照片」→ 导入
3. 选中 `IMG_xxx.JPG` 和 `IMG_xxx.MOV` 两个

两个必须一起导，只导 JPG 就只剩静止图。iMazing 也有 Live Photo 导入。

**有 Mac 就最简单**：`照片` App → 文件 → 导入 → 两个文件一起选中，照片 App
会自动认出配对，直接变成实况照片。

导完在相册里长按能动的，就是成了。朋友圈发实况要求 iPhone，安卓那边只显示静态图，
这是微信的限制，不是文件的问题。

## 目录

```
实况/
├── 启动.bat            双击启动
├── run.py              启动器（处理 -S 的路径问题）
├── app.py              Flask 后端 + 接口
├── livephoto/
│   ├── ffmpeg_util.py  ffmpeg 封装：探测、切片、抽帧、GIF
│   ├── builder.py      各格式的产出流程
│   └── exifutil.py     手写 EXIF / XMP / Apple MakerNote
├── static/             前端（原生 JS，没有框架）
├── tools/ffmpeg/bin/   ffmpeg.exe + ffprobe.exe（便携版，6.0）
├── data/               上传的视频、产出、临时文件（12 小时后自动清）
├── selftest.py         元数据自检（不依赖 ffmpeg）
├── e2e_test.py         端到端自检（需要真视频）
└── ui_check.py         界面自检（无头 Chrome 跑一遍流程并截图）
```

## 自检

```
python -S selftest.py                      # EXIF/XMP 写入是否正确
python -S e2e_test.py D:\some\video.mp4    # 完整产出流程
python -S ui_check.py D:\v.mp4 %TEMP%      # 界面流程 + 截图
```

## 几个实现上的坑（改代码前先看）

- **ffmpeg 的 MOV 元数据**：必须用 `-movflags use_metadata_tags` 才会写进 Apple 的
  keys/ilst 结构。直接 `-metadata` 会丢到 udta 的 `©` 标签里，相册读不到。
- **Apple MakerNote 内部的偏移是相对 MakerNote 起点**，不是相对整个 APP1，也不是相对 IFD。
  搞错就会读出半截 UUID。
- **`-ss` 放在 `-i` 前面**配重编码是精确的，不用解到关键帧再补。
- **宽高必须是偶数**，否则 `yuv420p` 编码报错。
- 手机竖拍视频靠 rotation 标记，`probe()` 里已经交换过宽高，别重复处理。

## 依赖

- Python 3.8（本机 3.8.6）
- Flask 3.0.3、Pillow 10.4.0（本机已有）
- ffmpeg 6.0 便携版（已放在 `tools/ffmpeg/bin/`）
