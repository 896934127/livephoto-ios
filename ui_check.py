# -*- coding: utf-8 -*-
"""界面自检：用无头 Chromium 跑一遍真实流程并截图。"""

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


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            args=["--force-color-profile=srgb"])
        page = browser.new_page(viewport={"width": 1500, "height": 1000},
                                device_scale_factor=1)
        page.on("console", lambda m: errors.append("console.%s: %s" % (m.type, m.text))
                if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append("pageerror: %s" % e))

        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(700)
        page.screenshot(path=os.path.join(OUT, "shot_1_upload.png"))
        print("shot 1 ok")

        page.set_input_files("#fileInput", VIDEO)
        page.wait_for_selector("#editor:not(.hidden)", timeout=30000)
        page.wait_for_timeout(2500)   # 等缩略图条 + 封面帧
        page.screenshot(path=os.path.join(OUT, "shot_2_editor.png"))
        print("shot 2 ok")

        # 点 1.5 秒预设，验证时长切换
        page.click('.chip[data-dur="1.5"]')
        page.wait_for_timeout(900)
        dur = page.inner_text("#durChip")
        print("时长切换后:", dur)
        if dur.strip() != "1.50s":
            errors.append("预设按钮没生效: %s" % dur)

        # 拖右手柄：模拟从选区右侧往右拉
        box = page.querySelector if False else page.locator("#timeline").bounding_box()
        sel = page.locator("#tlSel").bounding_box()
        if sel:
            page.mouse.move(sel["x"] + sel["width"] - 2, sel["y"] + 30)
            page.mouse.down()
            page.mouse.move(sel["x"] + sel["width"] + 180, sel["y"] + 30, steps=12)
            page.mouse.up()
            page.wait_for_timeout(600)
            print("拖拽后:", page.inner_text("#durChip"))

        page.screenshot(path=os.path.join(OUT, "shot_3_drag.png"))
        print("shot 3 ok")

        # 拖封面帧标记（验证点击热区够大）
        before = page.eval_on_selector("#tlCover", "e => e.style.left")
        cv = page.locator("#tlCover").bounding_box()
        if cv:
            page.mouse.move(cv["x"] + cv["width"] / 2, cv["y"] + 40)
            page.mouse.down()
            page.mouse.move(cv["x"] + cv["width"] / 2 - 70, cv["y"] + 40, steps=12)
            page.mouse.up()
            page.wait_for_timeout(700)
            after = page.eval_on_selector("#tlCover", "e => e.style.left")
            print("封面帧位置: %s -> %s" % (before, after))
            if before == after:
                errors.append("封面帧拖不动（热区太小）")

        # 生成
        page.click('.chip[data-dur="3"]')
        page.wait_for_timeout(400)
        page.check('input[name="fmt"][value="ios"]')
        page.click("#goBtn")
        page.wait_for_selector(".item", timeout=120000)
        page.wait_for_timeout(1200)
        page.screenshot(path=os.path.join(OUT, "shot_4_result.png"))
        n = page.locator(".item").count()
        nfiles = page.locator(".file-row").count()
        print("结果条数: %d, iOS 文件行: %d" % (n, nfiles))
        if n != 2:
            errors.append("预期 2 个结果，实际 %d" % n)
        if nfiles != 3:
            errors.append("iOS 应该有 3 个文件行，实际 %d" % nfiles)

        # 展开导入指引
        page.click(".guide summary")
        page.wait_for_timeout(500)
        page.screenshot(path=os.path.join(OUT, "shot_6_guide.png"))
        print("shot 6 ok")

        # 窄屏
        page.set_viewport_size({"width": 820, "height": 1100})
        page.wait_for_timeout(600)
        page.screenshot(path=os.path.join(OUT, "shot_5_narrow.png"), full_page=True)
        print("shot 5 ok")

        browser.close()


try:
    main()
except Exception as exc:
    print("EXC:", exc)
    errors.append(str(exc))

print("")
if errors:
    print("问题:")
    for e in errors:
        print("  -", e)
    sys.exit(1)
print("界面检查通过")
