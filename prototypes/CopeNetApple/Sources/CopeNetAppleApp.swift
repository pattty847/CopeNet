import SwiftUI

@main
struct CopeNetAppleApp: App {
    @StateObject private var model = AgentsViewModel(repository: MockAgentRepository())

    var body: some Scene {
        WindowGroup {
            AgentsPanel(model: model)
                .frame(minWidth: 980, minHeight: 680)
        }
        .defaultSize(width: 1340, height: 820)
#if os(macOS)
        .windowStyle(.hiddenTitleBar)
        .windowToolbarStyle(.unifiedCompact)
#endif
    }
}
