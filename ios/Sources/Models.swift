import Foundation

// Mirrors server/challenge.py and the /verify response. Decoded with .convertFromSnakeCase.

struct ChallengeState: Codable {
    let index: Int
    let shape: String?          // nil = plain full-screen color
    let shapeColor: String
    let background: String
    let position: String        // top / middle / bottom
    let durationS: Double
}

struct Challenge: Codable {
    let id: String
    let states: [ChallengeState]
    let settleColor: String
    let settleS: Double
    let colors: [String: [Int]]
    let shapeSpan: Double
}

struct AuthRequest: Codable, Identifiable {
    let id: String
    let user: String
    let appName: String
    let status: String
}

struct PendingResponse: Codable {
    let request: AuthRequest?
}

struct Tile: Codable, Identifiable {
    var id: String { name }
    let name: String
    let status: String          // green / yellow / red
    let headline: String
    let detail: String
}

struct LagPlot: Codable {
    let t: [Double]
    let measured: [[Double]]    // per frame [r, g, b]
    let expected: [[Double]]
}

struct LagSignal: Codable {
    let ok: Bool
    let reason: String?
    let lagMs: Double?
    let lagJitterMs: Double?
    let responseR2: Double?
    let plot: LagPlot?
}

struct CorneaState: Codable, Identifiable {
    var id: Int { state }
    let state: Int
    let sentShape: String
    let sentColor: String
    let sentPosition: String
    let decodedShape: String
    let score: Double
    let margin: Double
    let cropJpegB64: String
}

struct CorneaSignal: Codable {
    let ok: Bool
    let reason: String?
    let shapeAccuracy: Double?
    let positionCorr: Double?
    let colorScore: Double?
    let geometryOk: Bool?
    let reflectionWidthMm: Double?
    let states: [CorneaState]?
}

struct IdentitySignal: Codable {
    let similarity: Double?
    let reason: String?
}

struct Signals: Codable {
    let lag: LagSignal?
    let cornea: CorneaSignal?
    let identity: IdentitySignal?
}

struct VerifyResult: Codable {
    let verdict: String         // verified / unverified / unverifiable
    let reason: String
    let tiles: [Tile]
    let signals: Signals?
    let processingS: Double?
}

/// What the capture step hands to the uploader.
struct CaptureBundle {
    let videoURL: URL
    let frameTimestamps: [Double]       // host-clock seconds, one per written frame
    let droppedTimestamps: [Double]
    let displayEvents: [(stateIndex: Int, ts: Double)]
    let camera: [String: Any]
}
