import Foundation

struct PricePoint: Codable, Identifiable {
    let timestamp: String
    let close: Double
    var id: String { timestamp }
    var date: Date { ForecastSnapshot.date(timestamp) ?? .distantPast }
}

struct ForecastSnapshot: Codable {
    let version: Int
    let ticker: String
    let session_date: String
    let status: String
    let reason: String
    let market_close: String?
    let generated_at: String?
    let expires_at: String?
    let predicted_high: Double?
    let predicted_low: Double?
    let high_time: String?
    let low_time: String?
    let observed: [PricePoint]
    let predicted: [PricePoint]
    let quality_count: Int
    let interval_minutes: Int

    static func date(_ value: String) -> Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.date(from: value) ?? ISO8601DateFormatter().date(from: value)
    }
    func usable(at now: Date = Date()) -> Bool {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/New_York")!
        guard version == 1, status == "ready", let expiry = expires_at.flatMap(Self.date),
              let close = market_close.flatMap(Self.date), let generated = generated_at.flatMap(Self.date),
              generated <= now, now < expiry, now < close,
              let high = predicted_high, let low = predicted_low, high.isFinite, low.isFinite, high >= low,
              !predicted.isEmpty else { return false }
        let formatter = DateFormatter()
        formatter.calendar = calendar; formatter.timeZone = calendar.timeZone; formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: now) == session_date
    }
    func label(at now: Date = Date()) -> String {
        usable(at: now) ? "Today to close" : status == "closed" ? "Market closed" : status == "invalid" ? "Check forecast" : "Refresh on iPhone"
    }
}

enum SnapshotStore {
    static var defaults: UserDefaults? {
        guard let group = Bundle.main.object(forInfoDictionaryKey: "KronosAppGroup") as? String else { return nil }
        return UserDefaults(suiteName: group)
    }
    static func load() -> ForecastSnapshot? {
        guard let data = defaults?.data(forKey: "watchSnapshot") else { return nil }
        return try? JSONDecoder().decode(ForecastSnapshot.self, from: data)
    }
    static func save(_ data: Data, metric: String) throws {
        let value = try JSONDecoder().decode(ForecastSnapshot.self, from: data)
        guard value.version == 1, data.count < 200_000, let defaults else {
            throw NSError(domain: "Kronos", code: 1, userInfo: [NSLocalizedDescriptionKey:"Invalid snapshot or missing App Group configuration."])
        }
        defaults.set(data, forKey: "watchSnapshot")
        defaults.set(metric == "low" ? "low" : "high", forKey: "watchMetric")
    }
    static var metric: String { defaults?.string(forKey:"watchMetric") ?? "high" }
}
