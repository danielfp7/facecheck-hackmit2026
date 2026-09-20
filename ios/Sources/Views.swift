import AVFoundation
import SwiftUI

@main
struct InHumanApp: App {
    @StateObject private var flow = Flow()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(flow)
                .onAppear { flow.startPolling() }
        }
    }
}

struct RootView: View {
    @EnvironmentObject var flow: Flow
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        ZStack {
            switch flow.step {
            case .home: HomeView()
            case .approve: ApproveView()
            case .warning: WarningView()
            case .selfie(let enrolling): SelfieView(enrolling: enrolling)
            case .position: PositionView()
            case .challenge:
                if let ch = flow.challenge {
                    ChallengeScreen(challenge: ch, capture: flow.capture) { flow.challengeFinished($0) }
                        .ignoresSafeArea()
                }
            case .uploading: UploadingView()
            case .results: ResultsView()
            }
        }
        .onChange(of: scenePhase) { _, phase in
            // Leaving the app (or even pulling down Control Center) mid-check cancels it.
            if phase != .active { flow.sessionBroken("You left the app.") }
        }
        .alert("Something went wrong", isPresented: Binding(get: { flow.error != nil }, set: { if !$0 { flow.error = nil } })) {
            Button("OK", role: .cancel) {}
        } message: { Text(flow.error ?? "") }
    }
}

// MARK: Home

struct HomeView: View {
    @EnvironmentObject var flow: Flow
    @State private var showSettings = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                Spacer()
                Image(systemName: "person.badge.shield.checkmark.fill")
                    .font(.system(size: 64)).foregroundStyle(.tint)
                Text("InHuman").font(.largeTitle.bold())
                Text(statusLine).multilineTextAlignment(.center).foregroundStyle(.secondary)
                Spacer()

                if flow.enrolled {
                    Picker("Capture label", selection: $flow.label) {
                        ForEach(["real", "screen-attack", "replay", "print"], id: \.self) { Text($0) }
                    }
                    .pickerStyle(.segmented)
                    Button("Run a test check") { flow.beginTestRun() }
                        .buttonStyle(.bordered).controlSize(.large)
                }
                Button(flow.enrolled ? "Re-enroll my face" : "Enroll my face") { flow.beginEnrollment() }
                    .buttonStyle(.borderedProminent).controlSize(.large)
                    .disabled(!flow.serverReachable || flow.busy)
            }
            .padding(24)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showSettings = true } label: { Image(systemName: "gearshape") }
                }
            }
            .sheet(isPresented: $showSettings) { SettingsView() }
        }
    }

    private var statusLine: String {
        if !flow.serverReachable { return "Can't reach the server.\nCheck the address in Settings." }
        if !flow.enrolled { return "Enroll your face once to get started." }
        return "Waiting for a sign-in request for “\(flow.userName)”…"
    }
}

struct SettingsView: View {
    @AppStorage("serverURL") private var serverURL = Flow.defaultServerURL
    @AppStorage("userName") private var userName = "daniel"
    @AppStorage("distanceInches") private var distanceInches = 3.0
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Server") {
                    TextField("http://host:8000", text: $serverURL)
                        .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                }
                Section("Username") {
                    TextField("username", text: $userName)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                }
                Section("Eye distance") {
                    Stepper("\(Int(distanceInches)) inches", value: $distanceInches, in: 2...8, step: 1)
                    Text("Closer makes the reflection in the eye bigger and easier to read, as long as the camera still focuses.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                Section {
                    Text("For reliable results turn off Auto-Brightness, True Tone, Night Shift and Low Power Mode.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Settings")
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
    }
}

// MARK: Approve + warning

struct ApproveView: View {
    @EnvironmentObject var flow: Flow

    var body: some View {
        VStack(spacing: 20) {
            Spacer()
            Image(systemName: "lock.shield").font(.system(size: 56)).foregroundStyle(.tint)
            Text("Sign-in request").font(.title.bold())
            Text("\(flow.request?.appName ?? "An app") wants to confirm a live person is signing in as “\(flow.request?.user ?? "")”.")
                .multilineTextAlignment(.center).foregroundStyle(.secondary)
            Spacer()
            Button("Verify it's me") { flow.approve() }
                .buttonStyle(.borderedProminent).controlSize(.large)
            Button("Deny", role: .destructive) { flow.deny() }.controlSize(.large)
        }
        .padding(24)
    }
}

struct WarningView: View {
    @EnvironmentObject var flow: Flow

    var body: some View {
        VStack(spacing: 20) {
            Spacer()
            Image(systemName: "exclamationmark.triangle.fill").font(.system(size: 52)).foregroundStyle(.yellow)
            Text("Flashing colors ahead").font(.title2.bold())
            Text("This check flashes bright colored shapes for about 5 seconds with the phone close to your eye. Don't continue if you have photosensitive epilepsy. Tap the screen at any time to stop.")
                .multilineTextAlignment(.center).foregroundStyle(.secondary)
            Spacer()
            Button("Continue") { flow.acceptWarning() }
                .buttonStyle(.borderedProminent).controlSize(.large).disabled(flow.busy)
            Button("Cancel") { flow.deny() }.controlSize(.large)
        }
        .padding(24)
    }
}

