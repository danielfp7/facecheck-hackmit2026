import Foundation

enum APIError: LocalizedError {
    case badURL
    case server(Int, String)

    var errorDescription: String? {
        switch self {
        case .badURL: return "The server address isn't a valid URL."
        case .server(let code, let body): return "Server error \(code): \(body.prefix(200))"
        }
    }
}

struct API {
    var baseString: String

    private var decoder: JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func url(_ path: String, query: [URLQueryItem] = []) throws -> URL {
        guard var comps = URLComponents(string: baseString.trimmingCharacters(in: .whitespaces)) else { throw APIError.badURL }
        comps.path = path
        if !query.isEmpty { comps.queryItems = query }
        guard let u = comps.url, comps.host != nil else { throw APIError.badURL }
        return u
    }

    private func send(_ req: URLRequest) async throws -> Data {
        let (data, resp) = try await URLSession.shared.data(for: req)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(code) else {
            throw APIError.server(code, String(data: data, encoding: .utf8) ?? "")
        }
        return data
    }

    func health() async throws {
        _ = try await send(URLRequest(url: try url("/health"), timeoutInterval: 4))
    }

    func isEnrolled(user: String) async throws -> Bool {
        struct R: Codable { let enrolled: Bool }
        let data = try await send(URLRequest(url: try url("/users/\(user)"), timeoutInterval: 4))
        return try decoder.decode(R.self, from: data).enrolled
    }

    func pending(user: String) async throws -> AuthRequest? {
        let u = try url("/auth/pending", query: [URLQueryItem(name: "user", value: user)])
        let data = try await send(URLRequest(url: u, timeoutInterval: 4))
        return try decoder.decode(PendingResponse.self, from: data).request
    }

    func deny(requestID: String) async throws {
        var req = URLRequest(url: try url("/auth/requests/\(requestID)/deny"))
        req.httpMethod = "POST"
        _ = try await send(req)
    }

    func newChallenge() async throws -> Challenge {
        var req = URLRequest(url: try url("/challenge"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = Data("{}".utf8)
        return try decoder.decode(Challenge.self, from: try await send(req))
    }

    func enroll(user: String, selfie: Data) async throws {
        var form = Multipart()
        form.field("user", user)
        form.file("selfie", filename: "selfie.jpg", mime: "image/jpeg", data: selfie)
        _ = try await send(form.request(to: try url("/enroll")))
    }

    func verify(challengeID: String, metaJSON: Data, video: URL, selfie: Data?, user: String,
                requestID: String?, label: String) async throws -> VerifyResult {
        var form = Multipart()
        form.field("challenge_id", challengeID)
        form.field("meta", String(data: metaJSON, encoding: .utf8) ?? "{}")
        form.field("user", user)
        form.field("label", label)
        if let requestID { form.field("request_id", requestID) }
        form.file("video", filename: "video.mov", mime: "video/quicktime", data: try Data(contentsOf: video))
        if let selfie { form.file("selfie", filename: "selfie.jpg", mime: "image/jpeg", data: selfie) }
        var req = form.request(to: try url("/verify"))
        req.timeoutInterval = 120
        return try decoder.decode(VerifyResult.self, from: try await send(req))
    }
}

struct Multipart {
    private let boundary = "inhuman-\(UUID().uuidString)"
    private var body = Data()

    mutating func field(_ name: String, _ value: String) {
        body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".utf8))
    }

    mutating func file(_ name: String, filename: String, mime: String, data: Data) {
        body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"; filename=\"\(filename)\"\r\nContent-Type: \(mime)\r\n\r\n".utf8))
        body.append(data)
        body.append(Data("\r\n".utf8))
    }

    func request(to url: URL) -> URLRequest {
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        var full = body
        full.append(Data("--\(boundary)--\r\n".utf8))
        req.httpBody = full
        return req
    }
}
