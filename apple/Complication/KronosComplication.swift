import SwiftUI
import WidgetKit

struct ForecastEntry: TimelineEntry {
    let date: Date
    let snapshot: ForecastSnapshot?
    let metric: String
}
struct Provider: TimelineProvider {
    func placeholder(in context: Context) -> ForecastEntry { ForecastEntry(date:Date(),snapshot:nil,metric:"high") }
    func getSnapshot(in context: Context, completion: @escaping (ForecastEntry)->Void) {
        completion(ForecastEntry(date:Date(),snapshot:SnapshotStore.load(),metric:SnapshotStore.metric))
    }
    func getTimeline(in context: Context, completion: @escaping (Timeline<ForecastEntry>)->Void) {
        let now=Date(), value=SnapshotStore.load(), metric=SnapshotStore.metric
        var entries=[ForecastEntry(date:now,snapshot:value,metric:metric)]
        if let value, let expiry=value.expires_at.flatMap(ForecastSnapshot.date), expiry > now {
            entries.append(ForecastEntry(date:expiry,snapshot:value,metric:metric))
        }
        completion(Timeline(entries:entries,policy:.after(now.addingTimeInterval(15*60))))
    }
}
struct ComplicationView: View {
    let entry: ForecastEntry
    var body: some View {
        VStack(alignment:.leading,spacing:2) {
            if let value=entry.snapshot {
                HStack {
                    Text(value.ticker).bold()
                    Spacer()
                    if value.usable(at:entry.date), let number=entry.metric == "low" ? value.predicted_low : value.predicted_high {
                        Text("Pred \(entry.metric == "low" ? "L" : "H") \(number, specifier:"%.2f")").monospacedDigit()
                    }
                }.font(.caption)
                if value.usable(at:entry.date) { ForecastChart(snapshot:value) }
                Text(value.label(at:entry.date)).font(.system(size:9)).foregroundStyle(.secondary)
            } else {
                Text("Kronos Today").font(.caption).bold()
                Text("Choose a symbol on iPhone").font(.caption2)
            }
        }
        .containerBackground(for:.widget) { Color.clear }
        .widgetURL(URL(string:"kronos://today"))
    }
}
@main struct KronosComplication: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind:"KronosToday",provider:Provider()) { ComplicationView(entry:$0) }
            .configurationDisplayName("Kronos Today")
            .description("Today's chart and predicted high or low before close.")
            .supportedFamilies([.accessoryRectangular])
    }
}
