using System;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Reflection;
using System.Threading;
using System.Diagnostics;
using System.Windows.Forms;
using System.Drawing;

class KronosServer : IDisposable {
    readonly string root;
    TcpListener listener;
    public int Port { get; private set; }
    public KronosServer(string directory) {
        root = Path.GetFullPath(directory).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        for (int p=7090;p<7100;p++) {
            try { listener = new TcpListener(IPAddress.Loopback,p); listener.Start(16); Port=p; break; }
            catch(SocketException) { listener=null; }
        }
        if(listener==null) throw new IOException("Ports 7090-7099 are busy. Close another Kronos launcher or try again later.");
        ThreadPool.QueueUserWorkItem(delegate { Accept(); });
    }
    void Accept() {
        while(listener!=null) {
            try { var current=listener; if(current==null) break; TcpClient client=current.AcceptTcpClient(); ThreadPool.QueueUserWorkItem(delegate { Serve(client); }); }
            catch(SocketException) { break; } catch(ObjectDisposedException) { break; }
        }
    }
    public static string Mime(string p) {
        switch(Path.GetExtension(p).ToLowerInvariant()) {
            case ".html": return "text/html; charset=utf-8";
            case ".js": case ".mjs": return "application/javascript; charset=utf-8";
            case ".json": return "application/json";
            case ".css": return "text/css; charset=utf-8";
            case ".wasm": return "application/wasm";
            case ".svg": return "image/svg+xml";
            case ".png": return "image/png";
            case ".txt": case ".md": case ".pine": return "text/plain; charset=utf-8";
            default: return "application/octet-stream";
        }
    }
    void Reply(NetworkStream stream,int status,string mime,byte[] data,bool head) {
        string reason=status==200?"OK":status==404?"Not Found":status==405?"Method Not Allowed":"Bad Request";
        byte[] header=Encoding.ASCII.GetBytes("HTTP/1.1 "+status+" "+reason+"\r\nContent-Type: "+mime+"\r\nContent-Length: "+data.Length+"\r\nConnection: close\r\nCache-Control: no-cache\r\nX-Content-Type-Options: nosniff\r\n\r\n");
        stream.Write(header,0,header.Length); if(!head) stream.Write(data,0,data.Length);
    }
    void Serve(TcpClient client) {
        using(client) {
            client.ReceiveTimeout=5000; client.SendTimeout=30000;
            try {
                var stream=client.GetStream(); var header=new StringBuilder(); int b;
                while(header.Length<16384 && (b=stream.ReadByte())>=0) { header.Append((char)b); if(header.ToString().EndsWith("\r\n\r\n")) break; }
                string[] lines=header.ToString().Split(new[]{"\r\n"},StringSplitOptions.None);
                string[] first=lines[0].Split(' '); bool head=first[0]=="HEAD";
                if(first.Length!=3 || header.Length>=16384) { Reply(stream,400,"text/plain",Encoding.UTF8.GetBytes("Invalid request"),false); return; }
                if(first[0]!="GET" && !head) { Reply(stream,405,"text/plain",new byte[0],false); return; }
                string expected="127.0.0.1:"+Port;
                string host=null; foreach(string line in lines) if(line.StartsWith("Host:",StringComparison.OrdinalIgnoreCase)) host=line.Substring(5).Trim();
                if(host!=expected && host!="localhost:"+Port) { Reply(stream,400,"text/plain",Encoding.UTF8.GetBytes("Invalid host"),head); return; }
                string raw=first[1].Split('?')[0]; string url=Uri.UnescapeDataString(raw);
                if(url=="/health") { Reply(stream,200,"application/json",Encoding.UTF8.GetBytes("{\"app\":\"kronos-webgpu-desktop\",\"version\":\"1.0.0\"}"),head); return; }
                if(!url.StartsWith("/") || url.Contains("\\") || url.Contains(":")) { Reply(stream,400,"text/plain",new byte[0],head); return; }
                string relative=url=="/"?"workbench/index.html":url.TrimStart('/');
                if(url.StartsWith("/src/")) relative="workbench/"+url.TrimStart('/');
                string file=Path.GetFullPath(Path.Combine(root,relative.Replace('/',Path.DirectorySeparatorChar)));
                if(!file.StartsWith(root,StringComparison.OrdinalIgnoreCase) || !File.Exists(file)) { Reply(stream,404,"text/plain",new byte[0],head); return; }
                // Reparse points could redirect a packaged path outside the application.
                for(string p=file;p!=root.TrimEnd(Path.DirectorySeparatorChar);p=Path.GetDirectoryName(p)) if((File.GetAttributes(p)&FileAttributes.ReparsePoint)!=0) { Reply(stream,404,"text/plain",new byte[0],head); return; }
                Reply(stream,200,Mime(file),File.ReadAllBytes(file),head);
            } catch(IOException) {} catch(ArgumentException) {} catch(UnauthorizedAccessException) {}
        }
    }
    public void Dispose() { var old=listener; listener=null; if(old!=null) old.Stop(); }
}

