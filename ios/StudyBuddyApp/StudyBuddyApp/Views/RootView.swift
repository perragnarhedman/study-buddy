import SwiftUI

struct RootView: View {
    @EnvironmentObject private var store: AppStore
    @State private var showingSettings = false

    var body: some View {
        TabView {
            NavigationStack {
                ChatView()
                    .navigationTitle("Chat")
                    .toolbar {
                        ToolbarItem(placement: .topBarTrailing) {
                            Button {
                                showingSettings = true
                            } label: {
                                Image(systemName: "gearshape")
                            }
                            .accessibilityLabel("Debug Settings")
                        }
                    }
            }
            .tabItem {
                Label("Chat", systemImage: "message")
            }

            NavigationStack {
                PlanView()
                    .navigationTitle("Plan")
                    .toolbar {
                        ToolbarItem(placement: .topBarTrailing) {
                            Button {
                                showingSettings = true
                            } label: {
                                Image(systemName: "gearshape")
                            }
                            .accessibilityLabel("Debug Settings")
                        }
                    }
            }
            .tabItem {
                Label("Plan", systemImage: "calendar")
            }
        }
        .sheet(isPresented: $showingSettings) {
            DebugSettingsView()
                .environmentObject(store)
        }
    }
}


