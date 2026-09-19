import CoreHaptics
import CoreMotion
import QuartzCore

/// Gyro + accelerometer at 100 Hz. CoreMotion timestamps are seconds since boot, the same
/// clock as camera frames (after conversion) and CADisplayLink, so everything lines up.
final class MotionRecorder {
    private let manager = CMMotionManager()
    private let queue = OperationQueue()
    private let lock = NSLock()
    private var t: [Double] = []
    private var gyro: [[Double]] = []
    private var accel: [[Double]] = []

    func start() {
        guard manager.isDeviceMotionAvailable else { return }
        lock.lock(); t = []; gyro = []; accel = []; lock.unlock()
        queue.maxConcurrentOperationCount = 1
        manager.deviceMotionUpdateInterval = 1.0 / 100.0
        manager.startDeviceMotionUpdates(to: queue) { [weak self] motion, _ in
            guard let self, let m = motion else { return }
            self.lock.lock()
            self.t.append(m.timestamp)
            self.gyro.append([m.rotationRate.x, m.rotationRate.y, m.rotationRate.z])
            self.accel.append([m.userAcceleration.x, m.userAcceleration.y, m.userAcceleration.z])
            self.lock.unlock()
        }
    }

    /// Stops and returns the log in the shape the server expects.
    func stop() -> [String: Any] {
        manager.stopDeviceMotionUpdates()
        lock.lock(); defer { lock.unlock() }
        return ["t": t, "gyro": gyro, "accel": accel]
    }
}

/// Short, strong haptic bursts, with the host-clock time each one was commanded.
final class HapticPlayer {
    private var engine: CHHapticEngine?
    private(set) var log: [[String: Any]] = []

    func prepare() {
        guard CHHapticEngine.capabilitiesForHardware().supportsHaptics else { return }
        do {
            let e = try CHHapticEngine()
            e.playsHapticsOnly = true
            e.isAutoShutdownEnabled = false
            try e.start()
            engine = e
            log = []
        } catch {
            engine = nil
        }
    }

    func burst(duration: Double) {
        guard let engine else { return }
        // As strong as the Taptic Engine goes: full intensity and sharpness held for the whole
        // burst, plus sharp transients through it. (0.15 s at sharpness 0.4 registered at only
        // ~4x background on the accelerometer and was barely visible to the camera.)
        func p(_ id: CHHapticEvent.ParameterID, _ v: Float) -> CHHapticEventParameter { CHHapticEventParameter(parameterID: id, value: v) }
        var events = [CHHapticEvent(eventType: .hapticContinuous,
                                    parameters: [p(.hapticIntensity, 1.0), p(.hapticSharpness, 1.0)],
                                    relativeTime: 0, duration: duration)]
        var t = 0.0
        while t < duration {
            events.append(CHHapticEvent(eventType: .hapticTransient,
                                        parameters: [p(.hapticIntensity, 1.0), p(.hapticSharpness, 1.0)], relativeTime: t))
            t += 0.04
        }
        do {
            let player = try engine.makePlayer(with: CHHapticPattern(events: events, parameters: []))
            let now = CACurrentMediaTime()
            try player.start(atTime: CHHapticTimeImmediate)
            log.append(["ts": now, "duration_s": duration])
        } catch {
            // A missed burst is visible to the server as "sensor felt n-1 of n".
        }
    }

    func stop() {
        engine?.stop(completionHandler: nil)
        engine = nil
    }
}
