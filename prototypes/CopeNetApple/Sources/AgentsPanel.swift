import SwiftUI

struct AgentsPanel: View {
    @ObservedObject var model: AgentsViewModel

    var body: some View {
        NavigationSplitView {
            AgentSidebar(model: model)
                .navigationSplitViewColumnWidth(min: 230, ideal: 260, max: 310)
        } content: {
            if let agent = model.selectedAgent {
                AgentWorkspace(agent: agent, model: model)
                    .id(agent.id)
                    .transition(.opacity.combined(with: .move(edge: .trailing)))
            } else {
                ContentUnavailableView(
                    "Select an Agent",
                    systemImage: "cpu",
                    description: Text("Choose an agent to inspect its runtime.")
                )
            }
        } detail: {
            if let agent = model.selectedAgent {
                AgentInspector(agent: agent, model: model)
                    .navigationSplitViewColumnWidth(min: 260, ideal: 300, max: 360)
            }
        }
        .navigationSplitViewStyle(.balanced)
        .tint(.orange)
        .background(Atmosphere())
        .animation(.snappy(duration: 0.28), value: model.selection)
        .overlay(alignment: .bottom) {
            if let message = model.sessionMessage {
                Label(message, systemImage: "checkmark.circle.fill")
                    .font(.callout.weight(.medium))
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(.thickMaterial, in: Capsule())
                    .shadow(color: .black.opacity(0.18), radius: 18, y: 8)
                    .padding(.bottom, 18)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .task {
                        try? await Task.sleep(for: .seconds(2))
                        withAnimation { model.sessionMessage = nil }
                    }
            }
        }
        .sheet(isPresented: $model.showingSession) {
            SessionSheet(agent: model.selectedAgent)
        }
    }
}

private struct AgentSidebar: View {
    @ObservedObject var model: AgentsViewModel
    @State private var search = ""

    private var filteredAgents: [AgentProfile] {
        guard !search.isEmpty else { return model.agents }
        return model.agents.filter {
            $0.name.localizedCaseInsensitiveContains(search)
                || $0.provider.localizedCaseInsensitiveContains(search)
        }
    }

    var body: some View {
        List(selection: $model.selection) {
            Section {
                ForEach(filteredAgents) { agent in
                    AgentRow(agent: agent)
                        .tag(agent.id)
                }
            } header: {
                Text("\(filteredAgents.count) agents")
            }
        }
        .listStyle(.sidebar)
        .searchable(text: $search, placement: .sidebar, prompt: "Search agents")
        .navigationTitle("Agents")
        .toolbar {
            ToolbarItem {
                Button(action: {}) {
                    Label("New Agent", systemImage: "plus")
                }
                .help("New Agent")
            }
        }
        .safeAreaInset(edge: .bottom) {
            HStack(spacing: 10) {
                Image(systemName: "bolt.horizontal.circle.fill")
                    .foregroundStyle(.green)
                VStack(alignment: .leading, spacing: 1) {
                    Text("CopeNet Gateway")
                        .font(.caption.weight(.semibold))
                    Text("Mock preview")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Circle()
                    .fill(.green)
                    .frame(width: 7, height: 7)
            }
            .padding(12)
            .background(.ultraThinMaterial)
        }
    }
}

private struct AgentRow: View {
    let agent: AgentProfile

    var body: some View {
        HStack(spacing: 11) {
            ZStack {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(agent.status.color.opacity(0.14))
                Image(systemName: agent.status == .working ? "waveform" : "cpu")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(agent.status.color)
            }
            .frame(width: 36, height: 36)

            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(agent.name)
                        .font(.callout.weight(.semibold))
                        .lineLimit(1)
                    if !agent.isEnabled {
                        Image(systemName: "pause.fill")
                            .font(.system(size: 8))
                            .foregroundStyle(.secondary)
                    }
                }
                Text("\(agent.provider) · \(agent.model)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .padding(.vertical, 5)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(agent.name), \(agent.status.rawValue)")
    }
}

private struct AgentWorkspace: View {
    let agent: AgentProfile
    @ObservedObject var model: AgentsViewModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                HStack(alignment: .top, spacing: 16) {
                    ZStack {
                        RoundedRectangle(cornerRadius: 18, style: .continuous)
                            .fill(.orange.gradient.opacity(0.2))
                        Image(systemName: "cpu.fill")
                            .font(.system(size: 28, weight: .medium))
                            .foregroundStyle(.orange)
                    }
                    .frame(width: 64, height: 64)

                    VStack(alignment: .leading, spacing: 7) {
                        HStack {
                            Text(agent.name)
                                .font(.largeTitle.bold())
                            StatusPill(status: agent.status)
                        }
                        Text(agent.summary)
                            .font(.body)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }

                VStack(alignment: .leading, spacing: 12) {
                    Text("Runtime")
                        .font(.headline)
                    HStack(spacing: 12) {
                        RuntimeCard(title: "Provider", value: agent.provider, symbol: "network")
                        RuntimeCard(title: "Model", value: agent.model, symbol: "sparkles")
                        RuntimeCard(title: "Access", value: agent.access, symbol: "lock.shield")
                    }
                }

                VStack(alignment: .leading, spacing: 12) {
                    Text("Capabilities")
                        .font(.headline)
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 125), spacing: 10)], spacing: 10) {
                        ForEach(agent.capabilities) { capability in
                            Label(capability.name, systemImage: capability.symbol)
                                .font(.callout.weight(.medium))
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(12)
                                .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 13))
                        }
                    }
                }

                VStack(alignment: .leading, spacing: 12) {
                    Text("Recent activity")
                        .font(.headline)
                    ActivityRow(
                        symbol: agent.status == .working ? "gearshape.2.fill" : "checkmark.circle.fill",
                        title: agent.status == .working ? "Running evidence sweep" : "Ready for a new session",
                        detail: "\(agent.lastActivity) · \(agent.capabilities.count) tools available",
                        color: agent.status.color
                    )
                    ActivityRow(
                        symbol: "lock.shield.fill",
                        title: "Runtime binding is explicit",
                        detail: "\(agent.provider) / \(agent.model) · \(agent.access)",
                        color: .blue
                    )
                }
            }
            .padding(28)
            .frame(maxWidth: 720, alignment: .leading)
        }
        .background(.regularMaterial.opacity(0.35))
        .navigationTitle(agent.name)
        .toolbar {
            ToolbarItemGroup {
                Button(action: {}) {
                    Image(systemName: "ellipsis.circle")
                }
                .help("Agent Actions")
                Button {
                    model.startSession()
                } label: {
                    Label("Open Chat", systemImage: "message.fill")
                }
                .buttonStyle(.borderedProminent)
                .disabled(!agent.isEnabled || agent.status == .offline)
                .help(agent.isEnabled ? "Open a new agent session" : "Enable this agent first")
            }
        }
    }
}

