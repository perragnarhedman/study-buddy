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
                Section("Networking") {
                    TextField("Base URL", text: $draftBaseURL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)

                    Toggle("Use Stub Data", isOn: $store.useStubData)
                }

                Section("Google Classroom") {
                    Button("Connect Google Classroom") {
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
                        Text("Not connected yet")
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

                Section("Tips") {
                    Text("Run the backend locally and set Base URL to http://127.0.0.1:8000 (default).")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Debug Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Close") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Save") {
                        store.baseURL = draftBaseURL.trimmingCharacters(in: .whitespacesAndNewlines)
                        dismiss()
                    }
                    .disabled(draftBaseURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
            .onAppear {
                draftBaseURL = store.baseURL
                Task { await store.refreshClassroomAssignmentsImportedCount() }
            }
        }
    }

    private func connectGoogle() async {
        authStatus = "Opening Google sign-in…"
        do {
            store.baseURL = draftBaseURL.trimmingCharacters(in: .whitespacesAndNewlines)
            let api = APIClient(baseURLString: store.baseURL)
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


