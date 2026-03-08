import SwiftUI

struct DebugSettingsView: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL

    @State private var draftBaseURL: String = ""
    @State private var authStatus: String? = nil

    var body: some View {
        NavigationStack {
            Form {
#if DEBUG
                Section("Networking") {
                    TextField("Base URL", text: $draftBaseURL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)

                    Toggle("Use Stub Data", isOn: $store.useStubData)
                }
#else
                Section("Server") {
                    Text(store.baseURL)
                        .textSelection(.enabled)
                        .foregroundStyle(.secondary)
                }
#endif

                Section("Google Classroom") {
                    Button("Sign in to Google Classroom") {
                        Task { await connectGoogle() }
                    }
                    .disabled(store.useStubData)

                    if let count = store.classroomAssignmentsImported {
                        Text("\(count) assignments imported")
                            .foregroundStyle(.secondary)
                    } else if let authStatus {
                        Text(authStatus)
                            .foregroundStyle(.secondary)
                    } else {
                        Text("Not signed in yet")
                            .foregroundStyle(.secondary)
                    }

                    if store.classroomAssignmentsImported == nil {
                        Text("Use this to connect your assignments to Study Buddy.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }

                    if !store.classroomAssignments.isEmpty {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Latest assignment (preview)")
                                .font(.subheadline)
                                .fontWeight(.semibold)

                            let a = store.classroomAssignments.first!
                            Text(a.title)
                                .font(.subheadline)

                            if let desc = a.description, !desc.isEmpty {
                                Text(desc)
                                    .font(.footnote)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(6)
                            } else {
                                Text("No instructions available for this assignment.")
                                    .font(.footnote)
                                    .foregroundStyle(.secondary)
                            }

                            if let urlStr = a.url, let url = URL(string: urlStr) {
                                Button("Open in Classroom") {
                                    openURL(url)
                                }
                            }
                        }
                        .padding(.top, 6)
                    }
                }

                if store.isSignedIn {
                    Section("Account") {
                        Button("Sign out", role: .destructive) {
                            store.signOut()
                            dismiss()
                        }
                    }
                }

                Section("Tips") {
                    Text("If sign-in fails, confirm the app is pointing at a reachable backend URL.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                Section("Chat") {
                    Button("Reset conversation") {
                        Task { await store.resetConversation() }
                    }
                    .disabled(store.useStubData == false && (store.sessionToken ?? "").isEmpty)
                }
            }
#if DEBUG
            .navigationTitle("Debug Settings")
#else
            .navigationTitle("Settings")
#endif
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Close") { dismiss() }
                }
#if DEBUG
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Save") {
                        store.baseURL = draftBaseURL.trimmingCharacters(in: .whitespacesAndNewlines)
                        dismiss()
                    }
                    .disabled(draftBaseURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
#endif
            }
            .onAppear {
#if DEBUG
                draftBaseURL = store.baseURL
#endif
                Task { await store.refreshClassroomAssignmentsImportedCount() }
            }
        }
    }

    private func connectGoogle() async {
        authStatus = "Opening Google sign-in…"
        do {
#if DEBUG
            store.baseURL = draftBaseURL.trimmingCharacters(in: .whitespacesAndNewlines)
            let api = APIClient(baseURLString: store.baseURL)
#else
            let api = APIClient(baseURLString: store.baseURL)
#endif
            let resp = try await api.googleAuthStart()
            guard let url = URL(string: resp.authorizationURL) else {
                authStatus = "Invalid auth URL"
                return
            }
            authStatus = "Complete sign-in in Safari…"
            openURL(url)
        } catch {
            authStatus = "Could not start auth"
        }
    }
}


