import Foundation

// Shared meaning with backend schemas (stable).

struct ChatMessage: Identifiable, Codable, Equatable {
    let id: String
    let role: Role
    var text: String
    let timestamp: String // ISO8601

    enum Role: String, Codable {
        case user
        case assistant
    }
}

struct PlanItem: Identifiable, Codable, Equatable {
    let id: String
    let title: String
    let dueDate: String?
    let estimatedMinutes: Int?
    let status: Status
    let sourceAssignmentId: String?

    enum Status: String, Codable {
        case todo
        case doing
        case done
    }
}

struct WeeklyPlan: Codable, Equatable {
    let weekStart: String // ISO8601 date (YYYY-MM-DD)
    let items: [PlanItem]
}

struct ChatSendRequest: Codable {
    let userMessage: String
    let currentPlan: WeeklyPlan?

    enum CodingKeys: String, CodingKey {
        case userMessage = "user_message"
        case currentPlan = "current_plan"
    }
}

struct ChatSendResponse: Codable {
    let assistantMessage: ChatMessage
    let bestNextAction: PlanItem?

    enum CodingKeys: String, CodingKey {
        case assistantMessage = "assistant_message"
        case bestNextAction = "best_next_action"
    }
}


