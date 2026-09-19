import SwiftUI
import UIKit

/// Full-screen challenge: flash sequence (with haptic bursts), then a steady soft-white
/// heartbeat window.
///
/// Geometry contract shared with server/render.py:
///  - shape centered horizontally, spanning `shapeSpan` of the screen width
///  - vertical center at 0.25 / 0.50 / 0.75 of the height for top / middle / bottom
///  - triangle is equilateral, pointing up
///
/// State changes are made inside the CADisplayLink callback and stamped with the tick's
/// `targetTimestamp` (host clock), which is when that frame reaches the panel. Any fixed
/// offset left over is absorbed by the server's per-device lag baseline.
final class ChallengeViewController: UIViewController {
    private let challenge: Challenge
    private let capture: CaptureController
    private let onDone: (Result<CaptureBundle, Error>) -> Void

    private let shapeLayer = CAShapeLayer()
    private let pulseLabel = UILabel()
    private var link: CADisplayLink?
    private var previousBrightness: CGFloat = 0.5
    private var finished = false
    private let motion = MotionRecorder()
    private let haptics = HapticPlayer()

    // Sequence timing, all on the host clock.
    private var settleLoggedAt: Double?
    private var sequenceStart: Double = 0
    private var boundaries: [Double] = []       // cumulative end time of each state
    private var shownIndex: Int? = nil
    private var events: [(stateIndex: Int, ts: Double)] = []
    private var pendingHaptics: [Double] = []

    private let settleHold = 0.4    // recorded settle color before the first state
    private let tail = 0.5          // keep recording after the last state for late responses

    init(challenge: Challenge, capture: CaptureController, onDone: @escaping (Result<CaptureBundle, Error>) -> Void) {
        self.challenge = challenge
        self.capture = capture
        self.onDone = onDone
        super.init(nibName: nil, bundle: nil)
    }

    required init?(coder: NSCoder) { fatalError("not used") }

