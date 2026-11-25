# -*- coding: utf-8 -*-
"""启动器。

本机 Python 的 site-packages 里有个 GBK 编码的 .pth（dynamic_skill_agent），
不带 -S 启动会直接 Fatal error，所以这里先用 -S 起来再手动补路径。
"""

import os
import sys
import sysconfig

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    purelib = sysconfig.get_path("purelib")
except Exception:
    purelib = None

if purelib and os.path.isdir(purelib) and purelib not in sys.path:
    sys.path.append(purelib)

if __name__ == "__main__":
    import threading
    import time
    import webbrowser

    from app import main

    port = 8770
    no_browser = "--no-browser" in sys.argv
    for a in sys.argv[1:]:
        if a.isdigit():
            port = int(a)

    if not no_browser:
        def _open():
            time.sleep(1.6)
            webbrowser.open("http://127.0.0.1:%d" % port)

        threading.Thread(target=_open, daemon=True).start()

    main(port=port)
