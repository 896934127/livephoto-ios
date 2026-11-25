import SwiftUI

// MARK: - 配色

enum Theme {
    static let bg = Color(red: 13 / 255, green: 15 / 255, blue: 19 / 255)
    static let panel = Color(red: 20 / 255, green: 23 / 255, blue: 28 / 255)
    static let panel2 = Color(red: 25 / 255, green: 29 / 255, blue: 35 / 255)
    static let line = Color(red: 36 / 255, green: 42 / 255, blue: 51 / 255)
    static let text = Color(red: 230 / 255, green: 233 / 255, blue: 238 / 255)
    static let dim = Color(red: 134 / 255, green: 142 / 255, blue: 155 / 255)
    static let dim2 = Color(red: 98 / 255, green: 106 / 255, blue: 118 / 255)
    static let accent = Color(red: 76 / 255, green: 141 / 255, blue: 255 / 255)
    static let ok = Color(red: 78 / 255, green: 201 / 255, blue: 160 / 255)
}

// MARK: - 入口

@main
struct LivePhotoApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .preferredColorScheme(.dark)
        }
    }
}

// MARK: - 选中的视频

struct PickedVideo: Identifiable, Equatable {
    let id = UUID()
    let url: URL
    let duration: Double
    let size: CGSize

    static func == (lhs: PickedVideo, rhs: PickedVideo) -> Bool {
        lhs.id == rhs.id
    }
}

// MARK: - 根容器

struct ContentView: View {
    @State private var picked: PickedVideo?
    @State private var showPicker = false
    @State private var loading = false

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()

            if let video = picked {
                EditorView(video: video, onChangeVideo: {
                    picked = nil
                    showPicker = true
                })
            } else {
                HomeView(loading: loading) {
                    showPicker = true
                }
            }
        }
        .sheet(isPresented: $showPicker) {
            VideoPicker { url in
                showPicker = false
                guard let url = url else { return }
                loading = true
                VideoInfo.load(url: url) { info in
                    loading = false
                    if let info = info {
                        picked = info
                    }
                }
            }
        }
    }
}

// MARK: - 首页

struct HomeView: View {
    let loading: Bool
    let onPick: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            Spacer()

            RingMark()

            Text("实况图")
                .font(.system(size: 24, weight: .semibold))
                .foregroundColor(Theme.text)
                .padding(.top, 24)

            Text("从视频里截一段，存成实况照片")
                .font(.system(size: 13.5))
                .foregroundColor(Theme.dim)
                .padding(.top, 8)

            Spacer()

            VStack(spacing: 12) {
                Button {
                    onPick()
                } label: {
                    HStack(spacing: 8) {
                        if loading {
                            ProgressView()
                                .progressViewStyle(.circular)
                                .tint(.white)
                        } else {
                            Image(systemName: "photo.on.rectangle.angled")
                                .font(.system(size: 16, weight: .medium))
                        }
                        Text(loading ? "正在读取视频…" : "从相册选视频")
                            .font(.system(size: 16, weight: .medium))
                    }
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(Theme.accent)
                    .cornerRadius(13)
                }
                .disabled(loading)

                Text("选好后拖时间轴挑片段，生成会直接存进相册")
                    .font(.system(size: 12))
                    .foregroundColor(Theme.dim2)
                    .multilineTextAlignment(.center)
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 54)
        }
    }
}

struct RingMark: View {
    var body: some View {
        ZStack {
            Circle()
                .stroke(Theme.accent.opacity(0.3), lineWidth: 1)
                .frame(width: 92, height: 92)
            Circle()
                .stroke(Theme.accent, lineWidth: 2.5)
                .frame(width: 64, height: 64)
            Circle()
                .fill(Theme.accent)
                .frame(width: 18, height: 18)
        }
    }
}
