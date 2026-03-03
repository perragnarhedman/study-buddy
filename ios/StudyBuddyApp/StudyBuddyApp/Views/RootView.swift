import SwiftUI

struct RootView: View {
    @EnvironmentObject private var store: AppStore
    @State private var showingSettings = false

    var body: some View {
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
        .sheet(isPresented: $showingSettings) {
            DebugSettingsView()
                .environmentObject(store)
        }
    }
}


