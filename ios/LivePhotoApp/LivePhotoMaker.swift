import Foundation
import AVFoundation
import Photos
import UIKit
import CoreImage
import ImageIO

// MARK: - 结果类型

enum ClipResult {
    case ok(URL, Double, Double)      // 文件, 起点, 时长
    case bad(String)
}

enum MakeResult {
    case ok
    case bad(String)
}

// MARK: - 生成实况照片

/// 全程用系统 API，不依赖 ffmpeg、不依赖电脑。
///
/// 实况照片不是「一张 JPG 挨着一个 MOV」，Photos 会校验三样东西：
///   1. 静图的 Apple MakerNote 里有 tag 17 = asset identifier
///   2. MOV 顶层有 com.apple.quicktime.content.identifier，值必须一模一样
///   3. MOV 里有一条 com.apple.quicktime.still-image-time 元数据轨，标记封面帧的位置
/// 三样缺一样就报 PHPhotosErrorDomain 3302（InvalidResource），所以这里必须自己写。
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

                case .ok(let clipURL, let begin, let seconds):

                    // 这一对文件的「身份证」，两边必须完全相同
                    let identifier = UUID().uuidString

                    report(progress, "正在取封面帧…")

                    guard let pair = stills(video: url,
                                            at: cover,
                                            identifier: identifier) else {
                        try? FileManager.default.removeItem(at: clipURL)
                        DispatchQueue.main.async {
                            completion(.bad("封面帧没取出来，换个时间点再试"))
                        }
                        return
                    }

                    report(progress, "正在封装实况视频…")

                    // 封面帧在这段裁剪里的位置
                    let stillAt = min(max(cover - begin, 0), max(seconds - 0.1, 0))
                    let stillTime = CMTime(seconds: stillAt, preferredTimescale: 600)

                    guard let motionURL = livePhotoMovie(clip: clipURL,
                                                         identifier: identifier,
                                                         stillTime: stillTime) else {
                        try? FileManager.default.removeItem(at: clipURL)
                        try? FileManager.default.removeItem(at: pair.heic)
                        try? FileManager.default.removeItem(at: pair.jpg)
                        DispatchQueue.main.async {
                            completion(.bad("实况视频封装失败，换一段视频试试"))
                        }
                        return
                    }

                    report(progress, "正在写入相册…")

                    save(motion: motionURL,
                         heic: pair.heic,
                         jpg: pair.jpg) { result in
                        try? FileManager.default.removeItem(at: clipURL)
                        try? FileManager.default.removeItem(at: motionURL)
                        try? FileManager.default.removeItem(at: pair.heic)
                        try? FileManager.default.removeItem(at: pair.jpg)
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
                    outcome = .ok(out, realBegin, seconds)
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

    // MARK: - 2. 封面帧（带 Apple MakerNote tag 17）

    private struct Stills {
        let heic: URL
        let jpg: URL
    }

    /// 同时出一份 HEIC 和一份 JPEG：iOS 15.1 之后 JPEG 容易把 MakerNote 丢掉，
    /// 所以优先用 HEIC，写库失败再用 JPEG 兜一次。
    private static func stills(video url: URL,
                               at second: Double,
                               identifier: String) -> Stills? {
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

        let ci = CIImage(cgImage: cg)
        let props: [String: Any] = [
            kCGImagePropertyMakerAppleDictionary as String: ["17": identifier]
        ]
        let propertied = ci.settingProperties(props)

        let ctx = CIContext()
        let cs = CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB()
        let stem = UUID().uuidString

        let heicURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("still-\(stem).heic")
        let jpgURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("still-\(stem).jpg")

        var heicOK = false
        if let data = ctx.heifRepresentation(of: propertied, colorSpace: cs, options: [:]) {
            heicOK = (try? data.write(to: heicURL)) != nil
        }

        var jpgOK = false
        if let data = ctx.jpegRepresentation(of: propertied, colorSpace: cs, options: [:]) {
            jpgOK = (try? data.write(to: jpgURL)) != nil
        }

        if heicOK && jpgOK { return Stills(heic: heicURL, jpg: jpgURL) }
        if jpgOK { return Stills(heic: jpgURL, jpg: jpgURL) }
        if heicOK { return Stills(heic: heicURL, jpg: heicURL) }
        return nil
    }

    // MARK: - 3. 封装成实况视频（content identifier + still-image-time 轨）

    private static func livePhotoMovie(clip: URL,
                                       identifier: String,
                                       stillTime: CMTime) -> URL? {

        let asset = AVURLAsset(url: clip)
        let out = FileManager.default.temporaryDirectory
            .appendingPathComponent("motion-\(UUID().uuidString).mov")
        try? FileManager.default.removeItem(at: out)

        guard let writer = try? AVAssetWriter(outputURL: out, fileType: .mov) else {
            return nil
        }

        // 顶层元数据：content identifier
        let cid = AVMutableMetadataItem()
        cid.key = AVMetadataKey.quickTimeMetadataKeyContentIdentifier as NSString
        cid.keySpace = AVMetadataKeySpace.quickTimeMetadata
        cid.value = identifier as NSString
        cid.dataType = kCMMetadataBaseDataType_UTF8 as String
        writer.metadata = [cid]

        // 元数据轨：still-image-time
        let spec: [String: Any] = [
            kCMMetadataFormatDescriptionMetadataSpecificationKey_Identifier as String:
                "mdta/com.apple.quicktime.still-image-time",
            kCMMetadataFormatDescriptionMetadataSpecificationKey_DataType as String:
                kCMMetadataBaseDataType_SInt8 as String
        ]
        var desc: CMFormatDescription?
        let status = CMMetadataFormatDescriptionCreateWithMetadataSpecifications(
            allocator: kCFAllocatorDefault,
            metadataType: kCMMetadataFormatType_Boxed,
            metadataSpecifications: [spec] as CFArray,
            formatDescriptionOut: &desc)

        guard status == noErr, let mdDesc = desc else { return nil }

        let metaInput = AVAssetWriterInput(mediaType: .metadata,
                                           outputSettings: nil,
                                           sourceFormatHint: mdDesc)
        metaInput.expectsMediaDataInRealTime = false
        let adaptor = AVAssetWriterInputMetadataAdaptor(assetWriterInput: metaInput)
        guard writer.canAdd(metaInput) else { return nil }
        writer.add(metaInput)

        // 视频/音频裸流直通
        guard let reader = try? AVAssetReader(asset: asset) else { return nil }

        var pipes: [(AVAssetWriterInput, AVAssetReaderTrackOutput)] = []
        var clipDuration = CMTime.zero

        for track in asset.tracks {
            guard track.mediaType == .video || track.mediaType == .audio else { continue }

            let output = AVAssetReaderTrackOutput(track: track, outputSettings: nil)
            guard reader.canAdd(output) else { continue }
            reader.add(output)

            let formats = track.formatDescriptions as! [CMFormatDescription]
            let input = AVAssetWriterInput(mediaType: track.mediaType,
                                           outputSettings: nil,
                                           sourceFormatHint: formats.first)
            input.expectsMediaDataInRealTime = false
            guard writer.canAdd(input) else { continue }
            writer.add(input)

            pipes.append((input, output))

            if track.mediaType == .video {
                let d = track.timeRange.duration
                clipDuration = CMTimeGetSeconds(d) > 0 ? d : asset.duration
            }
        }

        guard !pipes.isEmpty else { return nil }

        guard reader.startReading() else { return nil }
        guard writer.startWriting() else { return nil }
        writer.startSession(atSourceTime: .zero)

        let group = DispatchGroup()

        for (input, output) in pipes {
            group.enter()
            let queue = DispatchQueue(label: "mux-\(UUID().uuidString)")
            var left = false

            input.requestMediaDataWhenReady(on: queue) {
                while input.isReadyForMoreMediaData {
                    if let sample = output.copyNextSampleBuffer() {
                        if !input.append(sample) {
                            input.markAsFinished()
                            if !left { left = true; group.leave() }
                            return
                        }
                    } else {
                        input.markAsFinished()
                        if !left { left = true; group.leave() }
                        return
                    }
                }
            }
        }

        group.wait()

        if reader.status == .failed {
            writer.cancelWriting()
            try? FileManager.default.removeItem(at: out)
            return nil
        }

        // 封面帧位置的元数据样本
        let total = CMTimeGetSeconds(clipDuration)
        var startSeconds = CMTimeGetSeconds(stillTime)
        if !startSeconds.isFinite || startSeconds < 0 { startSeconds = 0 }
        if total > 0 && startSeconds > total - 0.05 { startSeconds = max(total - 0.05, 0) }

        let start = CMTime(seconds: startSeconds, preferredTimescale: 600)
        let end = total > 0 ? CMTime(seconds: Double(total), preferredTimescale: 600)
                            : CMTimeAdd(start, CMTime(value: 1, timescale: 30))

        let stillItem = AVMutableMetadataItem()
        stillItem.key = "com.apple.quicktime.still-image-time" as NSString
        stillItem.keySpace = AVMetadataKeySpace.quickTimeMetadata
        stillItem.value = 0 as NSNumber
        stillItem.dataType = kCMMetadataBaseDataType_SInt8 as String

        let range = CMTimeRange(start: start, end: CMTimeMaximum(end, CMTimeAdd(start, CMTime(value: 1, timescale: 600))))

        // 元数据输入可能还没就绪，等一会儿再塞，塞失败这条轨就空了 —— 相册照样报 3302
        var waited = 0
        while !metaInput.isReadyForMoreMediaData && waited < 400 {
            Thread.sleep(forTimeInterval: 0.005)
            waited += 1
        }
        _ = adaptor.append(AVTimedMetadataGroup(items: [stillItem], timeRange: range))
        metaInput.markAsFinished()

        writer.endSession(atSourceTime: CMTimeMaximum(end, start))

        let semaphore = DispatchSemaphore(value: 0)
        writer.finishWriting { semaphore.signal() }
        semaphore.wait()

        if writer.status != .completed {
            try? FileManager.default.removeItem(at: out)
            return nil
        }
        return out
    }

    // MARK: - 4. 写进相册

    private static func save(motion: URL,
                             heic: URL,
                             jpg: URL,
                             completion: @escaping (MakeResult) -> Void) {

        let onlyOne = heic == jpg

        attempt(photo: heic, motion: motion) { result in
            switch result {
            case .ok:
                completion(.ok)
            case .bad(let msg):
                guard !onlyOne else { completion(.bad(msg)); return }
                // HEIC 不行就换 JPEG 再试一次
                attempt(photo: jpg, motion: motion) { second in
                    switch second {
                    case .ok:
                        completion(.ok)
                    case .bad(let msg2):
                        completion(.bad(msg2))
                    }
                }
            }
        }
    }

    private static func attempt(photo: URL,
                                motion: URL,
                                completion: @escaping (MakeResult) -> Void) {

        let box = IDBox()
        let photoName = "LivePhoto." + photo.pathExtension
        let videoName = "LivePhoto.mov"

        PHPhotoLibrary.shared().performChanges({

            let request = PHAssetCreationRequest.forAsset()

            let photoOptions = PHAssetResourceCreationOptions()
            photoOptions.shouldMoveFile = false
            photoOptions.originalFilename = photoName
            request.addResource(with: .photo, fileURL: photo, options: photoOptions)

            let videoOptions = PHAssetResourceCreationOptions()
            videoOptions.shouldMoveFile = false
            videoOptions.originalFilename = videoName
            // .pairedVideo 就是「跟这张照片配对的视频」，系统据此合成实况照片
            request.addResource(with: .pairedVideo, fileURL: motion, options: videoOptions)

            box.value = request.placeholderForCreatedAsset?.localIdentifier

        }, completionHandler: { success, error in

            guard success else {
                let code = (error as NSError?)?.code ?? -1
                if code == 3302 {
                    completion(.bad("相册没认这对文件（3302）。换一段视频、或把封面帧往前挪一点再试"))
                } else {
                    completion(.bad(error?.localizedDescription ?? "写入相册失败"))
                }
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

    private final class IDBox {
        var value: String?
    }

    // MARK: - 小工具

    private static func report(_ callback: @escaping (String) -> Void, _ text: String) {
        DispatchQueue.main.async { callback(text) }
    }
}
