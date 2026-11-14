import Foundation

/// Plain-language reading of a Kronos snapshot: direction, range, timing, freshness and
/// what-if scenarios. It only describes the model output; it never places or suggests trades.
struct ForecastExplanation: Equatable {
    enum Direction: String { case up = "Up", down = "Down", flat = "Flat", unavailable = "No forecast" }
    enum Spread: String { case tight = "Tight", normal = "Normal", wide = "Wide" }

    let direction: Direction
    let headline: String
    let points: [String]
    let scenarios: [String]
    let spread: Spread?
    let caution: String

    /// Compact text for Siri, notifications and the on-device model.
    var spokenSummary: String {
        ([headline] + points.prefix(2)).joined(separator: " ")
    }
}

enum ForecastExplainer {
    static let caution = "Model estimate from a single sample, not a prediction you can count on and not financial advice."

    static func explain(_ s: ForecastSnapshot, now: Date = Date()) -> ForecastExplanation {
        guard s.usable(at: now),
              let high = s.predicted_high, let low = s.predicted_low,
              let last = s.observed.last(where: { $0.close.isFinite })?.close, last > 0,
              let end = s.predicted.last(where: { $0.close.isFinite })?.close else {
            return unavailable(s, now: now)
        }

        let changePct = (end - last) / last * 100
        let direction: ForecastExplanation.Direction = changePct > 0.15 ? .up : (changePct < -0.15 ? .down : .flat)
        let upPct = (high - last) / last * 100
        let downPct = (low - last) / last * 100
        let widthPct = (high - low) / last * 100
        let spread: ForecastExplanation.Spread = widthPct < 0.6 ? .tight : (widthPct < 1.5 ? .normal : .wide)

        let headline: String
        switch direction {
        case .up: headline = "\(s.ticker): model leans higher into the close, ending near \(price(end)) (\(signed(changePct)))."
        case .down: headline = "\(s.ticker): model leans lower into the close, ending near \(price(end)) (\(signed(changePct)))."
        default: headline = "\(s.ticker): model sees little net change by the close, ending near \(price(end)) (\(signed(changePct)))."
        }

        var points = [
            "Last price \(price(last)). Predicted range \(price(low))–\(price(high)), a \(spread.rawValue.lowercased()) spread of \(String(format: "%.2f", widthPct))%."
        ]
        if let closeDate = s.market_close.flatMap(ForecastSnapshot.date) {
            let minutes = max(0, Int(closeDate.timeIntervalSince(now) / 60))
            points.append("\(duration(minutes)) left in the regular session (\(s.interval_minutes)-minute candles).")
        }
        if let expiry = s.expires_at.flatMap(ForecastSnapshot.date) {
            let minutes = max(0, Int(expiry.timeIntervalSince(now) / 60))
            points.append("This forecast goes stale in \(duration(minutes)); refresh on iPhone after that.")
        }
        if s.quality_count > 0 {
            points.append("\(s.quality_count) predicted candle\(s.quality_count == 1 ? " was" : "s were") flagged for inconsistent bounds — read the range loosely.")
        }

        var scenarios: [String] = []
        scenarios.append("If it follows the path: about \(price(end)) at the close.")
        scenarios.append("Upside case: touches \(price(high)) (\(signed(upPct)))\(timeText(s.high_time)).")
        scenarios.append("Downside case: dips to \(price(low)) (\(signed(downPct)))\(timeText(s.low_time)).")

        return ForecastExplanation(direction: direction, headline: headline, points: points,
                                   scenarios: scenarios, spread: spread, caution: caution)
    }

    static func unavailable(_ s: ForecastSnapshot, now: Date) -> ForecastExplanation {
        let reason: String
        if s.status == "closed" {
            reason = "The market is closed, so there's no forecast for the rest of today."
        } else if s.status == "invalid" {
            reason = "The server marked this forecast invalid: \(s.reason)"
        } else if let expiry = s.expires_at.flatMap(ForecastSnapshot.date), now >= expiry {
            reason = "This forecast expired at \(clock(expiry)). Refresh or generate a new one on iPhone."
        } else if s.status != "ready" {
            reason = "The server says: \(s.reason)"
        } else {
            reason = "This forecast isn't for today's session or is missing its high/low. Generate a new one."
        }
        return ForecastExplanation(direction: .unavailable, headline: "\(s.ticker): no usable forecast right now.",
                                   points: [reason], scenarios: [], spread: nil, caution: caution)
    }

    // MARK: Formatting

    static func price(_ value: Double) -> String { String(format: "%.2f", value) }

    static func signed(_ pct: Double) -> String {
        String(format: "%@%.2f%%", pct >= 0 ? "+" : "−", abs(pct))
    }

    static func duration(_ minutes: Int) -> String {
        minutes >= 60 ? "\(minutes / 60)h \(minutes % 60)m" : "\(minutes) min"
    }

    static func clock(_ date: Date) -> String {
        let f = DateFormatter()
        f.timeZone = TimeZone(identifier: "America/New_York")
        f.dateFormat = "h:mm a"
        return f.string(from: date) + " ET"
    }

    static func timeText(_ iso: String?) -> String {
        guard let date = iso.flatMap(ForecastSnapshot.date) else { return "" }
        return " around \(clock(date))"
    }
}
