import Foundation
import WatchConnectivity
import WidgetKit
import Combine

final class WatchBridge: NSObject, ObservableObject, WCSessionDelegate {
    static let shared = WatchBridge()
    @Published var snapshot = SnapshotStore.load()
    @Published var message = ""
    private var pending: [String:Any]?
    private override init() {
        super.init()
        if WCSession.isSupported() { WCSession.default.delegate = self; WCSession.default.activate() }
    }
    func publish(_ data: Data, metric: String) throws {
        try SnapshotStore.save(data, metric:metric)
        snapshot = SnapshotStore.load()
        pending = ["snapshot":data,"metric":metric]
        flush()
    }
    private func flush() {
        guard WCSession.isSupported(), WCSession.default.activationState == .activated, let pending else { return }
        do { try WCSession.default.updateApplicationContext(pending); self.pending=nil; message="Watch update queued; delivery is controlled by watchOS." }
        catch { message="Watch update failed: \(error.localizedDescription)" }
    }
    func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        DispatchQueue.main.async { if let error { self.message=error.localizedDescription } else { self.flush() } }
    }
    func session(_ session: WCSession, didReceiveApplicationContext applicationContext: [String:Any]) {
        guard let data=applicationContext["snapshot"] as? Data, let metric=applicationContext["metric"] as? String else { return }
        do {
            try SnapshotStore.save(data, metric:metric)
            DispatchQueue.main.async { self.snapshot=SnapshotStore.load() }
            WidgetCenter.shared.reloadTimelines(ofKind:"KronosToday")
        } catch { DispatchQueue.main.async { self.message="Invalid phone forecast: \(error.localizedDescription)" } }
    }
    #if os(iOS)
    func sessionDidBecomeInactive(_ session: WCSession) {}
    func sessionDidDeactivate(_ session: WCSession) { session.activate() }
    #endif
}
