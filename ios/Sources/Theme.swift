import SwiftUI

// MARK: - Tokens
//
// The phone half of web/app/tokens.css: one look across the app, the browser client and
// the panel embedded in a relying party's page. Dark, minimal, instrument-like. Nothing
// outside this file hard-codes a colour, a radius or a duration.

extension Color {
    init(hex: UInt32, opacity: Double = 1) {
        self.init(.sRGB,
                  red: Double((hex >> 16) & 0xFF) / 255,
                  green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255,
                  opacity: opacity)
    }

    // Surfaces
    static let ihBg = Color(hex: 0x0A0C10)          /// page
    static let ihSurface = Color(hex: 0x11141A)     /// cards
    static let ihRaised = Color(hex: 0x171B23)      /// things on cards
    static let ihLine = Color(hex: 0x232936)        /// 1px hairlines

    // Type
    static let ihText = Color(hex: 0xECEFF5)
    static let ihText2 = Color(hex: 0x9AA3B5)       /// secondary
    static let ihText3 = Color(hex: 0x5F6878)       /// labels, captions

    // Signal
    static let ihAccent = Color(hex: 0x6E8BFF)      /// brand, tracking, progress
    static let ihOk = Color(hex: 0x35D49A)          /// verified
    static let ihBad = Color(hex: 0xFF5D5D)         /// rejected
    static let ihWarn = Color(hex: 0xFFB547)        /// couldn't verify

    static let ihAccentSoft = Color(hex: 0x6E8BFF, opacity: 0.14)
    static let ihOkSoft = Color(hex: 0x35D49A, opacity: 0.13)
    static let ihBadSoft = Color(hex: 0xFF5D5D, opacity: 0.13)
    static let ihWarnSoft = Color(hex: 0xFFB547, opacity: 0.13)

    /// Server tile / verdict status -> colour.
    static func ihStatus(_ status: String) -> Color {
        switch status {
        case "green": return .ihOk
        case "red": return .ihBad
        default: return .ihWarn
        }
    }

    static func ihStatusSoft(_ status: String) -> Color {
        switch status {
        case "green": return .ihOkSoft
        case "red": return .ihBadSoft
        default: return .ihWarnSoft
        }
    }
}

enum Radius {
    static let sm: CGFloat = 10
    static let md: CGFloat = 14
    static let lg: CGFloat = 20
}

/// Everything eases out. Same three durations as the web client.
enum Anim {
    static let fast = Animation.timingCurve(0.2, 0.8, 0.2, 1, duration: 0.18)
    static let med = Animation.timingCurve(0.2, 0.8, 0.2, 1, duration: 0.32)
    static let slow = Animation.timingCurve(0.2, 0.8, 0.2, 1, duration: 0.52)
}

// MARK: - Text styles

/// Small uppercase monospaced data label, used above every number.
struct DataLabel: ViewModifier {
    var color: Color = .ihText3
    var size: CGFloat = 11

    func body(content: Content) -> some View {
        content
            .font(.system(size: size, weight: .semibold, design: .monospaced))
            .tracking(size * 0.08)
            .textCase(.uppercase)
            .foregroundStyle(color)
    }
}

extension View {
    func dataLabel(_ color: Color = .ihText3, size: CGFloat = 11) -> some View {
        modifier(DataLabel(color: color, size: size))
    }

    /// Tabular figures, so numbers don't jitter as they update.
    func numeric(_ size: CGFloat, weight: Font.Weight = .semibold) -> some View {
        font(.system(size: size, weight: weight).monospacedDigit())
    }
}

// MARK: - Surfaces

struct CardStyle: ViewModifier {
    var radius: CGFloat = Radius.lg
    var fill: Color = .ihSurface
    var stroke: Color = .ihLine

    func body(content: Content) -> some View {
        content
            .background(fill, in: RoundedRectangle(cornerRadius: radius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .strokeBorder(stroke, lineWidth: 1)
            }
    }
}

extension View {
    func card(radius: CGFloat = Radius.lg, fill: Color = .ihSurface, stroke: Color = .ihLine) -> some View {
        modifier(CardStyle(radius: radius, fill: fill, stroke: stroke))
    }

