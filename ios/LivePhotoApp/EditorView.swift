import SwiftUI
import AVKit
import AVFoundation
import UIKit

// MARK: - 缩略图生成

enum Thumbnailer {

    static func make(url: URL, count: Int, height: CGFloat,
                     done: @escaping ([UIImage]) -> Void) {
        DispatchQueue.global(qos: .userInitiated).async {
            let asset = AVURLAsset(url: url)
            let total = CMTimeGetSeconds(asset.duration)

            guard total.isFinite, total > 0 else {
                DispatchQueue.main.async { done([]) }
                return
            }

            let gen = AVAssetImageGenerator(asset: asset)
            gen.appliesPreferredTrackTransform = true
            gen.maximumSize = CGSize(width: height * 3, height: height * 3)
            gen.requestedTimeToleranceBefore = CMTime(seconds: 0.4, preferredTimescale: 600)
            gen.requestedTimeToleranceAfter = CMTime(seconds: 0.4, preferredTimescale: 600)

            var images: [UIImage] = []
            for i in 0..<count {
                let t = total * (Double(i) + 0.5) / Double(count)
                let time = CMTime(seconds: t, preferredTimescale: 600)
                if let cg = try? gen.copyCGImage(at: time, actualTime: nil) {
                    images.append(UIImage(cgImage: cg))
                }
            }

            DispatchQueue.main.async { done(images) }
        }
    }

    static func one(url: URL, at second: Double, done: @escaping (UIImage?) -> Void) {
        DispatchQueue.global(qos: .userInitiated).async {
            let asset = AVURLAsset(url: url)
            let gen = AVAssetImageGenerator(asset: asset)
            gen.appliesPreferredTrackTransform = true
            gen.maximumSize = CGSize(width: 640, height: 640)
            gen.requestedTimeToleranceBefore = .zero
            gen.requestedTimeToleranceAfter = .zero

            let time = CMTime(seconds: max(second, 0), preferredTimescale: 600)
            let image = (try? gen.copyCGImage(at: time, actualTime: nil))
                .map { UIImage(cgImage: $0) }

            DispatchQueue.main.async { done(image) }
        }
    }
}

// MARK: - 时间轴选区

struct TimelineSelector: View {
    let thumbs: [UIImage]
    @Binding var start: Double
    @Binding var end: Double
    let total: Double
    let minSpan: Double
    var maxSpan: Double = 3.0

    private enum DragMode {
        case none, left, right, move
    }

    @State private var mode: DragMode = .none
    @State private var baseStart: Double = 0
    @State private var baseEnd: Double = 0
    @State private var anchorTime: Double = 0

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let h = geo.size.height
            let cell = w / CGFloat(Swift.max(thumbs.count, 1))
            let lx = CGFloat(clamped(start) / safeTotal) * w
            let rx = CGFloat(clamped(end) / safeTotal) * w

            ZStack(alignment: .topLeading) {

                // 缩略图条
                HStack(spacing: 0) {
                    ForEach(0..<Swift.max(thumbs.count, 1), id: \.self) { i in
                        Group {
                            if i < thumbs.count {
                                Image(uiImage: thumbs[i])
                                    .resizable()
                                    .aspectRatio(contentMode: .fill)
                            } else {
                                Rectangle().fill(Theme.panel2)
                            }
                        }
                        .frame(width: cell, height: h)
                        .clipped()
                    }
                }

                // 未选中的暗区
                Rectangle()
                    .fill(Color.black.opacity(0.66))
                    .frame(width: Swift.max(lx, 0), height: h)

                Rectangle()
                    .fill(Color.black.opacity(0.66))
                    .frame(width: Swift.max(w - rx, 0), height: h)
                    .offset(x: rx)

                // 选框
                Rectangle()
                    .stroke(Theme.accent, lineWidth: 2)
                    .frame(width: Swift.max(rx - lx, 1), height: h)
                    .offset(x: lx)

                // 两个手柄
                handle(height: h)
                    .offset(x: Swift.min(Swift.max(lx - 13, 0), w - 26))
                handle(height: h)
                    .offset(x: Swift.min(Swift.max(rx - 13, 0), w - 26))
            }
            .frame(width: w, height: h)
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { value in
                        let px = Swift.min(Swift.max(value.location.x, 0), w)
                        let t = Double(px / Swift.max(w, 1)) * safeTotal

                        if mode == .none {
                            let sl = value.startLocation.x
                            anchorTime = Double(Swift.min(Swift.max(sl, 0), w) / Swift.max(w, 1)) * safeTotal
                            baseStart = start
                            baseEnd = end
                            let dl = abs(sl - lx)
                            let dr = abs(sl - rx)

                            if dl < 32 && dl <= dr {
                                mode = .left
                            } else if dr < 32 {
                                mode = .right
                            } else {
                                mode = .move
                            }
                        }

                        switch mode {
                        case .left:
                            var v = Swift.min(Swift.max(t, 0), end - minSpan)
                            v = Swift.max(v, end - maxSpan)
                            start = Swift.max(v, 0)

                        case .right:
                            var v = Swift.max(Swift.min(t, safeTotal), start + minSpan)
                            v = Swift.min(v, start + maxSpan)
                            end = Swift.min(v, safeTotal)

                        case .move:
                            let span = baseEnd - baseStart
                            var ns = baseStart + (t - anchorTime)
                            ns = Swift.min(Swift.max(ns, 0), Swift.max(safeTotal - span, 0))
                            start = ns
                            end = ns + span

                        case .none:
                            break
                        }
                    }
                    .onEnded { _ in
                        mode = .none
                    }
            )
        }
        .frame(height: 76)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8).stroke(Theme.line, lineWidth: 1)
        )
    }

    private var safeTotal: Double {
        Swift.max(total, 0.01)
    }

    private func clamped(_ v: Double) -> Double {
        Swift.min(Swift.max(v, 0), safeTotal)
    }

    private func handle(height: CGFloat) -> some View {
        RoundedRectangle(cornerRadius: 4)
            .fill(Theme.accent)
            .frame(width: 26, height: height - 14)
            .overlay(
                VStack(spacing: 3) {
                    ForEach(0..<3, id: \.self) { _ in
                        Capsule()
                            .fill(Color.white.opacity(0.85))
                            .frame(width: 11, height: 2)
                    }
                }
            )
            .offset(y: 7)
    }
}

