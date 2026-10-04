#import <Cocoa/Cocoa.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <signal.h>

static NSString *root;
static int serverFD=-1, port=0;
static NSString *mime(NSString *file) {
    NSDictionary *types=@{@"html":@"text/html; charset=utf-8",@"js":@"application/javascript; charset=utf-8",@"mjs":@"application/javascript; charset=utf-8",@"json":@"application/json",@"css":@"text/css; charset=utf-8",@"wasm":@"application/wasm",@"svg":@"image/svg+xml",@"png":@"image/png",@"txt":@"text/plain; charset=utf-8",@"md":@"text/plain; charset=utf-8",@"pine":@"text/plain; charset=utf-8"};
    return types[file.pathExtension.lowercaseString] ?: @"application/octet-stream";
}
static void sendAll(int fd,const void *bytes,size_t length) { const char *p=bytes; while(length) { ssize_t n=send(fd,p,length,0); if(n<=0) break; p+=n; length-=n; } }
static void reply(int fd,int status,NSString *type,NSData *data,BOOL head) {
    NSString *reason=status==200?@"OK":status==404?@"Not Found":status==405?@"Method Not Allowed":@"Bad Request";
    NSString *text=[NSString stringWithFormat:@"HTTP/1.1 %d %@\r\nContent-Type: %@\r\nContent-Length: %lu\r\nConnection: close\r\nCache-Control: no-cache\r\nX-Content-Type-Options: nosniff\r\n\r\n",status,reason,type,(unsigned long)data.length];
    NSData *header=[text dataUsingEncoding:NSUTF8StringEncoding]; sendAll(fd,header.bytes,header.length); if(!head) sendAll(fd,data.bytes,data.length);
}
static void serve(int fd) { @autoreleasepool {
    int noSig=1; setsockopt(fd,SOL_SOCKET,SO_NOSIGPIPE,&noSig,sizeof(noSig));
    struct timeval timeout={5,0}; setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout)); timeout.tv_sec=30; setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&timeout,sizeof(timeout));
    NSMutableData *header=[NSMutableData data]; char bytes[1024];
    while(header.length<16384) { ssize_t n=recv(fd,bytes,sizeof(bytes),0); if(n<=0) break; [header appendBytes:bytes length:n]; if([[NSString alloc] initWithData:header encoding:NSASCIIStringEncoding] && [[[NSString alloc] initWithData:header encoding:NSASCIIStringEncoding] containsString:@"\r\n\r\n"]) break; }
    NSString *text=[[NSString alloc] initWithData:header encoding:NSASCIIStringEncoding]; NSArray *lines=[text componentsSeparatedByString:@"\r\n"]; NSArray *first=[lines.firstObject componentsSeparatedByString:@" "]; BOOL head=[first.firstObject isEqual:@"HEAD"];
    NSData *empty=[NSData data];
    if(first.count!=3 || header.length>=16384) { reply(fd,400,@"text/plain",empty,NO); close(fd); return; }
    if(![first.firstObject isEqual:@"GET"] && !head) { reply(fd,405,@"text/plain",empty,NO); close(fd); return; }
    NSString *host=nil; for(NSString *line in lines) if([line.lowercaseString hasPrefix:@"host:"]) host=[[line substringFromIndex:5] stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
    if(![host isEqual:[NSString stringWithFormat:@"127.0.0.1:%d",port]] && ![host isEqual:[NSString stringWithFormat:@"localhost:%d",port]]) { reply(fd,400,@"text/plain",empty,head); close(fd); return; }
    NSString *url=[[[first[1] componentsSeparatedByString:@"?"] firstObject] stringByRemovingPercentEncoding];
    if([url isEqual:@"/health"]) { reply(fd,200,@"application/json",[@"{\"app\":\"kronos-webgpu-desktop\",\"version\":\"1.0.0\"}" dataUsingEncoding:NSUTF8StringEncoding],head); close(fd); return; }
    if(!url || ![url hasPrefix:@"/"] || [url containsString:@"\\"] || [url containsString:@":"]) { reply(fd,400,@"text/plain",empty,head); close(fd); return; }
    NSString *relative=[url isEqual:@"/"]?@"workbench/index.html":[url substringFromIndex:1]; if([url hasPrefix:@"/src/"]) relative=[@"workbench/" stringByAppendingString:[url substringFromIndex:1]];
    NSString *file=[[root stringByAppendingPathComponent:relative] stringByResolvingSymlinksInPath];
    if(![file hasPrefix:[root stringByAppendingString:@"/"]]) { reply(fd,404,@"text/plain",empty,head); close(fd); return; }
    NSData *data=[NSData dataWithContentsOfFile:file]; if(!data) reply(fd,404,@"text/plain",empty,head); else reply(fd,200,mime(file),data,head); close(fd);
} }
static BOOL startServer(void) {
    for(int p=7090;p<7100;p++) {
        int fd=socket(AF_INET,SOCK_STREAM,0); if(fd<0) continue;
        struct sockaddr_in addr={0}; addr.sin_family=AF_INET; addr.sin_port=htons(p); addr.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
        if(bind(fd,(struct sockaddr *)&addr,sizeof(addr))==0 && listen(fd,16)==0) { serverFD=fd; port=p; break; } close(fd);
    }
    if(serverFD<0) return NO;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY,0),^{ while(serverFD>=0) { int fd=accept(serverFD,NULL,NULL); if(fd<0) break; dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY,0),^{serve(fd);}); } }); return YES;
}
@interface KronosDelegate : NSObject <NSApplicationDelegate>
@property(strong) NSWindow *window;
@end
@implementation KronosDelegate
- (void)alert:(NSString *)message { NSAlert *a=[NSAlert new]; a.messageText=@"Kronos WebGPU"; a.informativeText=message; [a runModal]; }
- (void)openChrome:(id)sender {
    NSURL *chrome=[NSWorkspace.sharedWorkspace URLForApplicationWithBundleIdentifier:@"com.google.Chrome"];
    if(!chrome) { [self alert:@"Google Chrome is required. Install it from google.com/chrome, then try again."]; return; }
    NSURL *url=[NSURL URLWithString:[NSString stringWithFormat:@"http://127.0.0.1:%d/",port]];
    [NSWorkspace.sharedWorkspace openURLs:@[url] withApplicationAtURL:chrome configuration:NSWorkspaceOpenConfiguration.configuration completionHandler:^(NSRunningApplication *app,NSError *error){ if(error) dispatch_async(dispatch_get_main_queue(),^{[self alert:error.localizedDescription];}); }];
}
- (void)showExtension:(id)sender { [NSWorkspace.sharedWorkspace activateFileViewerSelectingURLs:@[[NSURL fileURLWithPath:[root stringByAppendingPathComponent:@"chrome-bridge/extension"]]]]; }
- (void)showInstructions:(id)sender { [NSWorkspace.sharedWorkspace openURL:[NSURL fileURLWithPath:[root stringByAppendingPathComponent:@"START-HERE.txt"]]]; }
- (void)addButton:(NSString *)text y:(CGFloat)y action:(SEL)action { NSButton *button=[NSButton buttonWithTitle:text target:self action:action]; button.frame=NSMakeRect(24,y,392,36); [self.window.contentView addSubview:button]; }
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    if(!startServer()) { [self alert:@"Ports 7090-7099 are busy. Close another Kronos launcher or try later."]; [NSApp terminate:nil]; return; }
    self.window=[[NSWindow alloc] initWithContentRect:NSMakeRect(0,0,440,310) styleMask:NSWindowStyleMaskTitled|NSWindowStyleMaskClosable|NSWindowStyleMaskMiniaturizable backing:NSBackingStoreBuffered defer:NO]; self.window.title=@"Kronos WebGPU";
    NSTextField *label=[NSTextField wrappingLabelWithString:[NSString stringWithFormat:@"Kronos is running at http://127.0.0.1:%d/\nModel inference runs in Chrome on this device.\nKeep this window open. Closing it stops the local server.\nNo server is exposed to your network.",port]]; label.frame=NSMakeRect(24,186,392,98); [self.window.contentView addSubview:label];
    [self addButton:@"Open Kronos in Chrome" y:136 action:@selector(openChrome:)]; [self addButton:@"Show Chrome extension folder" y:88 action:@selector(showExtension:)]; [self addButton:@"Read setup instructions" y:40 action:@selector(showInstructions:)];
    NSMenu *menu=[NSMenu new]; NSMenuItem *appItem=[NSMenuItem new]; [menu addItem:appItem]; NSMenu *appMenu=[NSMenu new]; [appMenu addItemWithTitle:@"Quit Kronos" action:@selector(terminate:) keyEquivalent:@"q"]; appItem.submenu=appMenu; NSApp.mainMenu=menu;
    [self.window center]; [self.window makeKeyAndOrderFront:nil]; [NSApp activateIgnoringOtherApps:YES]; [self openChrome:nil];
}
- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)app { return YES; }
- (void)applicationWillTerminate:(NSNotification *)notification { if(serverFD>=0) { shutdown(serverFD,SHUT_RDWR); close(serverFD); serverFD=-1; } }
@end
int main(int argc,const char *argv[]) { @autoreleasepool {
    root=[[[NSBundle mainBundle].resourcePath stringByAppendingPathComponent:@"content"] stringByResolvingSymlinksInPath];
    if(argc==4 && strcmp(argv[1],"--serve")==0) { root=[[NSString stringWithUTF8String:argv[2]] stringByResolvingSymlinksInPath]; if(!startServer()) return 1; [[NSString stringWithFormat:@"%d",port] writeToFile:[NSString stringWithUTF8String:argv[3]] atomically:YES encoding:NSUTF8StringEncoding error:NULL]; sleep(60); return 0; }
    [NSApplication sharedApplication]; [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular]; KronosDelegate *delegate=[KronosDelegate new]; NSApp.delegate=delegate; [NSApp run]; return 0;
} }
