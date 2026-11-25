import SwiftUI
import Photos
import PhotosUI
import AVFoundation
import UniformTypeIdentifiers

// MARK: - 系统相册选择器（只挑视频）

struct VideoPicker: UIViewControllerRepresentable {
    let onPick: (URL?) -> Void

    func makeUIViewController(context: Context) -> PHPickerViewController {
        var conf = PHPickerConfiguration(photoLibrary: PHPhotoLibrary.shared())
        conf.filter = .videos
        conf.selectionLimit = 1
        conf.preferredAssetRepresentationMode = .current

        let vc = PHPickerViewController(configuration: conf)
        vc.delegate = context.coordinator
        return vc
    }

    func updateUIViewController(_ uiViewController: PHPickerViewController, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(onPick: onPick)
    }

    final class Coordinator: NSObject, PHPickerViewControllerDelegate {
        private let onPick: (URL?) -> Void

        init(onPick: @escaping (URL?) -> Void) {
            self.onPick = onPick
        }

        func picker(_ picker: PHPickerViewController,
                    didFinishPicking results: [PHPickerResult]) {
            guard let provider = results.first?.itemProvider else {
                onPick(nil)
                return
            }

            let typeID = UTType.movie.identifier
            guard provider.hasItemConformingToTypeIdentifier(typeID) else {
                onPick(nil)
                return
            }

            provider.loadFileRepresentation(forTypeIdentifier: typeID) { url, _ in
                guard let url = url else {
                    DispatchQueue.main.async { self.onPick(nil) }
                    return
                }

                // 这个 URL 在回调返回后马上就失效了，必须先拷进自己目录
                let ext = url.pathExtension.isEmpty ? "mov" : url.pathExtension
                let dest = FileManager.default.temporaryDirectory
                    .appendingPathComponent("src-\(UUID().uuidString).\(ext)")

                do {
                    try FileManager.default.copyItem(at: url, to: dest)
                    DispatchQueue.main.async { self.onPick(dest) }
                } catch {
                    DispatchQueue.main.async { self.onPick(nil) }
                }
            }
        }
    }
}

// MARK: - 读视频基本信息

enum VideoInfo {

    static func load(url: URL, completion: @escaping (PickedVideo?) -> Void) {
        DispatchQueue.global(qos: .userInitiated).async {
            let asset = AVURLAsset(url: url)
            let seconds = CMTimeGetSeconds(asset.duration)

            guard seconds.isFinite, seconds > 0.3 else {
                DispatchQueue.main.async { completion(nil) }
                return
            }

            var size = CGSize(width: 0, height: 0)
            if let track = asset.tracks(withMediaType: .video).first {
                let natural = track.naturalSize
                let rotated = natural.applying(track.preferredTransform)
                size = CGSize(width: abs(rotated.width), height: abs(rotated.height))
            }

            let info = PickedVideo(url: url, duration: seconds, size: size)
            DispatchQueue.main.async { completion(info) }
        }
    }
}
