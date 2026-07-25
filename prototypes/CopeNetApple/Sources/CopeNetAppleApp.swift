import SwiftUI

@main
struct CopeNetAppleApp: App {
    @StateObject private var model = AgentsViewModel(repository: MockAgentRepository())

    var body: some Scene {
        WindowGroup {
            AgentsPanel(model: model)
                .frame(minWidth: 820, minHeight: 600)
        }
        .defaultSize(width: 1240, height: 780)
#if os(macOS)
        .windowStyle(.hiddenTitleBar)
        .windowToolbarStyle(.unifiedCompact)
#endif
    }
}
