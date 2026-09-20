import Charts
import SwiftUI

struct ResultsView: View {
    @EnvironmentObject var flow: Flow

    var body: some View {
        ScrollView {
            if let r = flow.result {
                VStack(spacing: 12) {
                    header
                    VerdictBanner(result: r)
                    FaceRecognitionOnlyTile(similarity: r.signals?.identity?.similarity, verdict: r.verdict)
                    ForEach(r.tiles) { tile in
                        TileCard(tile: tile) {
                            switch tile.name {
                            case "Light response":
                                if let plot = r.signals?.lag?.plot { LightResponseChart(plot: plot) }
                            case "Eye reflection":
                                if let states = r.signals?.cornea?.states { EyeReflectionGrid(states: states) }
                            case "Vibration":
                                if let plot = r.signals?.vibration?.plot { VibrationChart(plot: plot) }
                            case "Face match":
                                if let data = flow.selfie, let img = UIImage(data: data) {
                                    Image(uiImage: img).resizable().scaledToFill()
                                        .frame(width: 84, height: 84)
                                        .clipShape(Circle())
                                        .overlay { Circle().strokeBorder(Color.ihLine, lineWidth: 1) }
                                        .scaleEffect(x: -1, y: 1)   // show it the way the preview did
                                }
                            default: EmptyView()
                            }
                        }
                    }
                    footer(r)
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 20)
            }
        }
        .scrollIndicators(.hidden)
    }

    private var header: some View {
        HStack {
            Text("InHuman · report").dataLabel()
            Spacer()
            Text(flow.label).dataLabel(.ihText3, size: 10)
        }
        .padding(.top, 8)
    }

    private func footer(_ r: VerifyResult) -> some View {
        VStack(spacing: 14) {
            if let s = r.processingS {
                Text(String(format: "Analyzed in %.1f s", s)).dataLabel(.ihText3, size: 10)
            }
            Button("Done") { flow.reset() }
                .buttonStyle(PrimaryButtonStyle())
        }
        .padding(.top, 6)
    }
}

/// verdict string -> the server's own status vocabulary, so one colour table serves both.
private func verdictStatus(_ verdict: String) -> String {
    switch verdict {
    case "verified": return "green"
    case "unverified": return "red"
    default: return "yellow"
    }
}

struct VerdictBanner: View {
    let result: VerifyResult

    private var style: (title: String, icon: String, color: Color) {
        switch result.verdict {
        case "verified": return ("Verified", "checkmark.seal.fill", .ihOk)
        case "unverified": return ("Not verified", "xmark.seal.fill", .ihBad)
        default: return ("Couldn't verify", "questionmark.circle.fill", .ihWarn)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                StatusDot(color: style.color, size: 8)
                Text("Verdict").dataLabel(style.color)
                Spacer()
                Image(systemName: style.icon)
                    .font(.system(size: 17))
                    .foregroundStyle(style.color)
            }
            Text(style.title)
                .font(.system(size: 34, weight: .bold))
                .foregroundStyle(Color.ihText)
            Text(result.reason)
                .font(.system(size: 14))
                .foregroundStyle(Color.ihText2)
                .lineSpacing(2)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(18)
        .card(fill: Color.ihStatusSoft(verdictStatus(result.verdict)),
              stroke: style.color.opacity(0.35))
    }
}

/// The pitch, in one tile: what a face-recognition-only login would have decided.
/// A live face swap scores far above the 0.35 pass mark, so this is where InHuman earns its keep.
struct FaceRecognitionOnlyTile: View {
    let similarity: Double?
    let verdict: String

    static let passMark = 0.35

    private var passes: Bool { (similarity ?? 0) >= Self.passMark }
    private var inhumanAllowed: Bool { verdict == "verified" }
    private var bypass: Bool { similarity != nil && passes && !inhumanAllowed }

    private var tint: Color {
        guard similarity != nil else { return .ihWarn }
        if bypass { return .ihBad }
        if !passes && inhumanAllowed { return .ihWarn }
        return .ihOk
    }

    private var headline: String {
        guard similarity != nil else { return "Nothing to compare" }
        if bypass { return "Would have let this through" }
        if !passes && inhumanAllowed { return "Would have blocked a real person" }
        if passes { return "Would have allowed it too" }
        return "Would have blocked it too"
    }

    private var detail: String {
        guard let s = similarity else { return "No face was scored against the enrolled photo." }
        return String(format: "similarity %.2f vs %.2f pass mark", s, Self.passMark)
    }

    private var stamp: String {
        guard similarity != nil else { return "no score" }
        if bypass { return "bypassed" }
        if !passes && inhumanAllowed { return "false reject" }
        return "agrees"
    }

