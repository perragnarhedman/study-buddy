import Foundation

// Shared meaning with backend schemas (stable).

struct AttachmentLink: Codable, Equatable {
    let title: String
    let url: String
}

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
    let attachments: [AttachmentLink]?

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

struct AssignmentCard: Identifiable, Codable, Equatable {
    let id: String
    let title: String
    let courseName: String?
    let dueDate: String?
    let estimatedMinutes: Int?
    let status: PlanItem.Status
    let sourceAssignmentId: String?
    let url: String?
    let attachments: [AttachmentLink]?
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
    let assignmentCards: [AssignmentCard]?

    enum CodingKeys: String, CodingKey {
        case assistantMessage = "assistant_message"
        case bestNextAction = "best_next_action"
        case assignmentCards = "assignment_cards"
    }
}

struct SetAssignmentStatusRequest: Codable {
    let sourceAssignmentId: String
    let status: PlanItem.Status
}

struct Assignment: Codable, Equatable {
    let id: String
    let title: String
    let dueDate: String?
    let courseName: String
    let description: String?
    let url: String?
    let estimatedMinutes: Int?
    let attachments: [AttachmentLink]?
}

struct GoogleAuthStartResponse: Codable {
    let authorizationURL: String
    let state: String

    enum CodingKeys: String, CodingKey {
        case authorizationURL = "authorization_url"
        case state
    }
}


