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
                .onOpenURL { url in
                    // studybuddy://auth?token=<SESSION_TOKEN>
                    guard url.scheme == "studybuddy" else { return }
                    guard url.host == "auth" else { return }
                    guard let comps = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return }
                    let token = comps.queryItems?.first(where: { $0.name == "token" })?.value
                    guard let token, !token.isEmpty else { return }
                    store.saveSessionToken(token)
                    Task { await store.refreshClassroomAssignmentsImportedCount() }
                }
        }
    }
}


