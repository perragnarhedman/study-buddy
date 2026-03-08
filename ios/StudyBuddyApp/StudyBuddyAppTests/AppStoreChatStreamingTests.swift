import XCTest
@testable import StudyBuddyApp

@MainActor
final class AppStoreChatStreamingTests: XCTestCase {
    func testFirstOutgoingRequestFromFreshVisibleChatMarksVisibleChatEmpty() async {
        let api = MockChatAPIClient(
            streamEvents: [
                .init(type: .typingStarted, messageId: nil, delta: nil, bestNextAction: nil, message: nil),
                .init(type: .turnCompleted, messageId: nil, delta: nil, bestNextAction: nil, message: nil),
            ]
        )
        let store = AppStore(
            apiClientFactory: { _ in api },
            sessionTokenProvider: { "token" }
        )
        store.useStubData = false

        await store.sendUserMessage("Hej")

        XCTAssertEqual(api.sendChatStreamCalls.map(\.visibleChatIsEmpty), [true])
    }

    func testLaterOutgoingRequestFromSameVisibleChatDoesNotMarkVisibleChatEmpty() async {
        let api = MockChatAPIClient(
            streamEvents: [
                .init(type: .typingStarted, messageId: nil, delta: nil, bestNextAction: nil, message: nil),
                .init(type: .turnCompleted, messageId: nil, delta: nil, bestNextAction: nil, message: nil),
            ]
        )
        let store = AppStore(
            apiClientFactory: { _ in api },
            sessionTokenProvider: { "token" }
        )
        store.useStubData = false

        await store.sendUserMessage("Hej")
        await store.sendUserMessage("Vad har jag?")

        XCTAssertEqual(api.sendChatStreamCalls.map(\.visibleChatIsEmpty), [true, false])
    }

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
            sessionTokenProvider: { "token" }
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
            sessionTokenProvider: { "token" }
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
            sessionTokenProvider: { "token" }
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
            sessionTokenProvider: { "token" }
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

    func testUnsignedStoreStartsInIntroModeAndUsesIntroChatMode() async {
        let api = MockChatAPIClient(
            streamEvents: [
                .init(type: .typingStarted, messageId: nil, delta: nil, bestNextAction: nil, message: nil),
                .init(type: .turnCompleted, messageId: nil, delta: nil, bestNextAction: nil, message: nil),
            ]
        )
        let store = AppStore(
            apiClientFactory: { _ in api },
            sessionTokenProvider: { nil }
        )
        store.useStubData = false

        XCTAssertEqual(store.messages.map(\.role), [.assistant, .assistant])
        XCTAssertTrue(store.messages.first?.text.contains("Hello") ?? false)
        XCTAssertTrue(store.messages.first?.text.contains("Bonjour") ?? false)
        XCTAssertTrue(store.messages.first?.text.contains("Hola") ?? false)
        XCTAssertEqual(
            store.messages.last?.text,
            "Study Buddy helps you understand what to work on and get started with schoolwork."
        )

        await store.sendUserMessage("What can you help with?")

        XCTAssertEqual(api.sendChatStreamCalls.map(\.chatMode), [.intro])
        XCTAssertEqual(api.sendChatStreamCalls.map(\.visibleChatIsEmpty), [true])
    }

    func testSignOutReturnsSignedInStoreToIntroWelcome() {
        let store = AppStore(
            apiClientFactory: { _ in MockChatAPIClient() },
            sessionTokenProvider: { "token" }
        )
        store.useStubData = false
        store.messages = [
            ChatMessage(id: "u1", role: .user, text: "Help me", timestamp: "t")
        ]
        store.classroomAssignmentsImported = 3
        store.classroomAssignments = [
            Assignment(
                id: "a1",
                title: "Essay",
                dueDate: nil,
                courseName: "English",
                description: nil,
                url: nil,
                estimatedMinutes: nil,
                attachments: nil
            )
        ]

        store.signOut()

        XCTAssertFalse(store.isSignedIn)
        XCTAssertNil(store.classroomAssignmentsImported)
        XCTAssertTrue(store.classroomAssignments.isEmpty)
        XCTAssertEqual(store.messages.map(\.role), [.assistant, .assistant])
        XCTAssertTrue(store.messages.first?.text.contains("Hello") ?? false)
        XCTAssertEqual(
            store.messages.last?.text,
            "Study Buddy helps you understand what to work on and get started with schoolwork."
        )
    }

    func testSaveSessionTokenShowsSignedInWelcomeMessage() {
        let store = AppStore(
            apiClientFactory: { _ in MockChatAPIClient() },
            sessionTokenProvider: { nil }
        )
        store.useStubData = false

        store.saveSessionToken("fresh-token")

        XCTAssertTrue(store.isSignedIn)
        XCTAssertEqual(store.messages.count, 1)
        XCTAssertEqual(store.messages.first?.role, .assistant)
        XCTAssertEqual(store.messages.first?.text, "Welcome. I'm ready to help with your schoolwork.")
    }
}

private final class MockChatAPIClient: ChatAPIClient {
    struct ChatCall: Equatable {
        let userMessage: String
        let visibleChatIsEmpty: Bool
        let chatMode: ChatMode
    }

    private let streamEvents: [ChatStreamEvent]
    private let streamError: Error?
    private let fallbackResponse: ChatSendResponse
    private(set) var sendChatCalls: [ChatCall] = []
    private(set) var sendChatStreamCalls: [ChatCall] = []

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

    func sendChat(
        userMessage: String,
        visibleChatIsEmpty: Bool,
        chatMode: ChatMode,
        sessionToken: String?
    ) async throws -> ChatSendResponse {
        sendChatCalls.append(.init(userMessage: userMessage, visibleChatIsEmpty: visibleChatIsEmpty, chatMode: chatMode))
        return fallbackResponse
    }

    func sendChatStream(
        userMessage: String,
        visibleChatIsEmpty: Bool,
        chatMode: ChatMode,
        sessionToken: String?
    ) -> AsyncThrowingStream<ChatStreamEvent, Error> {
        sendChatStreamCalls.append(.init(userMessage: userMessage, visibleChatIsEmpty: visibleChatIsEmpty, chatMode: chatMode))
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
