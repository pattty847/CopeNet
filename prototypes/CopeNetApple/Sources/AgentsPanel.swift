import SwiftUI

enum ConsoleStyle {
    static let background = Color(red: 0.025, green: 0.025, blue: 0.028)
    static let panel = Color(red: 0.055, green: 0.055, blue: 0.062)
    static let card = Color(red: 0.075, green: 0.075, blue: 0.084)
    static let border = Color(red: 0.14, green: 0.14, blue: 0.16)
    static let accent = Color(red: 1.0, green: 0.54, blue: 0.0)
    static let muted = Color(red: 0.55, green: 0.55, blue: 0.60)
}

struct AgentsPanel: View {
    @ObservedObject var model: AgentsViewModel

    var body: some View {
        NavigationSplitView {
            AgentSidebar(model: model)
                .navigationSplitViewColumnWidth(min: 220, ideal: 248, max: 290)
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
                    .navigationSplitViewColumnWidth(min: 250, ideal: 280, max: 330)
            }
        }
        .navigationSplitViewStyle(.balanced)
        .tint(ConsoleStyle.accent)
        .background(ConsoleAtmosphere())
        .preferredColorScheme(.dark)
        .animation(.snappy(duration: 0.28), value: model.selection)
        .overlay(alignment: .bottom) {
            if let message = model.sessionMessage {
                Label(message, systemImage: "checkmark.circle.fill")
                    .font(.callout.weight(.medium))
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(.thickMaterial, in: Capsule())
                    .overlay(Capsule().stroke(ConsoleStyle.border))
                    .shadow(color: .black.opacity(0.45), radius: 20, y: 8)
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

private struct ConsoleAtmosphere: View {
    var body: some View {
        ZStack {
            ConsoleStyle.background
            Circle()
                .fill(ConsoleStyle.accent.opacity(0.065))
                .frame(width: 520)
                .blur(radius: 120)
                .offset(x: 300, y: -300)
        }
        .ignoresSafeArea()
        .allowsHitTesting(false)
    }
}
