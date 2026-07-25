import Foundation

protocol AgentRepository: Sendable {
    func fetchAgents() -> [AgentProfile]
}

struct MockAgentRepository: AgentRepository {
    func fetchAgents() -> [AgentProfile] {
        [
            AgentProfile(
                id: UUID(uuidString: "20B98677-4CF4-4BDE-9F4F-EC631071E8B2")!,
                name: "CopeNet Core",
                summary: "General operator for research, implementation, and day-to-day project work.",
                provider: "OpenAI Codex",
                model: "gpt-5.5",
                status: .ready,
                capabilities: [
                    .init(id: "repo", name: "Repository", symbol: "folder"),
                    .init(id: "shell", name: "Shell", symbol: "terminal"),
                    .init(id: "web", name: "Web", symbol: "globe"),
                    .init(id: "memory", name: "Memory", symbol: "brain"),
                ],
                lastActivity: "2 min ago",
                access: "Full Access",
                isEnabled: true
            ),
            AgentProfile(
                id: UUID(uuidString: "62247F01-9C97-433D-B9DE-613A545FA84A")!,
                name: "Market Research",
                summary: "Slow-timeframe market radar with evidence, scenarios, and portfolio context.",
                provider: "OpenAI Codex",
                model: "gpt-5.5",
                status: .working,
                capabilities: [
                    .init(id: "market", name: "Market", symbol: "chart.xyaxis.line"),
                    .init(id: "evidence", name: "Evidence", symbol: "doc.text.magnifyingglass"),
                    .init(id: "web", name: "Web", symbol: "globe"),
                ],
                lastActivity: "Now",
                access: "Read-only",
                isEnabled: true
            ),
            AgentProfile(
                id: UUID(uuidString: "BAAB0A6A-1971-4C8B-A746-F29F208A1CC1")!,
                name: "Research Scout",
                summary: "Collects sources, compares claims, and returns compact evidence briefs.",
                provider: "Claude CLI",
                model: "Sonnet",
                status: .paused,
                capabilities: [
                    .init(id: "web", name: "Web", symbol: "globe"),
                    .init(id: "files", name: "Files", symbol: "doc.on.doc"),
                ],
                lastActivity: "Yesterday",
                access: "Read-only",
                isEnabled: false
            ),
            AgentProfile(
                id: UUID(uuidString: "6019C706-4814-4D75-B8D9-012D11D2075C")!,
                name: "Local Lab",
                summary: "Private local-model lane for quick experiments and offline drafts.",
                provider: "LM Studio",
                model: "Qwen 3",
                status: .offline,
                capabilities: [
                    .init(id: "local", name: "Local", symbol: "desktopcomputer"),
                    .init(id: "files", name: "Files", symbol: "doc.on.doc"),
                ],
                lastActivity: "3 days ago",
                access: "Guarded",
                isEnabled: false
            ),
        ]
    }
}
