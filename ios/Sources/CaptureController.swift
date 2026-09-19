import AVFoundation
import CoreImage
import UIKit

enum CaptureError: LocalizedError {
    case noCamera, denied, writerFailed(String), aborted

    var errorDescription: String? {
        switch self {
        case .noCamera: return "No front camera available."
        case .denied: return "Camera access is off. Enable it in Settings > InHuman."
        case .writerFailed(let why): return "Recording failed: \(why)"
        case .aborted: return "Check cancelled."
        }
    }
}

/// Front-camera capture with everything automatic turned off, recording frames with
/// host-clock timestamps so they can be lined up against the display's change times.
///
/// Uses AVCaptureVideoDataOutput + AVAssetWriter; AVCaptureMovieFileOutput would lose
/// the per-frame clock mapping. No audio input on purpose: it can change the session's
/// synchronization clock.
/// `@unchecked Sendable`: all mutable recording state is confined to `queue`.
final class CaptureController: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate, @unchecked Sendable {
    let session = AVCaptureSession()
    private(set) var device: AVCaptureDevice?
    private let output = AVCaptureVideoDataOutput()
    private let queue = DispatchQueue(label: "inhuman.capture")
    private let ciContext = CIContext()
    private var configured = false

    // Touched only on `queue`.
    private var recording = false
    private var writer: AVAssetWriter?
    private var writerInput: AVAssetWriterInput?
    private var frameTS: [Double] = []
    private var droppedTS: [Double] = []
    private var selfieWaiters: [(Data?) -> Void] = []
    private var frameSize = CGSize.zero
    // Heartbeat window: per-frame mean color over a grid, instead of more video.
    private var sampling = false
    private var sampleTS: [Double] = []
    private var sampleRGB: [[[Double]]] = []
    static let gridRows = 6, gridCols = 4
    // Transit: small frames from the selfie until the flashes start, so the server can
    // watch the move to the eye as one continuous shot.
    private var transitOn = false
    private var transitBlob = Data()
    private var transitTS: [Double] = []
    private var lastTransit = 0.0
    static let transitInterval = 0.1, transitWidth: CGFloat = 480, transitMaxFrames = 260

    private(set) var fps: Double = 30

    // MARK: Setup

