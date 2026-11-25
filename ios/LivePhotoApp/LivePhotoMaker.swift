import Foundation
import AVFoundation
import Photos
import UIKit

// MARK: - 结果类型

enum ClipResult {
    case ok(URL)
    case bad(String)
}

enum MakeResult {
    case ok
    case bad(String)
}

// MARK: - 生成实况照片

/// 全程用系统 API，不依赖 ffmpeg、不依赖电脑：
///   1. AVAssetExportSession 裁出 3 秒以内的 MOV
///   2. AVAssetImageGenerator 取封面帧存 JPG
///   3. PHAssetCreationRequest 把 .photo + .pairedVideo 一起写入 —— 这就是实况照片
enum LivePhotoMaker {

    /// 实况照片的标准时长上限
    static let maxSeconds: Double = 3.0

    static func make(video url: URL,
                     start: Double,
                     duration: Double,
                     cover: Double,
                     progress: @escaping (String) -> Void,
                     completion: @escaping (MakeResult) -> Void) {

        // 要读回刚写入的资源来校验，所以请求读写权限
        PHPhotoLibrary.requestAuthorization(for: .readWrite) { status in

            guard status == .authorized || status == .limited else {
                DispatchQueue.main.async {
                    completion(.bad("没有相册权限。去「设置 → 实况图 → 照片」里打开"))
                }
                return
            }

            DispatchQueue.global(qos: .userInitiated).async {

                report(progress, "正在裁剪视频…")

                switch clip(video: url, start: start, duration: duration) {

                case .bad(let msg):
                    DispatchQueue.main.async { completion(.bad(msg)) }

                case .ok(let movURL):
                    report(progress, "正在取封面帧…")

                    guard let jpgURL = stillImage(video: url, at: cover) else {
                        try? FileManager.default.removeItem(at: movURL)
                        DispatchQueue.main.async {
                            completion(.bad("封面帧没取出来，换个时间点再试"))
                        }
                        return
                    }

                    report(progress, "正在写入相册…")

                    saveToLibrary(mov: movURL, jpg: jpgURL) { result in
                        try? FileManager.default.removeItem(at: movURL)
                        try? FileManager.default.removeItem(at: jpgURL)
                        DispatchQueue.main.async { completion(result) }
                    }
                }
            }
        }
    }

    // MARK: - 1. 裁剪

    private static func clip(video url: URL,
                             start: Double,
                             duration: Double) -> ClipResult {
        let asset = AVURLAsset(url: url)

        guard let track = asset.tracks(withMediaType: .video).first else {
            return .bad("这个文件里没有视频轨")
        }

        let natural = track.naturalSize.applying(track.preferredTransform)
        let longEdge = max(abs(natural.width), abs(natural.height))

        var presets: [String] = []
        if longEdge > 1920 {
            presets.append(AVAssetExportPreset1920x1080)
        }
        presets.append(AVAssetExportPresetHighestQuality)
        presets.append(AVAssetExportPreset1280x720)
        presets.append(AVAssetExportPresetMediumQuality)

        var session: AVAssetExportSession?
        for name in presets {
            if let s = AVAssetExportSession(asset: asset, presetName: name) {
                session = s
                break
            }
        }

        guard let exporter = session else {
            return .bad("这个视频的编码解不了，换一个试试")
        }

        let seconds = min(max(duration, 0.3), maxSeconds)
        let begin = max(start, 0)
        let total = CMTimeGetSeconds(asset.duration)

        var realBegin = begin
        if total > 0 && realBegin + seconds > total {
            realBegin = max(total - seconds, 0)
        }

        let out = FileManager.default.temporaryDirectory
            .appendingPathComponent("clip-\(UUID().uuidString).mov")

        try? FileManager.default.removeItem(at: out)

        exporter.outputURL = out
        exporter.outputFileType = .mov
        exporter.shouldOptimizeForNetworkUse = false
        exporter.timeRange = CMTimeRange(
            start: CMTime(seconds: realBegin, preferredTimescale: 600),
            duration: CMTime(seconds: seconds, preferredTimescale: 600))

        let semaphore = DispatchSemaphore(value: 0)
        var outcome: ClipResult = .bad("裁剪没有完成")

        exporter.exportAsynchronously {
            switch exporter.status {
            case .completed:
                if FileManager.default.fileExists(atPath: out.path) {
                    outcome = .ok(out)
                } else {
                    outcome = .bad("裁剪完了但文件没生成")
                }
            case .failed:
                outcome = .bad(exporter.error?.localizedDescription ?? "视频裁剪失败")
            case .cancelled:
                outcome = .bad("裁剪被中断了")
            default:
                outcome = .bad("视频裁剪意外结束")
            }
            semaphore.signal()
        }

        semaphore.wait()
        return outcome
    }