// MARK: - 编辑页

struct EditorView: View {
    let video: PickedVideo
    let onChangeVideo: () -> Void

    @State private var player: AVPlayer
    @State private var start: Double
    @State private var end: Double
    @State private var cover: Double

    @State private var thumbs: [UIImage] = []
    @State private var coverImage: UIImage?

    @State private var busy = false
    @State private var busyText = "正在处理…"
    @State private var message: String?
    @State private var isError = false

    init(video: PickedVideo, onChangeVideo: @escaping () -> Void) {
        self.video = video
        self.onChangeVideo = onChangeVideo

        let total = video.duration
        let length = Swift.min(3.0, total)

        _player = State(initialValue: AVPlayer(url: video.url))
        _start = State(initialValue: 0)
        _end = State(initialValue: Swift.max(length, Swift.min(0.5, total)))
        _cover = State(initialValue: Swift.max(length, Swift.min(0.5, total)) / 2)
    }

    var body: some View {
        VStack(spacing: 0) {
            header

            ScrollView(showsIndicators: false) {
                VStack(spacing: 12) {
                    playerCard
                    timelineCard
                    coverCard
                }
                .padding(.horizontal, 14)
                .padding(.top, 2)
                .padding(.bottom, 130)
            }
        }
        .overlay(alignment: .bottom) {
            bottomBar
        }
        .onAppear {
            loadThumbs()
            loadCover()
        }
        .onChange(of: cover) { _ in
            loadCover()
        }
    }

    // MARK: 顶栏

