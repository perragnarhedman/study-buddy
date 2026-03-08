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
    @Published var isAssistantTyping: Bool = false

    private let sessionTokenKey = "studybuddy.sessionToken"
    private let apiClientFactory: (String) -> ChatAPIClient
    private let sessionTokenProvider: () -> String?
    var sessionToken: String? { sessionTokenProvider() }

    init(
        apiClientFactory: @escaping (String) -> ChatAPIClient = { APIClient(baseURLString: $0) },
        sessionTokenProvider: @escaping () -> String? = { Keychain.getString(forKey: "studybuddy.sessionToken") }
    ) {
        self.apiClientFactory = apiClientFactory
        self.sessionTokenProvider = sessionTokenProvider
        // If an older build saved a localhost baseURL, move it to the current default.
        // This makes upgrades (and simulator reinstalls) behave consistently.
        migrateSavedDefaultsIfNeeded()
    }

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
        // Match TestFlight by default; can be toggled in Debug Settings when needed.
        return false
#else
        return false
#endif
    }

    private func migrateSavedDefaultsIfNeeded() {
        let saved = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        // Only auto-migrate the legacy localhost default; respect any explicit override.
        guard saved == "http://127.0.0.1:8000" else { return }
        let desired = Self.defaultBaseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !desired.isEmpty, desired != saved else { return }
        baseURL = desired
    }

    func assignmentDescription(forSourceAssignmentId id: String?) -> String? {
        guard let id, !id.isEmpty else { return nil }
        return classroomAssignments.first(where: { $0.id == id })?.description
    }

    func assignmentCourseName(forSourceAssignmentId id: String?) -> String? {
        guard let id, !id.isEmpty else { return nil }
        return classroomAssignments.first(where: { $0.id == id })?.courseName
    }

    private var api: ChatAPIClient { apiClientFactory(baseURL) }

    func resetConversation() async {
        guard !useStubData else {
            messages = []
            bestNextActionFromChat = nil
            chatErrorMessage = nil
            chatInfoMessage = "Conversation reset."
            isAssistantTyping = false
            return
        }
        do {
            try await api.resetConversation(
                sessionToken: sessionToken,
                clearAssignmentStatus: false,
                clearPreferences: false
            )
            messages = []
            bestNextActionFromChat = nil
            chatErrorMessage = nil
            chatInfoMessage = "Conversation reset."
            isAssistantTyping = false
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
        chatErrorMessage = nil
        chatInfoMessage = nil
        isAssistantTyping = true

        if useStubData {
            let resp = Self.stubChatResponse(for: trimmed)
            appendAssistantReplyText(resp.assistantMessage.text)
            bestNextActionFromChat = resp.bestNextAction
            chatErrorMessage = nil
            isAssistantTyping = false
            return
        }

        let assistantCountBefore = messages.filter { $0.role == .assistant }.count

        do {
            try await consumeChatStream(
                api.sendChatStream(userMessage: trimmed, sessionToken: sessionToken)
            )
            chatErrorMessage = nil
            authErrorMessage = nil
        } catch let streamError {
            let hasAssistantContent = messages.filter { $0.role == .assistant }.count > assistantCountBefore

            if !hasAssistantContent {
                do {
                    let fallback = try await api.sendChat(userMessage: trimmed, sessionToken: sessionToken)
                    bestNextActionFromChat = fallback.bestNextAction
                    appendAssistantReplyText(fallback.assistantMessage.text)
                    chatErrorMessage = nil
                    authErrorMessage = nil
                    isAssistantTyping = false
                    return
                } catch {
                    handleChatFailure(error, assistantCountBefore: assistantCountBefore)
                    return
                }
            }

            handleChatFailure(streamError, assistantCountBefore: assistantCountBefore)
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

    func appendMessageDelta(id: String, delta: String) {
        guard let idx = messages.firstIndex(where: { $0.id == id }) else { return }
        messages[idx].text += delta
    }

    private func appendAssistantMessage(id: String = UUID().uuidString, text: String) {
        messages.append(
            ChatMessage(
                id: id,
                role: .assistant,
                text: text,
                timestamp: Self.isoNow()
            )
        )
    }

    private func appendAssistantErrorIfNeeded(_ text: String, assistantCountBefore: Int) {
        if messages.filter({ $0.role == .assistant }).count == assistantCountBefore {
            appendAssistantMessage(text: text)
        }
    }

    private func appendAssistantReplyText(_ text: String) {
        for part in segmentedAssistantMessages(from: text) {
            appendAssistantMessage(text: part)
        }
    }

    private func handleChatFailure(_ error: Error, assistantCountBefore: Int) {
        bestNextActionFromChat = nil
        isAssistantTyping = false

        if let apiError = error as? APIError, case .serviceUnavailable = apiError {
            chatErrorMessage = "Coach service unavailable (OpenAI)."
            appendAssistantErrorIfNeeded(
                "Coach service unavailable right now (OpenAI).",
                assistantCountBefore: assistantCountBefore
            )
        } else if let apiError = error as? APIError, case .badRequest(let detail) = apiError {
            chatErrorMessage = "Chat request was invalid."
            let short = detail.isEmpty ? "" : "\n\nDetails: \(detail)"
            appendAssistantErrorIfNeeded(
                "I couldn’t send that.\(short)",
                assistantCountBefore: assistantCountBefore
            )
        } else if let apiError = error as? APIError, case .unauthorized = apiError {
            authErrorMessage = "Please sign in to use Study Buddy."
            chatErrorMessage = "Please sign in (Settings → Connect Google Classroom)."
            appendAssistantErrorIfNeeded(
                "Please sign in to continue (Settings → Connect Google Classroom).",
                assistantCountBefore: assistantCountBefore
            )
        } else if let apiError = error as? APIError, case .badStatus(let code) = apiError {
            chatErrorMessage = "Backend returned an error (\(code))."
            appendAssistantErrorIfNeeded(
                "Backend returned an error (\(code)).",
                assistantCountBefore: assistantCountBefore
            )
        } else {
            chatErrorMessage = "Could not reach backend."
            appendAssistantErrorIfNeeded(
                "Could not reach backend.",
                assistantCountBefore: assistantCountBefore
            )
        }
    }

    private func consumeChatStream(_ stream: AsyncThrowingStream<ChatStreamEvent, Error>) async throws {
        for try await event in stream {
            switch event.type {
            case .typingStarted:
                isAssistantTyping = true

            case .messageStarted:
                guard let messageId = event.messageId else { continue }
                appendAssistantMessage(id: messageId, text: "")
                isAssistantTyping = false

            case .messageDelta:
                guard let messageId = event.messageId, let delta = event.delta else { continue }
                appendMessageDelta(id: messageId, delta: delta)
                isAssistantTyping = false

            case .messageCompleted:
                isAssistantTyping = true

            case .bestNextAction:
                bestNextActionFromChat = event.bestNextAction

            case .turnCompleted:
                isAssistantTyping = false

            case .error:
                isAssistantTyping = false
                if let message = event.message, !message.isEmpty {
                    throw APIError.badRequest(message)
                }
                throw APIError.badStatus(-1)
            }
        }
    }

    private func segmentedAssistantMessages(from text: String) -> [String] {
        let normalized = text.replacingOccurrences(of: "\r\n", with: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalized.isEmpty else { return [] }

        let parts = normalized
            .components(separatedBy: "\n\n")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        guard let first = parts.first else { return [] }
        if let openerSplit = splitShortOpener(first) {
            var segmented = [openerSplit.0, openerSplit.1]
            segmented.append(contentsOf: parts.dropFirst())
            return segmented
        }
        return parts
    }

    private func splitShortOpener(_ text: String) -> (String, String)? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }

        var idx = trimmed.startIndex
        var count = 0
        while idx < trimmed.endIndex, count < 40 {
            let ch = trimmed[idx]
            if ch == "." || ch == "!" || ch == "?" {
                let next = trimmed.index(after: idx)
                let remainder = String(trimmed[next...]).trimmingCharacters(in: .whitespacesAndNewlines)
                let opener = String(trimmed[..<next]).trimmingCharacters(in: .whitespacesAndNewlines)
                if !opener.isEmpty,
                   !remainder.isEmpty,
                   remainder.rangeOfCharacter(from: .uppercaseLetters)?.lowerBound == remainder.startIndex {
                    return (opener, remainder)
                }
            }
            idx = trimmed.index(after: idx)
            count += 1
        }

        return nil
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