    private var faceVerdict: String {
        guard similarity != nil else { return "No score" }
        return passes ? "Allow" : "Block"
    }

    private var inhumanVerdict: String {
        switch verdict {
        case "verified": return "Verified"
        case "unverified": return "Rejected"
        default: return "Unverifiable"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                StatusDot(color: tint, size: 7)
                Text("Face recognition alone").dataLabel(.ihText2)
                Spacer()
                Text(stamp).dataLabel(tint, size: 10)
            }
            Hairline()
            HStack(alignment: .top, spacing: 14) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(similarity.map { String(format: "%.2f", $0) } ?? "—")
                        .numeric(40, weight: .bold)
                        .foregroundStyle(tint)
                    Text("Similarity").dataLabel(.ihText3, size: 9)
                }
                VStack(alignment: .leading, spacing: 4) {
                    Text(headline)
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundStyle(tint)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(detail)
                        .font(.system(size: 13))
                        .foregroundStyle(Color.ihText2)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }
            meter
            Hairline()
            HStack(alignment: .top, spacing: 12) {
                comparison("Face recognition", faceVerdict, similarity == nil ? .ihText2 : tint)
                Rectangle().fill(Color.ihLine).frame(width: 1, height: 34)
                comparison("InHuman", inhumanVerdict, Color.ihStatus(verdictStatus(verdict)))
            }
            Text("A deepfake is built to pass face recognition. These checks are what it can't fake.")
                .font(.system(size: 12))
                .foregroundStyle(Color.ihText3)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(18)
        .card(fill: bypass ? Color.ihBadSoft : Color.ihSurface,
              stroke: bypass ? Color.ihBad.opacity(0.35) : Color.ihLine)
    }

    private var meter: some View {
        VStack(alignment: .leading, spacing: 2) {
            ThresholdMeter(value: similarity ?? 0, threshold: Self.passMark, tint: tint)
            GeometryReader { geo in
                Text(String(format: "%.2f pass mark", Self.passMark))
                    .dataLabel(.ihText3, size: 9)
                    .offset(x: max(0, geo.size.width * CGFloat(Self.passMark) - 16))
            }
            .frame(height: 12)
        }
    }

    private func comparison(_ label: String, _ value: String, _ color: Color) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).dataLabel(.ihText3, size: 9)
            HStack(spacing: 6) {
                StatusDot(color: color, size: 6)
                Text(value).dataLabel(color, size: 11)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct TileCard<Content: View>: View {
    let tile: Tile
    @ViewBuilder var content: () -> Content

    private var color: Color { Color.ihStatus(tile.status) }

    private var word: String {
        switch tile.status {
        case "green": return "pass"
        case "red": return "fail"
        default: return "info"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                StatusDot(color: color, size: 7)
                Text(tile.name).dataLabel(.ihText2)
                Spacer()
                Text(word).dataLabel(color, size: 10)
            }
            Hairline()
            Text(tile.headline)
                .numeric(21)
                .foregroundStyle(Color.ihText)
                .fixedSize(horizontal: false, vertical: true)
            if !tile.detail.isEmpty {
                Text(tile.detail)
                    .font(.system(size: 13))
                    .foregroundStyle(Color.ihText2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            content()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .card()
    }
}

/// Small key under a chart: which line is which, without a legend box.
private struct ChartKey: View {
    let items: [(String, Color, Bool)]      // name, colour, dashed

    var body: some View {
        HStack(spacing: 12) {
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                HStack(spacing: 5) {
                    Capsule()
                        .fill(item.1)
                        .frame(width: item.2 ? 5 : 14, height: 2)
                        .opacity(item.2 ? 0.9 : 1)
                    Text(item.0).dataLabel(.ihText3, size: 9)
                }
            }
            Spacer(minLength: 0)
        }
    }
}

/// Measured skin color (solid) against what the screen sent, shifted by the measured lag (dashed).
struct LightResponseChart: View {
    let plot: LagPlot

    private struct Point: Identifiable {
        let id: Int
        let t: Double
        let value: Double
        let series: String
    }

    private var points: [Point] {
        var out: [Point] = []
        let channels: [(Int, String)] = [(0, "red"), (1, "green")]
        for (c, name) in channels {
            // Normalize each channel to 0...1 so both fit one axis.
            let m = plot.measured.map { $0[c] }
            let lo = m.min() ?? 0, span = max((m.max() ?? 1) - lo, 1e-6)
            for i in plot.t.indices {
                out.append(Point(id: out.count, t: plot.t[i], value: (plot.measured[i][c] - lo) / span, series: "\(name) measured"))
                out.append(Point(id: out.count, t: plot.t[i], value: (plot.expected[i][c] - lo) / span, series: "\(name) sent"))
            }
        }
        return out
    }

    /// One hue for what the skin did, one for what the screen sent: the story is the gap
    /// between them, not which channel is which.
    private func color(_ series: String) -> Color {
        if series.hasSuffix("sent") { return .ihText3 }
        return series.hasPrefix("red") ? .ihAccent : .ihAccent.opacity(0.55)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Chart(points) { p in
                LineMark(x: .value("s", p.t), y: .value("level", p.value), series: .value("series", p.series))
                    .foregroundStyle(color(p.series))
                    .lineStyle(StrokeStyle(lineWidth: p.series.hasSuffix("sent") ? 1 : 1.6,
                                           lineJoin: .round,
                                           dash: p.series.hasSuffix("sent") ? [3, 3] : []))
            }
            .chartYAxis(.hidden)
            .chartXAxis {
                AxisMarks(values: .automatic(desiredCount: 4)) { _ in
                    AxisGridLine().foregroundStyle(Color.ihLine)
                    AxisValueLabel()
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(Color.ihText3)
                }
            }
            .chartLegend(.hidden)
            .frame(height: 130)
            ChartKey(items: [("skin, measured", .ihAccent, false), ("screen, sent", .ihText3, true)])
        }
        .padding(.top, 2)
    }
}

/// Shake felt by the motion sensor against the shake seen by the camera; ticks are the bursts.
struct VibrationChart: View {
    let plot: VibrationPlot

    private struct Point: Identifiable {
        let id: Int
        let t: Double
        let value: Double
        let series: String
    }

    private var points: [Point] {
        var out: [Point] = []
        // The sensor runs at 100 Hz; every other sample is plenty for a small chart.
        for i in stride(from: 0, to: plot.tImu.count, by: 2) {
            out.append(Point(id: out.count, t: plot.tImu[i], value: plot.imu[i], series: "sensor"))
        }
        for i in plot.tVideo.indices {
            out.append(Point(id: out.count, t: plot.tVideo[i], value: -plot.video[i], series: "camera"))
        }
        return out
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Chart {
                ForEach(plot.bursts, id: \.self) { b in
                    RuleMark(x: .value("burst", b))
                        .foregroundStyle(Color.ihLine)
                        .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
                }
                ForEach(points) { p in
                    LineMark(x: .value("s", p.t), y: .value("shake", p.value), series: .value("series", p.series))
                        .foregroundStyle(p.series == "sensor" ? Color.ihAccent : Color.ihWarn)
                        .lineStyle(StrokeStyle(lineWidth: 1.4, lineJoin: .round))
                }
            }
            .chartYAxis(.hidden)
            .chartXAxis {
                AxisMarks(values: .automatic(desiredCount: 4)) { _ in
                    AxisGridLine().foregroundStyle(Color.ihLine)
                    AxisValueLabel()
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(Color.ihText3)
                }
            }
            .chartLegend(.hidden)
            .frame(height: 110)
            ChartKey(items: [("phone sensor", .ihAccent, false), ("camera", .ihWarn, false), ("burst", .ihLine, true)])
        }
        .padding(.top, 2)
    }
}

