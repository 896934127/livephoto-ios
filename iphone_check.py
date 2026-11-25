# -*- coding: utf-8 -*-
"""iPhone 视口自检：390x844 / 3x / 触屏，跑完整流程并截图。

只用来验证布局和交互，不代表真机表现（真机的 Safari 引擎细节不同）。
"""

import os
import sys
import sysconfig

_sp = sysconfig.get_path("purelib")
if _sp not in sys.path:
    sys.path.append(_sp)

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8770/"
VIDEO = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("TEMP", ".")

errors = []
notes = []


def main():
    with sync_playwright() as p:
        dev = dict(p.devices["iPhone 13"])
        browser = p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            args=["--force-color-profile=srgb"])

        ctx = browser.new_context(**dev)
        page = ctx.new_page()
        page.on("console", lambda m: errors.append("console.error: %s" % m.text)
                if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append("pageerror: %s" % e))

        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(800)

        # --- 环境判断 ---
        env = page.evaluate("""() => ({
            coarse: matchMedia('(pointer: coarse)').matches,
            w: innerWidth, h: innerHeight,
            touch: navigator.maxTouchPoints,
            ua: navigator.userAgent.indexOf('iPhone') >= 0,
            canShare: !!navigator.canShare,
            tip: !document.getElementById('installTip').classList.contains('hidden'),
            touchIcon: !!document.querySelector('link[rel=apple-touch-icon]'),
            manifest: !!document.querySelector('link[rel=manifest]'),
            standalone: !!(window.navigator.standalone)
        })""")
        notes.append("视口 %dx%d, 触摸点 %s, coarse=%s, iOS UA=%s, 分享API=%s"
                     % (env["w"], env["h"], env["touch"], env["coarse"],
                        env["ua"], env["canShare"]))
        notes.append("安装提示条显示=%s, 主屏图标标签=%s, manifest=%s"
                     % (env["tip"], env["touchIcon"], env["manifest"]))

        if not env["coarse"]:
            errors.append("pointer: coarse 没生效，触摸热区规则不会应用")
        if not env["tip"]:
            errors.append("iPhone 上没出现添加到主屏幕的提示")
        if not env["touchIcon"]:
            errors.append("缺少 apple-touch-icon")

        # 没有横向滚动条才算布局没问题
        ovf = page.evaluate("() => document.documentElement.scrollWidth - innerWidth")
        if ovf > 1:
            errors.append("页面横向溢出 %dpx" % ovf)

        page.screenshot(path=os.path.join(OUT, "p1_upload.png"))
        print("p1 上传页 ok")

        # --- 上传 ---
        page.set_input_files("#fileInput", VIDEO)
        page.wait_for_selector("#editor:not(.hidden)", timeout=30000)
        page.wait_for_timeout(2600)

        # 操作条是否固定到底部、有没有压住内容
        bar = page.eval_on_selector(".action-bar", """e => {
            const r = e.getBoundingClientRect();
            return {top: r.top, bottom: r.bottom, h: r.height,
                    pos: getComputedStyle(e).position, vh: innerHeight};
        }""")
        notes.append("操作条 position=%s 高=%d 底边距视口底=%d"
                     % (bar["pos"], round(bar["h"]), round(bar["vh"] - bar["bottom"])))
        if bar["pos"] != "fixed":
            errors.append("手机端操作条没固定到底部")
        if abs(bar["vh"] - bar["bottom"]) > 2:
            errors.append("操作条没贴住屏幕底部（差 %dpx）"
                          % round(bar["vh"] - bar["bottom"]))

        pad = page.eval_on_selector("#editor", "e => getComputedStyle(e).paddingBottom")
        notes.append("编辑区底部留白 = %s，操作条高 = %dpx" % (pad, round(bar["h"])))

        # 时间轴尺寸 + 手柄热区
        tl = page.eval_on_selector("#timeline", "e => {const r=e.getBoundingClientRect();return {h:r.height,w:r.width}}")
        hw = page.eval_on_selector(".tl-handle", "e => e.getBoundingClientRect().width")
        coverPe = page.eval_on_selector("#tlCover", "e => getComputedStyle(e).pointerEvents")
        notes.append("时间轴 %dx%d, 手柄热区宽 %dpx, 封面三角 pointer-events=%s"
                     % (round(tl["w"]), round(tl["h"]), round(hw), coverPe))
        if hw < 26:
            errors.append("手柄热区只有 %dpx，手指按不准" % round(hw))
        if coverPe != "none":
            errors.append("封面三角还在抢触摸，会跟拖动冲突")

        page.screenshot(path=os.path.join(OUT, "p2_editor.png"))
        print("p2 编辑页 ok")

        # 手指点预设（触摸）
        chip = page.locator('.chip[data-dur="1.5"]')
        b = chip.bounding_box()
        page.touchscreen.tap(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
        page.wait_for_timeout(700)
        dur = page.inner_text("#durChip").strip()
        notes.append("点 1.5 秒预设后 = %s" % dur)
        if dur != "1.50s":
            errors.append("触摸点预设没生效: %s" % dur)

        # 拖右手柄（用 pointer 事件，和手指路径一致）
        sel = page.locator("#tlSel").bounding_box()
        if sel:
            page.mouse.move(sel["x"] + sel["width"] - 4, sel["y"] + sel["height"] / 2)
            page.mouse.down()
            page.mouse.move(sel["x"] + sel["width"] + 96,
                            sel["y"] + sel["height"] / 2, steps=14)
            page.mouse.up()
            page.wait_for_timeout(600)
            notes.append("拖手柄后时长 = %s" % page.inner_text("#durChip").strip())

        page.screenshot(path=os.path.join(OUT, "p3_drag.png"))
        print("p3 拖动后 ok")

        # --- 生成（只要 iOS，默认已勾） ---
        page.click('.chip[data-dur="3"]')
        page.wait_for_timeout(400)
        page.click("#goBtn")
        page.wait_for_selector(".item", timeout=120000)
        page.wait_for_timeout(1800)

        page.screenshot(path=os.path.join(OUT, "p4_result.png"))
        print("p4 结果 ok")

        n = page.locator(".item").count()
        saveBtns = page.locator(".save-btn").count()
        saveVisible = page.eval_on_selector(
            ".save-btn", "e => getComputedStyle(e.closest('.save-wrap')).display !== 'none'")
        saveText = page.inner_text(".save-btn").strip()
        notes.append("结果 %d 条, 保存按钮 %d 个, 可见=%s, 文案=「%s」"
                     % (n, saveBtns, saveVisible, saveText))
        if n < 1:
            errors.append("没生成出结果")
        if not saveVisible:
            errors.append("手机上「保存到手机」按钮没显示")

        # 结果卡片不能被底部操作条盖住
        overlap = page.evaluate("""() => {
            const bar = document.querySelector('.action-bar').getBoundingClientRect();
            const items = [...document.querySelectorAll('.item')];
            if (!items.length) return -1;
            const last = items[items.length-1].getBoundingClientRect();
            return Math.round(bar.top - last.bottom);
        }""")
        notes.append("最后一张结果卡与操作条的间距 = %d px（负数是被盖住）" % overlap)

        # 全页长图，肉眼看整体
        page.screenshot(path=os.path.join(OUT, "p5_full.png"), full_page=True)
        print("p5 长图 ok")

        # 展开指引（先确认滚到底部时没被固定操作条盖住）
        occ = page.evaluate("""() => {
            const s = document.querySelector('.guide summary');
            s.scrollIntoView({block: 'center'});
            const r = s.getBoundingClientRect();
            const hit = document.elementFromPoint(r.left + r.width/2,
                                                  r.top + r.height/2);
            const bar = document.querySelector('.action-bar').getBoundingClientRect();
            return {
                covered: !(hit === s || (s.parentNode && s.parentNode.contains(hit))),
                hit: hit ? (hit.className || hit.tagName) : 'none',
                gapToBar: Math.round(bar.top - r.bottom)
            };
        }""")
        notes.append("指引标题可点=%s（命中 %s，距操作条 %dpx）"
                     % (not occ["covered"], occ["hit"], occ["gapToBar"]))
        if occ["covered"]:
            errors.append("指引面板被底部操作条盖住，点不进去（命中 %s）" % occ["hit"])

        page.wait_for_timeout(300)
        page.click(".guide summary")
        page.wait_for_timeout(600)
        page.eval_on_selector(".guide", "e => e.scrollIntoView({block:'center'})")
        page.wait_for_timeout(400)
        page.screenshot(path=os.path.join(OUT, "p6_guide.png"))
        print("p6 指引 ok")

        gw = page.evaluate("""() => {
            const b = document.querySelector('.guide-body');
            return b.scrollWidth - b.clientWidth;
        }""")
        if gw > 1:
            errors.append("指引面板文字横向溢出 %dpx" % gw)

        browser.close()


try:
    main()
except Exception as exc:
    import traceback
    traceback.print_exc()
    errors.append(str(exc))

print("")
for n in notes:
    print("  ·", n)
print("")
if errors:
    print("问题:")
    for e in errors:
        print("  -", e)
    sys.exit(1)
print("iPhone 视口检查通过")
