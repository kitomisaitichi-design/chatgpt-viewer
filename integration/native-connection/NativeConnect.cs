// App-owned ChatGPT sign-in. Credentials stay in the private WebView2 profile.
using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Net.Http;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

[assembly: System.Reflection.AssemblyVersion("1.1.18.0")]
[assembly: System.Reflection.AssemblyFileVersion("1.1.18.0")]

static class Program {
    [STAThread] static void Main(string[] args) {
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        try {
            bool test = args.Length > 0 && args[0] == "--self-test";
            Dictionary<string,object> config;
            if (test) {
                string data = Path.GetFullPath(args[1]); Directory.CreateDirectory(data);
                config = new Dictionary<string,object> { {"endpoint","http://127.0.0.1:1"}, {"key","self-test"}, {"data",data}, {"profile",Path.Combine(data,"profile")}, {"show",false}, {"parent",0} };
            } else config = NativeWindow.Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(args[0]));
            Application.Run(new NativeWindow(config,test));
        } catch (Exception e) { Console.Error.WriteLine(e.Message); Environment.ExitCode=1; }
    }
}

sealed class NativeWindow : Form {
    internal static readonly JavaScriptSerializer Json = new JavaScriptSerializer { MaxJsonLength=64*1024*1024, RecursionLimit=256 };
    readonly Dictionary<string,object> config; readonly bool test;
    readonly WebView2 web = new WebView2(); readonly Label caption = new Label();
    readonly HttpClient http = new HttpClient(new HttpClientHandler { AllowAutoRedirect=false });
    readonly Timer timer = new Timer(); readonly Dictionary<string,TaskCompletionSource<Dictionary<string,object>>> calls = new Dictionary<string,TaskCompletionSource<Dictionary<string,object>>>();
    readonly string data, client = "native-"+Guid.NewGuid().ToString("N");
    bool busy, ready, quitting, allowVisible, connected, authWanted=true, loginNavigated;
    int attempts, transportErrors; DateTime next=DateTime.MinValue, authAt=DateTime.MinValue;
    string phase="starting", error="", command="", nonce="";
    Dictionary<string,object> scope;
    internal NativeWindow(Dictionary<string,object> c,bool selfTest) {
        config=c; test=selfTest; data=TextOf(c,"data"); allowVisible=Flag(c,"show");
        Uri endpoint = new Uri(TextOf(c,"endpoint"));
        if (endpoint.Scheme!="http" || (endpoint.Host!="127.0.0.1" && endpoint.Host!="localhost")) throw new Exception("Connection endpoint must be local");
        http.BaseAddress=endpoint; http.Timeout=TimeSpan.FromSeconds(20); http.DefaultRequestHeaders.Add("X-Viewer-Connection",TextOf(c,"key"));
        Text="ChatGPT sign-in · Offline Chat Viewer"; Width=1080; Height=820; MinimumSize=new Size(640,480); StartPosition=FormStartPosition.CenterScreen;
        BackColor=Color.FromArgb(23,26,33); ForeColor=Color.White; Icon=SystemIcons.Application;
        caption.Dock=DockStyle.Top;caption.Height=42;caption.Padding=new Padding(14,12,0,0);caption.ForeColor=Color.Gainsboro;caption.BackColor=BackColor;caption.Text="Connecting to ChatGPT…";
        web.Dock=DockStyle.Fill;web.DefaultBackgroundColor=Color.FromArgb(23,26,33);Controls.Add(web);Controls.Add(caption);
        timer.Interval=1500;timer.Tick+=async delegate { await Tick(); };
        FormClosing+=delegate(object sender,FormClosingEventArgs e) { if (!quitting && connected) { e.Cancel=true;Hide();allowVisible=false; } else { quitting=true;State("disconnected","Sign-in window closed. Select Connect to try again."); } };
        var handle=Handle;BeginInvoke(new Action(async delegate { await Start(); }));
    }
    protected override void SetVisibleCore(bool value) { base.SetVisibleCore(value && allowVisible); }
    static string TextOf(Dictionary<string,object> d,string key) { object v;return d.TryGetValue(key,out v) && v!=null?Convert.ToString(v):""; }
    static bool Flag(Dictionary<string,object> d,string key) { object v;return d.TryGetValue(key,out v) && v is bool && (bool)v; }
    static Dictionary<string,object> Dict(Dictionary<string,object> d,string key) { object v;return d.TryGetValue(key,out v)?v as Dictionary<string,object>:null; }
    static int Status(Dictionary<string,object> d) { object v;return d.TryGetValue("status",out v)&&v!=null?Convert.ToInt32(v):0; }
    bool ChatGPT() { Uri u;return Uri.TryCreate(web.Source==null?"":web.Source.AbsoluteUri,UriKind.Absolute,out u)&&u.Scheme=="https"&&u.Host=="chatgpt.com"; }
    static bool LoginOrigin(string address) {
        Uri u;if(!Uri.TryCreate(address,UriKind.Absolute,out u)||u.Scheme!="https")return false;
        return u.Host=="chatgpt.com" || u.Host=="auth.openai.com" || u.Host=="auth0.openai.com" || u.Host=="accounts.google.com" || u.Host=="login.microsoftonline.com" || u.Host=="login.live.com" || u.Host=="appleid.apple.com" || u.Host=="challenges.cloudflare.com";
    }
    void Atomic(string name,object value) {
        Directory.CreateDirectory(data);string path=Path.Combine(data,name),temp=path+".tmp";
        File.WriteAllText(temp,Json.Serialize(value));if(File.Exists(path))File.Replace(temp,path,null);else File.Move(temp,path);
    }
    void State(string value,string detail) {
        phase=value;error=detail;caption.Text=value=="connected"?"Connected · you can close this window and keep using the viewer":value=="sign-in"?"Sign in to ChatGPT here. Return to the viewer when connected.":detail.Length>0?detail:"Connecting to ChatGPT…";
        Atomic("native-connection-state.json",new {phase=phase,error=error,attempts=attempts,updated=DateTimeOffset.UtcNow.ToUnixTimeSeconds(),pid=System.Diagnostics.Process.GetCurrentProcess().Id});
    }
    void Reveal() { allowVisible=true;Show();WindowState=FormWindowState.Normal;Activate(); }
    async Task Start() {
        try {
            State("starting","");
            // WinForms initializes WebView2 only with a visible parent. An invisible
            // first frame initializes remembered sessions without flashing a window.
            bool initialVisible=allowVisible;
            if(!initialVisible){allowVisible=true;Opacity=0;ShowInTaskbar=false;Show();}
            var creating=CoreWebView2Environment.CreateAsync(null,TextOf(config,"profile"));
            if(await Task.WhenAny(creating,Task.Delay(20000))!=creating)throw new Exception("Native sign-in did not start. Select Connect to retry.");
            CoreWebView2Environment env=await creating;var initializing=web.EnsureCoreWebView2Async(env);
            if(await Task.WhenAny(initializing,Task.Delay(20000))!=initializing)throw new Exception("Native sign-in did not initialize. Select Connect to retry.");
            await initializing;ready=true;
            web.CoreWebView2.Settings.AreDevToolsEnabled=false;web.CoreWebView2.Settings.IsStatusBarEnabled=false;
            web.CoreWebView2.NavigationStarting+=delegate(object sender,CoreWebView2NavigationStartingEventArgs e) {
                if(!test && !LoginOrigin(e.Uri))e.Cancel=true;
                foreach(var call in calls.Values)call.TrySetResult(new Dictionary<string,object>{{"ok",false},{"status",0},{"error","Page changed; checking outcome before retry"}});calls.Clear();
            };
            web.CoreWebView2.NavigationCompleted+=delegate { authWanted=true; };
            web.CoreWebView2.SourceChanged+=delegate { authWanted=true; };
            web.CoreWebView2.NewWindowRequested+=async delegate(object sender,CoreWebView2NewWindowRequestedEventArgs e) {
                e.Handled=true;if(!LoginOrigin(e.Uri))return;var deferral=e.GetDeferral();var popup=new Form {Text="ChatGPT sign-in",Width=800,Height=720,StartPosition=FormStartPosition.CenterParent};
                var child=new WebView2 {Dock=DockStyle.Fill};popup.Controls.Add(child);popup.Show(this);
                try { await child.EnsureCoreWebView2Async(env);child.CoreWebView2.NavigationStarting+=delegate(object s,CoreWebView2NavigationStartingEventArgs n){if(!LoginOrigin(n.Uri))n.Cancel=true;};child.CoreWebView2.WindowCloseRequested+=delegate{popup.Close();authWanted=true;};e.NewWindow=child.CoreWebView2; } finally { deferral.Complete(); }
            };
            web.CoreWebView2.WebMessageReceived+=delegate(object sender,CoreWebView2WebMessageReceivedEventArgs e) {
                if(!test && (!ChatGPT() || !e.Source.StartsWith("https://chatgpt.com/",StringComparison.Ordinal)))return;
                try { var message=Json.Deserialize<Dictionary<string,object>>(e.WebMessageAsJson);string id=TextOf(message,"id");TaskCompletionSource<Dictionary<string,object>> call;if(calls.TryGetValue(id,out call)){calls.Remove(id);call.TrySetResult(Dict(message,"result")??new Dictionary<string,object>());} } catch(ArgumentException) { }
            };
            string bridge=Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"..","..","integration","browser-companion","bridge.js"));
            await web.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync("if(location.origin==='https://chatgpt.com'){"+File.ReadAllText(bridge)+"}");
            if(test){await SelfTest();return;}
            if(!initialVisible){Hide();allowVisible=false;Opacity=1;ShowInTaskbar=true;}
            web.CoreWebView2.Navigate("https://chatgpt.com/");timer.Start();
        } catch(Exception e) { State("error",e is WebView2RuntimeNotFoundException?"Microsoft Edge WebView2 Runtime is missing.":e.Message);Environment.ExitCode=1;if(test){Atomic("self-test.json",new {ok=false,error=e.ToString()});Quit();} }
    }
    async Task<Dictionary<string,object>> Page(object args) {
        if(!test&&!ChatGPT())return new Dictionary<string,object>{{"ok",false},{"status",401},{"error","Sign in to ChatGPT"}};
        string id=Guid.NewGuid().ToString("N");var call=new TaskCompletionSource<Dictionary<string,object>>();calls[id]=call;
        string script="(async()=>{let result;try{result=window.__offlineViewerConnection?await window.__offlineViewerConnection.rpc("+Json.Serialize(args)+"):{ok:false,status:0,error:'Waiting for ChatGPT to load'};}catch(e){result={ok:false,status:0,error:e.message};}window.chrome.webview.postMessage({id:"+Json.Serialize(id)+",result});})()";
        try { await web.CoreWebView2.ExecuteScriptAsync(script);if(await Task.WhenAny(call.Task,Task.Delay(65000))!=call.Task)return new Dictionary<string,object>{{"ok",false},{"status",0},{"error","ChatGPT request timed out; checking outcome before retry"}};return await call.Task; } finally {calls.Remove(id);}
    }
    async Task<Dictionary<string,object>> Post(string op,object body) {
        using(var content=new StringContent(Json.Serialize(body),System.Text.Encoding.UTF8,"application/json"))using(var response=await http.PostAsync("/api/companion/"+op,content)) {
            response.EnsureSuccessStatusCode();return Json.Deserialize<Dictionary<string,object>>(await response.Content.ReadAsStringAsync());
        }
    }
    object Heartbeat(bool only) { return new {client=client,kind="native",connected=connected,scope=scope,heartbeat=only,connection=new {attempts=attempts,blocked=phase=="blocked",error=error,phase=phase}}; }
    void Failure(string detail) { connected=false;attempts++;next=DateTime.UtcNow.AddSeconds(5*Math.Pow(2,attempts-1));State(attempts>=3?"blocked":"starting",attempts>=3?"Connection paused. Select Connect to retry. "+detail:detail); }
    async Task Tick() {
        if(busy||!ready||quitting)return;busy=true;
        try {
            string control=Path.Combine(data,"native-connection-control.json");
            if(File.Exists(control)) {var c=Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(control));string id=TextOf(c,"id");if(id!=command){command=id;if(Flag(c,"stop")){Quit();return;}if(Flag(c,"show")){Reveal();}if(Flag(c,"reset")){attempts=0;connected=false;scope=null;authWanted=true;loginNavigated=false;next=DateTime.MinValue;State("starting","");}}}
            int parent=Convert.ToInt32(config["parent"]);if(parent>0)try{if(System.Diagnostics.Process.GetProcessById(parent).HasExited){Quit();return;}}catch(ArgumentException){Quit();return;}
            var hello=await Post("poll",Heartbeat(true));transportErrors=0;
            string fresh=TextOf(hello,"nonce");if(nonce.Length>0&&fresh!=nonce){attempts=0;scope=null;connected=false;authWanted=true;next=DateTime.MinValue;State("starting","");}nonce=fresh;
            if(phase=="blocked"||phase=="error"||DateTime.UtcNow<next)return;
            if(!ChatGPT()) {connected=false;State("sign-in","");return;}
            if(!connected && phase=="sign-in" && !authWanted)return;
            if(authWanted || !connected || (DateTime.UtcNow-authAt).TotalSeconds>35) {
                authWanted=false;var context=await Page(new {op="context"});
                if(!Flag(context,"ok")) {
                    if(Status(context)==401) { connected=false;State("sign-in","");if(!loginNavigated){loginNavigated=true;web.CoreWebView2.Navigate("https://chatgpt.com/auth/login");}return; }
                    Failure(TextOf(context,"error"));return;
                }
                var candidate=Dict(context,"scope");if(candidate==null){Failure("ChatGPT did not return an authenticated account");return;}
                if(scope!=null&&Json.Serialize(candidate)!=Json.Serialize(scope)){connected=false;State("blocked","Account changed. Select Connect to review the new session.");return;}
                bool justConnected=!connected;scope=candidate;connected=true;attempts=0;authAt=DateTime.UtcNow;State("connected","");
                if(justConnected){Hide();allowVisible=false;}
            }
            var response=await Post("poll",Heartbeat(false));var request=Dict(response,"request");
            double wait=15;object delay;if(response.TryGetValue("wait",out delay))wait=Convert.ToDouble(delay);next=DateTime.UtcNow.AddSeconds(Math.Max(1,Math.Min(15,wait)));
            if(request==null)return;
            request["client"]=client;var permit=await Post("permit",request);
            var result=Flag(permit,"allowed")?await Page(request):new Dictionary<string,object>{{"ok",false},{"status",409},{"error","Queue paused before request"}};
            request["result"]=result;await Post("result",request);next=DateTime.UtcNow.AddSeconds(1.5);
            if(Flag(permit,"allowed")&&(Status(result)==401||Status(result)==403||Status(result)==409)){authWanted=true;Failure(TextOf(result,"error"));}
        } catch(Exception e) {transportErrors++;connected=false;authWanted=true;next=DateTime.UtcNow.AddSeconds(5);State(transportErrors>=3?"error":"starting","Viewer connection interrupted: "+e.Message);if(transportErrors>=3)Quit();}
        finally {busy=false;}
    }
    async Task SelfTest() {
        var loaded=new TaskCompletionSource<bool>();EventHandler<CoreWebView2NavigationCompletedEventArgs> handler=delegate(object s,CoreWebView2NavigationCompletedEventArgs e){loaded.TrySetResult(e.IsSuccess);};
        web.CoreWebView2.NavigationCompleted+=handler;web.CoreWebView2.NavigateToString("<html><body style='background:#171a21;color:white;font:20px sans-serif;padding:32px'><h1>Native connection</h1><p>Offline asynchronous RPC check.</p><script>window.__offlineViewerConnection={rpc:async a=>{await new Promise(r=>setTimeout(r,10));return {ok:true,scope:{user:'offline-fixture',account:null},value:a.value}}}</script></body></html>");
        if(await Task.WhenAny(loaded.Task,Task.Delay(15000))!=loaded.Task||!await loaded.Task)throw new Exception("Native page failed to initialize");
        var r=await Page(new {op="context",value="round-trip"});if(!Flag(r,"ok")||TextOf(r,"value")!="round-trip")throw new Exception("Asynchronous native RPC failed");
        using(var image=File.Create(Path.Combine(data,"native-self-test.png")))await web.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png,image);
        Atomic("self-test.json",new {ok=true,asyncRpc=true,runtime=web.CoreWebView2.Environment.BrowserVersionString,extensionRequired=false,profile=TextOf(config,"profile")});Quit();
    }
    void Quit() {quitting=true;timer.Stop();Close();Application.ExitThread();}
    protected override void Dispose(bool disposing) {if(disposing){timer.Dispose();http.Dispose();web.Dispose();}base.Dispose(disposing);}
}
