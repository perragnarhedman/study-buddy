import Foundation
import SwiftUI

@MainActor
final class AppStore: ObservableObject {
    @AppStorage("useStubData") var useStubData: Bool = true
    @AppStorage("baseURL") var baseURL: String = "http://127.0.0.1:8000"

    @Published var messages: [ChatMessage] = []
    // Cards associated with a specific assistant message id (rendered inline in Chat).
    @Published var assignmentCardsByAssistantMessageId: [String: [AssignmentCard]] = [:]
    @Published var weeklyPlan: WeeklyPlan? = nil
    @Published var bestNextActionFromChat: PlanItem? = nil
    @Published var classroomAssignmentsImported: Int? = nil
    @Published var classroomAssignments: [Assignment] = []
    @Published var planErrorMessage: String? = nil
    @Published var chatErrorMessage: String? = nil
    @Published var chatInfoMessage: String? = nil
    @Published var authErrorMessage: String? = nil

    private let sessionTokenKey = "studybuddy.sessionToken"
    var sessionToken: String? { Keychain.getString(forKey: sessionTokenKey) }

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

    func loadWeeklyPlan(preserveChatAction: Bool = false) async {
        if useStubData {
            weeklyPlan = Self.stubWeeklyPlan()
            if !preserveChatAction { bestNextActionFromChat = nil }
            planErrorMessage = nil
            return
        }

        do {
            let prevDone = Set(weeklyPlan?.items.filter { $0.status == .done }.map { $0.sourceAssignmentId ?? "" } ?? [])
            weeklyPlan = try await api.fetchWeeklyPlan(sessionToken: sessionToken)
            if !preserveChatAction { bestNextActionFromChat = nil }
            planErrorMessage = nil
            authErrorMessage = nil

            // Simple confirmation feedback if something just became done.
            let nextDone = Set(weeklyPlan?.items.filter { $0.status == .done }.map { $0.sourceAssignmentId ?? "" } ?? [])
            if !prevDone.isEmpty || !nextDone.isEmpty {
                let newDone = nextDone.subtracting(prevDone).filter { !$0.isEmpty }
                if !newDone.isEmpty {
                    chatInfoMessage = "Updated: marked as done in your plan."
                    DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                        if self.chatInfoMessage == "Updated: marked as done in your plan." {
                            self.chatInfoMessage = nil
                        }
                    }
                }
            }
        } catch {
            if !preserveChatAction { bestNextActionFromChat = nil }
            if let apiError = error as? APIError, case .serviceUnavailable = apiError {
                planErrorMessage = "Coach service unavailable (OpenAI). Check backend OPENAI_API_KEY."
            } else if let apiError = error as? APIError, case .unauthorized = apiError {
                authErrorMessage = "Please sign in to use Study Buddy."
                planErrorMessage = "Please sign in (Settings → Connect Google Classroom)."
            } else {
                planErrorMessage = "Could not load plan. Check backend is running."
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
            let resp = Self.stubChatResponse(for: trimmed, currentPlan: weeklyPlan)
            updateMessageText(id: assistantId, newText: resp.assistantMessage.text)
            bestNextActionFromChat = resp.bestNextAction
            if let cards = resp.assignmentCards, !cards.isEmpty {
                assignmentCardsByAssistantMessageId[assistantId] = cards
            } else {
                assignmentCardsByAssistantMessageId.removeValue(forKey: assistantId)
            }
            chatErrorMessage = nil
            if weeklyPlan == nil { weeklyPlan = Self.stubWeeklyPlan() }
            return
        }

        // Ensure we have a current plan to send (backend requires current_plan).
        if weeklyPlan == nil || weeklyPlan?.items.isEmpty == true {
            await loadWeeklyPlan(preserveChatAction: true)
        }
        // If plan load failed, do NOT call /chat/send (backend will 400).
        guard let currentPlan = weeklyPlan, !currentPlan.items.isEmpty else {
            bestNextActionFromChat = nil
            chatErrorMessage = "Plan not loaded. Open the Plan tab (or pull to refresh) and try again."
            updateMessageText(id: assistantId, newText: "I can’t send that yet because your plan hasn’t loaded. Open the Plan tab and try again.")
            return
        }

        do {
            let resp = try await api.sendChat(userMessage: trimmed, currentPlan: currentPlan, sessionToken: sessionToken)
            updateMessageText(id: assistantId, newText: resp.assistantMessage.text)
            bestNextActionFromChat = resp.bestNextAction
            if let cards = resp.assignmentCards, !cards.isEmpty {
                assignmentCardsByAssistantMessageId[assistantId] = cards
            } else {
                assignmentCardsByAssistantMessageId.removeValue(forKey: assistantId)
            }
            chatErrorMessage = nil
            authErrorMessage = nil

            // Refresh plan to reflect any done-state changes the agent may have persisted.
            await loadWeeklyPlan(preserveChatAction: true)
        } catch {
            bestNextActionFromChat = nil
            assignmentCardsByAssistantMessageId.removeValue(forKey: assistantId)
            if let apiError = error as? APIError, case .serviceUnavailable = apiError {
                chatErrorMessage = "Coach service unavailable (OpenAI)."
                updateMessageText(id: assistantId, newText: "Coach service unavailable right now (OpenAI).")
            } else if let apiError = error as? APIError, case .badRequest(let detail) = apiError {
                // Usually means current_plan was missing or invalid. Treat as a plan-sync problem.
                chatErrorMessage = "Chat request was invalid. Please open the Plan tab to refresh, then try again."
                let short = detail.isEmpty ? "" : "\n\nDetails: \(detail)"
                updateMessageText(id: assistantId, newText: "I couldn’t send that because your plan wasn’t included/valid. Open the Plan tab to refresh, then try again.\(short)")
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

    func assignmentCards(forAssistantMessageId id: String) -> [AssignmentCard] {
        assignmentCardsByAssistantMessageId[id] ?? []
    }

    func markDoneFromCard(sourceAssignmentId: String) async {
        // Optimistic local update (both plan and currently displayed cards).
        if let plan = weeklyPlan {
            let updated = plan.items.map { it -> PlanItem in
                guard it.sourceAssignmentId == sourceAssignmentId else { return it }
                return PlanItem(
                    id: it.id,
                    title: it.title,
                    dueDate: it.dueDate,
                    estimatedMinutes: it.estimatedMinutes,
                    status: .done,
                    sourceAssignmentId: it.sourceAssignmentId,
                    attachments: it.attachments
                )
            }
            weeklyPlan = WeeklyPlan(weekStart: plan.weekStart, items: updated)
        }
        assignmentCardsByAssistantMessageId = assignmentCardsByAssistantMessageId.mapValues { cards in
            cards.map { c in
                guard c.sourceAssignmentId == sourceAssignmentId || c.id == sourceAssignmentId else { return c }
                return AssignmentCard(
                    id: c.id,
                    title: c.title,
                    courseName: c.courseName,
                    dueDate: c.dueDate,
                    estimatedMinutes: c.estimatedMinutes,
                    status: .done,
                    sourceAssignmentId: c.sourceAssignmentId,
                    url: c.url,
                    attachments: c.attachments
                )
            }
        }

        guard !useStubData else { return }
        do {
            try await api.setAssignmentStatus(
                sessionToken: sessionToken,
                sourceAssignmentId: sourceAssignmentId,
                status: .done
            )
            // Refresh plan so Plan/Chat stay consistent with persisted state.
            await loadWeeklyPlan(preserveChatAction: true)
        } catch {
            // If this fails, just refresh from server to reconcile.
            await loadWeeklyPlan(preserveChatAction: true)
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
        if let chatAction = bestNextActionFromChat {
            return chatAction
        }
        guard let plan = weeklyPlan else { return nil }
        return plan.items.first(where: { $0.status == .todo }) ?? plan.items.first
    }

    // MARK: - Stubs

    static func stubWeeklyPlan() -> WeeklyPlan {
        let weekStart = Self.weekStartISO()
        return WeeklyPlan(
            weekStart: weekStart,
            items: [
                PlanItem(
                    id: UUID().uuidString,
                    title: "10-min starter: open your notes and write 3 topics to review",
                    dueDate: nil,
                    estimatedMinutes: 10,
                    status: .todo,
                    sourceAssignmentId: nil,
                    attachments: nil
                ),
                PlanItem(
                    id: UUID().uuidString,
                    title: "15-min: outline 5 bullets for the next assignment/problem set",
                    dueDate: nil,
                    estimatedMinutes: 15,
                    status: .todo,
                    sourceAssignmentId: nil,
                    attachments: nil
                )
            ]
        )
    }

    static func stubChatResponse(for userText: String, currentPlan: WeeklyPlan?) -> ChatSendResponse {
        let assistant = ChatMessage(
            id: UUID().uuidString,
            role: .assistant,
            text: "Let’s keep momentum. Do a tiny starter now: set a 10‑minute timer and write the first 3 bullet points.\n\nYou said: \(userText)",
            timestamp: isoNow()
        )
        let best = currentPlan?.items.first(where: { $0.status == .todo }) ?? stubWeeklyPlan().items.first
        let lower = userText.lowercased()
        let wantsOverview = lower.contains("this week") || lower.contains("assignments") || lower.contains("uppgifter") || lower.contains("denna vecka")
        let cards: [AssignmentCard]? = wantsOverview
            ? (currentPlan?.items.prefix(5).map { it in
                AssignmentCard(
                    id: it.sourceAssignmentId ?? it.id,
                    title: it.title,
                    courseName: nil,
                    dueDate: it.dueDate,
                    estimatedMinutes: it.estimatedMinutes,
                    status: it.status,
                    sourceAssignmentId: it.sourceAssignmentId,
                    url: nil,
                    attachments: nil
                )
            } ?? [])
            : nil

        return ChatSendResponse(assistantMessage: assistant, bestNextAction: best, assignmentCards: cards)
    }

    static func isoNow() -> String {
        ISO8601DateFormatter().string(from: Date())
    }

    static func weekStartISO() -> String {
        let cal = Calendar(identifier: .iso8601)
        let now = Date()
        let comps = cal.dateComponents([.yearForWeekOfYear, .weekOfYear], from: now)
        let start = cal.date(from: comps) ?? now
        let formatter = DateFormatter()
        formatter.calendar = cal
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: start)
    }
}