    private var header: some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 2) {
                Text("选片段")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundColor(Theme.text)
                Text(metaText)
                    .font(.system(size: 11.5))
                    .foregroundColor(Theme.dim2)
                    .lineLimit(1)
            }

            Spacer(minLength: 8)

            Button(action: {
                player.pause()
                onChangeVideo()
            }) {
                Text("换视频")
                    .font(.system(size: 13))
                    .foregroundColor(Theme.dim)
                    .padding(.horizontal, 13)
                    .padding(.vertical, 8)
                    .background(Theme.panel2)
                    .cornerRadius(8)
                    .overlay(
                        RoundedRectangle(cornerRadius: 8).stroke(Theme.line, lineWidth: 1)
                    )
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 6)
        .padding(.bottom, 10)
    }

    private var metaText: String {
        let w = Int(video.size.width)
        let h = Int(video.size.height)
        let total = Int(video.duration)
        let m = total / 60
        let s = total % 60
        let size = w > 0 ? "\(w)×\(h)　·　" : ""
        return size + "\(m):\(String(format: "%02d", s))"
    }

    // MARK: 播放器

    private var playerCard: some View {
        VideoPlayer(player: player)
            .frame(height: 208)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(
                RoundedRectangle(cornerRadius: 10).stroke(Theme.line, lineWidth: 1)
            )
    }

    // MARK: 时间轴

    private var timelineCard: some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack(spacing: 6) {
                Text("片段")
                    .font(.system(size: 12.5, weight: .medium))
                    .foregroundColor(Theme.dim)

                Spacer(minLength: 6)

                Text("\(timeText(start)) → \(timeText(end))")
                    .font(.system(size: 11.5, design: .monospaced))
                    .foregroundColor(Theme.text)

                Text(String(format: "%.2fs", Swift.max(end - start, 0)))
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(Theme.accent)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Theme.accent.opacity(0.13))
                    .cornerRadius(4)
            }

            TimelineSelector(thumbs: thumbs,
                             start: $start,
                             end: $end,
                             total: video.duration,
                             minSpan: 0.3,
                             maxSpan: LivePhotoMaker.maxSeconds)

            HStack(spacing: 8) {
                presetButton("1 秒", 1.0)
                presetButton("1.5 秒", 1.5)
                presetButton("3 秒", 3.0)
            }

            Text("实况照片最长 3 秒，拖到更长会自动卡住")
                .font(.system(size: 11))
                .foregroundColor(Theme.dim2)
        }
        .padding(14)
        .background(Theme.panel)
        .cornerRadius(12)
        .overlay(
            RoundedRectangle(cornerRadius: 12).stroke(Theme.line, lineWidth: 1)
        )
    }

    private func presetButton(_ title: String, _ len: Double) -> some View {
        let on = abs((end - start) - len) < 0.06

        return Button {
            applyPreset(len)
        } label: {
            Text(title)
                .font(.system(size: 12.5))
                .foregroundColor(on ? Theme.accent : Theme.dim)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 9)
                .background(on ? Theme.accent.opacity(0.13) : Theme.panel2)
                .cornerRadius(8)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(on ? Theme.accent.opacity(0.45) : Theme.line, lineWidth: 1)
                )
        }
    }

    // MARK: 封面帧

    private var coverCard: some View {
        HStack(alignment: .center, spacing: 13) {
            ZStack {
                if let img = coverImage {
                    Image(uiImage: img)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                } else {
                    Theme.panel2
                }
            }
            .frame(width: 100, height: 74)
            .clipShape(RoundedRectangle(cornerRadius: 7))
            .overlay(
                RoundedRectangle(cornerRadius: 7).stroke(Theme.line, lineWidth: 1)
            )

            VStack(alignment: .leading, spacing: 6) {
                Text("封面帧")
                    .font(.system(size: 12.5, weight: .medium))
                    .foregroundColor(Theme.dim)

                Text("相册里点开看到的就是这一帧")
                    .font(.system(size: 11.5))
                    .foregroundColor(Theme.dim2)
                    .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 8) {
                    smallButton("取中间") {
                        cover = (start + end) / 2
                    }
                    smallButton("取当前") {
                        let t = CMTimeGetSeconds(player.currentTime())
                        if t.isFinite {
                            cover = Swift.min(Swift.max(t, start), end)
                        }
                    }
                }
                .padding(.top, 2)
            }

            Spacer(minLength: 0)
        }
        .padding(14)
        .background(Theme.panel)
        .cornerRadius(12)
        .overlay(
            RoundedRectangle(cornerRadius: 12).stroke(Theme.line, lineWidth: 1)
        )
    }

    private func smallButton(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 11.5))
                .foregroundColor(Theme.dim)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Theme.panel2)
                .cornerRadius(7)
                .overlay(
                    RoundedRectangle(cornerRadius: 7).stroke(Theme.line, lineWidth: 1)
                )
        }
    }

    // MARK: 底部操作

    private var bottomBar: some View {
        VStack(spacing: 9) {
            if let msg = message {
                HStack(spacing: 6) {
                    Image(systemName: isError ? "exclamationmark.circle" : "checkmark.circle.fill")
                        .font(.system(size: 12))
                    Text(msg)
                        .font(.system(size: 12))
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .foregroundColor(isError ? Color(red: 1, green: 0.42, blue: 0.42) : Theme.ok)
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            Button(action: make) {
                HStack(spacing: 8) {
                    if busy {
                        ProgressView()
                            .progressViewStyle(.circular)
                            .tint(.white)
                    } else {
                        Image(systemName: "sparkles")
                            .font(.system(size: 15, weight: .medium))
                    }

                    Text(busy ? busyText : "生成并存入相册")
                        .font(.system(size: 15.5, weight: .medium))
                }
                .foregroundColor(busy ? Theme.dim : .white)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 15)
                .background(busy ? Theme.panel2 : Theme.accent)
                .cornerRadius(12)
            }
            .disabled(busy)
        }
        .padding(.horizontal, 14)
        .padding(.top, 10)
        .padding(.bottom, 6)
        .background(Theme.bg.opacity(0.97))
    }

    // MARK: 动作

    private func loadThumbs() {
        Thumbnailer.make(url: video.url, count: 9, height: 90) { images in
            thumbs = images
        }
    }

    private func loadCover() {
        Thumbnailer.one(url: video.url, at: cover) { image in
            coverImage = image
        }
    }

    private func timeText(_ t: Double) -> String {
        let m = Int(t) / 60
        let s = t - Double(m * 60)
        return String(format: "%02d:%04.1f", m, s)
    }

    private func applyPreset(_ len: Double) {
        let total = video.duration
        let l = Swift.min(len, total)
        var s = start
        if s + l > total { s = Swift.max(total - l, 0) }

        start = s
        end = s + l

        if cover <= s || cover >= s + l {
            cover = s + l / 2
        }
    }

    private func make() {
        guard !busy else { return }

        busy = true
        busyText = "正在准备…"
        message = nil

        player.pause()

        LivePhotoMaker.make(video: video.url,
                            start: start,
                            duration: end - start,
                            cover: cover,
                            progress: { text in
                                busyText = text
                            },
                            completion: { result in
                                busy = false
                                busyText = "正在处理…"

                                switch result {
                                case .ok:
                                    isError = false
                                    message = "已经存进相册了，去「照片」里看"
                                case .bad(let msg):
                                    isError = true
                                    message = msg
                                }
                            })
    }
}
