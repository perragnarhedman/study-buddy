import Foundation
import SwiftUI

@MainActor
final class AppStore: ObservableObject {
    @AppStorage("useStubData") var useStubData: Bool = AppStore.defaultUseStubData
    @AppStorage("baseURL") var baseURL: String = AppStore.defaultBaseURL

    @Published var messages: [ChatMessage] = []
    @Published var bestNextActionFromChat: PlanItem? = nil
    @Published var classroomAssignmentsImported: Int? = nil
    @Published var classroomAssignments: [Assignment] = []
    @Published var chatErrorMessage: String? = nil
    @Published var chatInfoMessage: String? = nil
    @Published var authErrorMessage: String? = nil

    private let sessionTokenKey = "studybuddy.sessionToken"
    var sessionToken: String? { Keychain.getString(forKey: sessionTokenKey) }

    static var defaultBaseURL: String {
        // Prefer build-time configuration (Info.plist substitution).
        if let v = Bundle.main.object(forInfoDictionaryKey: "STUDYBUDDY_DEFAULT_BASE_URL") as? String {
            let trimmed = v.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty, !trimmed.hasPrefix("$(") {
                return trimmed
            }
        }
#if DEBUG
        return "http://127.0.0.1:8000"
#else
        // Default for TestFlight/App Store: hosted backend (can be overridden via Info.plist).
        return "https://study-buddy-rtvu.onrender.com"
#endif
    }

    static var defaultUseStubData: Bool {
#if DEBUG
        return true
#else
        return false
#endif
    }

    func assignmentDescription(forSourceAssignmentId id: String?) -> String? {
        guard let id, !id.isEmpty else { return nil }
        return classroomAssignments.first(where: { $0.id == id })?.description
    }

    func assignmentCourseName(forSourceAssignmentId id: String?) -> String? {
        guard let id, !id.isEmpty else { return nil }
        return classroomAssignments.first(where: { $0.id == id })?.courseName
    }

    private var api: APIClient { APIClient(baseURLString: baseURL) }

    func resetConversation() async {
        guard !useStubData else {
            messages = []
            bestNextActionFromChat = nil
            chatErrorMessage = nil
            chatInfoMessage = "Conversation reset."
            return
        }
        do {
            try await api.resetConversation(sessionToken: sessionToken)
            messages = []
            bestNextActionFromChat = nil
            chatErrorMessage = nil
            chatInfoMessage = "Conversation reset."
        } catch {
            if let apiError = error as? APIError, case .unauthorized = apiError {
                authErrorMessage = "Please sign in to use Study Buddy."
                chatErrorMessage = "Please sign in (Settings → Connect Google Classroom)."
            } else {
                chatErrorMessage = "Could not reset conversation. Check backend is running."
            }
        }
    }

    func saveSessionToken(_ token: String) {
        Keychain.setString(token, forKey: sessionTokenKey)
    }

    func refreshClassroomAssignmentsImportedCount() async {
        guard !useStubData else {
            classroomAssignmentsImported = nil
            classroomAssignments = []
            return
        }
        guard let token = sessionToken else {
            classroomAssignmentsImported = nil
            classroomAssignments = []
            return
        }
        do {
            let assignments = try await api.fetchClassroomAssignments(sessionToken: token)
            classroomAssignmentsImported = assignments.count
            classroomAssignments = assignments
            authErrorMessage = nil
        } catch {
            if let apiError = error as? APIError, case .unauthorized = apiError {
                authErrorMessage = "Please sign in to use Study Buddy."
            }
            classroomAssignmentsImported = nil
            classroomAssignments = []
        }
    }

    func sendUserMessage(_ text: String) async {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }

        let userMsg = ChatMessage(
            id: UUID().uuidString,
            role: .user,
            text: trimmed,
            timestamp: Self.isoNow()
        )
        messages.append(userMsg)

        // Create placeholder assistant message (streaming-ready: update by id later).
        let assistantId = UUID().uuidString
        messages.append(
            ChatMessage(
                id: assistantId,
                role: .assistant,
                text: "Thinking…",
                timestamp: Self.isoNow()
            )
        )

        if useStubData {
            let resp = Self.stubChatResponse(for: trimmed)
            updateMessageText(id: assistantId, newText: resp.assistantMessage.text)
            bestNextActionFromChat = resp.bestNextAction
            chatErrorMessage = nil
            return
        }

        do {
            let resp = try await api.sendChat(userMessage: trimmed, sessionToken: sessionToken)
            updateMessageText(id: assistantId, newText: resp.assistantMessage.text)
            bestNextActionFromChat = resp.bestNextAction
            chatErrorMessage = nil
            authErrorMessage = nil
        } catch {
            bestNextActionFromChat = nil
            if let apiError = error as? APIError, case .serviceUnavailable = apiError {
                chatErrorMessage = "Coach service unavailable (OpenAI)."
                updateMessageText(id: assistantId, newText: "Coach service unavailable right now (OpenAI).")
            } else if let apiError = error as? APIError, case .badRequest(let detail) = apiError {
                chatErrorMessage = "Chat request was invalid."
                let short = detail.isEmpty ? "" : "\n\nDetails: \(detail)"
                updateMessageText(id: assistantId, newText: "I couldn’t send that.\(short)")
            } else if let apiError = error as? APIError, case .unauthorized = apiError {
                authErrorMessage = "Please sign in to use Study Buddy."
                chatErrorMessage = "Please sign in (Settings → Connect Google Classroom)."
                updateMessageText(id: assistantId, newText: "Please sign in to continue (Settings → Connect Google Classroom).")
            } else if let apiError = error as? APIError, case .badStatus(let code) = apiError {
                chatErrorMessage = "Backend returned an error (\(code))."
                updateMessageText(id: assistantId, newText: "Backend returned an error (\(code)).")
            } else {
                chatErrorMessage = "Could not reach backend."
                updateMessageText(id: assistantId, newText: "Could not reach backend.")
            }
        }
    }

    func assignmentURL(forSourceAssignmentId id: String?) -> URL? {
        guard let id, !id.isEmpty else { return nil }
        guard let raw = classroomAssignments.first(where: { $0.id == id })?.url else { return nil }
        return URL(string: raw)
    }

    func updateMessageText(id: String, newText: String) {
        guard let idx = messages.firstIndex(where: { $0.id == id }) else { return }
        messages[idx].text = newText
    }

    var bestNextAction: PlanItem? {
        bestNextActionFromChat
    }

    // MARK: - Stubs

    static func stubChatResponse(for userText: String) -> ChatSendResponse {
        let assistant = ChatMessage(
            id: UUID().uuidString,
            role: .assistant,
            text: "Let’s keep momentum. Do a tiny starter now: set a 10‑minute timer and write the first 3 bullet points.\n\nYou said: \(userText)",
            timestamp: isoNow()
        )
        let best = PlanItem(
            id: UUID().uuidString,
            title: "Start a 10‑minute review sprint",
            dueDate: nil,
            estimatedMinutes: 10,
            status: .todo,
            sourceAssignmentId: nil,
            attachments: nil
        )
        return ChatSendResponse(assistantMessage: assistant, bestNextAction: best)
    }

    static func isoNow() -> String {
        ISO8601DateFormatter().string(from: Date())
    }

}


