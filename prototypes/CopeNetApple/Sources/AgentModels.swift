import Foundation
import SwiftUI

enum AgentStatus: String, Hashable {
    case working = "Working"
    case ready = "Ready"
    case paused = "Paused"
    case offline = "Offline"

    var color: Color {
        switch self {
        case .working: .orange
        case .ready: .green
        case .paused: .yellow
        case .offline: .secondary
        }
    }

    var symbol: String {
        switch self {
        case .working: "waveform.path.ecg"
        case .ready: "checkmark.circle.fill"
        case .paused: "pause.circle.fill"
        case .offline: "circle.dashed"
        }
    }
}

struct AgentCapability: Identifiable, Hashable {
    let id: String
    let name: String
    let symbol: String
}

struct AgentProfile: Identifiable, Hashable {
    let id: UUID
    let name: String
    let summary: String
    let provider: String
    let model: String
    let status: AgentStatus
    let capabilities: [AgentCapability]
    let lastActivity: String
    let access: String
    var isEnabled: Bool
}

@MainActor
final class AgentsViewModel: ObservableObject {
    @Published private(set) var agents: [AgentProfile]
    @Published var selection: AgentProfile.ID?
    @Published var showingSession = false
    @Published var sessionMessage: String?

    private let repository: any AgentRepository

    init(repository: any AgentRepository) {
        self.repository = repository
        let loadedAgents = repository.fetchAgents()
        agents = loadedAgents
        selection = loadedAgents.first?.id
    }

    var selectedAgent: AgentProfile? {
        agents.first(where: { $0.id == selection })
    }

    func setEnabled(_ isEnabled: Bool) {
        guard let selection,
              let index = agents.firstIndex(where: { $0.id == selection }) else { return }
        agents[index].isEnabled = isEnabled
        sessionMessage = isEnabled ? "\(agents[index].name) enabled" : "\(agents[index].name) paused"
    }

    func startSession() {
        guard let agent = selectedAgent, agent.isEnabled else { return }
        showingSession = true
        sessionMessage = "Session ready with \(agent.name)"
    }
}