    func start() async throws {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: break
        case .notDetermined:
            guard await AVCaptureDevice.requestAccess(for: .video) else { throw CaptureError.denied }
        default: throw CaptureError.denied
        }
        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
            queue.async {
                do {
                    if !self.configured { try self.configure() }
                    if !self.session.isRunning { self.session.startRunning() }
                    cont.resume()
                } catch { cont.resume(throwing: error) }
            }
        }
    }

    func stop() {
        queue.async { if self.session.isRunning { self.session.stopRunning() } }
    }

    private func configure() throws {
        guard let cam = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .front) else {
            throw CaptureError.noCamera
        }
        device = cam
        session.beginConfiguration()
        session.sessionPreset = .inputPriority
        // Keep the capture in sRGB so displayed and measured colors are comparable.
        session.automaticallyConfiguresCaptureDeviceForWideColor = false

        let input = try AVCaptureDeviceInput(device: cam)
        guard session.canAddInput(input) else { throw CaptureError.noCamera }
        session.addInput(input)

        output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_420YpCbCr8BiPlanarFullRange]
        output.alwaysDiscardsLateVideoFrames = false
        output.setSampleBufferDelegate(self, queue: queue)
        guard session.canAddOutput(output) else { throw CaptureError.noCamera }
        session.addOutput(output)
        session.commitConfiguration()

        // Format: 1080p, plain 8-bit 420f, no HDR, fastest frame rate up to 60.
        let candidates = cam.formats.filter { f in
            let d = CMVideoFormatDescriptionGetDimensions(f.formatDescription)
            let sub = CMFormatDescriptionGetMediaSubType(f.formatDescription)
            return d.width == 1920 && d.height == 1080
                && sub == kCVPixelFormatType_420YpCbCr8BiPlanarFullRange
                && !f.isVideoHDRSupported
        }
        let pool = candidates.isEmpty ? cam.formats.filter {
            let d = CMVideoFormatDescriptionGetDimensions($0.formatDescription)
            return d.width == 1920 && d.height == 1080
        } : candidates
        let best = pool.max { a, b in
            (a.videoSupportedFrameRateRanges.map(\.maxFrameRate).max() ?? 0)
                < (b.videoSupportedFrameRateRanges.map(\.maxFrameRate).max() ?? 0)
        }

        try cam.lockForConfiguration()
        if let best {
            cam.activeFormat = best
            let maxRate = best.videoSupportedFrameRateRanges.map(\.maxFrameRate).max() ?? 30
            fps = min(60, maxRate)
            let dur = CMTime(value: 1, timescale: CMTimeScale(fps))
            cam.activeVideoMinFrameDuration = dur
            cam.activeVideoMaxFrameDuration = dur
        }
        if cam.activeFormat.isVideoHDRSupported {
            cam.automaticallyAdjustsVideoHDREnabled = false
            cam.isVideoHDREnabled = false
        }
        if cam.isLowLightBoostSupported { cam.automaticallyEnablesLowLightBoostWhenAvailable = false }
        if cam.activeColorSpace != .sRGB, cam.activeFormat.supportedColorSpaces.contains(.sRGB) {
            cam.activeColorSpace = .sRGB
        }
        cam.videoZoomFactor = 1
        cam.unlockForConfiguration()

        AVCaptureDevice.centerStageControlMode = .app
        AVCaptureDevice.isCenterStageEnabled = false

        if let conn = output.connection(with: .video) {
            // Deliver upright portrait buffers, unmirrored, so the server never has to guess.
            if conn.isVideoRotationAngleSupported(90) { conn.videoRotationAngle = 90 }
            conn.automaticallyAdjustsVideoMirroring = false
            conn.isVideoMirrored = false
            if conn.isVideoStabilizationSupported { conn.preferredVideoStabilizationMode = .off }
        }
        configured = true
    }

    // MARK: Exposure / focus

    /// Instructed eye-to-phone distance. Closer is much better: the corneal reflection's size
    /// goes as 1/distance^2. `minimumFocusDistance` is not used as a floor because it is
    /// conservative (an iPhone 14 Pro reports 200 mm yet is sharp well inside that); the server
    /// measures the true distance from the iris anyway.
    var workingDistanceMM: Double {
        let inches = UserDefaults.standard.double(forKey: "distanceInches")
        return (inches > 0 ? inches : 4) * 25.4
    }

    /// Back to fully automatic, for the selfie and positioning steps.
    func setAutomatic() {
        guard let cam = device, (try? cam.lockForConfiguration()) != nil else { return }
        if cam.isExposureModeSupported(.continuousAutoExposure) { cam.exposureMode = .continuousAutoExposure }
        cam.setExposureTargetBias(0, completionHandler: nil)
        if cam.isWhiteBalanceModeSupported(.continuousAutoWhiteBalance) { cam.whiteBalanceMode = .continuousAutoWhiteBalance }
        if cam.isFocusModeSupported(.continuousAutoFocus) {
            if cam.isAutoFocusRangeRestrictionSupported { cam.autoFocusRangeRestriction = .near }
            cam.focusMode = .continuousAutoFocus
        }
        cam.unlockForConfiguration()
    }

    /// Call while the brightest challenge color is on screen. Underexposes slightly so
    /// screen-lit skin doesn't clip, then freezes exposure, white balance and focus.
    func settleAndLock(settleSeconds: Double) async {
        guard let cam = device else { return }
        if (try? cam.lockForConfiguration()) != nil {
            cam.setExposureTargetBias(max(cam.minExposureTargetBias, -0.7), completionHandler: nil)
            cam.unlockForConfiguration()
        }
        try? await Task.sleep(nanoseconds: UInt64(settleSeconds * 1e9))

        guard (try? cam.lockForConfiguration()) != nil else { return }
        // Cap exposure at 1/120 s: short enough to keep transitions sharp in time, and a
        // fixed duration keeps the timestamp-to-exposure offset constant for calibration.
        let cap = CMTime(value: 1, timescale: 120)
        if cam.isExposureModeSupported(.custom), cam.exposureDuration > cap {
            let ratio = Float(cam.exposureDuration.seconds / cap.seconds)
            let iso = min(max(cam.iso * ratio, cam.activeFormat.minISO), cam.activeFormat.maxISO)
            cam.setExposureModeCustom(duration: cap, iso: iso, completionHandler: nil)
        } else if cam.isExposureModeSupported(.locked) {
            cam.exposureMode = .locked
        }
        if cam.isWhiteBalanceModeSupported(.locked) { cam.whiteBalanceMode = .locked }
        if cam.isFocusModeSupported(.locked) { cam.focusMode = .locked }   // stop AF hunting on black frames
        cam.unlockForConfiguration()
        try? await Task.sleep(nanoseconds: 120_000_000)   // let the lock take effect
    }

    var cameraMeta: [String: Any] {
        guard let cam = device else { return [:] }
        // videoFieldOfView is across the sensor's long side; frames are portrait, so
        // convert to the FOV across the delivered frame's width (the short side).
        let longFOV = Double(cam.activeFormat.videoFieldOfView) * .pi / 180
        let dims = CMVideoFormatDescriptionGetDimensions(cam.activeFormat.formatDescription)
        let shortOverLong = Double(min(dims.width, dims.height)) / Double(max(dims.width, dims.height))
        let widthFOV = 2 * atan(tan(longFOV / 2) * shortOverLong) * 180 / .pi
        return [
            "width": Int(frameSize.width), "height": Int(frameSize.height), "fps": fps,
            "fov_deg": widthFOV, "mirrored": false,
            "iso": Double(cam.iso), "exposure_s": cam.exposureDuration.seconds,
            "focus_locked": cam.focusMode == .locked,
            "min_focus_mm": cam.minimumFocusDistance,
            "lens_position": Double(cam.lensPosition),
        ]
    }

    // MARK: Selfie

    /// JPEG of the next camera frame.
    func takeSelfie() async -> Data? {
        await withCheckedContinuation { cont in
            queue.async { self.selfieWaiters.append { cont.resume(returning: $0) } }
        }
    }

    // MARK: Recording

    func startRecording() {
        queue.async {
            self.frameTS = []
            self.droppedTS = []
            self.writer = nil
            self.writerInput = nil
            self.recording = true
        }
    }

    func stopRecording() async throws -> (url: URL, frames: [Double], dropped: [Double]) {
        try await withCheckedThrowingContinuation { cont in
            queue.async {
                self.recording = false
                guard let writer = self.writer, let input = self.writerInput else {
                    cont.resume(throwing: CaptureError.writerFailed("no frames were recorded"))
                    return
                }
                let frames = self.frameTS, dropped = self.droppedTS
                input.markAsFinished()
                writer.finishWriting {
                    if writer.status == .completed {
                        cont.resume(returning: (writer.outputURL, frames, dropped))
                    } else {
                        cont.resume(throwing: CaptureError.writerFailed(writer.error?.localizedDescription ?? "unknown"))
                    }
                }
                self.writer = nil
                self.writerInput = nil
            }
        }
    }

    func cancelRecording() {
        queue.async {
            self.recording = false
            self.writer?.cancelWriting()
            self.writer = nil
            self.writerInput = nil
        }
    }

    // MARK: Transit frames

    func startTransit() {
        queue.async {
            self.transitBlob = Data()
            self.transitTS = []
            self.lastTransit = 0
            self.transitOn = true
        }
    }

    func stopTransit() {
        queue.async { self.transitOn = false }
    }

    /// Frames packed as repeated [uint32 little-endian length][JPEG], plus their timestamps.
    func takeTransit() async -> (blob: Data, ts: [Double]) {
        await withCheckedContinuation { cont in
            queue.async {
                self.transitOn = false
                cont.resume(returning: (self.transitBlob, self.transitTS))
                self.transitBlob = Data()
                self.transitTS = []
            }
        }
    }

    private func appendTransit(_ pixels: CVPixelBuffer, at ts: Double) {
        guard transitTS.count < CaptureController.transitMaxFrames else { return }
        let image = CIImage(cvPixelBuffer: pixels)
        let scale = CaptureController.transitWidth / image.extent.width
        let small = image.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        guard let jpeg = ciContext.jpegRepresentation(
            of: small, colorSpace: CGColorSpace(name: CGColorSpace.sRGB)!,
            options: [kCGImageDestinationLossyCompressionQuality as CIImageRepresentationOption: 0.65]) else { return }
        var n = UInt32(jpeg.count).littleEndian
        withUnsafeBytes(of: &n) { transitBlob.append(contentsOf: $0) }
        transitBlob.append(jpeg)
        transitTS.append(ts)
        lastTransit = ts
    }

    // MARK: Heartbeat sampling

    func startSampling() {
        queue.async {
            self.sampleTS = []
            self.sampleRGB = []
            self.sampling = true
        }
    }

    func stopSampling() async -> [String: Any] {
        await withCheckedContinuation { cont in
            queue.async {
                self.sampling = false
                cont.resume(returning: ["t": self.sampleTS, "rgb": self.sampleRGB,
                                        "grid": [CaptureController.gridRows, CaptureController.gridCols]])
            }
        }
    }

    /// Mean RGB (0...1) per grid cell of a 420f bi-planar buffer, sampling every 8th pixel.
    private func gridMeans(_ pb: CVPixelBuffer) -> [[Double]] {
        let rows = CaptureController.gridRows, cols = CaptureController.gridCols
        CVPixelBufferLockBaseAddress(pb, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pb, .readOnly) }
        guard CVPixelBufferGetPlaneCount(pb) >= 2,
              let yBase = CVPixelBufferGetBaseAddressOfPlane(pb, 0),
              let cBase = CVPixelBufferGetBaseAddressOfPlane(pb, 1) else { return [] }
        let w = CVPixelBufferGetWidthOfPlane(pb, 0), h = CVPixelBufferGetHeightOfPlane(pb, 0)
        let yStride = CVPixelBufferGetBytesPerRowOfPlane(pb, 0), cStride = CVPixelBufferGetBytesPerRowOfPlane(pb, 1)
        let yp = yBase.assumingMemoryBound(to: UInt8.self), cp = cBase.assumingMemoryBound(to: UInt8.self)
        let n = rows * cols
        var sy = [Double](repeating: 0, count: n), sb = sy, sr = sy, cnt = sy
        let step = 8
        for y in stride(from: 0, to: h, by: step) {
            let r = min(y * rows / h, rows - 1)
            let yRow = yp + y * yStride, cRow = cp + (y / 2) * cStride
            for x in stride(from: 0, to: w, by: step) {
                let i = r * cols + min(x * cols / w, cols - 1)
                let cx = (x / 2) * 2
                sy[i] += Double(yRow[x]); sb[i] += Double(cRow[cx]); sr[i] += Double(cRow[cx + 1]); cnt[i] += 1
            }
        }
        // Full-range BT.709 YCbCr -> RGB. Means commute with the linear transform.
        return (0..<n).map { i in
            let c = max(cnt[i], 1), Y = sy[i] / c, cb = sb[i] / c - 128, cr = sr[i] / c - 128
            return [(Y + 1.5748 * cr) / 255, (Y - 0.1873 * cb - 0.4681 * cr) / 255, (Y + 1.8556 * cb) / 255]
        }
    }

    private func makeWriter(width: Int, height: Int) throws {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("capture-\(UUID().uuidString).mov")
        let w = try AVAssetWriter(outputURL: url, fileType: .mov)
        // High bitrate, no B-frames: the corneal reflection is a few dozen pixels and
        // must survive compression.
        let settings: [String: Any] = [
            AVVideoCodecKey: AVVideoCodecType.h264,
            AVVideoWidthKey: width,
            AVVideoHeightKey: height,
            AVVideoCompressionPropertiesKey: [
                AVVideoAverageBitRateKey: 45_000_000,
                AVVideoMaxKeyFrameIntervalKey: 30,
                AVVideoAllowFrameReorderingKey: false,
                AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel,
            ],
        ]
        let input = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
        input.expectsMediaDataInRealTime = true
        guard w.canAdd(input) else { throw CaptureError.writerFailed("cannot add video input") }
        w.add(input)
        writer = w
        writerInput = input
    }

    /// Camera PTS on the host clock: the same timebase as CADisplayLink and CoreMotion.
    private func hostSeconds(_ pts: CMTime) -> Double {
        let from = session.synchronizationClock ?? CMClockGetHostTimeClock()
        return CMSyncConvertTime(pts, from: from, to: CMClockGetHostTimeClock()).seconds
    }

    // MARK: AVCaptureVideoDataOutputSampleBufferDelegate

    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        guard let pixels = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        let w = CVPixelBufferGetWidth(pixels), h = CVPixelBufferGetHeight(pixels)
        frameSize = CGSize(width: w, height: h)

        if !selfieWaiters.isEmpty {
            let image = CIImage(cvPixelBuffer: pixels)
            let data = ciContext.jpegRepresentation(of: image, colorSpace: CGColorSpace(name: CGColorSpace.sRGB)!,
                                                    options: [kCGImageDestinationLossyCompressionQuality as CIImageRepresentationOption: 0.9])
            selfieWaiters.forEach { $0(data) }
            selfieWaiters = []
        }

        if transitOn {
            let ts = hostSeconds(CMSampleBufferGetPresentationTimeStamp(sampleBuffer))
            if ts - lastTransit >= CaptureController.transitInterval - 0.004 { appendTransit(pixels, at: ts) }
        }

        if sampling {
            let cells = gridMeans(pixels)
            if !cells.isEmpty {
                sampleTS.append(hostSeconds(CMSampleBufferGetPresentationTimeStamp(sampleBuffer)))
                sampleRGB.append(cells)
            }
        }

        guard recording else { return }
        let pts = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
        if writer == nil {
            do {
                try makeWriter(width: w, height: h)
                writer?.startWriting()
                writer?.startSession(atSourceTime: pts)
            } catch {
                recording = false
                return
            }
        }
        // The timestamp list must stay 1:1 with frames in the file.
        if let input = writerInput, input.isReadyForMoreMediaData, input.append(sampleBuffer) {
            frameTS.append(hostSeconds(pts))
        } else {
            droppedTS.append(hostSeconds(pts))
        }
    }

    func captureOutput(_ output: AVCaptureOutput, didDrop sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        guard recording else { return }
        droppedTS.append(hostSeconds(CMSampleBufferGetPresentationTimeStamp(sampleBuffer)))
    }
}
