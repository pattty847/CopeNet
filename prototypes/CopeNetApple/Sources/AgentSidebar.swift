import SwiftUI

struct AgentSidebar: View {
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
                        .listRowBackground(Color.clear)
                }
            } header: {
                Text("\(filteredAgents.count) agents")
                    .foregroundStyle(ConsoleStyle.muted)
            }
        }
        .scrollContentBackground(.hidden)
        .background(ConsoleStyle.panel.opacity(0.98))
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
                ZStack {
                    Circle().fill(.green.opacity(0.14))
                    Circle().fill(.green).frame(width: 7, height: 7)
                }
                .frame(width: 24, height: 24)

                VStack(alignment: .leading, spacing: 1) {
                    Text("CopeNet Gateway")
                        .font(.caption.weight(.semibold))
                    Text("Native preview · Online")
                        .font(.caption2)
                        .foregroundStyle(ConsoleStyle.muted)
                }
                Spacer()
            }
            .padding(12)
            .background(.ultraThinMaterial)
            .overlay(alignment: .top) {
                Rectangle().fill(ConsoleStyle.border).frame(height: 1)
            }
        }
    }
}

private struct AgentRow: View {
    let agent: AgentProfile

    var body: some View {
        HStack(spacing: 11) {
            ZStack {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(agent.status.color.opacity(0.15))
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
                            .foregroundStyle(ConsoleStyle.muted)
                    }
                }
                Text("\(agent.provider) · \(agent.model)")
                    .font(.caption)
                    .foregroundStyle(ConsoleStyle.muted)
                    .lineLimit(1)
            }
        }
        .padding(.vertical, 5)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(agent.name), \(agent.status.rawValue)")
    }
}
