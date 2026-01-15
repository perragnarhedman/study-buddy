import SwiftUI

struct DebugSettingsView: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.dismiss) private var dismiss

    @State private var draftBaseURL: String = ""

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
            }
        }
    }
}


