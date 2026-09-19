import Charts
import SwiftUI

struct ResultsView: View {
    @EnvironmentObject var flow: Flow

    var body: some View {
        ScrollView {
            if let r = flow.result {
                VStack(spacing: 14) {
                    VerdictBanner(result: r)
                    ForEach(r.tiles) { tile in
                        TileCard(tile: tile) {
                            switch tile.name {
                            case "Light response":
                                if let plot = r.signals?.lag?.plot { LightResponseChart(plot: plot) }
                            case "Eye reflection":
                                if let states = r.signals?.cornea?.states { EyeReflectionGrid(states: states) }
                            case "Face match":
                                if let data = flow.selfie, let img = UIImage(data: data) {
                                    Image(uiImage: img).resizable().scaledToFill()
                                        .frame(width: 84, height: 84).clipShape(Circle())
                                        .scaleEffect(x: -1, y: 1)   // show it the way the preview did
                                }
                            default: EmptyView()
                            }
                        }
                    }
                    if let s = r.processingS {
                        Text(String(format: "Analyzed in %.1f s", s)).font(.footnote).foregroundStyle(.secondary)
                    }
                    Button("Done") { flow.reset() }
                        .buttonStyle(.borderedProminent).controlSize(.large).padding(.top, 8)
                }
                .padding(16)
            }
        }
    }
}

private func statusColor(_ status: String) -> Color {
    switch status {
    case "green": return .green
    case "red": return .red
    default: return .yellow
    }
}

struct VerdictBanner: View {
    let result: VerifyResult

    private var style: (title: String, icon: String, color: Color) {
        switch result.verdict {
        case "verified": return ("Verified", "checkmark.seal.fill", .green)
        case "unverified": return ("Not verified", "xmark.seal.fill", .red)
        default: return ("Couldn't verify", "questionmark.circle.fill", .yellow)
        }
    }

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: style.icon).font(.system(size: 40)).foregroundStyle(style.color)
            VStack(alignment: .leading, spacing: 2) {
                Text(style.title).font(.title2.bold())
                Text(result.reason).font(.subheadline).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .padding(16)
        .background(style.color.opacity(0.14), in: RoundedRectangle(cornerRadius: 16))
    }
}

struct TileCard<Content: View>: View {
    let tile: Tile
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Circle().fill(statusColor(tile.status)).frame(width: 12, height: 12)
                Text(tile.name.uppercased()).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                Spacer()
            }
            Text(tile.headline).font(.title3.weight(.semibold))
            if !tile.detail.isEmpty {
                Text(tile.detail).font(.footnote).foregroundStyle(.secondary)
            }
            content()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 16))
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

    var body: some View {
        Chart(points) { p in
            LineMark(x: .value("s", p.t), y: .value("level", p.value), series: .value("series", p.series))
                .foregroundStyle(p.series.hasPrefix("red") ? Color.red : Color.green)
                .lineStyle(StrokeStyle(lineWidth: p.series.hasSuffix("sent") ? 1 : 2,
                                       dash: p.series.hasSuffix("sent") ? [4, 3] : []))
        }
        .chartYAxis(.hidden)
        .chartLegend(.hidden)
        .frame(height: 130)
    }
}

/// Each displayed shape next to the crop of the eye while it was on screen.
struct EyeReflectionGrid: View {
    let states: [CorneaState]

    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 92), spacing: 10)], spacing: 10) {
            ForEach(states) { s in
                VStack(spacing: 4) {
                    if let data = Data(base64Encoded: s.cropJpegB64), let img = UIImage(data: data) {
                        Image(uiImage: img).resizable().interpolation(.none).scaledToFit()
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                    }
                    HStack(spacing: 4) {
                        Image(systemName: symbol(s.sentShape))
                            .foregroundStyle(s.sentColor == "green" ? Color.green : Color.orange)
                        Image(systemName: s.decodedShape == s.sentShape ? "checkmark" : "xmark")
                            .foregroundStyle(s.decodedShape == s.sentShape ? Color.green : Color.red)
                        Text(String(format: "%.2f", s.score)).font(.caption2).foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    private func symbol(_ shape: String) -> String {
        switch shape {
        case "circle": return "circle.fill"
        case "square": return "square.fill"
        default: return "triangle.fill"
        }
    }
}
