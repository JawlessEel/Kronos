import SwiftUI
import AppIntents
#if canImport(FoundationModels)
import FoundationModels
#endif

/// Optional friendlier wording from Apple's on-device model (iOS 26 with Apple Intelligence on).
/// Falls back to the deterministic ForecastExplainer text everywhere else.
enum ForecastBrain {
    static var isAvailable: Bool {
        #if canImport(FoundationModels)
        if #available(iOS 26.0, *) {
            if case .available = SystemLanguageModel.default.availability { return true }
        }
        #endif
        return false
    }

    static func simplify(_ e: ForecastExplanation) async -> String? {
        #if canImport(FoundationModels)
        if #available(iOS 26.0, *) {
            guard case .available = SystemLanguageModel.default.availability else { return nil }
            let facts = ([e.headline] + e.points + e.scenarios).joined(separator: "\n")
            do {
                let session = LanguageModelSession(instructions: """
                Rewrite stock-forecast facts for a non-expert in three short plain sentences. \
                Use only the numbers given. Never recommend buying, selling or holding. \
                End with: "This is a model estimate, not advice."
                """)
                let reply = try await session.respond(to: facts)
                let text = reply.content.trimmingCharacters(in: .whitespacesAndNewlines)
                return text.isEmpty ? nil : text
            } catch { return nil }
        }
        #endif
        return nil
    }
}

/// "Explain" card shown under the phone chart.
struct ForecastExplainerCard: View {
    let snapshot: ForecastSnapshot
    let now: Date
    @State private var simpleText: String?
    @State private var working = false

    var body: some View {
        let e = ForecastExplainer.explain(snapshot, now: now)
        VStack(alignment: .leading, spacing: 6) {
            Label(e.headline, systemImage: icon(e.direction)).font(.subheadline.weight(.semibold))
            ForEach(e.points, id: \.self) { Text("• " + $0).font(.caption) }
            if !e.scenarios.isEmpty {
                Text("Scenarios").font(.caption.weight(.bold)).padding(.top, 2)
                ForEach(e.scenarios, id: \.self) { Text("• " + $0).font(.caption) }
            }
            if let simpleText {
                Text(simpleText).font(.caption).padding(8)
                    .background(.cyan.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
            } else if ForecastBrain.isAvailable && e.direction != .unavailable {
                Button(working ? "Thinking…" : "Say it simply (on-device)") {
                    working = true
                    Task { simpleText = await ForecastBrain.simplify(e); working = false }
                }
                .font(.caption).disabled(working)
            }
            Text(e.caution).font(.caption2).foregroundStyle(.secondary)
        }
        .onChange(of: snapshot.generated_at) { _, _ in simpleText = nil }
    }

    private func icon(_ d: ForecastExplanation.Direction) -> String {
        switch d {
        case .up: return "arrow.up.right"
        case .down: return "arrow.down.right"
        case .flat: return "arrow.right"
        case .unavailable: return "clock.badge.exclamationmark"
        }
    }
}

// MARK: - Siri / Shortcuts (read-only)

struct ExplainForecastIntent: AppIntent {
    static let title: LocalizedStringResource = "Explain Today's Forecast"
    static let description = IntentDescription("Reads the latest saved Kronos forecast in plain language. It never runs the model or trades.")

    func perform() async throws -> some IntentResult & ProvidesDialog {
        guard let snapshot = SnapshotStore.load() else {
            return .result(dialog: "There's no saved Kronos forecast yet. Open Kronos and read or generate one.")
        }
        let e = ForecastExplainer.explain(snapshot)
        return .result(dialog: "\(e.spokenSummary) \(ForecastExplainer.caution)")
    }
}

struct KronosShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: ExplainForecastIntent(),
            phrases: ["Explain my \(.applicationName) forecast", "What does \(.applicationName) say today"],
            shortTitle: "Explain Forecast",
            systemImageName: "chart.line.uptrend.xyaxis"
        )
    }
}
