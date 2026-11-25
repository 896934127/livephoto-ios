/* 实况图工厂 —— Service Worker
 *
 * 只缓存界面壳子，接口一律走网络。
 * 注意：局域网 HTTP 下浏览器不会允许注册 SW，注册失败不影响任何功能；
 * 部署到 https 之后它才会生效，负责离线打开界面。
 */
const CACHE = "livephoto-shell-v1";

const SHELL = [
  "/",
  "/static/style.css",
  "/static/app.js",
  "/static/manifest.json",
  "/static/icons/apple-touch-icon.png",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png"
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE)
      .then((c) => c.addAll(SHELL))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;   // 视频、导出结果不做缓存

  e.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
        }
        return res;
      })
      .catch(() =>
        caches.match(req).then((hit) => hit || caches.match("/"))
      )
  );
});
