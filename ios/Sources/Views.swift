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
            ScreenBackground().ignoresSafeArea()
            step
        }
        .preferredColorScheme(.dark)
        .tint(.ihAccent)
        // Hard cut into the flash sequence: nothing may fade over a frame being measured.
        .animation(flow.step == .challenge ? nil : Anim.med, value: flow.step)
        .onChange(of: scenePhase) { _, phase in
            // Leaving the app (or even pulling down Control Center) mid-check cancels it.
            if phase != .active { flow.sessionBroken("You left the app.") }
        }
        .alert("Something went wrong", isPresented: Binding(get: { flow.error != nil }, set: { if !$0 { flow.error = nil } })) {
            Button("OK", role: .cancel) {}
        } message: { Text(flow.error ?? "") }
    }

    @ViewBuilder private var step: some View {
        switch flow.step {
        case .home: HomeView().transition(Self.enter)
        case .approve: ApproveView().transition(Self.enter)
        case .warning: WarningView().transition(Self.enter)
        case .selfie(let enrolling): SelfieView(enrolling: enrolling).transition(.opacity)
        case .position: PositionView().transition(.opacity)
        case .challenge:
            if let ch = flow.challenge {
                ChallengeScreen(challenge: ch, capture: flow.capture) { flow.challengeFinished($0) }
                    .ignoresSafeArea()
            }
        case .uploading: UploadingView().transition(Self.enter)
        case .results: ResultsView().transition(Self.enter)
        }
    }

    private static let enter = AnyTransition.asymmetric(
        insertion: .opacity.combined(with: .scale(scale: 0.98)),
        removal: .opacity)
}

// MARK: Home

struct HomeView: View {
    @EnvironmentObject var flow: Flow
    @State private var showSettings = false

    private var waiting: Bool { flow.serverReachable && flow.enrolled }

    var body: some View {
        VStack(spacing: 0) {
            topBar
            Spacer(minLength: 8)
            IrisMark(size: 124, active: waiting)
            Text("InHuman")
                .font(.system(size: 38, weight: .bold))
                .foregroundStyle(Color.ihText)
                .padding(.top, 24)
            Text("Proves a live human is holding the phone,\nnot a real-time face swap.")
                .font(.system(size: 14))
                .foregroundStyle(Color.ihText2)
                .multilineTextAlignment(.center)
                .lineSpacing(3)
                .padding(.top, 8)
            HStack(spacing: 6) {
                Chip(text: "light response", color: .ihText3, fill: .ihSurface, showsDot: false)
                Chip(text: "cornea", color: .ihText3, fill: .ihSurface, showsDot: false)
                Chip(text: "continuity", color: .ihText3, fill: .ihSurface, showsDot: false)
            }
            .padding(.top, 16)
            Spacer(minLength: 8)
            statusCard.padding(.bottom, 14)
            controls
        }
        .padding(.horizontal, 22)
        .padding(.bottom, 14)
        .sheet(isPresented: $showSettings) { SettingsView() }
    }

    private var topBar: some View {
        HStack {
            Text("InHuman · second factor").dataLabel()
            Spacer()
            Button { showSettings = true } label: {
                Image(systemName: "slider.horizontal.3")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(Color.ihText2)
                    .frame(width: 38, height: 38)
                    .card(radius: Radius.sm, fill: .ihSurface)
            }
            .buttonStyle(.plain)
        }
        .padding(.top, 6)
    }

