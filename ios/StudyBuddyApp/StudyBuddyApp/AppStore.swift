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

    private let sessionTokenKey = "studybuddy.sessionToken"
    var sessionToken: String? { Keychain.getString(forKey: sessionTokenKey) }

    private var api: APIClient { APIClient(baseURLString: baseURL) }

    func loadWeeklyPlan() async {
        if useStubData {
            weeklyPlan = Self.stubWeeklyPlan()
            bestNextActionFromChat = nil
            return
        }

        do {
            weeklyPlan = try await api.fetchWeeklyPlan()
            bestNextActionFromChat = nil
        } catch {
            // Fallback for MVP: show stub on failure.
            weeklyPlan = Self.stubWeeklyPlan()
            bestNextActionFromChat = nil
        }
    }

    func saveSessionToken(_ token: String) {
        Keychain.setString(token, forKey: sessionTokenKey)
    }

    func refreshClassroomAssignmentsImportedCount() async {
        guard !useStubData else {
            classroomAssignmentsImported = nil
            return
        }
        guard let token = sessionToken else {
            classroomAssignmentsImported = nil
            return
        }
        do {
            let assignments = try await api.fetchClassroomAssignments(sessionToken: token)
            classroomAssignmentsImported = assignments.count
        } catch {
            classroomAssignmentsImported = nil
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
            if weeklyPlan == nil { weeklyPlan = Self.stubWeeklyPlan() }
            return
        }

        do {
            let resp = try await api.sendChat(userMessage: trimmed, currentPlan: weeklyPlan)
            updateMessageText(id: assistantId, newText: resp.assistantMessage.text)
            bestNextActionFromChat = resp.bestNextAction
        } catch {
            let resp = Self.stubChatResponse(for: trimmed, currentPlan: weeklyPlan)
            updateMessageText(id: assistantId, newText: resp.assistantMessage.text)
            bestNextActionFromChat = resp.bestNextAction
        }
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


