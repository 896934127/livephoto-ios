/* 实况图工厂 —— 前端逻辑 */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };

  var S = {
    vid: null,
    duration: 0,
    start: 0,
    end: 3,
    cover: 1.5,
    minLen: 0.2,
    busy: false,
    uploading: false
  };

  var el = {
    dropzone: $("dropzone"),
    fileInput: $("fileInput"),
    pickBtn: $("pickBtn"),
    upProgress: $("upProgress"),
    editor: $("editor"),
    video: $("video"),
    fileMeta: $("fileMeta"),
    resetBtn: $("resetBtn"),
    timeline: $("timeline"),
    tlStrip: $("tlStrip"),
    tlSel: $("tlSel"),
    tlCover: $("tlCover"),
    tlHead: $("tlHead"),
    shadeL: $("shadeL"),
    shadeR: $("shadeR"),
    inStart: $("inStart"),
    inEnd: $("inEnd"),
    durChip: $("durChip"),
    loopSel: $("loopSel"),
    markIn: $("markIn"),
    coverImg: $("coverImg"),
    coverMid: $("coverMid"),
    coverNow: $("coverNow"),
    maxEdge: $("maxEdge"),
    crf: $("crf"),
    goBtn: $("goBtn"),
    actionInfo: $("actionInfo"),
    resultList: $("resultList"),
    resEmpty: $("resEmpty"),
    resCount: $("resCount"),
    ffBadge: $("ffBadge"),
    toast: $("toast"),
    installTip: $("installTip"),
    installClose: $("installClose")
  };

  var IS_TOUCH = ("ontouchstart" in window) ||
                 (navigator.maxTouchPoints || 0) > 0;
  var IS_IOS = /iPad|iPhone|iPod/.test(navigator.userAgent) ||
               (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  var IS_STANDALONE = window.navigator.standalone === true ||
                      (window.matchMedia &&
                       window.matchMedia("(display-mode: standalone)").matches);

  /* ---------------- 通用 ---------------- */

  var toastTimer = null;
  function toast(msg, isErr) {
    el.toast.textContent = msg;
    el.toast.className = "toast show" + (isErr ? " err" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      el.toast.className = "toast" + (isErr ? " err" : "");
    }, 3200);
  }

  function fmtTime(t) {
    if (!isFinite(t) || t < 0) t = 0;
    var m = Math.floor(t / 60);
    var s = t - m * 60;
    return (m < 10 ? "0" + m : m) + ":" + (s < 10 ? "0" + s.toFixed(1) : s.toFixed(1));
  }

  function parseTime(str) {
    var m = String(str).trim().match(/^(\d+):(\d+(?:\.\d+)?)$/);
    if (m) return parseInt(m[1], 10) * 60 + parseFloat(m[2]);
    var n = parseFloat(str);
    return isNaN(n) ? null : n;
  }

  function fmtDur(t) {
    var m = Math.floor(t / 60);
    var s = Math.round(t % 60);
    return m + ":" + (s < 10 ? "0" + s : s);
  }

  function fmtSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
    return (bytes / 1024 / 1024).toFixed(2) + " MB";
  }

  function clamp(v, lo, hi) { return Math.min(Math.max(v, lo), hi); }

  /* ---------------- 环境 ---------------- */

  fetch("/api/status").then(function (r) { return r.json(); }).then(function (d) {
    if (d.ffmpeg) {
      el.ffBadge.textContent = "环境就绪";
      el.ffBadge.className = "badge ok";
      el.ffBadge.title = d.version || "";
    } else {
      el.ffBadge.textContent = "缺少 ffmpeg";
      el.ffBadge.className = "badge bad";
      toast("没找到 ffmpeg，视频处理会失败", true);
    }
  }).catch(function () {
    el.ffBadge.textContent = "服务未连接";
    el.ffBadge.className = "badge bad";
  });

  /* ---------------- 装到主屏幕 ---------------- */

  // 只在 iPhone 的 Safari 里、还没加到主屏幕时提示一次
  (function () {
    if (!IS_IOS || IS_STANDALONE) return;
    if (localStorage.getItem("lp_install_dismissed") === "1") return;
    el.installTip.classList.remove("hidden");

    el.installClose.addEventListener("click", function () {
      el.installTip.classList.add("hidden");
      try { localStorage.setItem("lp_install_dismissed", "1"); } catch (e) {}
    });
  })();

  // Service Worker：HTTP 局域网下浏览器会拒绝，失败了完全不影响使用
  if ("serviceWorker" in navigator && location.protocol !== "file:") {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js").catch(function () {});
    });
  }

  /* ---------------- 上传 ---------------- */

  function pick() { el.fileInput.click(); }

  el.pickBtn.addEventListener("click", function (e) { e.stopPropagation(); pick(); });
  el.dropzone.addEventListener("click", pick);

  ["dragenter", "dragover"].forEach(function (ev) {
    el.dropzone.addEventListener(ev, function (e) {
      e.preventDefault();
      el.dropzone.classList.add("hover");
    });
  });
  ["dragleave", "drop"].forEach(function (ev) {
    el.dropzone.addEventListener(ev, function (e) {
      e.preventDefault();
      el.dropzone.classList.remove("hover");
    });
  });
  el.dropzone.addEventListener("drop", function (e) {
    if (e.dataTransfer.files && e.dataTransfer.files.length) {
      upload(e.dataTransfer.files[0]);
    }
  });

  el.fileInput.addEventListener("change", function () {
    if (this.files && this.files[0]) upload(this.files[0]);
    this.value = "";
  });

  // 整页也接受拖放，防手滑丢到外面浏览器直接打开视频
  window.addEventListener("dragover", function (e) { e.preventDefault(); });
  window.addEventListener("drop", function (e) {
    e.preventDefault();
    if (S.uploading || !el.editor.classList.contains("hidden")) return;
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
      upload(e.dataTransfer.files[0]);
    }
  });

  function upload(file) {
    if (S.uploading) return;
    S.uploading = true;
    el.upProgress.classList.remove("hidden");
    var bar = el.upProgress.querySelector("i");
    var pct = el.upProgress.querySelector(".pct");

    var fd = new FormData();
    fd.append("file", file);

    var xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload");
    xhr.upload.onprogress = function (e) {
      if (e.lengthComputable) {
        var p = Math.round(e.loaded / e.total * 100);
        bar.style.width = p + "%";
        pct.textContent = p + "%";
      }
    };
    xhr.onload = function () {
      S.uploading = false;
      el.upProgress.classList.add("hidden");
      bar.style.width = "0%";
      var data = null;
      try { data = JSON.parse(xhr.responseText); } catch (err) { data = null; }
      if (xhr.status !== 200 || !data || data.error) {
        toast((data && data.error) || "上传失败", true);
        return;
      }
      onLoaded(data, file);
    };
    xhr.onerror = function () {
      S.uploading = false;
      el.upProgress.classList.add("hidden");
      toast("上传出错了，网络或服务断了", true);
    };
    xhr.send(fd);
  }

  /* ---------------- 载入视频 ---------------- */

  function onLoaded(data, file) {
    S.vid = data.vid;
    S.duration = data.info.duration || 0;
    S.start = 0;
    S.end = Math.min(3, S.duration);
    if (S.end <= 0) S.end = S.duration;
    S.cover = (S.start + S.end) / 2;

    el.dropzone.classList.add("hidden");
    el.editor.classList.remove("hidden");
    document.body.classList.add("editing");

    el.video.src = data.url;
    el.video.load();

    var info = data.info;
    el.fileMeta.textContent =
      (file ? file.name : "视频") + "　·　" +
      info.width + "×" + info.height + "　·　" +
      fmtDur(S.duration) + "　·　" +
      (info.fps ? info.fps.toFixed(1) + " fps" : "未知帧率");

    el.tlStrip.style.backgroundImage = "url(/api/filmstrip/" + S.vid + ")";

    setPreset(3);
    renderTimeline();
    refreshCover(true);
    el.actionInfo.textContent = "选好片段就能生成了";
    el.actionInfo.classList.remove("err");
  }

  el.resetBtn.addEventListener("click", function () {
    el.video.pause();
    el.video.removeAttribute("src");
    el.video.load();
    el.editor.classList.add("hidden");
    el.dropzone.classList.remove("hidden");
    document.body.classList.remove("editing");
    S.vid = null;
  });

  /* ---------------- 时间轴渲染 ---------------- */

  function pct(t) {
    if (!S.duration) return 0;
    return clamp(t / S.duration * 100, 0, 100);
  }

  function renderTimeline() {
    var a = pct(S.start), b = pct(S.end);
    el.tlSel.style.left = a + "%";
    el.tlSel.style.width = Math.max(b - a, 0.4) + "%";
    el.shadeL.style.width = a + "%";
    el.shadeR.style.width = (100 - b) + "%";
    el.tlCover.style.left = pct(S.cover) + "%";

    el.inStart.value = fmtTime(S.start);
    el.inEnd.value = fmtTime(S.end);
    el.durChip.textContent = (S.end - S.start).toFixed(2) + "s";

    document.querySelectorAll(".presets .chip").forEach(function (c) {
      var d = parseFloat(c.dataset.dur);
      c.classList.toggle("on", Math.abs(d - (S.end - S.start)) < 0.06);
    });
  }

  function renderPlayhead() {
    if (!S.duration) return;
    el.tlHead.style.left = pct(el.video.currentTime) + "%";
  }

  el.video.addEventListener("timeupdate", function () {
    renderPlayhead();
    if (el.loopSel.checked && !el.video.paused &&
        el.video.currentTime > S.end - 0.02) {
      el.video.currentTime = S.start;
    }
  });
  el.video.addEventListener("seeked", renderPlayhead);

  /* ---------------- 时间轴拖动 ---------------- */

  function timeAt(clientX) {
    var r = el.timeline.getBoundingClientRect();
    var x = clamp((clientX - r.left) / r.width, 0, 1);
    return x * S.duration;
  }

  var drag = null;

  el.timeline.addEventListener("pointerdown", function (e) {
    if (!S.duration) return;
    var t = timeAt(e.clientX);
    var target = e.target;
    var mode = null;

    if (target.classList.contains("tl-handle")) {
      mode = target.dataset.side === "l" ? "l" : "r";
    } else if (target === el.tlCover || target.parentNode === el.tlCover) {
      mode = "cover";
    } else if (target === el.tlSel || target.parentNode === el.tlSel) {
      mode = "move";
    } else {
      mode = "seek";
    }

    if (mode === "seek") {
      el.video.currentTime = t;
      renderPlayhead();
      return;
    }

    drag = {
      mode: mode,
      x0: e.clientX,
      t0: t,
      start0: S.start,
      end0: S.end,
      cover0: S.cover
    };
    if (mode === "move") el.tlSel.style.cursor = "grabbing";
    el.timeline.setPointerCapture(e.pointerId);
    e.preventDefault();
  });

  el.timeline.addEventListener("pointermove", function (e) {
    if (!drag) return;
    var t = timeAt(e.clientX);
    var len = drag.end0 - drag.start0;

    if (drag.mode === "l") {
      S.start = clamp(t, 0, drag.end0 - S.minLen);
    } else if (drag.mode === "r") {
      S.end = clamp(t, drag.start0 + S.minLen, S.duration);
    } else if (drag.mode === "move") {
      var dt = t - drag.t0;
      S.start = clamp(drag.start0 + dt, 0, S.duration - len);
      S.end = S.start + len;
    } else if (drag.mode === "cover") {
      S.cover = clamp(t, S.start, S.end);
      refreshCover(false);
    }

    if (drag.mode !== "cover") {
      S.cover = clamp(S.cover, S.start, S.end);
    }
    renderTimeline();
  });

  el.timeline.addEventListener("pointerup", function (e) {
    if (!drag) return;
    drag = null;
    el.tlSel.style.cursor = "grab";
    refreshCover(true);
  });

  el.timeline.addEventListener("pointercancel", function () {
    drag = null;
    el.tlSel.style.cursor = "grab";
  });

  /* ---------------- 起点终点输入 ---------------- */

  function applyStartInput() {
    var v = parseTime(el.inStart.value);
    if (v === null) { renderTimeline(); return; }
    v = clamp(v, 0, S.end - S.minLen);
    S.start = v;
    S.cover = clamp(S.cover, S.start, S.end);
    renderTimeline();
    refreshCover(true);
  }

  function applyEndInput() {
    var v = parseTime(el.inEnd.value);
    if (v === null) { renderTimeline(); return; }
    v = clamp(v, S.start + S.minLen, S.duration);
    S.end = v;
    S.cover = clamp(S.cover, S.start, S.end);
    renderTimeline();
    refreshCover(true);
  }

  el.inStart.addEventListener("blur", applyStartInput);
  el.inEnd.addEventListener("blur", applyEndInput);
  el.inStart.addEventListener("keydown", function (e) { if (e.key === "Enter") this.blur(); });
  el.inEnd.addEventListener("keydown", function (e) { if (e.key === "Enter") this.blur(); });

  /* ---------------- 时长预设 ---------------- */

  function setPreset(dur) {
    var len = Math.min(dur, S.duration);
    var start = S.start;
    if (start + len > S.duration) start = Math.max(S.duration - len, 0);
    S.start = start;
    S.end = Math.min(start + len, S.duration);
    S.cover = clamp(S.cover, S.start, S.end);
    if (S.cover <= S.start || S.cover >= S.end) S.cover = (S.start + S.end) / 2;
    renderTimeline();
    refreshCover(true);
  }

  document.querySelectorAll(".presets .chip").forEach(function (c) {
    c.addEventListener("click", function () {
      if (!S.duration) return;
      setPreset(parseFloat(c.dataset.dur));
    });
  });

  el.markIn.addEventListener("click", function () {
    if (!S.duration) return;
    var len = S.end - S.start;
    var t = el.video.currentTime;
    S.start = clamp(t, 0, S.duration - S.minLen);
    S.end = clamp(S.start + len, S.start + S.minLen, S.duration);
    S.cover = clamp(S.cover, S.start, S.end);
    renderTimeline();
    refreshCover(true);
  });

  /* ---------------- 封面帧 ---------------- */

  var coverTimer = null;
  var coverReq = 0;

  function refreshCover(now) {
    if (!S.vid) return;
    clearTimeout(coverTimer);
    var run = function () {
      var id = ++coverReq;
      var img = new Image();
      img.onload = function () {
        if (id !== coverReq) return;
        el.coverImg.style.backgroundImage = "url(" + img.src + ")";
        var hint = el.coverImg.querySelector(".cover-hint");
        if (hint) hint.remove();
      };
      img.src = "/api/frame/" + S.vid + "?t=" + S.cover.toFixed(3) + "&edge=400";
    };
    if (now) run();
    else coverTimer = setTimeout(run, 140);
  }

  el.coverMid.addEventListener("click", function () {
    S.cover = (S.start + S.end) / 2;
    renderTimeline();
    refreshCover(true);
  });

  el.coverNow.addEventListener("click", function () {
    S.cover = clamp(el.video.currentTime, S.start, S.end);
    renderTimeline();
    refreshCover(true);
  });

  /* ---------------- 生成 ---------------- */

  el.goBtn.addEventListener("click", function () {
    if (S.busy || !S.vid) return;

    var formats = [];
    document.querySelectorAll('input[name="fmt"]:checked').forEach(function (i) {
      formats.push(i.value);
    });
    if (!formats.length) {
      toast("至少选一种输出格式", true);
      return;
    }

    S.busy = true;
    el.goBtn.disabled = true;
    el.goBtn.innerHTML = '<span class="spin"></span> 生成中…';
    el.actionInfo.textContent = "正在处理，别关页面…";
    el.actionInfo.classList.remove("err");

    var payload = {
      vid: S.vid,
      start: S.start,
      duration: S.end - S.start,
      cover: S.cover,
      formats: formats,
      max_edge: parseInt(el.maxEdge.value, 10),
      crf: parseInt(el.crf.value, 10)
    };

    fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (!d || d.error) throw new Error((d && d.error) || "生成失败");
      renderResults(d.items, d.elapsed);
      el.actionInfo.textContent = "搞定，用了 " + d.elapsed + " 秒。右边点下载。";
    }).catch(function (err) {
      el.actionInfo.textContent = "出错了：" + err.message;
      el.actionInfo.classList.add("err");
      toast(err.message, true);
    }).then(function () {
      S.busy = false;
      el.goBtn.disabled = false;
      el.goBtn.innerHTML =
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
        '<path d="M5 12h13M13 6l6 6-6 6"></path></svg> 生成实况图';
    });
  });

  /* ---------------- 结果 ---------------- */

  var KIND_TAG = {
    motion: "MOTION",
    ios: "IOS",
    gif: "GIF",
    mp4: "MP4",
    still: "JPG"
  };

  function renderResults(items, elapsed) {
    el.resEmpty.classList.add("hidden");
    items.forEach(function (it) {
      var div = document.createElement("div");
      div.className = "item";

      var verify = "";
      if (it.kind === "ios") {
        verify = it.verified
          ? '<span class="verify">元数据已校验</span>'
          : '<span class="verify bad">MOV 元数据写入存疑</span>';
      }

      var body;
      if (it.files && it.files.length) {
        body = '<div class="file-list">' + it.files.map(function (f) {
          return '<div class="file-row">' +
              '<span class="file-tag">' + f.tag + "</span>" +
              '<a class="file-name" href="/api/download/' + f.name +
                '" title="' + f.note + '">' + f.name + "</a>" +
              '<span class="file-size">' + fmtSize(f.size) + "</span>" +
            "</div>";
        }).join("") + "</div>";
        if (verify) body += '<div class="item-foot">' + verify + "</div>";
      } else {
        body = '<div class="item-bottom">' +
            '<span class="item-size">' + fmtSize(it.size) + "　" + verify + "</span>" +
            '<a class="dl" href="' + it.download + '">下载</a>' +
          "</div>";
      }

      // 手机上走这个大按钮：优先系统分享面板，退路是直接下载
      var saveUrl, saveName, saveLabel;
      if (it.files && it.files.length) {
        saveUrl = "/api/download/" + it.files[0].name;
        saveName = it.files[0].name;
        saveLabel = it.kind === "ios" ? "存 .livp 到相册" : "保存到手机";
      } else {
        saveUrl = it.download;
        saveName = (it.name || it.download.split("/").pop());
        saveLabel = it.kind === "motion" ? "存实况图到手机"
                  : it.kind === "still" ? "存这张图"
                  : "保存到手机";
      }

      body += '<div class="save-wrap">' +
          '<button class="save-btn" data-url="' + saveUrl +
            '" data-name="' + saveName + '">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
            '<path d="M12 4v11M8 11l4 4 4-4M5 19h14"></path></svg>' +
            saveLabel +
          "</button>" +
        "</div>";

      div.innerHTML =
        '<div class="item-top">' +
          '<span class="item-name">' + it.label + "</span>" +
          '<span class="item-kind">' + (KIND_TAG[it.kind] || "") + "</span>" +
        "</div>" +
        '<div class="item-hint">' + (it.hint || "") + "</div>" +
        body;
      el.resultList.insertBefore(div, el.resultList.firstChild);
    });

    el.resCount.textContent = el.resultList.querySelectorAll(".item").length;

    // 手机上生成完，把结果推到眼前
    if (IS_TOUCH) {
      setTimeout(function () {
        var box = document.querySelector(".results");
        if (box) box.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 150);
    }
  }

  /* ---------------- 存到手机 ---------------- */

  function saveToPhone(url, name, btn) {
    var original = btn.innerHTML;
    var done = false;
    function restore() {
      btn.disabled = false;
      btn.innerHTML = original;
    }

    // 不支持分享就老老实实下载
    if (!navigator.canShare || !window.fetch) {
      window.location.href = url;
      return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span> 准备中…';

    // 网络太慢就别干等，直接走下载
    var timer = setTimeout(function () {
      if (done) return;
      done = true;
      restore();
      window.location.href = url;
    }, 9000);

    fetch(url).then(function (r) {
      if (!r.ok) throw new Error("取文件失败");
      return r.blob();
    }).then(function (blob) {
      if (done) return;
      clearTimeout(timer);

      var file = null;
      try {
        file = new File([blob], name, {
          type: blob.type || "application/octet-stream"
        });
      } catch (e) { file = null; }

      var shareable = false;
      try {
        shareable = !!file && navigator.canShare({ files: [file] });
      } catch (e) { shareable = false; }

      if (!shareable) {
        done = true;
        restore();
        window.location.href = url;
        return;
      }

      // iOS 的分享面板：能直接「存储到文件」，装了转换 App 也会出现在这里
      return navigator.share({ files: [file] }).then(function () {
        restore();
      });
    }).catch(function (err) {
      clearTimeout(timer);
      if (done) return;
      done = true;
      restore();
      if (err && err.name === "AbortError") return;   // 用户自己取消的
      window.location.href = url;
    });
  }

  el.resultList.addEventListener("click", function (e) {
    var node = e.target;
    while (node && node !== el.resultList && !(node.classList && node.classList.contains("save-btn"))) {
      node = node.parentNode;
    }
    if (!node || node === el.resultList) return;
    saveToPhone(node.dataset.url, node.dataset.name, node);
  });

})();
