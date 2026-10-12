import Foundation
import Security

enum ClientError: LocalizedError {
    case message(String)
    var errorDescription: String? { if case .message(let text)=self { return text };return nil }
}
enum TokenKeychain {
    static func query(_ host:String)->[String:Any] { [kSecClass as String:kSecClassGenericPassword,kSecAttrService as String:"Kronos dashboard",kSecAttrAccount as String:host] }
    static func load(_ host:String)->String {
        var q=query(host);q[kSecReturnData as String]=true;q[kSecMatchLimit as String]=kSecMatchLimitOne
        var result:CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary,&result)==errSecSuccess,let data=result as? Data else {return ""}
        return String(data:data,encoding:.utf8) ?? ""
    }
    static func save(_ token:String,host:String)throws {
        let q=query(host), values=[kSecValueData as String:Data(token.utf8)]
        let update=SecItemUpdate(q as CFDictionary,values as CFDictionary)
        if update==errSecItemNotFound {
            var item=q;values.forEach{item[$0.key]=$0.value};item[kSecAttrAccessible as String]=kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            guard SecItemAdd(item as CFDictionary,nil)==errSecSuccess else {throw ClientError.message("Cannot save dashboard access in Keychain.")};return
        }
        guard update==errSecSuccess else {throw ClientError.message("Cannot update Keychain access.")}
    }
}
struct ModelCatalog: Decodable {
    struct ModelInfo:Decodable {let name:String;let context_length:Int}
    let models:[String:ModelInfo]
    let devices:[String:Bool]
}
struct KronosClient {
    let base:URL
    private static let session:URLSession = {
        let config=URLSessionConfiguration.default
        config.timeoutIntervalForRequest=600;config.timeoutIntervalForResource=650
        return URLSession(configuration:config)
    }()
    init(address:String)throws {
        guard let url=URL(string:address.trimmingCharacters(in:.whitespacesAndNewlines)), let host=url.host,
              url.user==nil,url.password==nil,url.query==nil,url.fragment==nil,
              (url.path.isEmpty || url.path=="/"),
              url.scheme=="https" || (url.scheme=="http" && ["localhost","127.0.0.1"].contains(host)) else {
            throw ClientError.message("Enter the Mac mini's private HTTPS base address, with no path or credentials.")
        }
        base=url
    }
    var origin:String { var parts=URLComponents(url:base,resolvingAgainstBaseURL:false)!;parts.path="";return parts.string! }
    func call(_ path:String,body:[String:Any]?=nil)async throws->Data {
        guard let url=URL(string:path,relativeTo:base)?.absoluteURL else {throw ClientError.message("Invalid API address.")}
        var request=URLRequest(url:url)
        request.setValue(origin,forHTTPHeaderField:"Origin")
        if let body {request.httpMethod="POST";request.setValue("application/json",forHTTPHeaderField:"Content-Type");request.httpBody=try JSONSerialization.data(withJSONObject:body)}
        let (data,response)=try await Self.session.data(for:request)
        guard let http=response as? HTTPURLResponse else {throw ClientError.message("No server response.")}
        guard (200..<300).contains(http.statusCode) else {
            let error=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any]
            throw ClientError.message(error?["error"] as? String ?? "Server returned HTTP \(http.statusCode).")
        }
        return data
    }
    func signIn(token:String)async throws {
        var request=URLRequest(url:base.appendingPathComponent("login"))
        request.httpMethod="POST";request.setValue("application/x-www-form-urlencoded",forHTTPHeaderField:"Content-Type")
        var parts=URLComponents();parts.queryItems=[URLQueryItem(name:"token",value:token)]
        request.httpBody=Data((parts.percentEncodedQuery ?? "").replacingOccurrences(of:"+",with:"%2B").utf8)
        let (_,response)=try await Self.session.data(for:request)
        if let response=response as? HTTPURLResponse,response.statusCode==429 {throw ClientError.message("Too many login attempts; wait one minute.")}
        _ = try await call("/api/model-status")
    }
    func summary(symbol:String,interval:Int)async throws->Data {
        var parts=URLComponents();parts.path="/api/live/watch-summary";parts.queryItems=[URLQueryItem(name:"ticker",value:symbol),URLQueryItem(name:"interval",value:String(interval))]
        return try await call(parts.string!)
    }
}