// MARK: Camera steps

struct CameraPreview: UIViewRepresentable {
    let session: AVCaptureSession

    final class PreviewView: UIView {
        override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
        var previewLayer: AVCaptureVideoPreviewLayer { layer as! AVCaptureVideoPreviewLayer }
    }

    func makeUIView(context: Context) -> PreviewView {
        let v = PreviewView()
        v.previewLayer.session = session
        v.previewLayer.videoGravity = .resizeAspectFill
        return v
    }

    func updateUIView(_ uiView: PreviewView, context: Context) {}
}

struct SelfieView: View {
    @EnvironmentObject var flow: Flow
    let enrolling: Bool

    var body: some View {
        ZStack {
            CameraPreview(session: flow.capture.session).ignoresSafeArea()
            // Large on purpose: filling it puts the face close, which gives the recogniser more
            // pixels and shortens the move in to the eye.
            GeometryReader { geo in
                Ellipse()
                    .strokeBorder(.white.opacity(0.9), style: StrokeStyle(lineWidth: 3, dash: [10, 8]))
                    .frame(width: geo.size.width * 0.84, height: geo.size.width * 0.84 * 1.32)
                    .position(x: geo.size.width / 2, y: geo.size.height * 0.46)
            }
            .ignoresSafeArea()
            VStack {
                Text(enrolling ? "Enroll: fill the outline with your face" : "Fill the outline with your face")
                    .font(.headline).padding(12)
                    .background(.ultraThinMaterial, in: Capsule())
                    .padding(.top, 24)
                Spacer()
                Button { flow.shutter(enrolling: enrolling) } label: {
                    Circle().fill(.white).frame(width: 74, height: 74)
                        .overlay(Circle().stroke(.black.opacity(0.25), lineWidth: 2).padding(5))
                }
                .disabled(flow.busy)
                Button("Cancel") { flow.deny() }.foregroundStyle(.white).padding(.bottom, 12)
            }
        }
    }
}

struct PositionView: View {
    @EnvironmentObject var flow: Flow
    @State private var countdown: Int?

    private var inches: String {
        String(format: "%.0f", (flow.capture.workingDistanceMM / 25.4).rounded())
    }

    var body: some View {
        ZStack {
            CameraPreview(session: flow.capture.session).ignoresSafeArea()
            // A ring the size the iris should appear at the target distance (irises are ~11.7 mm
            // in everyone). "Put your eye in the outline" left people at 5-6 inches; matching
            // the iris to a ring is a precise distance cue.
            GeometryReader { geo in
                let ring = irisRingDiameter(in: geo.size)
                ZStack {
                    Ellipse().strokeBorder(.white.opacity(0.55), lineWidth: 2)
                        .frame(width: ring * 2.7, height: ring * 1.35)
                    Circle().strokeBorder(.white, lineWidth: 3)
                        .frame(width: ring, height: ring)
                }
                .position(x: geo.size.width / 2, y: geo.size.height / 2)
            }
            .ignoresSafeArea()
            VStack {
                VStack(spacing: 6) {
                    Text("Keep the camera on your face")
                        .font(.title2.bold())
                    Text("Without lowering the phone, slowly bring it in until the colored part of one eye fills the ring (about \(inches) inches).")
                        .font(.subheadline)
                    Text("The move is being watched. Looking away, covering the camera or leaving the app cancels the check.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                .multilineTextAlignment(.center).padding(14)
                .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 16))
                .padding([.top, .horizontal], 20)
                Spacer()
                if let countdown {
                    Text("\(countdown)").font(.system(size: 96, weight: .bold)).foregroundStyle(.white)
                    Text("Hold it right there. Keep still, eye open.").font(.headline).foregroundStyle(.white)
                } else {
                    Button("I'm in position") { begin() }
                        .buttonStyle(.borderedProminent).controlSize(.large)
                    Button("Cancel") { flow.deny() }.foregroundStyle(.white)
                }
            }
            .padding(.bottom, 24)
        }
    }

    /// On-screen diameter of an iris at the working distance. The preview fills the screen
    /// (aspect fill), so points per video pixel is the larger of the two axis ratios.
    private func irisRingDiameter(in size: CGSize) -> CGFloat {
        let fov = (flow.capture.cameraMeta["fov_deg"] as? Double) ?? 46
        let frameW = 1080.0, frameH = 1920.0
        let pxPerMM = frameW / (2 * flow.capture.workingDistanceMM * tan(fov * .pi / 360))
        let pointsPerPx = max(Double(size.width) / frameW, Double(size.height) / frameH)
        return CGFloat(11.7 * pxPerMM * pointsPerPx)
    }

    private func begin() {
        Task {
            for n in stride(from: 3, through: 1, by: -1) {
                countdown = n
                try? await Task.sleep(nanoseconds: 800_000_000)
            }
            flow.startChallenge()
        }
    }
}

struct UploadingView: View {
    var body: some View {
        VStack(spacing: 16) {
            ProgressView().controlSize(.large)
            Text("Checking the light response and eye reflection…").foregroundStyle(.secondary)
        }
    }
}
