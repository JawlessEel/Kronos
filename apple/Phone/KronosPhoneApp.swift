import SwiftUI

@main struct KronosPhoneApp: App {
    var body: some Scene { WindowGroup { PhoneView() } }
}
struct PhoneView: View {
    @AppStorage("serverAddress") private var address=""
    @AppStorage("watchlist") private var watchlist="SPY,AAPL"
    @AppStorage("selectedSymbol") private var symbol="SPY"
    @AppStorage("watchMetric") private var metric="high"
    @AppStorage("nativeInterval") private var interval=5
    @AppStorage("nativeModel") private var model="kronos-base"
    @State private var token=""
    @State private var status="Connect to your Mac mini's private HTTPS dashboard."
    @State private var busy=false
    @State private var catalog:ModelCatalog?
    @State private var device="cpu"
    @StateObject private var bridge=WatchBridge.shared
    private var symbols:[String] {Array(Set(watchlist.uppercased().split(separator:",").map{String($0).trimmingCharacters(in:.whitespaces)})).filter{!$0.isEmpty}.sorted()}
    func perform(_ operation:@escaping ()async throws->Void) {
        guard !busy else{return};busy=true
        Task {do {try await operation()}catch{status=error.localizedDescription};busy=false}
    }
    func refresh(_ client:KronosClient)async throws {
        let data=try await client.summary(symbol:symbol,interval:interval)
        try bridge.publish(data,metric:metric)
        status=bridge.snapshot?.reason ?? "No current-day forecast."
    }
    var body: some View {
        NavigationStack {
            Form {
                Section("Mac mini connection") {
                    TextField("Private HTTPS dashboard address",text:$address).textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                    SecureField("Dashboard access token",text:$token)
                    Button("Connect / sign in") {perform{
                        let client=try KronosClient(address:address)
                        try await client.signIn(token:token)
                        try TokenKeychain.save(token,host:client.origin)
                        let catalogData=try await client.call("/api/available-models")
                        catalog=try JSONDecoder().decode(ModelCatalog.self,from:catalogData)
                        device=catalog?.devices["mps"] == true ? "mps" : catalog?.devices["cuda"] == true ? "cuda" : "cpu"
                        status="Connected. Load a model or use the model already loaded on the Mac."
                    }}
                }
                Section("Watch symbol and number") {
                    TextField("Comma-separated symbols",text:$watchlist).textInputAutocapitalization(.characters).autocorrectionDisabled()
                    Picker("Symbol",selection:$symbol) {ForEach(symbols,id:\.self){Text($0).tag($0)}}
                    Picker("Complication number",selection:$metric) {Text("Predicted high").tag("high");Text("Predicted low").tag("low")}
                    Picker("Candle interval",selection:$interval) {Text("1 minute").tag(1);Text("5 minutes").tag(5);Text("15 minutes").tag(15)}
                    Text("Use the same symbols as Stocks. This watchlist is managed in Kronos.").font(.caption).foregroundStyle(.secondary)
                }
                Section("Today to market close") {
                    if let catalog {
                        Picker("Server model",selection:$model){ForEach(catalog.models.keys.sorted(),id:\.self){key in Text(catalog.models[key]!.name).tag(key)}}
                        Picker("Server device",selection:$device){ForEach(catalog.devices.keys.filter{catalog.devices[$0] == true}.sorted(),id:\.self){Text($0.uppercased()).tag($0)}}
                        Button("Load selected server model"){perform{let client=try KronosClient(address:address);_ = try await client.call("/api/load-model",body:["model_key":model,"device":device]);status="Model loaded."}}
                    }
                    Button("Read saved today forecast"){perform{try await refresh(KronosClient(address:address))}}
                    Button("Generate forecast through today's close"){perform{
                        let client=try KronosClient(address:address)
                        _ = try await client.call("/api/live/predict",body:["ticker":symbol,"interval":interval,"lookback":400,"history":1000,"pred_len":30,"target_today":true,"temperature":0.6,"top_p":0.9,"sample_count":1])
                        try await refresh(client)
                    }}
                    if busy {ProgressView("Working on the Mac mini…")}
                    Text(status).font(.caption)
                    TimelineView(.periodic(from:.now,by:60)){context in
                        if let value=bridge.snapshot,value.ticker==symbol,value.interval_minutes==interval {
                            VStack(alignment:.leading){
                                Text(value.label(at:context.date)).font(.headline)
                                if value.usable(at:context.date) {
                                    ForecastChart(snapshot:value).frame(height:180)
                                    HStack {Text("Pred H \(value.predicted_high!,specifier:"%.2f")");Spacer();Text("Pred L \(value.predicted_low!,specifier:"%.2f")")}.monospacedDigit()
                                    Text("Solid: observed · Dashed: predicted · Times: New York").font(.caption2)
                                }
                            }
                        }
                    }
                }
                Section("Apple Watch") {Text(bridge.message.isEmpty ? "Choose Kronos Today in a rectangular watch-face pane after pairing and installation." : bridge.message).font(.caption)}
            }
            .navigationTitle("Kronos Today")
            .disabled(busy)
            .onAppear {if let client=try? KronosClient(address:address){token=TokenKeychain.load(client.origin)}}
            .onChange(of:watchlist) {_,_ in if !symbols.contains(symbol) {symbol=symbols.first ?? "SPY"}}
            .onChange(of:metric) {_,_ in if let value=bridge.snapshot,let data=try? JSONEncoder().encode(value){do{try bridge.publish(data,metric:metric)}catch{status=error.localizedDescription}}}
        }
    }
}