/// Each displayed shape next to the crop of the eye while it was on screen.
struct EyeReflectionGrid: View {
    let states: [CorneaState]

    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 88), spacing: 8)], spacing: 8) {
            ForEach(states) { s in
                VStack(spacing: 6) {
                    if let data = Data(base64Encoded: s.cropJpegB64), let img = UIImage(data: data) {
                        Image(uiImage: img).resizable().interpolation(.none).scaledToFit()
                            .clipShape(RoundedRectangle(cornerRadius: Radius.sm, style: .continuous))
                            .overlay {
                                RoundedRectangle(cornerRadius: Radius.sm, style: .continuous)
                                    .strokeBorder(Color.ihLine, lineWidth: 1)
                            }
                    }
                    HStack(spacing: 5) {
                        Image(systemName: symbol(s.sentShape))
                            .font(.system(size: 9))
                            .foregroundStyle(s.sentColor == "green" ? Color.ihOk : Color.ihWarn)
                        Text(s.sentPosition).dataLabel(.ihText3, size: 9)
                        Image(systemName: matched(s) ? "checkmark" : "xmark")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundStyle(matched(s) ? Color.ihOk : Color.ihBad)
                    }
                }
                .padding(6)
                .card(radius: Radius.sm, fill: .ihRaised)
            }
        }
        .padding(.top, 2)
    }

    private func matched(_ s: CorneaState) -> Bool {
        s.match ?? (s.decodedShape == s.sentShape)
    }

    private func symbol(_ shape: String) -> String {
        switch shape {
        case "circle": return "circle.fill"
        case "square": return "square.fill"
        default: return "triangle.fill"
        }
    }
}
