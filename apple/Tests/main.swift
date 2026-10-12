import Foundation

// Synthetic contract fixture only; never used by the apps or server.
let fixture = """
{"version":1,"ticker":"SPY","session_date":"2026-10-02","status":"ready",
 "reason":"Contract test","market_close":"2026-10-02T20:00:00+00:00",
 "generated_at":"2026-10-02T16:06:00.123456+00:00","expires_at":"2026-10-02T16:21:00+00:00",
 "predicted_high":102,"predicted_low":99,"high_time":"2026-10-02T19:55:00+00:00",
 "low_time":"2026-10-02T16:10:00+00:00","observed":[{"timestamp":"2026-10-02T16:00:00+00:00","close":100}],
 "predicted":[{"timestamp":"2026-10-02T16:10:00+00:00","close":101}],"quality_count":0,"interval_minutes":5}
"""
let now = ForecastSnapshot.date("2026-10-02T16:07:00Z")!
func decode(_ text: String) throws -> ForecastSnapshot {
    try JSONDecoder().decode(ForecastSnapshot.self, from: Data(text.utf8))
}
let value = try decode(fixture)
precondition(value.usable(at: now))
precondition(!value.usable(at: ForecastSnapshot.date("2026-10-02T16:21:00Z")!))
precondition(!value.usable(at: ForecastSnapshot.date("2026-10-02T20:00:00Z")!))
precondition(!value.usable(at: ForecastSnapshot.date("2026-10-05T16:07:00Z")!))
precondition(!value.usable(at: ForecastSnapshot.date("2026-10-02T16:05:00Z")!))
let invalid = try decode(fixture.replacingOccurrences(of: "\"ready\"", with: "\"invalid\""))
let reversedRange = try decode(fixture.replacingOccurrences(of: "\"predicted_high\":102", with: "\"predicted_high\":98"))
let otherDay = try decode(fixture.replacingOccurrences(of: "\"session_date\":\"2026-10-02\"", with: "\"session_date\":\"2026-10-01\""))
precondition(!invalid.usable(at: now))
precondition(!reversedRange.usable(at: now))
precondition(!otherDay.usable(at: now))
precondition(ForecastSnapshot.date("not a timestamp") == nil)
print("Swift snapshot contract, expiry, closed session and invalid range checks passed.")
