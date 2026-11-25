import SwiftUI

/// 连不上电脑时的引导页。
/// 这个 App 的计算都在电脑上，所以连不上是常态之一，必须说清楚怎么办。
struct SetupView: View {
    let message: String
    let onConnect: (String) -> Void
    let onRetry: () -> Void

    @State private var addr: String
    @FocusState private var focused: Bool

    init(message: String,
         initial: String,
         onConnect: @escaping (String) -> Void,
         onRetry: @escaping () -> Void) {
        self.message = message
        self.onConnect = onConnect
        self.onRetry = onRetry
        let start = initial
            .replacingOccurrences(of: "http://", with: "")
            .trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        _addr = State(initialValue: start.isEmpty ? "172.20.10.2:8770" : start)
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                Spacer().frame(height: 54)

                RingMark()

                Text("连不上电脑")
                    .font(.system(size: 21, weight: .semibold))
                    .foregroundColor(Theme.text)
                    .padding(.top, 22)

                Text(message)
                    .font(.system(size: 13))
                    .foregroundColor(Theme.dim2)
                    .multilineTextAlignment(.center)
                    .padding(.top, 7)
                    .padding(.horizontal, 30)

                // 三步检查
                VStack(alignment: .leading, spacing: 0) {
                    StepRow(index: "1",
                            title: "电脑上把服务开着",
                            detail: "双击「启动.bat」，出来的黑窗口别关")
                    Divider().overlay(Theme.line).padding(.leading, 44)
                    StepRow(index: "2",
                            title: "手机和电脑连着",
                            detail: "插着数据线，或者连同一个 WiFi")
                    Divider().overlay(Theme.line).padding(.leading, 44)
                    StepRow(index: "3",
                            title: "电脑弹窗要点允许",
                            detail: "「Windows 安全中心」问是否允许访问，点允许")
                }
                .background(Theme.panel)
                .cornerRadius(12)
                .overlay(
                    RoundedRectangle(cornerRadius: 12).stroke(Theme.line, lineWidth: 1)
                )
                .padding(.horizontal, 20)
                .padding(.top, 26)

                // 手填地址
                VStack(alignment: .leading, spacing: 9) {
                    Text("电脑地址")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(Theme.dim)

                    HStack(spacing: 0) {
                        Text("http://")
                            .font(.system(size: 14, design: .monospaced))
                            .foregroundColor(Theme.dim2)
                            .padding(.leading, 12)

                        TextField("172.20.10.2:8770", text: $addr)
                            .font(.system(size: 15, design: .monospaced))
                            .foregroundColor(Theme.text)
                            .keyboardType(.URL)
                            .autocapitalization(.none)
                            .disableAutocorrection(true)
                            .textFieldStyle(.plain)
                            .focused($focused)
                            .padding(.vertical, 11)
                            .padding(.trailing, 12)
                    }
                    .background(Theme.panel2)
                    .cornerRadius(9)
                    .overlay(
                        RoundedRectangle(cornerRadius: 9)
                            .stroke(focused ? Theme.accent.opacity(0.6) : Theme.line, lineWidth: 1)
                    )

                    Text("电脑上那个黑窗口里会打印「手机上打开：http://…」，照着填就行")
                        .font(.system(size: 11.5))
                        .foregroundColor(Theme.dim2)
                        .lineSpacing(2)
                }
                .padding(.horizontal, 20)
                .padding(.top, 20)

                Button {
                    focused = false
                    let cleaned = addr.trimmingCharacters(in: .whitespacesAndNewlines)
                    if !cleaned.isEmpty {
                        onConnect(cleaned)
                    }
                } label: {
                    Text("连接")
                        .font(.system(size: 15, weight: .medium))
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 13)
                        .background(Theme.accent)
                        .cornerRadius(10)
                }
                .padding(.horizontal, 20)
                .padding(.top, 18)

                Button {
                    onRetry()
                } label: {
                    Text("自动重新扫描")
                        .font(.system(size: 14))
                        .foregroundColor(Theme.dim)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .background(Theme.panel2)
                        .cornerRadius(10)
                        .overlay(
                            RoundedRectangle(cornerRadius: 10).stroke(Theme.line, lineWidth: 1)
                        )
                }
                .padding(.horizontal, 20)
                .padding(.top, 10)

                Spacer().frame(height: 40)
            }
        }
        .background(Theme.bg)
        .onTapGesture { focused = false }
    }
}

private struct RingMark: View {
    var body: some View {
        ZStack {
            Circle()
                .stroke(Theme.accent.opacity(0.35), lineWidth: 1)
                .frame(width: 66, height: 66)
            Circle()
                .stroke(Theme.accent, lineWidth: 2.5)
                .frame(width: 46, height: 46)
            Circle()
                .fill(Theme.accent)
                .frame(width: 13, height: 13)
        }
    }
}

private struct StepRow: View {
    let index: String
    let title: String
    let detail: String

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Text(index)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(Theme.accent)
                .frame(width: 20, height: 20)
                .background(Theme.accent.opacity(0.14))
                .clipShape(Circle())

            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.system(size: 13.5, weight: .medium))
                    .foregroundColor(Theme.text)
                Text(detail)
                    .font(.system(size: 12))
                    .foregroundColor(Theme.dim2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
    }
}
