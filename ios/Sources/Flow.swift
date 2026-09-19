import SwiftUI
import UIKit

enum Step: Equatable {
    case home
    case approve
    case warning
    case selfie(enrolling: Bool)
    case position
    case challenge
    case uploading
    case results
}

/// One verification from request to verdict. The camera session runs continuously from
/// the selfie through the close-up so the two can't be separate sittings.
@MainActor
final class Flow: ObservableObject {
    // Edited in SettingsView through @AppStorage with the same keys.
    static let defaultServerURL = "http://Daniels-Mac.local:8000"   // this Mac by name; works on hotspot, USB or shared Wi-Fi
    var serverURL: String { UserDefaults.standard.string(forKey: "serverURL") ?? Flow.defaultServerURL }
    var userName: String { UserDefaults.standard.string(forKey: "userName") ?? "daniel" }

    @Published var step: Step = .home
    @Published var request: AuthRequest?
    @Published var enrolled = false
    @Published var serverReachable = false
    @Published var challenge: Challenge?
    @Published var result: VerifyResult?
    @Published var selfie: Data?
    @Published var error: String?
    @Published var busy = false
    /// Tags the saved capture on the server, for threshold tuning.
    @Published var label = "real"

    let capture = CaptureController()
    var api: API { API(baseString: serverURL) }
    private var pollTask: Task<Void, Never>?

    // MARK: Polling (stands in for a push notification)

    func startPolling() {
        pollTask?.cancel()
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.pollOnce()
                try? await Task.sleep(nanoseconds: 2_000_000_000)
            }
        }
    }

    private func pollOnce() async {
        guard step == .home else { return }
        do {
            enrolled = try await api.isEnrolled(user: userName)
            serverReachable = true
            if enrolled, let req = try await api.pending(user: userName), step == .home {
                request = req
                step = .approve
                UINotificationFeedbackGenerator().notificationOccurred(.warning)
            }
        } catch {
            // The first LAN request fails until the local-network prompt is accepted; keep trying.
            serverReachable = false
        }
    }

    // MARK: Steps

    func beginEnrollment() { request = nil; openCamera(then: .selfie(enrolling: true)) }
    func beginTestRun() { request = nil; step = .warning }
    func approve() { step = .warning }

    func deny() {
        let rid = request?.id
        reset()
        Task { if let rid { try? await api.deny(requestID: rid) } }
    }

    func acceptWarning() { openCamera(then: .selfie(enrolling: false)) }

    private func openCamera(then next: Step) {
        busy = true
        Task {
            do {
                try await capture.start()
                capture.setAutomatic()
                step = next
            } catch { fail(error) }
            busy = false
        }
    }

    func shutter(enrolling: Bool) {
        busy = true
        Task {
            guard let jpeg = await capture.takeSelfie() else { fail(CaptureError.noCamera); busy = false; return }
            if enrolling {
                do {
                    try await api.enroll(user: userName, selfie: jpeg)
                    enrolled = true
                    reset()
                } catch { fail(error) }
            } else {
                selfie = jpeg
                step = .position
            }
            busy = false
        }
    }

    func startChallenge() {
        busy = true
        Task {
            do {
                challenge = try await api.newChallenge()   // fetched last: it expires in 90 s
                step = .challenge
            } catch { fail(error) }
            busy = false
        }
    }

    func challengeFinished(_ outcome: Result<CaptureBundle, Error>) {
        capture.setAutomatic()
        switch outcome {
        case .failure(let e): fail(e)
        case .success(let bundle):
            step = .uploading
            Task { await upload(bundle) }
        }
    }

    private func upload(_ b: CaptureBundle) async {
        guard let ch = challenge else { return }
        let screen = Device.screenSizeMM()
        let meta: [String: Any] = [
            "schema": 1,
            "challenge_id": ch.id,
            "device_model": Device.modelIdentifier(),
            "frames": b.frameTimestamps,
            "dropped": b.droppedTimestamps,
            "display_events": b.displayEvents.map { ["state_index": $0.stateIndex, "ts": $0.ts] },
            "camera": b.camera,
            "screen": ["brightness": 1.0, "width_mm": screen.width, "height_mm": screen.height],
            "distance_mm": capture.workingDistanceMM,
            "imu": [], "haptics": [],
        ]
        do {
            let json = try JSONSerialization.data(withJSONObject: meta)
            result = try await api.verify(challengeID: ch.id, metaJSON: json, video: b.videoURL, selfie: selfie,
                                          user: userName, requestID: request?.id, label: label)
            try? FileManager.default.removeItem(at: b.videoURL)
            capture.stop()
            UINotificationFeedbackGenerator().notificationOccurred(result?.verdict == "verified" ? .success : .error)
            step = .results
        } catch { fail(error) }
    }

    func reset() {
        capture.stop()
        request = nil; challenge = nil; result = nil; selfie = nil
        step = .home
    }

    private func fail(_ e: Error) {
        error = e.localizedDescription
        reset()
    }
}

enum Device {
    static func modelIdentifier() -> String {
        var info = utsname()
        uname(&info)
        return withUnsafePointer(to: &info.machine) {
            $0.withMemoryRebound(to: CChar.self, capacity: 1) { String(cString: $0) }
        }
    }

    /// Physical screen size, from the point size -> diagonal of known iPhones. Only used for
    /// the corneal-reflection size check, which tolerates a wide range.
    static func screenSizeMM() -> (width: Double, height: Double) {
        let s = UIScreen.main.bounds.size
        let w = Double(min(s.width, s.height)), h = Double(max(s.width, s.height))
        let diagonalInches: Double
        switch (Int(w), Int(h)) {
        case (375, 667): diagonalInches = 4.7
        case (375, 812): diagonalInches = 5.6
        case (390, 844), (393, 852): diagonalInches = 6.1
        case (402, 874), (414, 896): diagonalInches = 6.3
        case (428, 926), (430, 932): diagonalInches = 6.7
        case (440, 956): diagonalInches = 6.9
        default: diagonalInches = 6.1
        }
        let diagMM = diagonalInches * 25.4
        let norm = (w * w + h * h).squareRoot()
        return (diagMM * w / norm, diagMM * h / norm)
    }
}
