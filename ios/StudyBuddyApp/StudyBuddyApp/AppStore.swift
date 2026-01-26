import Foundation
import SwiftUI

@MainActor
final class AppStore: ObservableObject {
    @AppStorage("useStubData") var useStubData: Bool = true
    @AppStorage("baseURL") var baseURL: String = "http://127.0.0.1:8000"

    @Published var messages: [ChatMessage] = []
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

    private var api: APIClient { APIClient(baseURLString: baseURL) }

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
            chatErrorMessage = nil
            if weeklyPlan == nil { weeklyPlan = Self.stubWeeklyPlan() }
            return
        }

        // Ensure we have a current plan to send (backend requires current_plan).
        if weeklyPlan == nil {
            await loadWeeklyPlan(preserveChatAction: true)
        }

        do {
            let resp = try await api.sendChat(userMessage: trimmed, currentPlan: weeklyPlan, sessionToken: sessionToken)
            updateMessageText(id: assistantId, newText: resp.assistantMessage.text)
            bestNextActionFromChat = resp.bestNextAction
            chatErrorMessage = nil
            authErrorMessage = nil

            // Refresh plan to reflect any done-state changes the agent may have persisted.
            await loadWeeklyPlan(preserveChatAction: true)
        } catch {
            bestNextActionFromChat = nil
            if let apiError = error as? APIError, case .serviceUnavailable = apiError {
                chatErrorMessage = "Coach service unavailable (OpenAI)."
                updateMessageText(id: assistantId, newText: "Coach service unavailable right now (OpenAI).")
            } else if let apiError = error as? APIError, case .unauthorized = apiError {
                authErrorMessage = "Please sign in to use Study Buddy."
                chatErrorMessage = "Please sign in (Settings → Connect Google Classroom)."
                updateMessageText(id: assistantId, newText: "Please sign in to continue (Settings → Connect Google Classroom).")
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
                    sourceAssignmentId: nil
                ),
                PlanItem(
                    id: UUID().uuidString,
                    title: "15-min: outline 5 bullets for the next assignment/problem set",
                    dueDate: nil,
                    estimatedMinutes: 15,
                    status: .todo,
                    sourceAssignmentId: nil
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
        return ChatSendResponse(assistantMessage: assistant, bestNextAction: best)
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