    // MARK: - 2. 封面帧

    private static func stillImage(video url: URL, at second: Double) -> URL? {
        let asset = AVURLAsset(url: url)
        let gen = AVAssetImageGenerator(asset: asset)
        gen.appliesPreferredTrackTransform = true
        gen.requestedTimeToleranceBefore = .zero
        gen.requestedTimeToleranceAfter = .zero
        gen.maximumSize = CGSize(width: 1600, height: 1600)

        let total = CMTimeGetSeconds(asset.duration)
        var t = max(second, 0)
        if total > 0 { t = min(t, max(total - 0.05, 0)) }

        let time = CMTime(seconds: t, preferredTimescale: 600)

        guard let cg = try? gen.copyCGImage(at: time, actualTime: nil) else {
            return nil
        }

        let image = UIImage(cgImage: cg)
        guard let data = image.jpegData(compressionQuality: 0.92) else {
            return nil
        }

        let out = FileManager.default.temporaryDirectory
            .appendingPathComponent("still-\(UUID().uuidString).jpg")

        do {
            try data.write(to: out)
            return out
        } catch {
            return nil
        }
    }

    // MARK: - 3. 写进相册（关键一步）

    private final class IDBox {
        var value: String?
    }

    private static func saveToLibrary(mov: URL,
                                      jpg: URL,
                                      completion: @escaping (MakeResult) -> Void) {
        let box = IDBox()

        PHPhotoLibrary.shared().performChanges({

            let request = PHAssetCreationRequest.forAsset()

            let photoOptions = PHAssetResourceCreationOptions()
            photoOptions.shouldMoveFile = false
            photoOptions.originalFilename = "LivePhoto.jpg"
            request.addResource(with: .photo, fileURL: jpg, options: photoOptions)

            let videoOptions = PHAssetResourceCreationOptions()
            videoOptions.shouldMoveFile = false
            videoOptions.originalFilename = "LivePhoto.mov"
            // .pairedVideo 就是「跟这张照片配对的视频」，系统据此合成实况照片
            request.addResource(with: .pairedVideo, fileURL: mov, options: videoOptions)

            box.value = request.placeholderForCreatedAsset?.localIdentifier

        }, completionHandler: { success, error in

            guard success else {
                let msg = error?.localizedDescription ?? "写入相册失败"
                completion(.bad(msg))
                return
            }

            // 读回来验证：真的被识别成实况照片了吗
            guard let identifier = box.value else {
                completion(.bad("写进去了，但拿不到照片标识"))
                return
            }

            let fetched = PHAsset.fetchAssets(withLocalIdentifiers: [identifier], options: nil)
            guard let asset = fetched.firstObject else {
                completion(.bad("写进去了，但相册里找不到这张"))
                return
            }

            if asset.mediaSubtypes.contains(.photoLive) {
                completion(.ok)
            } else {
                completion(.bad("相册只存成了普通照片，没认成实况。换一段视频试试"))
            }
        })
    }

    // MARK: - 小工具

    private static func report(_ callback: @escaping (String) -> Void, _ text: String) {
        DispatchQueue.main.async { callback(text) }
    }
}