class Launcher {
    const string Version="1.0.0";
    static string ChromePath() {
        foreach(string dir in new[]{Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData)}) {
            string path=Path.Combine(dir,"Google","Chrome","Application","chrome.exe"); if(File.Exists(path)) return path;
        }
        throw new FileNotFoundException("Google Chrome is required. Install Chrome from google.com/chrome, then launch Kronos again.");
    }
    static void Chrome(string url) { Process.Start(new ProcessStartInfo(ChromePath(),"\""+url+"\"") { UseShellExecute=false }); }
    static string InstallRoot { get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"KronosWebGPU",Version); } }
    static Button Button(string text,int y,Action action) { var b=new Button{Text=text,Left=24,Top=y,Width=390,Height=38}; b.Click+=delegate{try{action();}catch(Exception e){MessageBox.Show(e.Message,"Kronos",MessageBoxButtons.OK,MessageBoxIcon.Error);}};return b; }
    static Form Window(string title) { return new Form{Text=title,ClientSize=new Size(440,320),StartPosition=FormStartPosition.CenterScreen,FormBorderStyle=FormBorderStyle.FixedDialog,MaximizeBox=false}; }
    static void Extract(string destination) {
        if(Directory.Exists(destination) && !File.Exists(Path.Combine(destination,".kronos-managed"))) throw new IOException("Install folder already exists and is not a managed Kronos installation. No files were changed.");
        if(File.Exists(Path.Combine(destination,"Kronos.exe"))) throw new IOException("Kronos 1.0.0 is already installed. Use its desktop shortcut. No files were overwritten.");
        Directory.CreateDirectory(destination);
        using(var source=Assembly.GetExecutingAssembly().GetManifestResourceStream("KronosPayload.zip")) {
            if(source==null) throw new IOException("Installer payload is missing.");
            using(var archive=new ZipArchive(source,ZipArchiveMode.Read)) {
                foreach(var entry in archive.Entries) {
                    string relative=entry.FullName.Substring(entry.FullName.IndexOf('/')+1);
                    if(String.IsNullOrEmpty(relative) || relative.EndsWith("/")) continue;
                    string file=Path.GetFullPath(Path.Combine(destination,relative.Replace('/',Path.DirectorySeparatorChar)));
                    if(!file.StartsWith(destination+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)) throw new IOException("Invalid installer member.");
                    Directory.CreateDirectory(Path.GetDirectoryName(file)); using(var from=entry.Open()) using(var to=File.Create(file)) from.CopyTo(to);
                }
            }
        }
        File.WriteAllText(Path.Combine(destination,".kronos-managed"),Version);
        File.Copy(Assembly.GetExecutingAssembly().Location,Path.Combine(destination,"Kronos.exe"));
    }
    static void Shortcut(string target,string link) {
        Type shellType=Type.GetTypeFromProgID("WScript.Shell"); object shell=Activator.CreateInstance(shellType);
        if(File.Exists(link)) return;
        object shortcut=shellType.InvokeMember("CreateShortcut",BindingFlags.InvokeMethod,null,shell,new object[]{link}); Type type=shortcut.GetType();
        type.InvokeMember("TargetPath",BindingFlags.SetProperty,null,shortcut,new object[]{target});
        type.InvokeMember("WorkingDirectory",BindingFlags.SetProperty,null,shortcut,new object[]{Path.GetDirectoryName(target)});
        type.InvokeMember("Save",BindingFlags.InvokeMethod,null,shortcut,null);
    }
    [STAThread] static int Main(string[] args) {
        try {
            if(args.Length==2 && args[0]=="--extract-test") { string destination=Path.GetFullPath(args[1]); Extract(destination); Shortcut(Path.Combine(destination,"Kronos.exe"),Path.Combine(destination,"Kronos-test.lnk")); return 0; }
            if(args.Length==3 && args[0]=="--serve") { using(var server=new KronosServer(args[1])) { File.WriteAllText(args[2],server.Port.ToString()); Thread.Sleep(60000); } return 0; }
            Application.EnableVisualStyles(); string root=Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
            if(!File.Exists(Path.Combine(root,".kronos-managed"))) {
                var setup=Window("Install Kronos WebGPU");
                setup.Controls.Add(new Label{Text="Install for your Windows account.\nIncludes the models, Perchance files and Chrome bridge.\nNo administrator password or Python required.\nChrome is installed separately.",Left=24,Top=24,Width=390,Height=100});
                setup.Controls.Add(Button("Install and launch Kronos",140,delegate { ChromePath(); Extract(InstallRoot); Shortcut(Path.Combine(InstallRoot,"Kronos.exe"),Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),"Kronos WebGPU.lnk")); Process.Start(Path.Combine(InstallRoot,"Kronos.exe")); setup.Close(); }));
                setup.Controls.Add(Button("Cancel",190,delegate{setup.Close();})); Application.Run(setup); return 0;
            }
            bool owns; using(var mutex=new Mutex(true,"Local\\KronosWebGPUDesktop",out owns)) {
                if(!owns) { MessageBox.Show("Kronos is already open. Use its launcher window to reopen Chrome.","Kronos"); return 0; }
                ChromePath(); using(var server=new KronosServer(root)) {
                    string url="http://127.0.0.1:"+server.Port+"/"; var window=Window("Kronos WebGPU");
                    window.Controls.Add(new Label{Text="Kronos is running at "+url+"\nModel inference runs in Chrome on this device.\nKeep this window open. Closing it stops the local server.\nNo server is exposed to your network.",Left=24,Top=24,Width=390,Height=100});
                    window.Controls.Add(Button("Open Kronos in Chrome",140,delegate{Chrome(url);}));
                    window.Controls.Add(Button("Show Chrome extension folder",190,delegate{Process.Start("explorer.exe","\""+Path.Combine(root,"chrome-bridge","extension")+"\"");}));
                    window.Controls.Add(Button("Read setup instructions",240,delegate{Process.Start(Path.Combine(root,"START-HERE.txt"));}));
                    window.Shown+=delegate { Chrome(url); }; Application.Run(window);
                } mutex.ReleaseMutex();
            } return 0;
        } catch(Exception e) { if(args.Length>0) Console.Error.WriteLine(e.Message); else MessageBox.Show(e.Message,"Kronos",MessageBoxButtons.OK,MessageBoxIcon.Error); return 1; }
    }
}
