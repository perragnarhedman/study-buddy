import XCTest
@testable import StudyBuddyApp

@MainActor
final class AppStoreChatStreamingTests: XCTestCase {
    func testSendUserMessageBuildsAssistantBubblesFromStream() async {
        let api = MockChatAPIClient(
            streamEvents: [
                .init(type: .typingStarted, messageId: nil, delta: nil, bestNextAction: nil, message: nil),
                .init(type: .messageStarted, messageId: "a1", delta: nil, bestNextAction: nil, message: nil),
                .init(type: .messageDelta, messageId: "a1", delta: "Hi!", bestNextAction: nil, message: nil),
                .init(type: .messageCompleted, messageId: "a1", delta: nil, bestNextAction: nil, message: nil),
                .init(type: .messageStarted, messageId: "a2", delta: nil, bestNextAction: nil, message: nil),
                .init(type: .messageDelta, messageId: "a2", delta: "Här är en tydlig överblick.", bestNextAction: nil, message: nil),
                .init(type: .messageCompleted, messageId: "a2", delta: nil, bestNextAction: nil, message: nil),
                .init(
                    type: .bestNextAction,
                    messageId: nil,
                    delta: nil,
                    bestNextAction: PlanItem(
                        id: "p1",
                        title: "Start math",
                        dueDate: nil,
                        estimatedMinutes: 15,
                        status: .todo,
                        sourceAssignmentId: "a1",
                        attachments: nil
                    ),
                    message: nil
                ),
                .init(type: .turnCompleted, messageId: nil, delta: nil, bestNextAction: nil, message: nil),
            ]
        )
        let store = AppStore(
            apiClientFactory: { _ in api },
            sessionTokenProvider: { nil }
        )
        store.useStubData = false

        await store.sendUserMessage("Hej")

        XCTAssertEqual(store.messages.map(\.role), [.user, .assistant, .assistant])
        XCTAssertEqual(store.messages.map(\.text), ["Hej", "Hi!", "Här är en tydlig överblick."])
        XCTAssertEqual(store.bestNextAction?.title, "Start math")
        XCTAssertFalse(store.isAssistantTyping)
        XCTAssertNil(store.chatErrorMessage)
        XCTAssertEqual(api.sendChatCalls.count, 0)
    }

    func testSendUserMessageFallsBackToOneShotWhenStreamFailsBeforeAssistantContent() async {
        let fallbackResponse = ChatSendResponse(
            assistantMessage: ChatMessage(
                id: "assistant",
                role: .assistant,
                text: "Hi! Här är en tydlig överblick.\n\nMatte först.",
                timestamp: "t"
            ),
            bestNextAction: nil
        )
        let api = MockChatAPIClient(
            streamError: APIError.serviceUnavailable,
            fallbackResponse: fallbackResponse
        )
        let store = AppStore(
            apiClientFactory: { _ in api },
            sessionTokenProvider: { nil }
        )
        store.useStubData = false

        await store.sendUserMessage("Hej")

        XCTAssertEqual(store.messages.map(\.text), ["Hej", "Hi!", "Här är en tydlig överblick.", "Matte först."])
        XCTAssertFalse(store.isAssistantTyping)
        XCTAssertNil(store.chatErrorMessage)
        XCTAssertEqual(api.sendChatCalls.count, 1)
    }

    func testSendUserMessageFallbackMergesWeakPunctuationSegment() async {
        let fallbackResponse = ChatSendResponse(
            assistantMessage: ChatMessage(
                id: "assistant",
                role: .assistant,
                text: "Jag kan inte kolla det säkert här.\n\n).\n\nMen om du menar resultatet kan jag inte bekräfta det.",
                timestamp: "t"
            ),
            bestNextAction: nil
        )
        let api = MockChatAPIClient(
            streamError: APIError.serviceUnavailable,
            fallbackResponse: fallbackResponse
        )
        let store = AppStore(
            apiClientFactory: { _ in api },
            sessionTokenProvider: { nil }
        )
        store.useStubData = false

        await store.sendUserMessage("Hej")

        XCTAssertEqual(
            store.messages.map(\.text),
            [
                "Hej",
                "Jag kan inte kolla det säkert här.).",
                "Men om du menar resultatet kan jag inte bekräfta det.",
            ]
        )
    }

    func testSendUserMessageCoalescesWeakPunctuationStreamBubble() async {
        let api = MockChatAPIClient(
            streamEvents: [
                .init(type: .typingStarted, messageId: nil, delta: nil, bestNextAction: nil, message: nil),
                .init(type: .messageStarted, messageId: "a1", delta: nil, bestNextAction: nil, message: nil),
                .init(type: .messageDelta, messageId: "a1", delta: "Jag kan inte kolla det säkert här.", bestNextAction: nil, message: nil),
                .init(type: .messageCompleted, messageId: "a1", delta: nil, bestNextAction: nil, message: nil),
                .init(type: .messageStarted, messageId: "a2", delta: nil, bestNextAction: nil, message: nil),
                .init(type: .messageDelta, messageId: "a2", delta: ").", bestNextAction: nil, message: nil),
                .init(type: .messageCompleted, messageId: "a2", delta: nil, bestNextAction: nil, message: nil),
                .init(type: .messageStarted, messageId: "a3", delta: nil, bestNextAction: nil, message: nil),
                .init(type: .messageDelta, messageId: "a3", delta: "Men om du menar resultatet kan jag inte bekräfta det.", bestNextAction: nil, message: nil),
                .init(type: .messageCompleted, messageId: "a3", delta: nil, bestNextAction: nil, message: nil),
                .init(type: .turnCompleted, messageId: nil, delta: nil, bestNextAction: nil, message: nil),
            ]
        )
        let store = AppStore(
            apiClientFactory: { _ in api },
            sessionTokenProvider: { nil }
        )
        store.useStubData = false

        await store.sendUserMessage("Hej")

        XCTAssertEqual(
            store.messages.map(\.text),
            [
                "Hej",
                "Jag kan inte kolla det säkert här.).",
                "Men om du menar resultatet kan jag inte bekräfta det.",
            ]
        )
    }
}

private final class MockChatAPIClient: ChatAPIClient {
    private let streamEvents: [ChatStreamEvent]
    private let streamError: Error?
    private let fallbackResponse: ChatSendResponse
    private(set) var sendChatCalls: [String] = []

    init(
        streamEvents: [ChatStreamEvent] = [],
        streamError: Error? = nil,
        fallbackResponse: ChatSendResponse = ChatSendResponse(
            assistantMessage: ChatMessage(id: "fallback", role: .assistant, text: "Fallback", timestamp: "t"),
            bestNextAction: nil
        )
    ) {
        self.streamEvents = streamEvents
        self.streamError = streamError
        self.fallbackResponse = fallbackResponse
    }

    func sendChat(userMessage: String, sessionToken: String?) async throws -> ChatSendResponse {
        sendChatCalls.append(userMessage)
        return fallbackResponse
    }

    func sendChatStream(userMessage: String, sessionToken: String?) -> AsyncThrowingStream<ChatStreamEvent, Error> {
        AsyncThrowingStream { continuation in
            if let streamError {
                continuation.finish(throwing: streamError)
                return
            }

            for event in streamEvents {
                continuation.yield(event)
            }
            continuation.finish()
        }
    }

    func resetConversation(
        sessionToken: String?,
        clearAssignmentStatus: Bool,
        clearPreferences: Bool
    ) async throws {}

    func fetchClassroomAssignments(sessionToken: String) async throws -> [Assignment] {
        []
    }
}
