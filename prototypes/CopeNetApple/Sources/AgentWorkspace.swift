import SwiftUI

private enum WorkspaceMode: String, CaseIterable, Identifiable {
    case chat = "Chat"
    case fleet = "Fleet"

    var id: Self { self }
    var symbol: String { self == .chat ? "bubble.left.and.bubble.right" : "person.2" }
}

private struct Starter: Identifiable {
    let id = UUID()
    let title: String
    let detail: String
    let symbol: String
    let prompt: String
}

struct AgentWorkspace: View {
    let agent: AgentProfile
    @ObservedObject var model: AgentsViewModel

    @State private var mode: WorkspaceMode = .chat
    @State private var prompt = ""
    @State private var sentPrompt = ""
    @State private var sessionStarted = false

    private let starters = [
        Starter(
            title: "Think Through Something",
            detail: "Surface tradeoffs, unknowns, and the next best questions.",
            symbol: "brain.head.profile",
            prompt: "Help me think through "
        ),
        Starter(
            title: "Plan My Next Steps",
            detail: "Turn the mess into a concrete, ordered plan.",
            symbol: "list.bullet.clipboard",
            prompt: "Build a practical next-step plan for "
        ),
        Starter(
            title: "Reflect + Organize",
            detail: "Untangle what matters and organize it clearly.",
            symbol: "square.grid.2x2",
            prompt: "Help me reflect on and organize "
        ),
    ]