    private var statusCard: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Server").dataLabel()
                Spacer()
                StatusDot(color: flow.serverReachable ? .ihOk : .ihBad)
                Text(flow.serverReachable ? "Online" : "Unreachable")
                    .dataLabel(flow.serverReachable ? .ihOk : .ihBad)
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            Hairline()
            HStack {
                Text("Enrolled as").dataLabel()
                Spacer()
                Text(flow.enrolled ? flow.userName : "not enrolled")
                    .dataLabel(flow.enrolled ? .ihText : .ihWarn)
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            Hairline()
            HStack(spacing: 10) {
                if waiting { PulseDot(color: .ihAccent) } else { StatusDot(color: .ihText3, size: 6, glowing: false).frame(width: 22) }
                Text(statusLine)
                    .font(.system(size: 13))
                    .foregroundStyle(Color.ihText2)
                    .multilineTextAlignment(.leading)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 13).padding(.vertical, 12)
        }
        .card()
        .animation(Anim.med, value: flow.serverReachable)
        .animation(Anim.med, value: flow.enrolled)
    }

    @ViewBuilder private var controls: some View {
        VStack(spacing: 10) {
            if flow.enrolled {
                LabelPicker(selection: $flow.label)
                Button("Run a test check") { flow.beginTestRun() }
                    .buttonStyle(PrimaryButtonStyle())
                Button("Re-enroll my face") { flow.beginEnrollment() }
                    .buttonStyle(SecondaryButtonStyle())
                    .disabled(!flow.serverReachable || flow.busy)
            } else {
                Button("Enroll my face") { flow.beginEnrollment() }
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(!flow.serverReachable || flow.busy)
            }
        }
    }

    private var statusLine: String {
        if !flow.serverReachable { return "Can't reach the server. Check the address in Settings." }
        if !flow.enrolled { return "Enroll your face once to get started." }
        return "Waiting for a sign-in request for “\(flow.userName)”…"
    }
}

/// Tags the saved capture on the server, for threshold tuning.
struct LabelPicker: View {
    @Binding var selection: String
    @Namespace private var ns

    private let options = ["real", "screen-attack", "replay", "print"]

    var body: some View {
        HStack(spacing: 2) {
            ForEach(options, id: \.self) { option in
                Button {
                    withAnimation(Anim.fast) { selection = option }
                } label: {
                    Text(option)
                        .dataLabel(selection == option ? .ihBg : .ihText2, size: 10)
                        .lineLimit(1)
                        .minimumScaleFactor(0.75)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 9)
                        .background {
                            if selection == option {
                                RoundedRectangle(cornerRadius: Radius.sm, style: .continuous)
                                    .fill(Color.ihAccent)
                                    .matchedGeometryEffect(id: "label-pill", in: ns)
                            }
                        }
                }
                .buttonStyle(.plain)
            }
        }
        .padding(4)
        .card(radius: Radius.md, fill: .ihSurface)
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
                Section {
                    TextField("http://host:8000", text: $serverURL)
                        .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                        .font(.system(size: 15, design: .monospaced))
                        .foregroundStyle(Color.ihText)
                        .listRowBackground(Color.ihSurface)
                } header: { Text("Server").dataLabel() }
                Section {
                    TextField("username", text: $userName)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .font(.system(size: 15, design: .monospaced))
                        .foregroundStyle(Color.ihText)
                        .listRowBackground(Color.ihSurface)
                } header: { Text("Username").dataLabel() }
                Section {
                    Stepper(value: $distanceInches, in: 2...8, step: 1) {
                        HStack {
                            Text("Target").font(.system(size: 15)).foregroundStyle(Color.ihText)
                            Spacer()
                            Text("\(Int(distanceInches)) in").numeric(15).foregroundStyle(Color.ihAccent)
                        }
                    }
                    .listRowBackground(Color.ihSurface)
                    Text("Closer makes the reflection in the eye bigger and easier to read, as long as the camera still focuses.")
                        .font(.footnote).foregroundStyle(Color.ihText3)
                        .listRowBackground(Color.ihSurface)
                } header: { Text("Eye distance").dataLabel() }
                Section {
                    Text("For reliable results turn off Auto-Brightness, True Tone, Night Shift and Low Power Mode.")
                        .font(.footnote).foregroundStyle(Color.ihText3)
                        .listRowBackground(Color.ihSurface)
                }
            }
            .scrollContentBackground(.hidden)
            .background(ScreenBackground().ignoresSafeArea())
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
        .tint(.ihAccent)
        .preferredColorScheme(.dark)
    }
}

// MARK: Approve + warning

struct ApproveView: View {
    @EnvironmentObject var flow: Flow