private struct RuntimeCard: View {
    let title: String
    let value: String
    let symbol: String

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Image(systemName: symbol)
                .font(.title3)
                .foregroundStyle(.orange)
            Spacer(minLength: 2)
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.callout.weight(.semibold))
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, minHeight: 92, alignment: .leading)
        .padding(15)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(.white.opacity(0.08))
        }
    }
}

private struct ActivityRow: View {
    let symbol: String
    let title: String
    let detail: String
    let color: Color

    var body: some View {
        HStack(spacing: 13) {
            Image(systemName: symbol)
                .foregroundStyle(color)
                .frame(width: 24)
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.callout.weight(.medium))
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Image(systemName: "chevron.right")
                .font(.caption.weight(.bold))
                .foregroundStyle(.tertiary)
        }
        .padding(14)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 14))
    }
}

private struct AgentInspector: View {
    let agent: AgentProfile
    @ObservedObject var model: AgentsViewModel

    var body: some View {
        Form {
            Section("Availability") {
                Toggle(isOn: Binding(
                    get: { agent.isEnabled },
                    set: { model.setEnabled($0) }
                )) {
                    Label("Agent enabled", systemImage: "power")
                }
                LabeledContent("Status") {
                    StatusPill(status: agent.status)
                }
            }

            Section("Runtime") {
                LabeledContent("Provider", value: agent.provider)
                LabeledContent("Model", value: agent.model)
                LabeledContent("Access", value: agent.access)
            }

            Section("Session") {
                LabeledContent("Last activity", value: agent.lastActivity)
                LabeledContent("Tools", value: "\(agent.capabilities.count) available")
                Button {
                    model.startSession()
                } label: {
                    Label("Start New Session", systemImage: "plus.bubble.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(!agent.isEnabled || agent.status == .offline)
            }

            Section("Prototype") {
                Label("Mocked agent data", systemImage: "shippingbox")
                Text("The repository boundary is ready for CopeNet's existing RPC and WebSocket lane.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .navigationTitle("Inspector")
    }
}

private struct StatusPill: View {
    let status: AgentStatus

    var body: some View {
        Label(status.rawValue, systemImage: status.symbol)
            .font(.caption.weight(.semibold))
            .foregroundStyle(status.color)
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .background(status.color.opacity(0.12), in: Capsule())
    }
}

private struct SessionSheet: View {
    let agent: AgentProfile?
    @Environment(\.dismiss) private var dismiss
    @State private var prompt = ""

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("New session")
                        .font(.headline)
                    Text(agent?.name ?? "CopeNet")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button("Done") { dismiss() }
                    .keyboardShortcut(.cancelAction)
            }
            .padding()

            Divider()

            ContentUnavailableView {
                Label("Ready to work", systemImage: "message.badge.waveform.fill")
            } description: {
                Text("This is a visual prototype. Connecting send will use CopeNet's existing chat flow.")
            }
            .frame(maxHeight: .infinity)

            HStack(spacing: 10) {
                TextField("Message the agent…", text: $prompt, axis: .vertical)
                    .textFieldStyle(.plain)
                    .padding(12)
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 13))
                Button(action: {}) {
                    Image(systemName: "arrow.up")
                        .font(.body.bold())
                        .frame(width: 28, height: 28)
                }
                .buttonStyle(.borderedProminent)
                .buttonBorderShape(.circle)
                .disabled(prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding()
        }
        .frame(minWidth: 560, minHeight: 440)
    }
}

private struct Atmosphere: View {
    var body: some View {
        ZStack {
            Color.clear
            Circle()
                .fill(.orange.opacity(0.08))
                .frame(width: 420)
                .blur(radius: 90)
                .offset(x: 280, y: -260)
        }
        .ignoresSafeArea()
        .allowsHitTesting(false)
    }
}
