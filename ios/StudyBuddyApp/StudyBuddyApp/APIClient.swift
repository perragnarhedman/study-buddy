import Foundation

enum APIError: Error {
    case invalidURL
    case badStatus(Int)
    case badRequest(String)
    case decodingFailed
    case serviceUnavailable
    case unauthorized
}

protocol ChatAPIClient {
    func sendChat(userMessage: String, sessionToken: String?) async throws -> ChatSendResponse
    func sendChatStream(userMessage: String, sessionToken: String?) -> AsyncThrowingStream<ChatStreamEvent, Error>
    func resetConversation(
        sessionToken: String?,
        clearAssignmentStatus: Bool,
        clearPreferences: Bool
    ) async throws
    func fetchClassroomAssignments(sessionToken: String) async throws -> [Assignment]
}

extension ChatAPIClient {
    func resetConversation(sessionToken: String?) async throws {
        try await resetConversation(
            sessionToken: sessionToken,
            clearAssignmentStatus: false,
            clearPreferences: false
        )
    }
}

final class APIClient: ChatAPIClient {
    var baseURLString: String

    init(baseURLString: String) {
        self.baseURLString = baseURLString
    }

    private func url(_ path: String) throws -> URL {
        guard let base = URL(string: baseURLString) else { throw APIError.invalidURL }
        return base.appendingPathComponent(path)
    }

    func health() async throws -> Bool {
        let u = try url("health")
        var req = URLRequest(url: u)
        req.httpMethod = "GET"
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw APIError.badStatus(-1) }
        guard (200..<300).contains(http.statusCode) else { throw APIError.badStatus(http.statusCode) }
        let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        return obj?["status"] as? String == "ok"
    }

    func sendChat(userMessage: String, sessionToken: String?) async throws -> ChatSendResponse {
        let u = try url("chat/send")
        var req = URLRequest(url: u)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token = sessionToken, !token.isEmpty {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let payload = ChatSendRequest(userMessage: userMessage)
        req.httpBody = try JSONEncoder().encode(payload)

        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw APIError.badStatus(-1) }
        if http.statusCode == 400 {
            let msg = String(data: data, encoding: .utf8) ?? ""
            throw APIError.badRequest(msg)
        }
        if http.statusCode == 503 { throw APIError.serviceUnavailable }
        if http.statusCode == 401 { throw APIError.unauthorized }
        guard (200..<300).contains(http.statusCode) else { throw APIError.badStatus(http.statusCode) }
        let decoded = try JSONDecoder().decode(ChatSendResponse.self, from: data)
        return decoded
    }

    func sendChatStream(userMessage: String, sessionToken: String?) -> AsyncThrowingStream<ChatStreamEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let u = try self.url("chat/send_stream")
                    var req = URLRequest(url: u)
                    req.httpMethod = "POST"
                    req.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    if let token = sessionToken, !token.isEmpty {
                        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                    }

                    let payload = ChatSendRequest(userMessage: userMessage)
                    req.httpBody = try JSONEncoder().encode(payload)

                    let (bytes, resp) = try await URLSession.shared.bytes(for: req)
                    guard let http = resp as? HTTPURLResponse else { throw APIError.badStatus(-1) }
                    if http.statusCode == 503 { throw APIError.serviceUnavailable }
                    if http.statusCode == 401 { throw APIError.unauthorized }
                    guard (200..<300).contains(http.statusCode) else { throw APIError.badStatus(http.statusCode) }

                    let decoder = JSONDecoder()
                    for try await line in bytes.lines {
                        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
                        guard !trimmed.isEmpty else { continue }
                        let data = Data(trimmed.utf8)
                        let event = try decoder.decode(ChatStreamEvent.self, from: data)
                        continuation.yield(event)
                    }

                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { [task] _ in
                task.cancel()
            }
        }
    }

    func resetConversation(
        sessionToken: String?,
        clearAssignmentStatus: Bool = false,
        clearPreferences: Bool = false
    ) async throws {
        var u = try url("chat/reset")
        var q: [URLQueryItem] = []
        if clearAssignmentStatus {
            q.append(URLQueryItem(name: "clear_assignment_status", value: "true"))
        }
        if clearPreferences {
            q.append(URLQueryItem(name: "clear_preferences", value: "true"))
        }
        if !q.isEmpty {
            u = u.appending(queryItems: q)
        }
        var req = URLRequest(url: u)
        req.httpMethod = "POST"
        if let token = sessionToken, !token.isEmpty {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let (_, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw APIError.badStatus(-1) }
        if http.statusCode == 401 { throw APIError.unauthorized }
        guard (200..<300).contains(http.statusCode) else { throw APIError.badStatus(http.statusCode) }
    }

    func googleAuthStart() async throws -> GoogleAuthStartResponse {
        let u = try url("auth/google/start")
        var req = URLRequest(url: u)
        req.httpMethod = "GET"
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw APIError.badStatus(-1) }
        guard (200..<300).contains(http.statusCode) else { throw APIError.badStatus(http.statusCode) }
        return try JSONDecoder().decode(GoogleAuthStartResponse.self, from: data)
    }

    func fetchClassroomAssignments(sessionToken: String) async throws -> [Assignment] {
        let u = try url("classroom/assignments")
        var req = URLRequest(url: u)
        req.httpMethod = "GET"
        req.setValue("Bearer \(sessionToken)", forHTTPHeaderField: "Authorization")
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw APIError.badStatus(-1) }
        if http.statusCode == 401 { throw APIError.unauthorized }
        guard (200..<300).contains(http.statusCode) else { throw APIError.badStatus(http.statusCode) }
        return try JSONDecoder().decode([Assignment].self, from: data)
    }

    func fetchClassroomMaterials(sessionToken: String) async throws -> [Material] {
        let u = try url("classroom/materials")
        var req = URLRequest(url: u)
        req.httpMethod = "GET"
        req.setValue("Bearer \(sessionToken)", forHTTPHeaderField: "Authorization")
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw APIError.badStatus(-1) }
        if http.statusCode == 401 { throw APIError.unauthorized }
        guard (200..<300).contains(http.statusCode) else { throw APIError.badStatus(http.statusCode) }
        return try JSONDecoder().decode([Material].self, from: data)
    }

    func fetchClassroomAnnouncements(sessionToken: String) async throws -> [Announcement] {
        let u = try url("classroom/announcements")
        var req = URLRequest(url: u)
        req.httpMethod = "GET"
        req.setValue("Bearer \(sessionToken)", forHTTPHeaderField: "Authorization")
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw APIError.badStatus(-1) }
        if http.statusCode == 401 { throw APIError.unauthorized }
        guard (200..<300).contains(http.statusCode) else { throw APIError.badStatus(http.statusCode) }
        return try JSONDecoder().decode([Announcement].self, from: data)
    }
}


