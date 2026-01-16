import Foundation

enum APIError: Error {
    case invalidURL
    case badStatus(Int)
    case decodingFailed
}

final class APIClient {
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

    func fetchWeeklyPlan(sessionToken: String?) async throws -> WeeklyPlan {
        let u = try url("plan/week")
        var req = URLRequest(url: u)
        req.httpMethod = "GET"
        if let token = sessionToken, !token.isEmpty {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw APIError.badStatus(-1) }
        guard (200..<300).contains(http.statusCode) else { throw APIError.badStatus(http.statusCode) }
        return try JSONDecoder().decode(WeeklyPlan.self, from: data)
    }

    func sendChat(userMessage: String, currentPlan: WeeklyPlan?, sessionToken: String?) async throws -> ChatSendResponse {
        let u = try url("chat/send")
        var req = URLRequest(url: u)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token = sessionToken, !token.isEmpty {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let payload = ChatSendRequest(userMessage: userMessage, currentPlan: currentPlan)
        req.httpBody = try JSONEncoder().encode(payload)

        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw APIError.badStatus(-1) }
        guard (200..<300).contains(http.statusCode) else { throw APIError.badStatus(http.statusCode) }
        let decoded = try JSONDecoder().decode(ChatSendResponse.self, from: data)
        return decoded
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
        guard (200..<300).contains(http.statusCode) else { throw APIError.badStatus(http.statusCode) }
        return try JSONDecoder().decode([Assignment].self, from: data)
    }
}


