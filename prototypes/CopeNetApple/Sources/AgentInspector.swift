import SwiftUI

struct AgentInspector: View {
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

            Section("Capabilities") {
                ForEach(agent.capabilities) { capability in
                    Label(capability.name, systemImage: capability.symbol)
                }
            }

            Section("Prototype") {
                Label("Mocked agent data", systemImage: "shippingbox")
                Text("Ready for CopeNet’s existing RPC and WebSocket lane.")
                    .font(.caption)
                    .foregroundStyle(ConsoleStyle.muted)
            }
        }
        .scrollContentBackground(.hidden)
        .background(ConsoleStyle.panel)
        .formStyle(.grouped)
        .navigationTitle("Inspector")
    }
}

struct StatusPill: View {
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

struct SessionSheet: View {
    let agent: AgentProfile?
    @Environment(\.dismiss) private var dismiss
    @State private var prompt = ""

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("New Session")
                        .font(.headline)
                    Text(agent?.name ?? "CopeNet")
                        .font(.caption)
                        .foregroundStyle(ConsoleStyle.muted)
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
                Text("Connecting send will use CopeNet’s existing chat flow.")
            }
            .frame(maxHeight: .infinity)

            HStack(spacing: 10) {
                TextField("Message the agent…", text: $prompt, axis: .vertical)
                    .textFieldStyle(.plain)
                    .padding(12)
                    .background(ConsoleStyle.card, in: RoundedRectangle(cornerRadius: 13))
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
        .background(ConsoleStyle.background)
        .preferredColorScheme(.dark)
    }
}
