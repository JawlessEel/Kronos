import SwiftUI

struct ForecastChart: View {
    let snapshot: ForecastSnapshot
    var body: some View {
        Canvas { context, size in
            let observed = snapshot.observed.filter { $0.close.isFinite }
            let predicted = snapshot.predicted.filter { $0.close.isFinite }
            let points = observed + predicted
            guard points.count > 1, let first = points.map(\.date).min(), let last = points.map(\.date).max(),
                  let low = points.map(\.close).min(), let high = points.map(\.close).max() else { return }
            let span = max(last.timeIntervalSince(first), 1), range = max(high-low, 0.01)
            func path(_ values: [PricePoint]) -> Path {
                var path = Path()
                for (i, point) in values.enumerated() {
                    let p = CGPoint(x:point.date.timeIntervalSince(first)/span*size.width,
                                    y:(1-(point.close-low)/range)*(size.height-4)+2)
                    if i == 0 { path.move(to:p) } else { path.addLine(to:p) }
                }
                return path
            }
            context.stroke(path(observed), with:.color(.primary), lineWidth:1.5)
            context.stroke(path(Array(observed.suffix(1))+predicted), with:.color(.cyan), style:StrokeStyle(lineWidth:1.5,dash:[3,2]))
        }
        .accessibilityLabel("Today's observed prices, followed by a dashed model forecast to market close")
    }
}
