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

struct ChatSendRequest: Codable {
    let userMessage: String
    let visibleChatIsEmpty: Bool

    enum CodingKeys: String, CodingKey {
        case userMessage = "user_message"
        case visibleChatIsEmpty = "visible_chat_is_empty"
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

struct ChatStreamEvent: Codable {
    let type: EventType
    let messageId: String?
    let delta: String?
    let bestNextAction: PlanItem?
    let message: String?

    enum EventType: String, Codable {
        case typingStarted = "typing_started"
        case messageStarted = "message_started"
        case messageDelta = "message_delta"
        case messageCompleted = "message_completed"
        case bestNextAction = "best_next_action"
        case turnCompleted = "turn_completed"
        case error
    }

    enum CodingKeys: String, CodingKey {
        case type
        case messageId = "message_id"
        case delta
        case bestNextAction = "best_next_action"
        case message
    }
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

struct Material: Codable, Equatable {
    let id: String
    let title: String
    let courseName: String
    let description: String?
    let url: String?
    let updatedAt: String?
    let topicId: String?
    let attachments: [AttachmentLink]?
}

struct Announcement: Codable, Equatable {
    let id: String
    let courseName: String
    let text: String
    let url: String?
    let updatedAt: String?
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