    var body: some View {
        VStack(spacing: 0) {
            Spacer()
            Image(systemName: "lock.shield")
                .font(.system(size: 34, weight: .light))
                .foregroundStyle(Color.ihAccent)
                .frame(width: 84, height: 84)
                .background(Color.ihAccentSoft, in: Circle())
                .overlay { Circle().strokeBorder(Color.ihAccent.opacity(0.3), lineWidth: 1) }
            Text("Sign-in request")
                .font(.system(size: 30, weight: .bold))
                .foregroundStyle(Color.ihText)
                .padding(.top, 22)
            Text("\(flow.request?.appName ?? "An app") wants to confirm a live person is signing in as “\(flow.request?.user ?? "")”.")
                .font(.system(size: 15))
                .foregroundStyle(Color.ihText2)
                .multilineTextAlignment(.center)
                .lineSpacing(3)
                .padding(.top, 10)
                .padding(.horizontal, 8)
            details.padding(.top, 24)
            Spacer()
            Button("Verify it's me") { flow.approve() }
                .buttonStyle(PrimaryButtonStyle())
            Button("Deny") { flow.deny() }
                .buttonStyle(QuietButtonStyle(tint: .ihBad))
        }
        .padding(.horizontal, 22)
        .padding(.bottom, 14)
    }

    private var details: some View {
        VStack(spacing: 0) {
            row("Requested by", flow.request?.appName ?? "—")
            Hairline()
            row("Account", flow.request?.user ?? "—")
            Hairline()
            row("Checks", "light · cornea · face · motion")
        }
        .card()
    }

    private func row(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label).dataLabel()
            Spacer()
            Text(value).dataLabel(.ihText)
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
    }
}

struct WarningView: View {
    @EnvironmentObject var flow: Flow

    var body: some View {
        VStack(spacing: 0) {
            Spacer()
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 30))
                .foregroundStyle(Color.ihWarn)
                .frame(width: 84, height: 84)
                .background(Color.ihWarnSoft, in: Circle())
                .overlay { Circle().strokeBorder(Color.ihWarn.opacity(0.3), lineWidth: 1) }
            Text("Flashing colors ahead")
                .font(.system(size: 26, weight: .bold))
                .foregroundStyle(Color.ihText)
                .padding(.top, 22)
            Text("This check flashes bright colored shapes for about 5 seconds with the phone close to your eye. Don't continue if you have photosensitive epilepsy. Tap the screen at any time to stop.")
                .font(.system(size: 15))
                .foregroundStyle(Color.ihText2)
                .multilineTextAlignment(.center)
                .lineSpacing(3)
                .padding(.top, 10)
            HStack(spacing: 8) {
                Chip(text: "under 2 flashes a second", color: .ihText2, fill: .ihSurface, showsDot: false)
                Chip(text: "tap to stop", color: .ihText2, fill: .ihSurface, showsDot: false)
            }
            .padding(.top, 18)
            Spacer()
            Button("Continue") { flow.acceptWarning() }
                .buttonStyle(PrimaryButtonStyle(tint: .ihWarn))
                .disabled(flow.busy)
            Button("Cancel") { flow.deny() }
                .buttonStyle(QuietButtonStyle())
        }
        .padding(.horizontal, 22)
        .padding(.bottom, 14)
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
            guide.ignoresSafeArea()
            VStack(spacing: 0) {
                header
                Spacer()
                footer
            }
        }
    }

    // Large on purpose: filling it puts the face close, which gives the recogniser more
    // pixels and shortens the move in to the eye.
    private var guide: some View {
        GeometryReader { geo in
            let w = geo.size.width * 0.84
            let h = geo.size.width * 0.84 * 1.32
            let cx = geo.size.width / 2
            let cy = geo.size.height * 0.46
            ZStack {
                Rectangle()
                    .fill(Color.ihBg.opacity(0.55))
                    .reverseMask { Ellipse().frame(width: w, height: h).position(x: cx, y: cy) }
                ZStack {
                    Ellipse()
                        .strokeBorder(Color.ihText.opacity(0.85), lineWidth: 1.5)
                        .frame(width: w, height: h)
                    Reticle(arm: 24)
                        .stroke(Color.ihAccent, style: StrokeStyle(lineWidth: 2, lineCap: .round))
                        .frame(width: w * 1.02, height: h * 1.01)
                }
                .position(x: cx, y: cy)
            }
        }
    }

    private var header: some View {
        VStack(spacing: 10) {
            Chip(text: enrolling ? "Enrolling" : "Step 1 · Selfie", color: .ihAccent, fill: .ihSurface)
            Text(enrolling ? "Enroll: fill the outline with your face" : "Fill the outline with your face")
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(Color.ihText)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 16).padding(.vertical, 11)
                .hudCard()
        }
        .padding(.top, 14)
    }

    private var footer: some View {
        VStack(spacing: 6) {
            Text(enrolling ? "This face becomes the reference" : "The camera keeps running until the check ends")
                .dataLabel(.ihText2, size: 10)
                .padding(.horizontal, 12).padding(.vertical, 7)
                .hudCard(radius: Radius.sm)
                .padding(.bottom, 10)
            Button { flow.shutter(enrolling: enrolling) } label: {
                ZStack {
                    Circle().strokeBorder(Color.ihText.opacity(0.8), lineWidth: 2).frame(width: 78, height: 78)
                    Circle().fill(Color.ihText).frame(width: 62, height: 62)
                }
            }
            .buttonStyle(.plain)
            .disabled(flow.busy)
            .opacity(flow.busy ? 0.45 : 1)
            .animation(Anim.fast, value: flow.busy)
            Button("Cancel") { flow.deny() }
                .buttonStyle(QuietButtonStyle(tint: .ihText2))
        }
        .padding(.bottom, 8)
    }
}