    override var prefersStatusBarHidden: Bool { true }
    override var prefersHomeIndicatorAutoHidden: Bool { true }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = color(challenge.settleColor)
        shapeLayer.isHidden = true
        view.layer.addSublayer(shapeLayer)
        view.addGestureRecognizer(UITapGestureRecognizer(target: self, action: #selector(abort)))

        pulseLabel.textColor = UIColor(white: 0.35, alpha: 1)
        pulseLabel.font = .systemFont(ofSize: 17, weight: .medium)
        pulseLabel.textAlignment = .center
        pulseLabel.numberOfLines = 2
        pulseLabel.isHidden = true
        pulseLabel.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(pulseLabel)
        NSLayoutConstraint.activate([
            pulseLabel.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            pulseLabel.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -40),
        ])

        var t = 0.0
        boundaries = challenge.states.map { t += $0.durationS; return t }
        pendingHaptics = (challenge.hapticTimesS ?? []).sorted()
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        previousBrightness = UIScreen.main.brightness
        UIScreen.main.brightness = 1.0
        UIApplication.shared.isIdleTimerDisabled = true
        haptics.prepare()

        Task { @MainActor in
            // Brightest color is up: let auto-exposure converge on it, then freeze everything.
            await capture.settleAndLock(settleSeconds: max(challenge.settleS, 0.6))
            guard !finished else { return }
            capture.startRecording()
            motion.start()
            let link = CADisplayLink(target: self, selector: #selector(tick(_:)))
            link.preferredFrameRateRange = CAFrameRateRange(minimum: 60, maximum: 120, preferred: 120)
            link.add(to: .main, forMode: .common)
            self.link = link
        }
    }

    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)
        // Torn down from outside (app left, session interrupted): stop everything quietly.
        if !finished {
            finished = true
            capture.cancelRecording()
            _ = motion.stop()
        }
        cleanup()
    }

    private func cleanup() {
        link?.invalidate()
        link = nil
        haptics.stop()
        UIScreen.main.brightness = previousBrightness
        UIApplication.shared.isIdleTimerDisabled = false
    }

    @objc private func tick(_ link: CADisplayLink) {
        let now = link.targetTimestamp
        guard settleLoggedAt != nil else {
            settleLoggedAt = now
            sequenceStart = now + settleHold
            events.append((-1, now))
            return
        }
        let t = now - sequenceStart
        if t < 0 { return }
        if t >= (boundaries.last ?? 0) + tail { endFlashPhase(); return }

        if let next = pendingHaptics.first, t >= next {
            pendingHaptics.removeFirst()
            haptics.burst(duration: challenge.hapticDurationS ?? 0.15)
        }

        let idx = min(boundaries.firstIndex { t < $0 } ?? challenge.states.count - 1, challenge.states.count - 1)
        if idx != shownIndex {
            shownIndex = idx
            show(challenge.states[idx])
            events.append((challenge.states[idx].index, now))
        }
    }

    private func show(_ state: ChallengeState) {
        CATransaction.begin()
        CATransaction.setDisableActions(true)     // no implicit fade: changes must be a hard step
        view.layer.backgroundColor = color(state.background).cgColor
        if let shape = state.shape {
            shapeLayer.path = path(for: shape, position: state.position)
            shapeLayer.fillColor = color(state.shapeColor).cgColor
            shapeLayer.isHidden = false
        } else {
            shapeLayer.isHidden = true
        }
        CATransaction.commit()
    }

    private func path(for shape: String, position: String) -> CGPath {
        let b = view.bounds
        let span = CGFloat(challenge.shapeSpan) * b.width
        let cx = b.midX
        let cy = b.height * (["top": 0.25, "middle": 0.5, "bottom": 0.75][position] ?? 0.5)
        switch shape {
        case "circle":
            return CGPath(ellipseIn: CGRect(x: cx - span / 2, y: cy - span / 2, width: span, height: span), transform: nil)
        case "square":
            return CGPath(rect: CGRect(x: cx - span / 2, y: cy - span / 2, width: span, height: span), transform: nil)
        default:
            let th = span * sqrt(3) / 2
            let p = CGMutablePath()
            p.move(to: CGPoint(x: cx, y: cy - th / 2))
            p.addLine(to: CGPoint(x: cx - span / 2, y: cy + th / 2))
            p.addLine(to: CGPoint(x: cx + span / 2, y: cy + th / 2))
            p.closeSubpath()
            return p
        }
    }

    private func color(_ name: String) -> UIColor {
        let rgb = challenge.colors[name] ?? [0, 0, 0]
        return UIColor(red: CGFloat(rgb[0]) / 255, green: CGFloat(rgb[1]) / 255, blue: CGFloat(rgb[2]) / 255, alpha: 1)
    }

    /// Flashes are over: close the video, then hold a steady soft white for the heartbeat.
    private func endFlashPhase() {
        guard !finished, link != nil else { return }
        link?.invalidate()
        link = nil
        let imu = motion.stop()
        let hapticLog = haptics.log
        haptics.stop()
        let events = self.events
        let pulseSeconds = challenge.rppgS ?? 0

        Task { @MainActor in
            do {
                // The writer finishes in the background while the heartbeat window runs.
                async let recording = capture.stopRecording()
                var rppg: [String: Any]? = nil
                if pulseSeconds > 0 {
                    let level = CGFloat(challenge.rppgLevel ?? 0.8)
                    CATransaction.begin()
                    CATransaction.setDisableActions(true)
                    shapeLayer.isHidden = true
                    view.layer.backgroundColor = UIColor(white: level, alpha: 1).cgColor
                    CATransaction.commit()
                    pulseLabel.isHidden = false
                    capture.startSampling()
                    let whole = Int(pulseSeconds.rounded(.up))
                    for remaining in stride(from: whole, to: 0, by: -1) {
                        guard !finished else { return }
                        pulseLabel.text = "Hold still: reading your pulse\n\(remaining)"
                        try? await Task.sleep(nanoseconds: UInt64(pulseSeconds / Double(whole) * 1e9))
                    }
                    rppg = await capture.stopSampling()
                }
                let rec = try await recording
                guard !finished else { return }
                finished = true
                cleanup()
                onDone(.success(CaptureBundle(videoURL: rec.url, frameTimestamps: rec.frames,
                                              droppedTimestamps: rec.dropped, displayEvents: events,
                                              camera: capture.cameraMeta, imu: imu, haptics: hapticLog, rppg: rppg)))
            } catch {
                guard !finished else { return }
                finished = true
                cleanup()
                onDone(.failure(error))
            }
        }
    }

    /// Tap anywhere to stop the flashing immediately.
    @objc private func abort() {
        guard !finished else { return }
        finished = true
        cleanup()
        _ = motion.stop()
        capture.cancelRecording()
        onDone(.failure(CaptureError.aborted))
    }
}

struct ChallengeScreen: UIViewControllerRepresentable {
    let challenge: Challenge
    let capture: CaptureController
    let onDone: (Result<CaptureBundle, Error>) -> Void

    func makeUIViewController(context: Context) -> ChallengeViewController {
        ChallengeViewController(challenge: challenge, capture: capture, onDone: onDone)
    }

    func updateUIViewController(_ vc: ChallengeViewController, context: Context) {}
}