    var body: some View {
        VStack(spacing: 0) {
            WorkspaceHeader(mode: $mode)
            SessionStatus(agent: agent, isLive: sessionStarted)

            Group {
                if mode == .fleet {
                    FleetPreview()
                } else if sessionStarted {
                    ChatTranscript(prompt: sentPrompt, agent: agent)
                } else {
                    NewSessionWorkspace(
                        starters: starters,
                        prompt: $prompt
                    )
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            ComposerPanel(
                agent: agent,
                prompt: $prompt,
                isLive: sessionStarted,
                send: send
            )
        }
        .background(ConsoleStyle.background.opacity(0.97))
        .navigationTitle("")
        .toolbar {
            ToolbarItem {
                Button(action: {}) {
                    Image(systemName: "ellipsis")
                }
                .help("Workspace Actions")
            }
        }
    }

    private func send() {
        let trimmed = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        sentPrompt = trimmed
        prompt = ""
        withAnimation(.snappy(duration: 0.35)) {
            sessionStarted = true
        }
    }
}

private struct WorkspaceHeader: View {
    @Binding var mode: WorkspaceMode

    var body: some View {
        HStack(spacing: 14) {
            Picker("Workspace", selection: $mode) {
                ForEach(WorkspaceMode.allCases) { item in
                    Label(item.rawValue, systemImage: item.symbol).tag(item)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .frame(width: 180)

            Spacer()

            HStack(spacing: 6) {
                Circle().fill(ConsoleStyle.accent).frame(width: 6, height: 6)
                Text("Fleet ready")
                    .foregroundStyle(.white.opacity(0.72))
                Text("· Market Research Room")
                    .foregroundStyle(ConsoleStyle.muted)
                    .lineLimit(1)
            }
            .font(.caption.weight(.medium))
        }
        .padding(.horizontal, 18)
        .frame(height: 48)
        .background(.ultraThinMaterial)
        .overlay(alignment: .bottom) {
            Rectangle().fill(ConsoleStyle.border).frame(height: 1)
        }
    }
}

private struct SessionStatus: View {
    let agent: AgentProfile
    let isLive: Bool

    var body: some View {
        HStack(spacing: 9) {
            Circle()
                .fill(isLive ? .green : ConsoleStyle.accent)
                .frame(width: 7, height: 7)
                .shadow(color: (isLive ? Color.green : ConsoleStyle.accent).opacity(0.55), radius: 4)
            Text("New Chat")
                .font(.callout.weight(.semibold))
            Text("· \(agent.provider) / \(agent.model)")
                .font(.caption)
                .foregroundStyle(ConsoleStyle.muted)
            Spacer()
            Text(isLive ? "SESSION LIVE" : "NEW SESSION")
                .font(.system(size: 9, weight: .bold))
                .tracking(1.4)
                .foregroundStyle(isLive ? .green : ConsoleStyle.accent)
        }
        .padding(.horizontal, 20)
        .frame(height: 42)
        .background(ConsoleStyle.panel.opacity(0.65))
        .overlay(alignment: .bottom) {
            Rectangle().fill(ConsoleStyle.border.opacity(0.8)).frame(height: 1)
        }
    }
}

private struct NewSessionWorkspace: View {
    let starters: [Starter]
    @Binding var prompt: String

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 26) {
                VStack(alignment: .leading, spacing: 10) {
                    Text("NEW SESSION")
                        .font(.system(size: 10, weight: .bold))
                        .tracking(2)
                        .foregroundStyle(ConsoleStyle.accent)
                    Text("What are we working on?")
                        .font(.system(size: 38, weight: .semibold, design: .serif))
                    Text("Choose an opening move or describe the job. Your first message locks the runtime.")
                        .font(.callout)
                        .foregroundStyle(ConsoleStyle.muted)
                }

                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Text("OPENING MOVES")
                            .font(.system(size: 10, weight: .bold))
                            .tracking(1.7)
                            .foregroundStyle(ConsoleStyle.muted)
                        Spacer()
                        Text("567 ACTIVE · 0 ARCHIVED")
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundStyle(ConsoleStyle.muted)
                    }

                    HStack(spacing: 9) {
                        OpeningMove(title: "Research Scout", symbol: "binoculars") {
                            prompt = "Research and summarize "
                        }
                        OpeningMove(title: "Signal Sweep", symbol: "waveform.path.ecg") {
                            prompt = "Run a signal sweep for "
                        }
                        OpeningMove(title: "Workflow Draft", symbol: "point.3.connected.trianglepath.dotted") {
                            prompt = "Draft a reusable workflow for "
                        }
                    }
                }

                VStack(spacing: 10) {
                    ForEach(starters) { starter in
                        Button {
                            prompt = starter.prompt
                        } label: {
                            HStack(spacing: 14) {
                                ZStack {
                                    RoundedRectangle(cornerRadius: 11, style: .continuous)
                                        .fill(.white.opacity(0.045))
                                    Image(systemName: starter.symbol)
                                        .foregroundStyle(ConsoleStyle.accent)
                                }
                                .frame(width: 38, height: 38)

                                VStack(alignment: .leading, spacing: 3) {
                                    Text(starter.title)
                                        .font(.callout.weight(.semibold))
                                        .foregroundStyle(.white)
                                    Text(starter.detail)
                                        .font(.caption)
                                        .foregroundStyle(ConsoleStyle.muted)
                                }
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .font(.caption.bold())
                                    .foregroundStyle(ConsoleStyle.muted)
                            }
                            .padding(14)
                            .background(ConsoleStyle.card, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                            .overlay {
                                RoundedRectangle(cornerRadius: 16, style: .continuous)
                                    .stroke(ConsoleStyle.border)
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .padding(28)
            .frame(maxWidth: 760, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
    }
}

private struct OpeningMove: View {
    let title: String
    let symbol: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Label(title, systemImage: symbol)
                .font(.caption.weight(.semibold))
                .padding(.horizontal, 13)
                .padding(.vertical, 8)
                .background(ConsoleStyle.card, in: Capsule())
                .overlay(Capsule().stroke(ConsoleStyle.border))
        }
        .buttonStyle(.plain)
    }
}

private struct ChatTranscript: View {
    let prompt: String
    let agent: AgentProfile

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 26) {
                ChatMessage(role: "YOU", text: prompt, color: ConsoleStyle.accent)
                ChatMessage(
                    role: agent.name.uppercased(),
                    text: "I’m on it. I’ll keep the work scoped, show the evidence, and call out any decision that needs you.",
                    color: .green
                )
                HStack(spacing: 9) {
                    ProgressView().controlSize(.small)
                    Text("Preparing the first pass…")
                        .font(.caption)
                        .foregroundStyle(ConsoleStyle.muted)
                }
            }
            .padding(30)
            .frame(maxWidth: 760, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
        .transition(.opacity.combined(with: .move(edge: .bottom)))
    }
}

private struct ChatMessage: View {
    let role: String
    let text: String
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 7) {
                Circle().fill(color).frame(width: 6, height: 6)
                Text(role)
                    .font(.system(size: 9, weight: .bold))
                    .tracking(1.5)
                    .foregroundStyle(color)
            }
            Text(text)
                .font(.body)
                .foregroundStyle(.white.opacity(0.92))
                .textSelection(.enabled)
        }
    }
}

private struct FleetPreview: View {
    var body: some View {
        ContentUnavailableView {
            Label("Fleet is ready", systemImage: "person.2.wave.2")
        } description: {
            Text("Market Research Room is standing by with two agent lanes.")
        } actions: {
            Button("Open Fleet Room") {}
                .buttonStyle(.borderedProminent)
        }
        .foregroundStyle(.white)
    }
}
