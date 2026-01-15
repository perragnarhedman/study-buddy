import SwiftUI

@main
struct StudyBuddyAppApp: App {
    @StateObject private var store = AppStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .task {
                    await store.loadWeeklyPlan()
                }
        }
    }
}


