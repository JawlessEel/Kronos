import SwiftUI

@main struct KronosWatchApp: App {
    @StateObject private var bridge=WatchBridge.shared
    var body: some Scene {
        WindowGroup {
            TimelineView(.periodic(from:.now,by:60)) { context in
                VStack(alignment:.leading,spacing:8) {
                    if let value=bridge.snapshot {
                        Text(value.ticker).font(.headline)
                        if value.usable(at:context.date) {
                            ForecastChart(snapshot:value).frame(height:70)
                            if let number=SnapshotStore.metric == "low" ? value.predicted_low : value.predicted_high {
                                Text("Pred \(SnapshotStore.metric == "low" ? "Low" : "High") \(number, specifier:"%.2f")").monospacedDigit()
                            }
                        }
                        Text(value.label(at:context.date)).font(.caption2).foregroundStyle(.secondary)
                    } else { Text("Open Kronos on iPhone").font(.caption) }
                }.padding(6)
            }
        }
    }
}