    /// Card for use over the camera: the preview shows through, the text stays readable.
    func hudCard(radius: CGFloat = Radius.md) -> some View {
        background {
            RoundedRectangle(cornerRadius: radius, style: .continuous)
                .fill(.ultraThinMaterial)
                .overlay {
                    RoundedRectangle(cornerRadius: radius, style: .continuous)
                        .fill(Color.ihBg.opacity(0.55))
                }
                .overlay {
                    RoundedRectangle(cornerRadius: radius, style: .continuous)
                        .strokeBorder(Color.ihLine, lineWidth: 1)
                }
        }
        .environment(\.colorScheme, .dark)
    }

    /// Cuts `mask` out of the view. Used to dim everything outside a camera guide.
    func reverseMask<M: View>(alignment: Alignment = .center, @ViewBuilder _ mask: () -> M) -> some View {
        self.mask(alignment: alignment) {
            Rectangle()
                .overlay(alignment: alignment) { mask().blendMode(.destinationOut) }
                .compositingGroup()
        }
    }
}

/// The page: flat near-black with one cold light behind the content.
struct ScreenBackground: View {
    var body: some View {
        ZStack {
            Color.ihBg
            RadialGradient(colors: [Color.ihAccent.opacity(0.10), .clear],
                           center: UnitPoint(x: 0.5, y: 0.16), startRadius: 0, endRadius: 420)
            RadialGradient(colors: [Color.ihAccent.opacity(0.05), .clear],
                           center: UnitPoint(x: 0.9, y: 0.95), startRadius: 0, endRadius: 320)
        }
    }
}

// MARK: - Parts

struct Hairline: View {
    var color: Color = .ihLine
    var body: some View {
        Rectangle().fill(color).frame(height: 1)
    }
}

/// Status light. Glows so a green or red reads across a room during the demo.
struct StatusDot: View {
    var color: Color
    var size: CGFloat = 8
    var glowing = true

    var body: some View {
        Circle()
            .fill(color)
            .frame(width: size, height: size)
            .shadow(color: glowing ? color.opacity(0.7) : .clear, radius: size * 0.7)
    }
}

/// Status light with a slow ping: the app is alive and watching.
struct PulseDot: View {
    var color: Color = .ihAccent
    var size: CGFloat = 8

    @State private var ping = false

    var body: some View {
        ZStack {
            Circle()
                .fill(color.opacity(0.28))
                .frame(width: size * (ping ? 2.8 : 1), height: size * (ping ? 2.8 : 1))
                .opacity(ping ? 0 : 1)
            Circle().fill(color).frame(width: size, height: size)
        }
        .frame(width: size * 2.8, height: size * 2.8)
        .onAppear {
            withAnimation(.easeOut(duration: 1.8).repeatForever(autoreverses: false)) { ping = true }
        }
    }
}

/// Label above a tabular number, the unit of every readout in the app.
struct Metric: View {
    let label: String
    let value: String
    var tint: Color = .ihText
    var size: CGFloat = 17
    var alignment: HorizontalAlignment = .leading

    var body: some View {
        VStack(alignment: alignment, spacing: 3) {
            Text(label).dataLabel(.ihText3, size: 10)
            Text(value).numeric(size).foregroundStyle(tint)
        }
    }
}

/// Small capsule: a dot and a word. Used for verdicts and modes.
struct Chip: View {
    let text: String
    var color: Color = .ihText2
    var fill: Color = .ihRaised
    var showsDot = true

    var body: some View {
        HStack(spacing: 6) {
            if showsDot { StatusDot(color: color, size: 6) }
            Text(text).dataLabel(color, size: 10)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(fill, in: Capsule())
        .overlay { Capsule().strokeBorder(color.opacity(0.35), lineWidth: 1) }
    }
}

/// Corner brackets. Turns any rectangle into a viewfinder.
struct Reticle: Shape {
    var arm: CGFloat = 18

