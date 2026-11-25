import SwiftUI
import WebKit

/// 把网页装进 WKWebView，并接管两件网页自己干不了的事：
/// 1. 下载（.livp 落到「文件」App）
/// 2. 分享面板（WKWebView 没有 navigator.share，网页点保存会走 location.href，
///    在这里被截住，弹原生的分享面板，用户可以直接「存储到照片」）
struct WebShell: UIViewRepresentable {
    let urlString: String
    let reloadToken: UUID

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> WKWebView {
        let conf = WKWebViewConfiguration()
        conf.allowsInlineMediaPlayback = true
        conf.mediaTypesRequiringUserActionForPlayback = []
        conf.defaultWebpagePreferences.allowsContentJavaScript = true
        conf.preferences.javaScriptCanOpenWindowsAutomatically = true

        let wv = WKWebView(frame: .zero, configuration: conf)
        wv.navigationDelegate = context.coordinator
        wv.uiDelegate = context.coordinator
        wv.allowsBackForwardNavigationGestures = false
        wv.allowsLinkPreview = false
        wv.scrollView.contentInsetAdjustmentBehavior = .never
        wv.isOpaque = false
        wv.backgroundColor = UIColor(red: 13 / 255, green: 15 / 255, blue: 19 / 255, alpha: 1)
        wv.scrollView.backgroundColor = wv.backgroundColor

        context.coordinator.attach(wv)
        context.coordinator.load(urlString)
        return wv
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {
        if context.coordinator.token != reloadToken {
            context.coordinator.token = reloadToken
            context.coordinator.load(urlString)
        }
    }

    // MARK: - Coordinator

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
        private weak var webView: WKWebView?
        var token: UUID?

        /// download -> 目标文件
        private var destinations: [ObjectIdentifier: URL] = [:]

        func attach(_ wv: WKWebView) {
            webView = wv
        }

        func load(_ urlString: String) {
            guard let url = URL(string: urlString) else { return }
            var req = URLRequest(url: url)
            req.timeoutInterval = 20
            req.cachePolicy = .reloadIgnoringLocalCacheData
            webView?.load(req)
        }

        // MARK: 导航策略（把下载截下来）

        func webView(_ webView: WKWebView,
                     decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            if navigationAction.shouldPerformDownload {
                decisionHandler(.download)
            } else {
                decisionHandler(.allow)
            }
        }

        func webView(_ webView: WKWebView,
                     decidePolicyFor navigationResponse: WKNavigationResponse,
                     decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
            // livp / jpg / mov 这些 WKWebView 显示不了，直接走下载
            if navigationResponse.canShowMIMEType {
                decisionHandler(.allow)
            } else {
                decisionHandler(.download)
            }
        }

        func webView(_ webView: WKWebView,
                     navigationAction: WKNavigationAction,
                     didBecome download: WKDownload) {
            download.delegate = self
        }

        func webView(_ webView: WKWebView,
                     navigationResponse: WKNavigationResponse,
                     didBecome download: WKDownload) {
            download.delegate = self
        }

        // MARK: 下载落盘

        func download(_ download: WKDownload,
                      decideDestinationUsing response: URLResponse,
                      suggestedFilename: String,
                      completionHandler: @escaping (URL?) -> Void) {
            guard let dir = FileManager.default.urls(for: .documentDirectory,
                                                     in: .userDomainMask).first else {
                completionHandler(nil)
                return
            }

            var name = suggestedFilename.isEmpty ? "livephoto.bin" : suggestedFilename
            // 文件名里带路径分隔符会写失败
            name = name.replacingOccurrences(of: "/", with: "_")
                       .replacingOccurrences(of: ":", with: "_")

            var dest = dir.appendingPathComponent(name)
            if FileManager.default.fileExists(atPath: dest.path) {
                let base = dest.deletingPathExtension().lastPathComponent
                let ext = dest.pathExtension
                let stamp = Int(Date().timeIntervalSince1970)
                let newName = ext.isEmpty ? "\(base)-\(stamp)" : "\(base)-\(stamp).\(ext)"
                dest = dir.appendingPathComponent(newName)
            }

            destinations[ObjectIdentifier(download)] = dest
            completionHandler(dest)
        }

        func downloadDidFinish(_ download: WKDownload) {
            guard let file = destinations[ObjectIdentifier(download)] else { return }
            destinations.removeValue(forKey: ObjectIdentifier(download))

            if FileManager.default.fileExists(atPath: file.path) {
                presentShare(file)
            }
        }

        func download(_ download: WKDownload,
                      didFailWithError error: Error,
                      resumeData: Data?) {
            destinations.removeValue(forKey: ObjectIdentifier(download))
        }

        // MARK: 原生分享（关键：这里才能「存储到照片」）

        private func presentShare(_ file: URL) {
            DispatchQueue.main.async {
                guard let top = Self.topViewController() else { return }

                let ac = UIActivityViewController(activityItems: [file],
                                                  applicationActivities: nil)
                if let pop = ac.popoverPresentationController {
                    pop.sourceView = top.view
                    pop.sourceRect = CGRect(x: top.view.bounds.midX,
                                            y: top.view.bounds.midY,
                                            width: 0, height: 0)
                    pop.permittedArrowDirections = []
                }
                top.present(ac, animated: true)
            }
        }

        private static func topViewController() -> UIViewController? {
            let scenes = UIApplication.shared.connectedScenes
                .compactMap { $0 as? UIWindowScene }

            let windows = scenes.flatMap { $0.windows }
            guard let key = windows.first(where: { $0.isKeyWindow }) ?? windows.first else {
                return nil
            }

            var vc = key.rootViewController
            while let presented = vc?.presentedViewController {
                vc = presented
            }
            return vc
        }

        // MARK: 网页里的 alert / confirm 得有反应，否则会卡住

        func webView(_ webView: WKWebView,
                     runJavaScriptAlertPanelWithMessage message: String,
                     initiatedByFrame frame: WKFrameInfo,
                     completionHandler: @escaping () -> Void) {
            DispatchQueue.main.async {
                guard let top = Self.topViewController() else {
                    completionHandler()
                    return
                }
                let ac = UIAlertController(title: nil, message: message, preferredStyle: .alert)
                ac.addAction(UIAlertAction(title: "好", style: .default) { _ in
                    completionHandler()
                })
                top.present(ac, animated: true)
            }
        }

        func webView(_ webView: WKWebView,
                     runJavaScriptConfirmPanelWithMessage message: String,
                     initiatedByFrame frame: WKFrameInfo,
                     completionHandler: @escaping (Bool) -> Void) {
            DispatchQueue.main.async {
                guard let top = Self.topViewController() else {
                    completionHandler(false)
                    return
                }
                let ac = UIAlertController(title: nil, message: message, preferredStyle: .alert)
                ac.addAction(UIAlertAction(title: "取消", style: .cancel) { _ in
                    completionHandler(false)
                })
                ac.addAction(UIAlertAction(title: "确定", style: .default) { _ in
                    completionHandler(true)
                })
                top.present(ac, animated: true)
            }
        }
    }
}
