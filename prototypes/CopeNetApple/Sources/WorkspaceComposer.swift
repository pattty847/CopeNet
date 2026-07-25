import SwiftUI

struct ComposerPanel: View {
    let agent: AgentProfile
    @Binding var prompt: String
    let isLive: Bool
    let send: () -> Void

    var body: some View {
        VStack(spacing: 10) {
            HStack(alignment: .bottom, spacing: 10) {
                TextField(
                    isLive ? "Message the agent…" : "Send the first message to create this session…",
                    text: $prompt,
                    axis: .vertical
                )
                .lineLimit(1...4)
                .textFieldStyle(.plain)
                .font(.callout)
                .onSubmit(send)

                Button(action: {}) { Image(systemName: "paperclip") }
                    .buttonStyle(ComposerIconStyle())
                    .help("Attach")
                Button(action: {}) { Image(systemName: "mic") }
                    .buttonStyle(ComposerIconStyle())
                    .help("Voice Input")
                Button(action: {}) { Image(systemName: "wand.and.sparkles") }
                    .buttonStyle(ComposerIconStyle())
                    .help("Optimize Prompt")
                Button(action: send) {
                    Image(systemName: "arrow.up")
                        .font(.body.bold())
                        .frame(width: 30, height: 30)
                }
                .buttonStyle(.borderedProminent)
                .buttonBorderShape(.circle)
                .disabled(prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .help("Send")
            }
            .padding(12)
            .background(ConsoleStyle.card, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .stroke(ConsoleStyle.border)
            }

            HStack(spacing: 8) {
                RuntimeChip(label: "Provider", value: agent.provider)
                RuntimeChip(label: "Model", value: agent.model)
                RuntimeChip(label: "Profile", value: "Default")
                RuntimeChip(label: "Access", value: agent.access)
                RuntimeChip(label: "Workspace", value: "CopeNet Core", symbol: "folder.fill")
                Spacer(minLength: 0)
                if isLive {
                    Text("Session is live and locked to its runtime")
                        .font(.caption2)
                        .foregroundStyle(ConsoleStyle.muted)
                }
            }
        }
        .padding(.horizontal, 18)
        .padding(.top, 12)
        .padding(.bottom, 16)
        .background(.ultraThinMaterial)
        .overlay(alignment: .top) {
            Rectangle().fill(ConsoleStyle.border).frame(height: 1)
        }
    }
}

private struct RuntimeChip: View {
    let label: String
    let value: String
    var symbol: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label.uppercased())
                .font(.system(size: 7.5, weight: .bold))
                .tracking(0.8)
                .foregroundStyle(ConsoleStyle.muted)
            HStack(spacing: 4) {
                if let symbol {
                    Image(systemName: symbol).foregroundStyle(ConsoleStyle.accent)
                }
                Text(value)
                    .lineLimit(1)
            }
            .font(.system(size: 10.5, weight: .semibold))
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(ConsoleStyle.panel, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(ConsoleStyle.border)
        }
    }
}

private struct ComposerIconStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.callout)
            .foregroundStyle(configuration.isPressed ? ConsoleStyle.accent : ConsoleStyle.muted)
            .frame(width: 28, height: 28)
            .contentShape(Rectangle())
    }
}