struct PositionView: View {
    @EnvironmentObject var flow: Flow
    @State private var countdown: Int?
    @State private var meta: [String: Any] = [:]
    @State private var pulse = false

    private var inches: String {
        String(format: "%.0f", (flow.capture.workingDistanceMM / 25.4).rounded())
    }

    var body: some View {
        ZStack {
            CameraPreview(session: flow.capture.session).ignoresSafeArea()
            ring.ignoresSafeArea()
            VStack(spacing: 0) {
                header
                Spacer()
                footer
            }
        }
        .onAppear {
            meta = flow.capture.cameraMeta
            withAnimation(.easeInOut(duration: 1.6).repeatForever(autoreverses: true)) { pulse = true }
        }
    }

    // A ring the size the iris should appear at the target distance (irises are ~11.7 mm
    // in everyone). "Put your eye in the outline" left people at 5-6 inches; matching
    // the iris to a ring is a precise distance cue.
    private var ring: some View {
        GeometryReader { geo in
            let iris = irisRingDiameter(in: geo.size)
            let live = countdown == nil
            let halo = live && pulse ? 1.16 : 1.04
            ZStack {
                Ellipse()
                    .strokeBorder(Color.ihText.opacity(0.45), lineWidth: 1)
                    .frame(width: iris * 2.7, height: iris * 1.35)
                Circle()
                    .strokeBorder(live ? Color.ihAccent : Color.ihOk, lineWidth: 2)
                    .frame(width: iris, height: iris)
                Circle()
                    .strokeBorder((live ? Color.ihAccent : Color.ihOk).opacity(0.35), lineWidth: 1)
                    .frame(width: iris * halo, height: iris * halo)
                CrossTicks(size: CGSize(width: iris * 2.7, height: iris * 1.35), length: 14)
                    .stroke(Color.ihText.opacity(0.35), lineWidth: 1)
                    .frame(width: iris * 2.7 + 40, height: iris * 1.35 + 40)
            }
            .position(x: geo.size.width / 2, y: geo.size.height / 2)
            .animation(Anim.med, value: countdown)
        }
    }