    func path(in rect: CGRect) -> Path {
        var p = Path()
        let a = min(arm, min(rect.width, rect.height) / 2)
        let corners: [(CGPoint, CGPoint, CGPoint)] = [
            (CGPoint(x: rect.minX, y: rect.minY + a), CGPoint(x: rect.minX, y: rect.minY), CGPoint(x: rect.minX + a, y: rect.minY)),
            (CGPoint(x: rect.maxX - a, y: rect.minY), CGPoint(x: rect.maxX, y: rect.minY), CGPoint(x: rect.maxX, y: rect.minY + a)),
            (CGPoint(x: rect.maxX, y: rect.maxY - a), CGPoint(x: rect.maxX, y: rect.maxY), CGPoint(x: rect.maxX - a, y: rect.maxY)),
            (CGPoint(x: rect.minX + a, y: rect.maxY), CGPoint(x: rect.minX, y: rect.maxY), CGPoint(x: rect.minX, y: rect.maxY - a)),
        ]
        for (from, corner, to) in corners {
            p.move(to: from)
            p.addLine(to: corner)
            p.addLine(to: to)
        }
        return p
    }
}

/// Crosshair ticks pointing at an ellipse of `size`, drawn just outside its edge.
struct CrossTicks: Shape {
    var size: CGSize
    var length: CGFloat = 10

    init(diameter: CGFloat, length: CGFloat = 10) {
        self.size = CGSize(width: diameter, height: diameter)
        self.length = length
    }

    init(size: CGSize, length: CGFloat = 10) {
        self.size = size
        self.length = length
    }

    func path(in rect: CGRect) -> Path {
        var p = Path()
        let c = CGPoint(x: rect.midX, y: rect.midY)
        let rx = size.width / 2, ry = size.height / 2
        p.move(to: CGPoint(x: c.x - rx - length, y: c.y)); p.addLine(to: CGPoint(x: c.x - rx - 3, y: c.y))
        p.move(to: CGPoint(x: c.x + rx + 3, y: c.y)); p.addLine(to: CGPoint(x: c.x + rx + length, y: c.y))
        p.move(to: CGPoint(x: c.x, y: c.y - ry - length)); p.addLine(to: CGPoint(x: c.x, y: c.y - ry - 3))
        p.move(to: CGPoint(x: c.x, y: c.y + ry + 3)); p.addLine(to: CGPoint(x: c.x, y: c.y + ry + length))
        return p
    }
}

/// The brand mark: an iris with a scanning arc. `active` is the app's heartbeat, on when
/// it is enrolled and can reach the server.
struct IrisMark: View {
    var size: CGFloat = 120
    var active = true
    var tint: Color = .ihAccent

    @State private var spin = false
    @State private var breathe = false

    var body: some View {
        ZStack {
            Circle()
                .strokeBorder(tint.opacity(active ? 0.22 : 0.08), lineWidth: 1)
                .frame(width: size * (breathe ? 1.18 : 1.0), height: size * (breathe ? 1.18 : 1.0))
                .opacity(breathe ? 0 : 1)
            Circle().strokeBorder(Color.ihLine, lineWidth: 1)
            Circle().strokeBorder(Color.ihLine, lineWidth: 1).padding(size * 0.14)
            Circle()
                .fill(RadialGradient(colors: [tint.opacity(0.55), tint.opacity(0.06)],
                                     center: .center, startRadius: 0, endRadius: size * 0.3))
                .padding(size * 0.28)
            Circle()
                .strokeBorder(tint.opacity(0.75), lineWidth: 1)
                .padding(size * 0.28)
            Circle().fill(Color.ihBg).padding(size * 0.42)
            Circle()
                .trim(from: 0, to: 0.16)
                .stroke(tint, style: StrokeStyle(lineWidth: 2, lineCap: .round))
                .rotationEffect(.degrees(spin ? 360 : 0))
                .opacity(active ? 1 : 0.25)
            CrossTicks(diameter: size, length: size * 0.1)
                .stroke(Color.ihLine, lineWidth: 1)
        }
        .frame(width: size, height: size)
        .onAppear {
            withAnimation(.linear(duration: 5.5).repeatForever(autoreverses: false)) { spin = true }
            if active {
                withAnimation(.easeOut(duration: 2.4).repeatForever(autoreverses: false)) { breathe = true }
            }
        }
    }
}

/// Indeterminate progress that doesn't look like a system spinner.
struct ScanRing: View {
    var size: CGFloat = 76
    @State private var spin = false