    private var header: some View {
        VStack(spacing: 8) {
            Chip(text: "Step 2 · Eye", color: .ihAccent, fill: .ihSurface)
            VStack(spacing: 6) {
                Text("Keep the camera on your face")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(Color.ihText)
                Text("Without lowering the phone, slowly bring it in until the colored part of one eye fills the ring (about \(inches) inches).")
                    .font(.system(size: 14))
                    .foregroundStyle(Color.ihText2)
                Text("The move is being watched. Looking away, covering the camera or leaving the app cancels the check.")
                    .font(.system(size: 12))
                    .foregroundStyle(Color.ihText3)
            }
            .multilineTextAlignment(.center)
            .padding(14)
            .hudCard()
        }
        .padding([.top, .horizontal], 18)
    }

    private var readout: some View {
        HStack(spacing: 0) {
            Metric(label: "Target", value: "\(inches) in", tint: .ihAccent, size: 15)
                .frame(maxWidth: .infinity, alignment: .leading)
            Metric(label: "Distance", value: String(format: "%.0f mm", flow.capture.workingDistanceMM), size: 15)
                .frame(maxWidth: .infinity, alignment: .leading)
            Metric(label: "FOV", value: reading("fov_deg", "%.0f°"), size: 15)
                .frame(maxWidth: .infinity, alignment: .leading)
            Metric(label: "Rate", value: reading("fps", "%.0f fps"), size: 15)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 14).padding(.vertical, 11)
        .hudCard()
    }

    @ViewBuilder private var footer: some View {
        VStack(spacing: 12) {
            HStack(spacing: 8) {
                PulseDot(color: .ihBad, size: 6)
                Text("Tracking the move").dataLabel(.ihText2, size: 10)
            }
            .padding(.horizontal, 12).padding(.vertical, 6)
            .hudCard(radius: Radius.sm)
            readout
            if let countdown {
                VStack(spacing: 6) {
                    Text("\(countdown)")
                        .numeric(84, weight: .bold)
                        .foregroundStyle(Color.ihOk)
                        .contentTransition(.numericText(countsDown: true))
                    Text("Hold it right there. Keep still, eye open.")
                        .font(.system(size: 15, weight: .medium))
                        .foregroundStyle(Color.ihText)
                }
                .frame(height: 132)
            } else {
                VStack(spacing: 2) {
                    Button("I'm in position") { begin() }
                        .buttonStyle(PrimaryButtonStyle())
                    Button("Cancel") { flow.deny() }
                        .buttonStyle(QuietButtonStyle(tint: .ihText2))
                }
                .frame(height: 132)
            }
        }
        .padding(.horizontal, 18)
        .padding(.bottom, 10)
        .animation(Anim.med, value: countdown)
    }

    /// A camera number, or an em dash before the camera has reported one.
    private func reading(_ key: String, _ format: String) -> String {
        guard let v = meta[key] as? Double, v > 0 else { return "—" }
        return String(format: format, v)
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
    private let stages = ["Light response", "Eye reflection", "Face match", "Continuity", "Vibration"]
    @State private var lit = 0

    var body: some View {
        VStack(spacing: 0) {
            Spacer()
            ScanRing(size: 84)
            Text("Analyzing").dataLabel(.ihAccent, size: 12).padding(.top, 22)
            Text("Checking the light response and eye reflection…")
                .font(.system(size: 15))
                .foregroundStyle(Color.ihText2)
                .multilineTextAlignment(.center)
                .padding(.top, 8)
            VStack(spacing: 0) {
                ForEach(Array(stages.enumerated()), id: \.offset) { i, stage in
                    if i > 0 { Hairline() }
                    HStack {
                        Text(stage).dataLabel(i <= lit ? .ihText : .ihText3)
                        Spacer()
                        StatusDot(color: i <= lit ? .ihAccent : .ihLine, size: 6, glowing: i <= lit)
                    }
                    .padding(.horizontal, 16).padding(.vertical, 11)
                }
            }
            .card()
            .padding(.top, 26)
            .animation(Anim.med, value: lit)
            Spacer()
        }
        .padding(.horizontal, 22)
        .task {
            // Indeterminate: the server returns when it returns. This only shows the checks it runs.
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 700_000_000)
                lit = (lit + 1) % (stages.count + 1)
            }
        }
    }
}