    var body: some View {
        ZStack {
            Circle().strokeBorder(Color.ihLine, lineWidth: 1)
            Circle()
                .trim(from: 0, to: 0.22)
                .stroke(Color.ihAccent, style: StrokeStyle(lineWidth: 2, lineCap: .round))
                .rotationEffect(.degrees(spin ? 360 : 0))
            Circle()
                .trim(from: 0.5, to: 0.58)
                .stroke(Color.ihAccent.opacity(0.35), style: StrokeStyle(lineWidth: 2, lineCap: .round))
                .rotationEffect(.degrees(spin ? 360 : 0))
        }
        .frame(width: size, height: size)
        .onAppear { withAnimation(.linear(duration: 1.1).repeatForever(autoreverses: false)) { spin = true } }
    }
}

/// A 0...1 bar with a threshold tick: similarity against a pass mark, and anything else scored.
struct ThresholdMeter: View {
    var value: Double
    var threshold: Double
    var tint: Color
    var height: CGFloat = 10

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let v = CGFloat(min(max(value, 0), 1))
            let t = CGFloat(min(max(threshold, 0), 1))
            ZStack(alignment: .leading) {
                Capsule().fill(Color.ihRaised)
                Capsule().fill(tint).frame(width: max(w * v, height))
                Rectangle()
                    .fill(Color.ihText)
                    .frame(width: 2, height: height + 8)
                    .offset(x: w * t - 1)
            }
            .frame(height: height)
            .frame(maxHeight: .infinity, alignment: .center)
        }
        .frame(height: height + 8)
    }
}

// MARK: - Buttons

struct PrimaryButtonStyle: ButtonStyle {
    var tint: Color = .ihAccent

    func makeBody(configuration: Configuration) -> some View { Inner(configuration: configuration, tint: tint) }

    /// Nested view, not a plain builder: a ButtonStyle can't read @Environment itself.
    private struct Inner: View {
        let configuration: ButtonStyleConfiguration
        let tint: Color
        @Environment(\.isEnabled) private var isEnabled

        var body: some View {
            configuration.label
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(isEnabled ? Color.ihBg : Color.ihText3)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
                .background(isEnabled ? tint : Color.ihRaised,
                            in: RoundedRectangle(cornerRadius: Radius.md, style: .continuous))
                .overlay {
                    RoundedRectangle(cornerRadius: Radius.md, style: .continuous)
                        .strokeBorder(Color.ihLine, lineWidth: isEnabled ? 0 : 1)
                }
                .shadow(color: isEnabled ? tint.opacity(0.28) : .clear, radius: 18, y: 6)
                .opacity(configuration.isPressed ? 0.82 : 1)
                .scaleEffect(configuration.isPressed ? 0.985 : 1)
                .animation(Anim.fast, value: configuration.isPressed)
        }
    }
}

struct SecondaryButtonStyle: ButtonStyle {
    var tint: Color = .ihText

    func makeBody(configuration: Configuration) -> some View { Inner(configuration: configuration, tint: tint) }

    private struct Inner: View {
        let configuration: ButtonStyleConfiguration
        let tint: Color
        @Environment(\.isEnabled) private var isEnabled

        var body: some View {
            configuration.label
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(isEnabled ? tint : Color.ihText3)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .card(radius: Radius.md, fill: .ihRaised)
                .opacity(configuration.isPressed ? 0.75 : 1)
                .animation(Anim.fast, value: configuration.isPressed)
        }
    }
}

/// Text-only, for Cancel and Deny.
struct QuietButtonStyle: ButtonStyle {
    var tint: Color = .ihText2

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 15, weight: .medium))
            .foregroundStyle(tint)
            .padding(.vertical, 12)
            .padding(.horizontal, 20)
            .opacity(configuration.isPressed ? 0.6 : 1)
            .animation(Anim.fast, value: configuration.isPressed)
    }
}

/// Over the camera: readable on any frame.
struct GlassButtonStyle: ButtonStyle {
    var tint: Color = .ihText

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 14, weight: .semibold))
            .foregroundStyle(tint)
            .padding(.vertical, 11)
            .padding(.horizontal, 22)
            .hudCard(radius: 22)
            .opacity(configuration.isPressed ? 0.7 : 1)
            .animation(Anim.fast, value: configuration.isPressed)
    }
}
