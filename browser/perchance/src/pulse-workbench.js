window.WB={};
WB.market="crypto";
WB.provider="auto";
WB.activeVenue=null;
WB.gen=0;
WB.cache=new Map();
WB.errCount=0;
WB.autoStop=false;
WB.stocks=["SPY","QQQ","AAPL","MSFT","NVDA"];
WB.cryptoWatch=null;
WB.stockWatch=null;
WB.csvData=null;
WB.csvMeta=null;
WB.liveCandle=null;
WB.normMeta=null;
WB.view={count:0,end:0};
WB.fc={engine:"kronos-local",model:"kronos-mini",lookback:256,displayHistory:200,horizon:24,temp:1.0,top_p:0.9,samples:1,endpoint:"",status:"idle",result:null,elapsed:0,busy:false,abort:false,stale:false,readyNote:""};
WB.ind={mas:[{type:"SMA",period:20,src:"close",color:"#f59e0b",width:1.4,on:true},{type:"SMA",period:50,src:"close",color:"#22d3ee",width:1.4,on:true},{type:"SMA",period:200,src:"close",color:"#a78bfa",width:1.4,on:true},{type:"EMA",period:12,src:"close",color:"#22c55e",width:1.4,on:true},{type:"EMA",period:26,src:"close",color:"#ef4444",width:1.4,on:true}],bb:{on:false,period:20,mult:2,color:"#eab308"},rsi:{on:false,period:14},macd:{on:false,fast:12,slow:26,signal:9},vwap:{on:false},proj:false,gaps:true,lineMode:false,fcShow:true,fcUp:"#22d3ee",fcDn:"#f0abfc",grid:true,theme:"dark"};
WB.presets=[];
WB.TFMS={"1m":60000,"5m":300000,"15m":900000,"1h":3600000,"4h":14400000,"1d":86400000,"1w":604800000};
WB.MODEL_LIMIT={"kronos-base":512,"kronos-small":512,"kronos-mini":2048};WB.BROWSER_LIMIT={"kronos-mini":{lookback:256,horizon:24,samples:1},"kronos-small":{lookback:128,horizon:24,samples:1},"kronos-base":{lookback:128,horizon:24,samples:1}};
WB.HORIZON_LIMIT={"kronos-base":120,"kronos-small":120,"kronos-mini":240,"statistical":120};
WB.capNote=function(){
if(WB.market==="crypto")return "Crypto venues: Binance/OKX/Bybit spot. Intraday 1m/5m/15m/1h/4h + 1d/1w. Forecasts run UTC through weekends.";
if(WB.provider==="csv")return "CSV import: resolutions come from your file. Daily files support 1d/1w only. Intraday files support 1h/4h when smaller completed bars exist.";
return "Yahoo Finance: free 1d/1w + 1h (regular session, delayed), 4h aggregated from 1h (anchor 09:30 ET). Stooq daily fallback. Intraday 1m/5m/15m via CSV import.";
};
WB.okxBar=function(tf){var m={"1m":"1m","5m":"5m","15m":"15m","1h":"1H","4h":"4H","1d":"1D","1w":"1W"};return m[tf]||null};
WB.bybitIv=function(tf){var m={"1m":"1","5m":"5","15m":"15","1h":"60","4h":"240","1d":"D","1w":"W"};return m[tf]||null};
WB.stooqSym=function(s){return String(s||"").toLowerCase().replace(/[^a-z0-9.\-]/g,"")+".us".replace(".us.us",".us")};
WB.toOkxInst=function(sym){var b=String(sym).replace(/USDT$/,"");return b+"-USDT"};
WB.freshLabel=function(ts,limit){if(ts==null)return "UNAVAILABLE";var a=Date.now()-ts;if(a<0)a=0;if(a>limit)return "STALE "+Math.round(a/1000)+"s";return "LIVE "+Math.round(a/1000)+"s"};
WB.validNum=function(x){return typeof x==="number"&&isFinite(x)};
WB.normOne=function(o){
if(!o||!WB.validNum(o.o)||!WB.validNum(o.h)||!WB.validNum(o.l)||!WB.validNum(o.c))return null;
if(!(o.h>=o.l))return null;
var mx=Math.max(o.o,o.c),mn=Math.min(o.o,o.c);
if(o.h+1e-12<mx)return null;
if(o.l-1e-12>mn)return null;
if(o.vBase!=null&&!(o.vBase>=0&&isFinite(o.vBase)))return null;
if(o.turnover!=null&&!(o.turnover>=0&&isFinite(o.turnover)))return null;
return o;
};
WB.sortDedupe=function(arr){
var seen={},out=[];
arr.sort(function(a,b){return a.t-b.t});
for(var i=0;i<arr.length;i++){var k=arr[i];if(k==null||!isFinite(k.t))continue;var key=String(k.t);if(seen[key])continue;seen[key]=1;var v=WB.normOne(k);if(v)out.push(v)}
return out;
};
WB.parseBinance=function(raw,meta){
var out=[],live=null,now=Date.now();
for(var i=0;i<raw.length;i++){var k=raw[i];if(!k||k.length<6)continue;
var t=+k[0],ct=k[6]!=null?+k[6]:t+WB.TFMS[meta.tf]-1;
var o={t:t,tEnd:t+WB.TFMS[meta.tf],o:+k[1],h:+k[2],l:+k[3],c:+k[4],vBase:+k[5],turnover:+k[7],takerBuy:k[9]!=null?+k[9]:null,venue:"Binance spot",market:meta.market,symbol:meta.symbol,quote:"USDT",timeframe:meta.tf,timezone:"UTC",session:"24x7",retrievedAt:now,complete:ct<=now};
if(meta.tf==="1d"){var d=new Date(t);o.t=Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),d.getUTCDate());o.tEnd=o.t+86400000}
if(!o.complete){live=o;continue}
out.push(o)}
return {bars:WB.sortDedupe(out),live:live};
};
WB.parseOkx=function(raw,meta){
var out=[],live=null,now=Date.now();
var arr=Array.isArray(raw)?raw.slice():[];
for(var i=0;i<arr.length;i++){var k=arr[i];if(!k||k.length<6)continue;
var t=+k[0],conf=k[8];
var o={t:t,tEnd:t+WB.TFMS[meta.tf],o:+k[1],h:+k[2],l:+k[3],c:+k[4],vBase:+k[5],turnover:k[7]!=null?+k[7]:null,venue:"OKX spot",market:meta.market,symbol:meta.symbol,quote:"USDT",timeframe:meta.tf,timezone:"UTC",session:"24x7",retrievedAt:now,complete:String(conf)==="1"};
if(meta.tf==="1d"){var d=new Date(t);var u=Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),d.getUTCDate());o.t=u;o.tEnd=u+86400000}
if(arr.length>=2&&i===arr.length-1&&String(conf)!=="1"){live=o;continue}
if(!o.complete&&i===arr.length-1){live=o;continue}
if(o.complete)out.push(o);else out.push(o)}
var ded=WB.sortDedupe(out);
var last=ded[ded.length-1];
if(last&&last.tEnd>now){ded.pop();live=last}
return {bars:ded,live:live};
};
WB.parseBybit=function(raw,meta){
var out=[],live=null,now=Date.now(),ms=WB.TFMS[meta.tf];
for(var i=0;i<raw.length;i++){var k=raw[i];if(!k||k.length<5)continue;
var t=+k[0];
var o={t:t,tEnd:t+ms,o:+k[1],h:+k[2],l:+k[3],c:+k[4],vBase:+k[5],turnover:+k[6],venue:"Bybit spot",market:meta.market,symbol:meta.symbol,quote:"USDT",timeframe:meta.tf,timezone:"UTC",session:"24x7",retrievedAt:now,complete:(t+ms)<=now};
if(meta.tf==="1d"){var d=new Date(t);o.t=Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),d.getUTCDate());o.tEnd=o.t+86400000;o.complete=o.tEnd<=now}
if(!o.complete){if(i===raw.length-1||o.tEnd>now){live=o;continue}}
out.push(o)}
var ded=WB.sortDedupe(out);
var lt=ded[ded.length-1];
if(lt&&lt.tEnd>now){ded.pop();live=lt}
return {bars:ded,live:live};
};
WB.parseStooqDaily=function(text,meta){
var lines=String(text||"").trim().split("\n");
if(lines.length<2)return {bars:[],live:null,error:"empty csv"};
var head=lines[0].toLowerCase();
var di=head.indexOf("date"),oi=head.indexOf("open"),hi=head.indexOf("high"),li=head.indexOf("low"),ci=head.indexOf("close"),vi=head.indexOf("volume");
if(di<0||oi<0||hi<0||ci<0)return {bars:[],live:null,error:"missing columns"};
var out=[],now=Date.now();
for(var i=1;i<lines.length;i++){var p=lines[i].split(",");if(p.length<5)continue;
var ds=p[di].trim();if(!ds||ds.toLowerCase()==="null")continue;
var m=ds.match(/(\d{4})-(\d{2})-(\d{2})/);if(!m)continue;
var t=Date.UTC(+m[1],+m[2]-1,+m[3]);
var o={t:t,tEnd:t+86400000,o:parseFloat(p[oi]),h:parseFloat(p[hi]),l:parseFloat(p[li]),c:parseFloat(p[ci]),vBase:p[vi]!=null?parseFloat(p[vi]):null,turnover:null,venue:"Stooq daily",market:"stocks",symbol:meta.symbol,quote:"USD",timeframe:meta.tf==="1w"?"1w":"1d",timezone:"America/New_York",session:"regular",retrievedAt:now,complete:true,adjustedNote:"Stooq daily is split/dividend adjusted"};
if(!WB.validNum(o.o)||!WB.validNum(o.h)||!WB.validNum(o.l)||!WB.validNum(o.c))continue;
out.push(o)}
var ded=WB.sortDedupe(out);
if(meta.tf==="1w"){ded=WB.resampleWeekly(ded)}
return {bars:ded,live:null};
};
WB.resampleWeekly=function(daily){
var out=[],cur=null;
for(var i=0;i<daily.length;i++){var b=daily[i];var d=new Date(b.t);var dow=(d.getUTCDay()+6)%7;
if(!cur||dow===0&&cur){if(cur)out.push(cur);cur={t:b.t,tEnd:b.tEnd,o:b.o,h:b.h,l:b.l,c:b.c,vBase:b.vBase||0,turnover:b.turnover,venue:b.venue,market:b.market,symbol:b.symbol,quote:b.quote,timeframe:"1w",timezone:b.timezone,session:b.session,retrievedAt:b.retrievedAt,complete:true}}
if(cur){cur.h=Math.max(cur.h,b.h);cur.l=Math.min(cur.l,b.l);cur.c=b.c;cur.tEnd=b.tEnd;cur.vBase=(cur.vBase||0)+(b.vBase||0)}}
if(cur)out.push(cur);
return WB.sortDedupe(out);
};
WB.parseUserCsv=function(text,meta){
var lines=String(text||"").trim().split("\n").filter(function(l){return l.trim().length});
if(lines.length<2)return {bars:[],live:null,error:"empty csv"};
var head=lines[0].toLowerCase().split(/[,;]/).map(function(s){return s.trim()});
function col(names){for(var i=0;i<names.length;i++){var j=head.indexOf(names[i]);if(j>=0)return j}return -1}
var ti=col(["timestamp","time","datetime","date","t"]);var oi=col(["open","o"]);var hi=col(["high","h"]);var li=col(["low","l"]);var ci=col(["close","c"]);var vi=col(["volume","vol","v","base_volume"]);
if(ti<0||oi<0||hi<0||li<0||ci<0)return {bars:[],live:null,error:"need timestamp,open,high,low,close columns"};
var ms=WB.TFMS[meta.tf]||86400000;
var out=[],now=Date.now();
for(var i=1;i<lines.length;i++){var p=lines[i].split(/[,;]/);if(p.length<5)continue;
var ts=String(p[ti]).trim();var t=Date.parse(ts);
if(!isFinite(t)){var n=parseFloat(ts);if(isFinite(n)){t=n<1e12?n*1000:n}}
if(!isFinite(t))continue;
var o={t:t,tEnd:t+ms,o:parseFloat(p[oi]),h:parseFloat(p[hi]),l:parseFloat(p[li]),c:parseFloat(p[ci]),vBase:vi>=0?parseFloat(p[vi]):null,turnover:null,venue:"CSV import",market:meta.market,symbol:meta.symbol,quote:meta.market==="stocks"?"USD":"USDT",timeframe:meta.tf,timezone:(WB.csvMeta&&WB.csvMeta.timezone)||"UTC",session:(WB.csvMeta&&WB.csvMeta.session)||"mixed",retrievedAt:now,complete:true,adjustedNote:(WB.csvMeta&&WB.csvMeta.adjusted)||"as-imported"};
if(!WB.validNum(o.o)||!WB.validNum(o.h)||!WB.validNum(o.l)||!WB.validNum(o.c))continue;
out.push(o)}
return {bars:WB.sortDedupe(out),live:null};
};
WB.nyHolidays=function(y){
var f=[y+"-01-01",y+"-07-04",y+"-12-25"];
var extra={"2024":["2024-01-15","2024-02-19","2024-03-29","2024-05-27","2024-06-19","2024-09-02","2024-11-28","2024-12-25"],"2025":["2025-01-01","2025-01-09","2025-01-20","2025-02-17","2025-04-18","2025-05-26","2025-06-19","2025-07-04","2025-09-01","2025-11-27","2025-12-25"],"2026":["2026-01-01","2026-01-19","2026-02-16","2026-04-03","2026-05-25","2026-06-19","2026-07-03","2026-09-07","2026-11-26","2026-12-25"],"2027":["2027-01-01","2027-01-18","2027-02-15","2027-03-26","2027-05-31","2027-06-18","2027-07-05","2027-09-06","2027-11-25","2027-12-24"],"2028":["2028-01-03","2028-01-17","2028-02-21","2028-04-14","2028-05-29","2028-06-19","2028-07-04","2028-09-04","2028-11-23","2028-12-25"]};
return extra[String(y)]||f;
};
WB.nyEarly=function(){return ["2024-11-29","2024-12-24","2025-07-03","2025-11-28","2025-12-24","2026-11-27","2026-11-28","2026-12-24"]};
WB.etDay=function(ms){
try{var p=new Intl.DateTimeFormat("en-CA",{timeZone:"America/New_York",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date(ms));return p}catch(e){var d=new Date(ms);return d.getUTCFullYear()+"-"+String(d.getUTCMonth()+1).padStart(2,"0")+"-"+String(d.getUTCDate()).padStart(2,"0")}
};
WB.isTradingDay=function(ms){
var ds=WB.etDay(ms);var y=+ds.slice(0,4);
var h=WB.nyHolidays(y);if(h.indexOf(ds)>=0)return false;
var d=new Date(ds+"T12:00:00Z");var d2=new Date(ms);
try{var wd=new Intl.DateTimeFormat("en-US",{timeZone:"America/New_York",weekday:"short"}).format(new Date(ms));if(wd==="Sat"||wd==="Sun")return false}catch(e){if(d2.getUTCDay()===0||d2.getUTCDay()===6)return false}
return true;
};
WB.nextTradingDays=function(fromMs,n){
var out=[],t=fromMs+86400000,guard=0;
while(out.length<n&&guard<n*10+20){var ds=WB.etDay(t);var noon=Date.parse(ds+"T16:00:00-05:00");
if(WB.isTradingDay(t)){out.push(Date.parse(ds+"T00:00:00-05:00")||t)}
t+=86400000;guard++}
return out;
};
WB.futureTimes=function(lastT,tf,market,n){
var out=[],ms=WB.TFMS[tf]||86400000;
if(market==="crypto"){for(var i=1;i<=n;i++)out.push(lastT+i*ms);return out}
if(tf==="1d"||tf==="1w"){if(tf==="1w"){for(var w=1;w<=n;w++)out.push(lastT+w*7*86400000);return out}return WB.nextTradingDays(lastT,n)}
if(tf==="1h"||tf==="4h"){
var slots=tf==="1h"?[9,10,11,12,13,14,15]:[9,13];
var t=lastT+3600000,guard=0;
while(out.length<n&&guard<n*40+100){
var ds=WB.etDay(t);
if(WB.isTradingDay(t)){
var hr=0;try{hr=+new Intl.DateTimeFormat("en-US",{timeZone:"America/New_York",hour:"numeric",hour12:false}).format(new Date(t))}catch(e){hr=new Date(t).getUTCHours()}
if(slots.indexOf(hr)>=0)out.push(t);
}
t+=3600000;guard++}
if(out.length) return out;
for(var j=1;j<=n;j++)out.push(lastT+j*ms);
return out}
for(var k=1;k<=n;k++)out.push(lastT+k*ms);
return out;
};
WB.horizonLabel=function(){
var tf=state.tf,n=WB.fc.horizon;
if(WB.market==="stocks"&&(state.tf==="1d"))return n+" daily stock bars = "+n+" trading sessions";
if(WB.market==="stocks"&&state.tf==="1w")return n+" weekly bars = "+n+" weeks";
var ms=WB.TFMS[state.tf]||3600000;var hrs=ms*n/3600000;
if(hrs<48)return n+" "+state.tf+" crypto candles = "+hrs+" hours";
return n+" "+state.tf+" candles";
};
WB.cacheKey=function(){return WB.market+"|"+WB.provider+"|"+state.sym+"|"+state.tf+"|"+(WB.market==="stocks"?(WB.provider==="csv"?"csv":"stooq"):"spot")};
WB.fetchCryptoVenue=async function(venue,sym,tf,need){
var limit=venue==="okx"?100:1000;
var all=[],endMs=null,pages=0,maxP=Math.ceil(need/limit)+1;
if(maxP>8)maxP=8;
while(all.length<need&&pages<maxP){
var url="";
if(venue==="binance"){var b=state._pxBase||"https://data-api.binance.vision";url=b+"/api/v3/klines?symbol="+encodeURIComponent(sym)+"&interval="+encodeURIComponent(tf)+"&limit="+Math.min(limit,need);if(endMs)url+="&endTime="+endMs}
if(venue==="okx"){var inst=WB.toOkxInst(sym);var bar=WB.okxBar(tf);url="https://www.okx.com/api/v5/market/history-candles?instId="+encodeURIComponent(inst)+"&bar="+bar+"&limit="+Math.min(limit,need);if(endMs)url+="&after="+(endMs)}
if(venue==="bybit"){var iv=WB.bybitIv(tf);url="https://api.bybit.com/v5/market/kline?category=spot&symbol="+encodeURIComponent(sym)+"&interval="+iv+"&limit="+Math.min(limit,need);if(endMs)url+="&end="+endMs}
var r=await jget(url,18000);
var list=null;
if(venue==="binance"&&Array.isArray(r)&&r.length)list=r;
if(venue==="okx"&&r&&r.code==="0"&&Array.isArray(r.data)&&r.data.length)list=r.data;
if(venue==="bybit"&&r&&r.result&&Array.isArray(r.result.list)&&r.result.list.length)list=r.result.list;
if(!list||!list.length)break;
var meta={market:"crypto",symbol:sym,tf:tf};
var parsed=null;
if(venue==="binance")parsed=WB.parseBinance(list,meta);
if(venue==="okx")parsed=WB.parseOkx(list,meta);
if(venue==="bybit")parsed=WB.parseBybit(list,meta);
var bars=parsed.bars;
if(!bars.length)break;
all=bars.concat(all);
var oldest=all[0].t;
endMs=oldest-1;
pages++;
if(list.length<10)break;
if(all.length>=need)break;
}
all=WB.sortDedupe(all);
var tail=all.slice(-need);
var live=null;
if(all.length>tail.length)live=null;
return {bars:tail,venue:venue};
};
WB.fetchYahoo=async function(sym,tf){
var iv="1d",range="5y";
if(tf==="1w"){iv="1wk";range="10y"}
if(tf==="1h"){iv="60m";range="3mo"}
if(tf==="4h"){iv="60m";range="3mo"}
if(tf==="15m"){iv="15m";range="1mo"}
if(tf==="5m"){iv="5m";range="5d"}
if(tf==="1m"){iv="1m";range="2d"}
var url="https://query1.finance.yahoo.com/v8/finance/chart/"+encodeURIComponent(sym)+"?interval="+iv+"&range="+range+"&includePrePost=false&events=div%7Csplit";
var j=await jget(url,25000);
var r=j&&j.chart&&j.chart.result&&j.chart.result[0];
if(!r||!r.timestamp||!r.timestamp.length)throw new Error("yahoo empty for "+sym);
var q=r.indicators&&r.indicators.quote&&r.indicators.quote[0];
var ad=r.indicators&&r.indicators.adjclose&&r.indicators.adjclose[0]&&r.indicators.adjclose[0].adjclose;
if(!q)throw new Error("yahoo quote missing");
var now=Date.now(),out=[];
var stepMs=tf==="1d"?86400000:(tf==="1w"?7*86400000:(tf==="1h"||tf==="4h"?3600000:(tf==="15m"?900000:(tf==="5m"?300000:60000))));
for(var i=0;i<r.timestamp.length;i++){
var t=r.timestamp[i]*1000;
var o=q.open[i],h=q.high[i],l=q.low[i],c=q.close[i],v=q.volume[i];
if(o==null||h==null||l==null||c==null)continue;
var tEnd=t+stepMs;
if(tf==="1d"||tf==="1w"){var d=new Date(t);if(tf==="1d"){t=Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),d.getUTCDate());tEnd=t+86400000}}
out.push({t:t,tEnd:tEnd,o:o,h:h,l:l,c:c,vBase:v!=null?v:null,turnover:null,venue:"Yahoo Finance",market:"stocks",symbol:sym,quote:"USD",timeframe:tf==="4h"?"1h":tf,timezone:"America/New_York",session:"regular",retrievedAt:now,complete:tEnd<=now,adjustedNote:ad?"raw OHLC, adjclose available":"raw OHLC"})}
var ded=WB.sortDedupe(out);
if(tf==="4h"){ded=WB.agg4h(ded,sym)}
if(tf==="1w"&&ded.length&&ded[0].timeframe==="1w"){}
return {bars:ded,live:null};
};
WB.agg4h=function(hourly,sym){
var days={},order=[];
for(var i=0;i<hourly.length;i++){var b=hourly[i];if(!b.complete)continue;var ds=WB.etDay(b.t);if(!days[ds]){days[ds]=[];order.push(ds)}days[ds].push(b)}
var out=[];
for(var d=0;d<order.length;d++){var arr=days[order[d]].sort(function(a,b2){return a.t-b2.t});if(arr.length<3)continue;
var a1=arr.slice(0,4),a2=arr.slice(4);
function grp(g,idx){if(!g.length)return null;var o=g[0].o,c=g[g.length-1].c,h=Math.max.apply(null,g.map(function(x){return x.h})),l=Math.min.apply(null,g.map(function(x){return x.l})),v=g.reduce(function(s,x){return s+(x.vBase||0)},0);return {t:g[0].t,tEnd:g[g.length-1].tEnd,o:o,h:h,l:l,c:c,vBase:v,turnover:null,venue:"Yahoo Finance 4h agg",market:"stocks",symbol:sym,quote:"USD",timeframe:"4h",timezone:"America/New_York",session:"regular",retrievedAt:Date.now(),complete:true,adjustedNote:"aggregated from completed 1h bars, anchor 09:30 ET, partial final bar dropped"}}
var g1=grp(a1),g2=grp(a2);
if(g1)out.push(g1);if(g2)out.push(g2)}
return WB.sortDedupe(out);
};
WB.fetchStooq=async function(sym,tf){
var ss=WB.stooqSym(sym).replace(".us","");
var map={spy:"spy.us",qqq:"qqq.us",aapl:"aapl.us",msft:"msft.us",nvda:"nvda.us"};
var q=map[String(sym).toLowerCase()]||WB.stooqSym(sym);
var url="https://stooq.com/q/d/l/?s="+encodeURIComponent(q)+"&d1=20200101&d2=20301231&i=d";
var t=await sup(url,undefined,20000);
var txt=typeof t==="string"?t:"";
if(!txt||txt.indexOf("Date")<0)throw new Error("stooq empty for "+sym);
var meta={market:"stocks",symbol:sym,tf:tf};
return WB.parseStooqDaily(txt,meta);
};
WB.loadWorkbenchData=async function(){
var myGen=++WB.gen;
var need=Math.max(WB.fc.lookback,WB.fc.displayHistory,WB.ind.mas.reduce(function(a,m){return Math.max(a,m.period)},50))+60;
if(need>1200)need=1200;
if(WB.market==="stocks"&&WB.provider==="stooq"&&(state.tf==="1m"||state.tf==="5m"||state.tf==="15m"||state.tf==="1h"||state.tf==="4h")){
WB.normMeta={error:"stooq daily-only: "+state.tf+" unavailable. Use provider Yahoo for 1h/4h/1d/1w or CSV import."};
WB.renderWbStatus();
return false;
}
var key=WB.cacheKey();
var hit=WB.cache.get(key);
if(hit&&Date.now()-hit.ts<60000&&hit.bars.length){
if(myGen!==WB.gen)return false;
WB.applyNorm(hit,false);
return true;
}
WB.renderWbStatus("loading");
var venues=[];
if(WB.market==="crypto"){
if(WB.provider==="auto")venues=["binance","bybit","okx"];
else venues=[WB.provider];
}else{
if(WB.provider==="csv"){
if(!WB.csvData){WB.normMeta={error:"no CSV loaded"};WB.renderWbStatus();return false}
var pr=WB.parseUserCsv(WB.csvData,{market:"stocks",symbol:state.sym,tf:state.tf});
if(pr.error||!pr.bars.length){WB.normMeta={error:pr.error||"csv empty"};WB.renderWbStatus();return false}
if(myGen!==WB.gen)return false;
WB.applyNorm({bars:pr.bars,live:null,venue:"CSV import",meta:{timezone:(WB.csvMeta&&WB.csvMeta.timezone)||"UTC",session:(WB.csvMeta&&WB.csvMeta.session)||"mixed"}},true);
return true;
}else if(WB.provider==="yahoo"||WB.provider==="stooq")venues=[WB.provider];
else venues=["yahoo","stooq"];
}
var lastErr="";
for(var vi=0;vi<venues.length;vi++){
var v=venues[vi];
try{
var res=null;
if(v==="yahoo"){var yh=await WB.fetchYahoo(state.sym,state.tf);if(myGen!==WB.gen)return false;res={bars:yh.bars,live:yh.live,venue:"Yahoo Finance"}}
else if(v==="stooq"){var s=await WB.fetchStooq(state.sym,state.tf);if(myGen!==WB.gen)return false;res={bars:s.bars,live:s.live,venue:"Stooq daily"}}
else{res=await WB.fetchCryptoVenue(v,state.sym,state.tf,need)}
if(myGen!==WB.gen)return false;
if(res&&res.bars&&res.bars.length){
WB.activeVenue=v==="stooq"?"Stooq daily":(v==="yahoo"?"Yahoo Finance":(v==="binance"?"Binance spot":(v==="okx"?"OKX spot":"Bybit spot")));
WB.providerStay();
WB.applyNorm({bars:res.bars,live:res.live||null,venue:WB.activeVenue,meta:{}},true);
return true;
}else lastErr=v+": empty";
}catch(e){lastErr=v+": "+String((e&&e.message)||e).slice(0,90)}
}
if(myGen!==WB.gen)return false;
WB.normMeta={error:"all venues failed: "+lastErr+(WB.market==="crypto"?" (Binance geo-block/CORS possible; Bybit/OKX listing gaps possible)":"")};
WB.renderWbStatus();
return false;
};
WB.providerStay=function(){
try{var s=document.getElementById("wbProvSel");if(s&&WB.provider!=="auto")s.value=WB.provider;else if(s)s.value="auto"}catch(e){}
};
WB.applyNorm=function(res,isFresh){
var completed=res.bars||[];
if(completed.length>1200)completed=completed.slice(-1200);
var need2=Math.max(WB.fc.displayHistory,60);
var disp=completed.slice(-Math.min(completed.length,Math.max(need2,WB.fc.lookback+40)));
state.klines=disp.map(function(k){return {t:k.t,o:k.o,h:k.h,l:k.l,c:k.c,v:k.vBase||0,tb:k.takerBuy!=null?k.takerBuy:null}});
state.liveCandle=res.live||null;
WB.liveCandle=res.live||null;
WB.normMeta={venue:res.venue,count:completed.length,shown:disp.length,retrievedAt:Date.now(),tz:completed.length?(completed[0].timezone||"UTC"):"UTC",session:completed.length?(completed[0].session||""):"",quote:completed.length?(completed[0].quote||""):"",error:null,full:completed};
WB.fullBars=completed;
var cl=disp.map(function(k){return k.c});
state.sma20=sma(cl,20);state.sma50=sma(cl,50);state.sma200=sma(cl,Math.min(200,cl.length));
state.ema12=ema(cl,12);state.ema26=ema(cl,26);
state.delta=disp.map(function(k,idx){var kk=completed[completed.length-disp.length+idx];if(kk&&kk.takerBuy!=null&&kk.vBase!=null)return 2*kk.takerBuy-kk.vBase;var r=(k.h-k.l)||Math.abs(k.c-k.o)||1;return k.v*(k.c-k.o)/r});
var a=0;state.cvd=state.delta.map(function(d){a+=d;return a});
state.swing=swing(state.klines);
var up=state.swing.hiI>state.swing.loI;
state.fib=fibLevels(state.swing.hi,state.swing.lo,up);
state.sr=findSR(state.klines);
try{state.vp=vpLevels(state.klines)}catch(e){}
WB.view.count=disp.length;WB.view.end=disp.length;
WB.fc.stale=true;
try{WB.cache.set(WB.cacheKey(),{ts:Date.now(),bars:completed})}catch(e){}
try{renderStats();renderLevels();WB.drawFull();postChartIntel()}catch(e){try{draw()}catch(x){}}
WB.renderWbStatus();
WB.markFcStale();
WB.saveSel();
};
WB.saveSel=function(){
try{localStorage.setItem("pulse_wb_sel_v1",JSON.stringify({market:WB.market,provider:WB.provider,sym:state.sym,tf:state.tf,fc:{engine:WB.fc.engine,model:WB.fc.model,lookback:WB.fc.lookback,displayHistory:WB.fc.displayHistory,horizon:WB.fc.horizon,temp:WB.fc.temp,top_p:WB.fc.top_p,samples:WB.fc.samples},ind:WB.ind,viewCount:WB.view.count}))}catch(e){}
};
WB.loadSel=function(){
try{var s=JSON.parse(localStorage.getItem("pulse_wb_sel_v1")||"null");if(!s)return;
WB.market=s.market||"crypto";WB.provider=s.provider||"auto";
if(s.fc)for(var k in s.fc){if(k==="endpoint")continue;WB.fc[k]=s.fc[k];} if(WB.fc.engine==="kronos")WB.fc.engine="kronos-local"; if(WB.fc.model==="kronos-base"&&WB.fc.engine==="kronos-local")WB.fc.model="kronos-mini"; if(WB.fc.engine==="kronos-local"&&WB.fc.lookback>256)WB.fc.lookback=256;
if(s.ind)WB.ind=s.ind;
if(!WB.MODEL_LIMIT[WB.fc.model])WB.fc.model="kronos-mini";
}catch(e){}
};
WB.bb=function(close,period,mult){
var out={up:[],mid:[],lo:[]};
for(var i=0;i<close.length;i++){if(i<period-1){out.up.push(null);out.mid.push(null);out.lo.push(null);continue}
var w=close.slice(i-period+1,i+1);var m=w.reduce(function(x,y){return x+y},0)/period;var va=w.reduce(function(x,y){return x+(y-m)*(y-m)},0)/period;var sd=Math.sqrt(va);
out.mid.push(m);out.up.push(m+mult*sd);out.lo.push(m-mult*sd)}
return out;
};
WB.macdCalc=function(close,fast,slow,sig){
function ef(a,p){var k=2/(p+1),o=[],e=null;for(var i=0;i<a.length;i++){e=e==null?a[i]:a[i]*k+e*(1-k);o.push(i<p-1?null:e)}return o}
var f=ef(close,fast),s=ef(close,slow),m=close.map(function(_,i){return f[i]==null||s[i]==null?null:f[i]-s[i]});
var sg=[];var e2=null;for(var j=0;j<m.length;j++){if(m[j]==null){sg.push(null);continue}if(e2==null)e2=m[j];else e2=m[j]*(2/(sig+1))+e2*(1-2/(sig+1));sg.push(j<slow+sig-2?null:e2)}
return {macd:m,signal:sg};
};
WB.vwapCalc=function(ks,tf,market){
var out=new Array(ks.length).fill(null);
var pv=0,vv=0,curDay=null;
for(var i=0;i<ks.length;i++){var k=ks[i];
var day=null;
if(market==="stocks"){try{day=WB.etDay(k.t)}catch(e){day=new Date(k.t).toDateString()}}
else{var d=new Date(k.t);day=d.getUTCFullYear()+"-"+d.getUTCMonth()+"-"+d.getUTCDate()}
if(day!==curDay){curDay=day;pv=0;vv=0}
var tp=(k.h+k.l+k.c)/3;var v=k.v||0;pv+=tp*v;vv+=v;
out[i]=vv>0?pv/vv:null}
return out;
};
WB.maSeries=function(close,cfg){
var src=close;
var a=src;
if(cfg.type==="SMA"){var p=cfg.period;return a.map(function(_,i){return i<p-1?null:a.slice(i-p+1,i+1).reduce(function(x,y){return x+y},0)/p})}
var k=2/(cfg.period+1),o=new Array(a.length).fill(null),e=null;
for(var i=0;i<a.length;i++){e=e==null?a[i]:a[i]*k+e*(1-k);o[i]=i<cfg.period-1?null:e}
return o;
};
WB.statForecast=function(closes,horizon){
var n=Math.min(closes.length,96);
var lr=[];
for(var i=closes.length-n+1;i<closes.length;i++){if(closes[i-1]>0&&closes[i]>0)lr.push(Math.log(closes[i]/closes[i-1]))}
if(lr.length<5)return {error:"insufficient history for statistical forecast"};
var mean=lr.reduce(function(x,y){return x+y},0)/lr.length;
var va=lr.reduce(function(x,y){return x+(y-mean)*(y-mean)},0)/lr.length;
var sd=Math.sqrt(va);
var k=2/(12+1),e12=null;
for(var j=Math.max(0,closes.length-24);j<closes.length;j++){e12=e12==null?closes[j]:closes[j]*k+e12*(1-k)}
var last=closes[closes.length-1];
var out=[],lv=last;
for(var h=0;h<horizon;h++){var mr=(Math.log(e12/last))*0.15+mean*0.5;lv=lv*Math.exp(mr);out.push(lv)}
return {close:out,sd:sd,method:"statistical close-only: log-return drift (mean of last "+n+") blended with EMA12 mean-reversion (w=0.15); deterministic mean path, no sampled H/L/V"};
};
WB.fcKey=function(){return [WB.market,WB.provider,state.sym,state.tf,WB.fc.engine,WB.fc.model,WB.fc.lookback,WB.fc.horizon,WB.fc.temp,WB.fc.top_p,WB.fc.samples,(WB.fullBars||[]).length?WB.fullBars[WB.fullBars.length-1].t:"none"].join("|")};
WB.markFcStale=function(){
var el=document.getElementById("wbFcStatus");
if(WB.fc.result&&WB.fc.result.key!==WB.fcKey()){WB.fc.stale=true;if(el)el.innerHTML="<span class=y>stale — selection or parameters changed, regenerate</span>"}
};
WB.genForecast=async function(){
if(WB.fc.busy){WB.fc.abort=true;WB.renderWbStatus();return}
var lim=WB.fc.engine==="kronos-local"?(WB.BROWSER_LIMIT[WB.fc.model]||WB.BROWSER_LIMIT["kronos-mini"]).lookback:(WB.MODEL_LIMIT[WB.fc.model]||512);
var hlim=WB.fc.engine==="kronos-local"?(WB.BROWSER_LIMIT[WB.fc.model]||WB.BROWSER_LIMIT["kronos-mini"]).horizon:120;
if(WB.fc.lookback>lim){toast("lookback exceeds "+WB.fc.model+" limit "+lim);return}
if(WB.fc.horizon>hlim){toast("horizon exceeds limit "+hlim);return}
if(!WB.fullBars||WB.fullBars.length<10){toast("load data first");return}
var bars=WB.fullBars.slice(-WB.fc.lookback);
var forecastKey=WB.fcKey();
if(bars.length<WB.fc.lookback){toast("only "+bars.length+" bars available, need "+WB.fc.lookback);return}
WB.fc.busy=true;WB.fc.abort=false;WB.fc.status="running";
var t0=Date.now();
var timer=setInterval(function(){WB.fc.elapsed=(Date.now()-t0)/1000;var e=document.getElementById("wbElapsed");if(e)e.textContent=WB.fc.elapsed.toFixed(1)+"s"},100);
WB.renderFc();
try{
if(WB.fc.engine==="statistical"){
var closes=bars.map(function(b){return b.c});
var r=WB.statForecast(closes,WB.fc.horizon);
if(r.error)throw new Error(r.error);
var lastT=bars[bars.length-1].t;
var fts=WB.futureTimes(lastT,state.tf,WB.market,WB.fc.horizon);
var rows=[];
var prevC=bars[bars.length-1].c;
for(var i=0;i<WB.fc.horizon;i++){var c=r.close[i];
rows.push({i:i+1,t:fts[i],o:prevC,h:null,l:null,c:c,v:null,turnover:null,quality:"CLOSE-ONLY",method:r.method});
prevC=c}
WB.fc.result={engine:"statistical",label:"Statistical forecast",model:"stat-ema-drift/1",tokenizer:"n/a",settings:{lookback:WB.fc.lookback,horizon:WB.fc.horizon,temp:WB.fc.temp,top_p:WB.fc.top_p,samples:WB.fc.samples},anchorTime:bars[bars.length-1].t,generationTime:Date.now(),provider:WB.activeVenue||WB.provider,calendar:WB.market==="stocks"?"NYSE regular session":"UTC 24x7",rows:rows,provenance:{sourceBars:bars.length,venue:WB.activeVenue,dispersion:"none — single mean path"},key:WB.fcKey(),method:r.method};
WB.fc.stale=false;WB.fc.status="done";
}else{
if(!window.KronosLocal)throw new Error("local engine missing - refresh the page");
if(!KronosLocal.state.ready)throw new Error("local Kronos model not loaded - press Load model (load and smoke-test the model first)");
var bl=WB.BROWSER_LIMIT[WB.fc.model]||{lookback:256,horizon:24,samples:1};
if(WB.fc.lookback>bl.lookback)throw new Error(WB.fc.model+" browser default caps lookback at "+bl.lookback+" - lower it or benchmark first");
if(WB.fc.horizon>bl.horizon)throw new Error(WB.fc.model+" browser default caps horizon at "+bl.horizon);
if(WB.fc.samples>bl.samples)throw new Error(WB.fc.model+" browser default caps samples at "+bl.samples);
var pre=window.KronosPre?KronosPre.assemble6(bars):null;
if(!pre)throw new Error("preprocessor missing");
var ftsL=WB.futureTimes(bars[bars.length-1].t,state.tf,WB.market,WB.fc.horizon);
var seed=(Date.now()%2147483647);
var klReq={contract:"pulse-local-kronos/1",model:WB.fc.model,market:WB.market,symbol:state.sym,timeframe:state.tf,session:WB.market==="stocks"?"regular":"24x7",timezone:WB.market==="stocks"?"America/New_York":"UTC",lookback:WB.fc.lookback,horizon:WB.fc.horizon,temperature:WB.fc.temp,top_p:WB.fc.top_p,top_k:0,samples:WB.fc.samples,seed:seed,anchorTime:bars[bars.length-1].t,futureTimes:ftsL,candles:bars.map(function(b){return {t:b.t,o:b.o,h:b.h,l:b.l,c:b.c,v:b.vBase,turnover:b.turnover}}),timeMode:WB.market==="stocks"?"ET":"UTC"};
var klRes=await KronosLocal.predict(klReq,function(st){var el2=document.getElementById("wbElapsed");if(el2&&st.step!=null)el2.textContent=WB.fc.elapsed.toFixed(1)+"s · step "+st.step+"/"+st.of});
if(WB.fcKey()!==forecastKey)throw new Error("Selection or data changed while forecasting; regenerate for the current settings");
if(WB.fc.abort)throw new Error("cancelled");
if(!klRes||!klRes.rows||klRes.rows.length!==WB.fc.horizon)throw new Error("engine returned "+(klRes&&klRes.rows?klRes.rows.length:0)+" rows, expected "+WB.fc.horizon);
var rowsK=[];
for(var qk=0;qk<klRes.rows.length;qk++){var pk=klRes.rows[qk];var cc=pk.c!=null?+pk.c:null,oo=pk.o!=null?+pk.o:null,hh=pk.h!=null?+pk.h:null,ll=pk.l!=null?+pk.l:null,vv=pk.v!=null?+pk.v:null;var qual="OK";if(!WB.validNum(cc))qual="INVALID";else if(hh!=null&&ll!=null&&(hh<ll||hh<Math.max(oo,cc)-1e-9||ll>Math.min(oo,cc)+1e-9))qual="OHLC-FLAG";else if(vv!=null&&vv<0)qual="INVALID";rowsK.push({i:qk+1,t:klRes.times[qk],o:oo,h:hh,l:ll,c:cc,v:vv,turnover:pk.turnover!=null?+pk.turnover:null,quality:qual})}
WB.fc.result={engine:"kronos-local",label:"Kronos forecast (local WebGPU)",model:klRes.model||WB.fc.model,tokenizer:klRes.tokenizer||"Kronos-Tokenizer-2k",settings:{lookback:WB.fc.lookback,horizon:WB.fc.horizon,temp:WB.fc.temp,top_p:WB.fc.top_p,samples:WB.fc.samples,seed:seed},anchorTime:bars[bars.length-1].t,generationTime:Date.now(),provider:WB.activeVenue||WB.provider,calendar:WB.market==="stocks"?"NYSE regular session":"UTC 24x7",rows:rowsK,provenance:klRes.provenance||{backend:KronosLocal.state.backend},samples:klRes.sample_paths||null,key:WB.fcKey()};
WB.fc.stale=false;WB.fc.status="done";
}
}catch(e){
WB.fc.status="error";WB.fc.error=String((e&&e.message)||e).slice(0,300);
}
clearInterval(timer);
WB.fc.busy=false;WB.fc.elapsed=(Date.now()-t0)/1000;
WB.renderFc();WB.drawFull();WB.saveSel();
};
WB.fcCsv=function(){
if(!WB.fc.result)return "";
var h="row,start_iso,start_ms,timezone,open,high,low,close,volume,turnover,quality\n";
var tz=WB.market==="stocks"?"America/New_York":"UTC";
for(var i=0;i<WB.fc.result.rows.length;i++){var r=WB.fc.result.rows[i];
h+=(r.i+","+new Date(r.t).toISOString()+","+r.t+","+tz+","+(r.o==null?"":r.o)+","+(r.h==null?"":r.h)+","+(r.l==null?"":r.l)+","+(r.c==null?"":r.c)+","+(r.v==null?"":r.v)+","+(r.turnover==null?"":r.turnover)+","+r.quality+"\n")}
return h;
};
WB.fname=function(ext){
var d=new Date();function p(n){return String(n).padStart(2,"0")}
var s=d.getFullYear()+p(d.getMonth()+1)+p(d.getDate())+"-"+p(d.getHours())+p(d.getMinutes())+p(d.getSeconds());
var r=Math.random().toString(36).slice(2,7);
return state.sym+"_"+state.tf+"_"+s+"_"+r+"."+ext;
};
WB.renderWbStatus=function(msg){
var el=document.getElementById("wbDataStatus");
if(!el)return;
if(msg==="loading"){el.innerHTML="<span class=spin></span> loading "+esc(WB.market)+" "+esc(state.sym)+" "+esc(state.tf)+" via "+esc(WB.provider);return}
if(WB.normMeta&&WB.normMeta.error){el.innerHTML="<span class=r>"+esc(WB.normMeta.error)+"</span><br><span class=hint>provider stays on "+esc(WB.provider)+" — explicit selection kept on failure</span>";return}
if(!WB.normMeta||WB.normMeta.count==null){el.innerHTML="<span class=hint>"+esc(WB.capNote())+"</span>";return}
var live=WB.liveCandle?" · live candle "+new Date(WB.liveCandle.t).toISOString().slice(11,16)+" (unfinished, excluded from indicators)":"";
el.innerHTML="<span class=g>"+esc(String(WB.normMeta.count))+" completed bars</span> from <b>"+esc(WB.normMeta.venue||"")+"</b> · shown "+esc(String(WB.normMeta.shown))+" · "+esc(WB.freshLabel(WB.normMeta.retrievedAt,120000))+" · "+esc(WB.normMeta.tz||"")+" "+esc(WB.normMeta.session||"")+live+"<br><span class=hint>"+esc(WB.capNote())+"</span>";
var av=document.getElementById("wbAvail");if(av)av.textContent="available: "+WB.normMeta.count+" bars";
};
WB.renderFc=function(){
var s=document.getElementById("wbFcStatus");if(!s)return;
var h="";
h+="horizon: "+esc(WB.horizonLabel())+" · lookback "+WB.fc.lookback+" (limit "+(WB.fc.engine==="kronos-local"?(WB.BROWSER_LIMIT[WB.fc.model]||WB.BROWSER_LIMIT["kronos-mini"]).lookback:(WB.MODEL_LIMIT[WB.fc.model]||512))+") · horizon limit "+(WB.fc.engine==="kronos-local"?(WB.BROWSER_LIMIT[WB.fc.model]||WB.BROWSER_LIMIT["kronos-mini"]).horizon:120);
h+="<br>";
if(WB.fc.busy)h+="<span class=spin></span> running "+esc(WB.fc.engine)+"/"+esc(WB.fc.model)+" <span id=wbElapsed>0.0s</span>";
else if(WB.fc.status==="done"&&WB.fc.result)h+="<span class=g>"+esc(WB.fc.result.label)+" ready</span> · "+WB.fc.result.rows.length+" rows · "+WB.fc.elapsed.toFixed(1)+"s · anchor "+new Date(WB.fc.result.anchorTime).toISOString().slice(0,16)+" · "+(WB.fc.stale?"<span class=y>stale</span>":"<span class=g>fresh</span>");
if(window.KronosLocal&&KronosLocal.state){h+="<br>local model: "+(KronosLocal.state.ready?"ready ("+KronosLocal.state.model+")":(KronosLocal.state.loading?"loading "+Math.round((KronosLocal.state.progress||0)*100)+"%":"not loaded"))+" - backend "+KronosLocal.state.backend;}
if(WB.fc.status==="error")h+="<br><span class=r>error: "+esc(WB.fc.error||"")+"</span>";
else if(WB.fc.status==="idle")h+="<br>idle — press Generate forecast";
if(WB.fc.engine==="kronos-local"&&!(window.KronosLocal&&KronosLocal.state.ready))h+="<br><span class=y>local Kronos model not loaded — free data + existing analysis still work</span>";
s.innerHTML=h;
var cancelButton=document.getElementById("wbCancelBtn");if(cancelButton){cancelButton.hidden=!WB.fc.busy;cancelButton.style.display=WB.fc.busy?"":"none";cancelButton.onclick=function(){WB.fc.abort=true;if(window.KronosLocal)KronosLocal.cancelPredict();WB.fc.status="error";WB.fc.error="cancelled";WB.fc.busy=false;WB.refreshBackendPill();WB.renderFc()};}
WB.renderFcTable();
};
WB.renderFcTable=function(){
var w=document.getElementById("wbFcTable");if(!w)return;
if(!WB.fc.result||!WB.fc.result.rows.length){w.innerHTML="<span class=hint>No forecast yet. Kronos-local runs fully in this browser after Load model. Statistical is a labeled local fallback.</span>";return}
var r0=WB.fc.result.rows;
var lastObs=WB.fullBars&&WB.fullBars.length?WB.fullBars[WB.fullBars.length-1].c:null;
var tz=WB.market==="stocks"?"America/New_York":"UTC";
var h="<div style=\"overflow-x:auto;max-height:320px;overflow-y:auto\"><table class=t><thead><tr><th>#</th><th>Start ("+tz+")</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Chg</th><th>Chg%</th><th>Body</th><th>Vol</th><th>Turnover</th><th>Quality</th></tr></thead><tbody>";
for(var i=0;i<r0.length;i++){var r=r0[i];
var ref=i===0?lastObs:r0[i-1].c;
var chg=(r.c!=null&&ref!=null)?r.c-ref:null;
var chgp=(chg!=null&&ref)?chg/ref*100:null;
var body="—";
if(r.o!=null&&r.c!=null){body=r.c>r.o?"up":(r.c<r.o?"down":"flat")}
var dt=new Date(r.t);
var ds=dt.toISOString().slice(0,16).replace("T"," ");
h+="<tr><td>"+r.i+"</td><td>"+ds+"</td><td>"+(r.o==null?"—":fmtN(r.o))+"</td><td>"+(r.h==null?"—":fmtN(r.h))+"</td><td>"+(r.l==null?"—":fmtN(r.l))+"</td><td>"+(r.c==null?"—":fmtN(r.c))+"</td><td>"+(chg==null?"—":(chg>=0?"+":"")+fmtN(chg))+"</td><td>"+(chgp==null?"—":(chgp>=0?"+":"")+chgp.toFixed(2)+"%")+"</td><td>"+body+"</td><td>"+(r.v==null?"—":fmtN(r.v))+"</td><td>"+(r.turnover==null?"—":fmtN(r.turnover))+"</td><td>"+r.quality+"</td></tr>"}
h+="</tbody></table></div>";
var first=r0[0].t,last=r0[r0.length-1].t;
var fcs=r0.filter(function(x){return x.c!=null}).map(function(x){return x.c});
var fc=lastObs!=null?fcs[fcs.length-1]:null;
h+="<div class=hint>first "+new Date(first).toISOString()+" · last "+new Date(last).toISOString()+" · final close "+(fc==null?"—":fmtN(fc))+" · timestamps = candle-start, not intrabar turning points · "+esc(WB.fc.result.label)+" — model estimates, not observed prices/guarantees</div>";
w.innerHTML=h;
};
WB.drawFull=function(){
try{
var OD=window._origDraw||draw;
if(!WB.view.count||WB.view.count>=(state.klines.length||0)){OD();WB.overlayFc();WB.overlayExtra();return}
var full=state.klines.slice();
var fSMA20=state.sma20.slice(),fSMA50=state.sma50.slice(),fSMA200=state.sma200.slice(),fEMA12=state.ema12.slice(),fEMA26=state.ema26.slice(),fD=state.delta.slice(),fC=state.cvd.slice();
var n=full.length,end=Math.min(WB.view.end||n,n),cnt=Math.min(WB.view.count||n,n);
var st=Math.max(0,end-cnt);
state.klines=full.slice(st,end);
state.sma20=fSMA20.slice(st,end);state.sma50=fSMA50.slice(st,end);state.sma200=fSMA200.slice(st,end);state.ema12=fEMA12.slice(st,end);state.ema26=fEMA26.slice(st,end);state.delta=fD.slice(st,end);state.cvd=fC.slice(st,end);
OD();
state.klines=full;state.sma20=fSMA20;state.sma50=fSMA50;state.sma200=fSMA200;state.ema12=fEMA12;state.ema26=fEMA26;state.delta=fD;state.cvd=fC;
WB.overlayFc();WB.overlayExtra();
}catch(e){try{(window._origDraw||draw)()}catch(x){}}
};
WB.overlayFc=function(){
try{
if(!WB.fc.result||!WB.fc.result.rows.length||!WB.ind.fcShow)return;
var rows=WB.fc.result.rows.filter(function(r){return r.c!=null});
if(!rows.length)return;
var rct=cv.getBoundingClientRect();var W=rct.width,H=state.chartH||460;
var ks=state.klines;if(!ks.length)return;
var visN=WB.view.count&&WB.view.count<ks.length?WB.view.count:ks.length;
var vend=WB.view.end&&WB.view.end<ks.length?WB.view.end:ks.length;
var vstart=ks.length-visN;
var lo=1e18,hi=-1e18;
for(var i=vstart;i<vend;i++){lo=Math.min(lo,ks[i].l);hi=Math.max(hi,ks[i].h)}
rows.forEach(function(r){if(r.c!=null){lo=Math.min(lo,r.o!=null?Math.min(r.o,r.c):r.c);hi=Math.max(hi,r.o!=null?Math.max(r.o,r.c):r.c)}if(r.h!=null)hi=Math.max(hi,r.h);if(r.l!=null)lo=Math.min(lo,r.l)});
var pm=(hi-lo)*0.08||1;hi+=pm;lo-=pm;
var padL=8,padR=132,padT=12,padB=22;
var vw=W-padL-padR,vh=H-padT-padB-46;
function X2(x){return padL+vw*x}
function Y(p){return padT+vh*(1-(p-lo)/(hi-lo))}
var nObs=vend-vstart;
var step=vw/Math.max(1,(nObs+rows.length)-1);
var bx=padL+nObs*step;
ctx.save();
ctx.strokeStyle="#22d3ee";ctx.setLineDash([6,4]);ctx.beginPath();ctx.moveTo(bx,padT);ctx.lineTo(bx,padT+vh);ctx.stroke();ctx.setLineDash([]);
ctx.font="10px ui-monospace";ctx.fillStyle="#22d3ee";ctx.fillText("FORECAST →",bx+4,padT+10);
rows.forEach(function(r,idx){
var x=bx+(idx+0.5)*step;
var o=r.o,c=r.c;
if(o==null||c==null){ctx.fillStyle="#5f6b88";ctx.fillRect(x-2,Y(c)-2,4,4);return}
var up=c>=o;
var col=up?WB.ind.fcUp:WB.ind.fcDn;
ctx.strokeStyle=col;ctx.globalAlpha=0.85;
var yh=r.h!=null?Y(r.h):Y(Math.max(o,c)),yl=r.l!=null?Y(r.l):Y(Math.min(o,c));
ctx.beginPath();ctx.moveTo(x,yh);ctx.lineTo(x,yl);ctx.stroke();
var yO=Y(o),yC=Y(c);
ctx.globalAlpha=0.45;ctx.fillStyle=col;
var bw=Math.max(2,step*0.55);
ctx.fillRect(x-bw/2,Math.min(yO,yC),bw,Math.max(1,Math.abs(yC-yO)));
ctx.globalAlpha=1;
});
ctx.restore();
}catch(e){}
};
WB.overlayExtra=function(){
try{
var ks=state.klines;if(!ks.length)return;
var cl=ks.map(function(k){return k.c});
var rct=cv.getBoundingClientRect();var W=rct.width,H=state.chartH||460;
var padL=8,padR=132,padT=12,padB=22;
var vw=W-padL-padR,vh=H-padT-padB-46;
var lo=1e18,hi=-1e18;for(var i=0;i<ks.length;i++){lo=Math.min(lo,ks[i].l);hi=Math.max(hi,ks[i].h)}
var pm=(hi-lo)*0.08||1;hi+=pm;lo-=pm;
function X(i){return padL+vw*i/(ks.length-1)}
function Y(p){return padT+vh*(1-(p-lo)/(hi-lo))}
ctx.save();
for(var m=0;m<WB.ind.mas.length;m++){var cfg=WB.ind.mas[m];if(!cfg.on)continue;
if(cfg.period<=50){continue}
var s=WB.maSeries(cl,cfg);ctx.strokeStyle=cfg.color||"#fff";ctx.lineWidth=cfg.width||1.2;ctx.beginPath();var st=false;
for(var j=0;j<s.length;j++){if(s[j]==null)continue;if(!st){ctx.moveTo(X(j),Y(s[j]));st=true}else ctx.lineTo(X(j),Y(s[j]))}
ctx.stroke()}
if(WB.ind.bb.on){var bb=WB.bb(cl,WB.ind.bb.period||20,WB.ind.bb.mult||2);ctx.strokeStyle=WB.ind.bb.color||"#eab308";ctx.setLineDash([4,3]);
for(var k2=0;k2<2;k2++){var arr=k2===0?bb.up:bb.lo;ctx.beginPath();var s2=false;for(var q=0;q<arr.length;q++){if(arr[q]==null)continue;if(!s2){ctx.moveTo(X(q),Y(arr[q]));s2=true}else ctx.lineTo(X(q),Y(arr[q]))}ctx.stroke()}
ctx.setLineDash([])}
if(WB.ind.vwap.on){var vv=WB.vwapCalc(ks,state.tf,WB.market);ctx.strokeStyle="#f8fafc";ctx.lineWidth=1.2;ctx.setLineDash([6,3]);ctx.beginPath();var s3=false;for(var v2=0;v2<vv.length;v2++){if(vv[v2]==null)continue;if(!s3){ctx.moveTo(X(v2),Y(vv[v2]));s3=true}else ctx.lineTo(X(v2),Y(vv[v2]))}ctx.stroke();ctx.setLineDash([])}
ctx.restore();
ctx.lineWidth=1;
}catch(e){}
};
WB.buildUI=function(){
if(document.getElementById("wbMarketCard"))return;
var css=document.createElement("style");
css.textContent="@media(max-width:640px){.btn{min-height:44px}#wbMarketCard select,#wbMarketCard input,#wbPredCard select,#wbPredCard input{font-size:16px;min-height:44px}}#wbFcTable table.t{font-size:11px}#chartWrap.full{position:fixed;inset:0;z-index:300;background:#080d19;padding:10px}#chartWrap.full #chart{height:70vh}.wbgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:8px 0}.wbgrid label{font-size:11px;color:var(--m);display:flex;flex-direction:column;gap:4px}input[type=range]{width:100%}";
document.head.appendChild(css);
var left=document.getElementById("leftCol");
var chartCard=left.querySelector(".card");
var mc=document.createElement("div");mc.className="card";mc.id="wbMarketCard";
mc.innerHTML="<h2>◈ Market · Venue · Symbol</h2><p class=hint>Crypto spot (Binance/OKX/Bybit, free, no key) + Stocks/ETFs (Stooq daily free + CSV import). Spot forecasts stay separate from perpetual leverage metrics. USDT is a quote asset, not USD.</p><div class=row style=\"margin-bottom:8px\"><select id=wbMarketSel><option value=crypto>Crypto</option><option value=stocks>Stocks & ETFs</option></select><select id=wbProvSel><option value=auto>Auto venue</option><option value=binance>Binance spot</option><option value=okx>OKX spot</option><option value=bybit>Bybit spot</option><option value=yahoo>Yahoo stocks</option><option value=stooq>Stooq daily</option><option value=csv>CSV import</option></select><select id=wbSymSel></select><input type=text id=wbSearchInput placeholder=\"search/add symbol\" style=\"max-width:150px\"><button class=\"btn sm\" id=wbAddBtn>Add</button></div><div class=row style=\"margin-bottom:8px\"><select id=wbTfSel><option value=1m>1m</option><option value=5m>5m</option><option value=15m>15m</option><option value=1h>1H</option><option value=4h>4H</option><option value=1d>1D</option><option value=1w>1W</option></select><button class=\"btn sm pri\" id=wbLoadBtn>Load market data</button><span class=pill id=wbVenuePill>venue —</span></div><div id=wbDataStatus class=nitem>init…</div><div class=row style=\"margin-top:8px\"><span class=hint id=wbAvail></span><span class=hint>pagination: bounded by lookback + display history (max ~1200 bars)</span></div><div id=wbCsvBox hidden><p class=hint>Validated OHLCV CSV: needs timestamp,open,high,low,close (+volume). Keeps symbol/exchange/timezone/session + raw/adjusted metadata.</p><div class=row><input type=text id=wbCsvSym placeholder=\"SYM (e.g. SPY)\" style=\"max-width:90px\"><input type=text id=wbCsvEx placeholder=\"exchange (e.g. NYSE)\" style=\"max-width:110px\"><select id=wbCsvTz><option>America/New_York</option><option>UTC</option><option>America/Chicago</option><option>Europe/London</option></select><select id=wbCsvSess><option>regular</option><option>extended</option><option>mixed</option></select><select id=wbCsvAdj><option>raw</option><option>adjusted</option></select></div><textarea id=wbCsvText rows=4 style=\"width:100%;margin-top:6px\" placeholder=\"timestamp,open,high,low,close,volume&#10;2024-01-02 09:30,475.1,476.2,474.8,475.9,100000\"></textarea><div class=row style=\"margin-top:6px\"><button class=\"btn sm\" id=wbCsvLoadBtn>Validate + load CSV</button><input type=file id=wbCsvFile accept=\".csv,.txt\"></div><div id=wbCsvMsg class=hint></div></div>";
left.insertBefore(mc,left.children[1]);
var pc=document.createElement("div");pc.className="card";pc.id="wbPredCard";
pc.innerHTML="<h2>◉ Prediction — Local Kronos WebGPU + Statistical</h2><p class=hint>Kronos forecasts run on this device via WebGPU without uploading candles. Optional AI Analyst sends the market snapshot to Perchance's remote text plugin. No Polygon key or inference server is needed.</p><div class=row style=\"margin-bottom:6px\"><span class=pill id=wbBackendPill>backend …</span><span class=hint id=wbDlInfo></span></div><div class=wbgrid><label>Engine<select id=wbEngineSel><option value=kronos-local>Kronos-local WebGPU</option><option value=statistical>Statistical (fallback)</option></select></label><label>Model<select id=wbModelSel><option value=kronos-mini>kronos-mini (browser ctx \u2264256)</option><option value=kronos-small disabled>kronos-small (after mini)</option><option value=kronos-base disabled>kronos-base (after mini)</option></select></label><label>Lookback<input type=text id=wbLookInput value=256></label><label>Display history<input type=text id=wbHistInput value=200></label><label>Forecast candles<input type=text id=wbHorInput value=24></label><label>Temperature<input type=text id=wbTempInput value=1.0></label><label>top_p<input type=text id=wbTopPInput value=0.9></label><label>Samples<input type=text id=wbSampInput value=1></label></div><div class=row><button class=\"btn sm pri\" id=wbLoadModelBtn>Load model</button><button class=\"btn sm\" id=wbUnloadModelBtn>Unload</button><button class=\"btn sm\" id=wbRemoveCacheBtn>Remove cached model</button><button class=\"btn sm\" id=wbCapBtn>Check readiness</button><label><input type=checkbox id=wbPersistModel> Keep model cached on this device</label></div><div class=row style=\"margin-top:6px\"><button class=\"btn sm pri\" id=wbGenBtn>Generate forecast</button><button class=\"btn sm\" id=wbCancelBtn hidden>Cancel</button><button class=\"btn sm\" id=wbCsvExpBtn>Forecast CSV</button><span class=hint>mini defaults 256 lookback / 24 horizon / 1 sample until benchmarked</span></div><div id=wbFcStatus class=nitem style=\"margin-top:8px\">idle</div><div id=wbFcTable style=\"margin-top:8px\"></div><div class=hint id=wbProvNote></div>";
left.insertBefore(pc,left.children[2]);
var cc=document.createElement("div");cc.className="card";cc.id="wbChartCard";
cc.innerHTML="<h2>▣ Chart workbench</h2><div class=row><button class=\"btn sm\" id=wbExpandBtn>Expand</button><button class=\"btn sm\" id=wbFullBtn>Fullscreen</button><button class=\"btn sm\" id=wbResetBtn>Reset zoom</button><label class=chk>Height <input type=text id=wbHInput style=\"width:60px\" value=460></label><label class=chk>Visible <input type=text id=wbVisInput style=\"width:60px\" placeholder=\"all\"></label></div><div class=row style=\"margin-top:8px\"><label class=chk><input type=checkbox id=wbGaps checked> time gaps</label><label class=chk><input type=checkbox id=wbLine> line mode</label><label class=chk><input type=checkbox id=wbFcShow checked> forecast</label><label class=chk><input type=checkbox id=wbProj> projected indicators</label><label class=chk><input type=checkbox id=wbBB> Bollinger</label><label class=chk><input type=checkbox id=wbVwap> session VWAP</label><label class=chk><input type=checkbox id=wbGrid checked> grid</label></div><div class=row style=\"margin-top:8px\" id=wbMaRow></div><div class=row style=\"margin-top:8px\"><button class=\"btn sm\" id=wbAddMaBtn>+ MA overlay</button><button class=\"btn sm cy\" id=wbPdfBtn>Download dashboard PDF</button><button class=\"btn sm\" id=wbPdfChartBtn>Chart PDF</button></div><div class=hint>pan: drag · zoom: wheel/pinch · dblclick resets · session VWAP follows market/session (crypto UTC day, stocks NYSE regular)</div>";
left.insertBefore(cc,left.children[3]);
var prc=document.createElement("div");prc.className="card";prc.id="wbPresetCard";
prc.innerHTML="<h2>◐ Presets</h2><p class=hint>Captures market/venue/symbol/TF, engine/model, forecast controls, indicators, layout. No credentials or datasets. Apply never fetches or predicts.</p><div class=row><select id=wbPresetSel style=\"flex:1\"></select><button class=\"btn sm\" id=wbApplyBtn>Apply</button><button class=\"btn sm\" id=wbUpdateBtn>Update</button><button class=\"btn sm\" id=wbDelBtn>Delete</button></div><div class=row style=\"margin-top:6px\"><input type=text id=wbPresetName placeholder=\"preset name\" style=\"flex:1\"><button class=\"btn sm\" id=wbSaveBtn>Save new</button><button class=\"btn sm\" id=wbExpPresetBtn>Export JSON</button><button class=\"btn sm\" id=wbImpPresetBtn>Import JSON</button><input type=file id=wbPresetFile accept=\".json\" hidden></div><div id=wbPresetMsg class=hint></div>";
left.appendChild(prc);
WB.wireUI();
WB.refreshSymList();
WB.loadPresets();
};
WB.refreshSymList=function(){
var s=document.getElementById("wbSymSel");if(!s)return;
var list=WB.market==="crypto"?(typeof SYMS!=="undefined"?SYMS:["BTCUSDT"]):WB.stocks.map(function(x){return x});
s.innerHTML=list.map(function(x){return "<option"+(x===state.sym?" selected":"")+">"+x+"</option>"}).join("");
var t=document.getElementById("wbTfSel");if(t)t.value=state.tf;
var m=document.getElementById("wbMarketSel");if(m)m.value=WB.market;
var p=document.getElementById("wbProvSel");if(p)p.value=WB.provider;
var cb=document.getElementById("wbCsvBox");if(cb)cb.hidden=!(WB.market==="stocks"&&WB.provider==="csv");
var vp=document.getElementById("wbVenuePill");if(vp)vp.textContent=(WB.activeVenue||WB.provider)+" · free";
};
WB.wireUI=function(){
try{document.getElementById("wbPersistModel").checked=localStorage.getItem("kronos-cache-opt-in")==="true"}catch(e){}
document.getElementById("wbMarketSel").onchange=function(e){WB.market=e.target.value;if(WB.market==="crypto"){if(WB.provider==="stooq"||WB.provider==="csv"||WB.provider==="yahoo")WB.provider="auto";if(typeof SYMS!=="undefined")state.sym="BTCUSDT"}else{if(WB.provider!=="yahoo"&&WB.provider!=="stooq"&&WB.provider!=="csv")WB.provider="auto";state.sym="SPY"}WB.refreshSymList();WB.saveSel();WB.renderWbStatus()};
document.getElementById("wbProvSel").onchange=function(e){WB.provider=e.target.value;WB.refreshSymList();WB.saveSel();WB.renderWbStatus()};
document.getElementById("wbSymSel").onchange=function(e){state.sym=e.target.value;try{document.getElementById("symSel").value=state.sym}catch(x){}WB.saveSel();WB.markFcStale()};
document.getElementById("wbTfSel").onchange=function(e){state.tf=e.target.value;try{document.getElementById("tfSel").value=state.tf}catch(x){}WB.saveSel();WB.markFcStale()};
document.getElementById("wbAddBtn").onclick=function(){var v=document.getElementById("wbSearchInput").value.trim().toUpperCase().replace(/[^A-Z0-9]/g,"");if(!v)return;if(WB.market==="crypto"){v=v.indexOf("USDT")>0?v:v+"USDT";if(typeof SYMS!=="undefined"&&SYMS.indexOf(v)<0)SYMS.push(v)}else{if(WB.stocks.indexOf(v)<0)WB.stocks.push(v)}state.sym=v;WB.refreshSymList();WB.saveSel()};
document.getElementById("wbLoadBtn").onclick=async function(){try{document.getElementById("symSel").value=state.sym}catch(x){}try{document.getElementById("tfSel").value=state.tf}catch(x){}await WB.loadWorkbenchData();try{await loadLev(true)}catch(e){}WB.renderWbStatus()};
document.getElementById("wbCsvLoadBtn").onclick=function(){WB.loadCsvText()};
document.getElementById("wbCsvFile").onchange=function(e){var f=e.target.files[0];if(!f)return;var r=new FileReader();r.onload=function(){document.getElementById("wbCsvText").value=String(r.result).slice(0,200000);WB.loadCsvText()};r.readAsText(f)};
document.getElementById("wbEngineSel").value=WB.fc.engine;
document.getElementById("wbModelSel").value=WB.fc.model;
document.getElementById("wbLookInput").value=WB.fc.lookback;
document.getElementById("wbHistInput").value=WB.fc.displayHistory;
document.getElementById("wbHorInput").value=WB.fc.horizon;
document.getElementById("wbTempInput").value=WB.fc.temp;
document.getElementById("wbTopPInput").value=WB.fc.top_p;
document.getElementById("wbSampInput").value=WB.fc.samples;
try{WB.refreshBackendPill()}catch(e){}
function sync(){WB.fc.engine=document.getElementById("wbEngineSel").value;WB.fc.model=document.getElementById("wbModelSel").value;WB.fc.lookback=Math.max(10,parseInt(document.getElementById("wbLookInput").value)||128);WB.fc.displayHistory=Math.max(30,parseInt(document.getElementById("wbHistInput").value)||200);WB.fc.horizon=Math.max(1,parseInt(document.getElementById("wbHorInput").value)||24);WB.fc.temp=parseFloat(document.getElementById("wbTempInput").value);if(!(WB.fc.temp>=0&&WB.fc.temp<=2))WB.fc.temp=1.0;WB.fc.top_p=parseFloat(document.getElementById("wbTopPInput").value);if(!(WB.fc.top_p>0&&WB.fc.top_p<=1))WB.fc.top_p=0.9;WB.fc.samples=Math.max(1,Math.min(32,parseInt(document.getElementById("wbSampInput").value)||1));WB.markFcStale();WB.saveSel();WB.renderFc()}
var ids=["wbEngineSel","wbModelSel","wbLookInput","wbHistInput","wbHorInput","wbTempInput","wbTopPInput","wbSampInput"];
ids.forEach(function(id){document.getElementById(id).onchange=sync;document.getElementById(id).oninput=sync});
document.getElementById("wbGenBtn").onclick=function(){WB.genForecast()};document.getElementById("wbLoadModelBtn").onclick=function(){WB.loadLocalModel()};document.getElementById("wbUnloadModelBtn").onclick=function(){WB.unloadLocalModel()};document.getElementById("wbRemoveCacheBtn").onclick=function(){WB.removeLocalCache()};
document.getElementById("wbCapBtn").onclick=function(){WB.queryCaps()};
document.getElementById("wbCsvExpBtn").onclick=function(){var c=WB.fcCsv();if(!c){toast("no forecast");return}dl(WB.fname("csv"),c,"text/csv");toast("forecast CSV saved")};
document.getElementById("wbExpandBtn").onclick=function(){state.chartH=state.chartH>=650?460:650;var i=document.getElementById("wbHInput");if(i)i.value=state.chartH;try{WB.drawFull()}catch(e){}try{localStorage.setItem("pulse_layout",JSON.stringify({chartH:state.chartH}))}catch(x){}};
document.getElementById("wbFullBtn").onclick=function(){var w=document.getElementById("chartWrap");w.classList.toggle("full");try{sizeCanvas()}catch(e){}WB.drawFull();document.getElementById("wbFullBtn").textContent=w.classList.contains("full")?"Exit fullscreen":"Fullscreen"};
document.getElementById("wbResetBtn").onclick=function(){WB.view.count=state.klines.length;WB.view.end=state.klines.length;var v=document.getElementById("wbVisInput");if(v)v.value="";WB.drawFull()};
document.getElementById("wbHInput").onchange=function(e){var h=Math.max(300,Math.min(900,parseInt(e.target.value)||460));state.chartH=h;WB.drawFull()};
document.getElementById("wbVisInput").onchange=function(e){var v=parseInt(e.target.value);if(!v){WB.view.count=state.klines.length}else{WB.view.count=Math.max(20,Math.min(state.klines.length,v))}WB.view.end=state.klines.length;WB.drawFull()};
document.getElementById("wbGaps").onchange=function(e){WB.ind.gaps=e.target.checked;WB.drawFull();WB.saveSel()};
document.getElementById("wbLine").onchange=function(e){WB.ind.lineMode=e.target.checked;WB.drawFull();WB.saveSel()};
document.getElementById("wbFcShow").onchange=function(e){WB.ind.fcShow=e.target.checked;WB.drawFull();WB.saveSel()};
document.getElementById("wbProj").onchange=function(e){WB.ind.proj=e.target.checked;WB.drawFull();WB.saveSel()};
document.getElementById("wbBB").onchange=function(e){WB.ind.bb.on=e.target.checked;WB.drawFull();WB.saveSel()};
document.getElementById("wbVwap").onchange=function(e){WB.ind.vwap.on=e.target.checked;WB.drawFull();WB.saveSel()};
document.getElementById("wbGrid").onchange=function(e){WB.ind.grid=e.target.checked;WB.drawFull();WB.saveSel()};
document.getElementById("wbAddMaBtn").onclick=function(){WB.ind.mas.push({type:"EMA",period:50,src:"close",color:"#22d3ee",width:1.2,on:true});WB.renderMaRow();WB.drawFull();WB.saveSel()};
document.getElementById("wbPdfBtn").onclick=function(){WB.downloadPdf(true)};
document.getElementById("wbPdfChartBtn").onclick=function(){WB.downloadPdf(false)};
document.getElementById("wbSaveBtn").onclick=function(){WB.savePreset()};
document.getElementById("wbApplyBtn").onclick=function(){WB.applyPreset()};
document.getElementById("wbUpdateBtn").onclick=function(){WB.updatePreset()};
document.getElementById("wbDelBtn").onclick=function(){WB.delPreset()};
document.getElementById("wbExpPresetBtn").onclick=function(){WB.exportPresets()};
document.getElementById("wbImpPresetBtn").onclick=function(){document.getElementById("wbPresetFile").click()};
document.getElementById("wbPresetFile").onchange=function(e){WB.importPresets(e)};
WB.renderMaRow();
WB.attachPanZoom();
document.addEventListener("visibilitychange",function(){if(document.hidden&&state.auto){}});
};
WB.renderMaRow=function(){
var r=document.getElementById("wbMaRow");if(!r)return;
r.innerHTML="";
WB.ind.mas.forEach(function(m,i){
var d=document.createElement("span");d.className="chk"+(m.on?" on":"");
d.innerHTML="<select data-k=type><option>SMA</option><option>EMA</option></select><input type=text data-k=period style=\"width:44px\" value=\""+m.period+"\"><input type=color data-k=color value=\""+m.color+"\"> <button class=\"btn sm\">x</button>";
d.querySelector("[data-k=type]").value=m.type;
d.querySelector("[data-k=type]").onchange=function(e){m.type=e.target.value;WB.drawFull();WB.saveSel()};
d.querySelector("[data-k=period]").onchange=function(e){m.period=Math.max(2,Math.min(500,parseInt(e.target.value)||20));WB.drawFull();WB.saveSel()};
d.querySelector("[data-k=color]").oninput=function(e){m.color=e.target.value;WB.drawFull();WB.saveSel()};
d.querySelector("button").onclick=function(){WB.ind.mas.splice(i,1);WB.renderMaRow();WB.drawFull();WB.saveSel()};
d.onclick=function(e){if(e.target.tagName==="SELECT"||e.target.tagName==="INPUT"||e.target.tagName==="BUTTON")return;m.on=!m.on;d.classList.toggle("on",m.on);WB.drawFull();WB.saveSel()};
r.appendChild(d);
});
};
WB.attachPanZoom=function(){
try{
var dragging=false,sx=0,moved=0;
cv.addEventListener("pointerdown",function(e){dragging=true;sx=e.clientX;moved=0;try{cv.setPointerCapture(e.pointerId)}catch(x){}});
cv.addEventListener("pointermove",function(e){if(!dragging)return;var dx=e.clientX-sx;if(Math.abs(dx)>4){moved+=Math.abs(dx);sx=e.clientX;var step=Math.max(1,Math.round(dx/4));WB.view.end=Math.max(20,Math.min(state.klines.length,(WB.view.end||state.klines.length)-step));WB.drawFull()}});
cv.addEventListener("pointerup",function(){dragging=false});
cv.addEventListener("wheel",function(e){e.preventDefault();var n=WB.view.count||state.klines.length;var f=e.deltaY>0?1.15:0.87;n=Math.max(20,Math.min(state.klines.length,Math.round(n*f)));WB.view.count=n;var v=document.getElementById("wbVisInput");if(v)v.value=String(n);WB.drawFull()},{passive:false});
cv.addEventListener("dblclick",function(){WB.view.count=state.klines.length;WB.view.end=state.klines.length;WB.drawFull()});
}catch(e){}
};
WB.loadCsvText=function(){
var t=document.getElementById("wbCsvText").value;
var sym=(document.getElementById("wbCsvSym").value||"SPY").toUpperCase();
WB.csvMeta={exchange:document.getElementById("wbCsvEx").value||"NYSE",timezone:document.getElementById("wbCsvTz").value,session:document.getElementById("wbCsvSess").value,adjusted:document.getElementById("wbCsvAdj").value};
var pr=WB.parseUserCsv(t,{market:"stocks",symbol:sym,tf:state.tf});
var m=document.getElementById("wbCsvMsg");
if(pr.error||!pr.bars.length){if(m)m.textContent="CSV invalid: "+(pr.error||"no rows");return}
WB.csvData=t;state.sym=sym;
if(WB.stocks.indexOf(sym)<0)WB.stocks.push(sym);
WB.refreshSymList();
if(m)m.textContent="CSV OK: "+pr.bars.length+" rows · "+WB.csvMeta.exchange+" · "+WB.csvMeta.timezone+" · "+WB.csvMeta.session+" · "+WB.csvMeta.adjusted;
WB.loadWorkbenchData();
};
WB.refreshBackendPill=function(){
var p=document.getElementById("wbBackendPill");if(!p)return;
if(!window.KronosLocal){p.textContent="engine missing";return}
var st=KronosLocal.state;
p.textContent="backend "+st.backend+(st.ready?" · "+st.model+" ready":(st.loading?" · loading "+Math.round((st.progress||0)*100)+"%":" · not loaded"));
var d=document.getElementById("wbDlInfo");if(d){d.textContent=st.error?String(st.error).slice(0,140):(st.ready?"model hashes and four WebGPU graphs verified"+(st.artifacts&&st.artifacts.cache?(" · "+st.artifacts.cache.hits+" cache hits"+(st.artifacts.cache.warnings.length?" · "+st.artifacts.cache.warnings.join("; "):"")):""):"mini verified export · model not loaded");}
};
WB.loadLocalModel=async function(){
if(!window.KronosLocal){toast("engine missing");return}
var cacheCheck=document.getElementById("wbPersistModel");KronosLocal.setPersistentCache(!!(cacheCheck&&cacheCheck.checked));
try{toast("loading "+WB.fc.model+"…");await KronosLocal.loadModel(WB.fc.model,function(m){WB.refreshBackendPill();WB.renderFc()});toast("model ready");}catch(err){toast(String((err&&err.message)||err).slice(0,140))}
WB.refreshBackendPill();WB.renderFc();
};
WB.unloadLocalModel=async function(){
if(!window.KronosLocal)return;
try{if(window.KronosLocal.cancelPredict)KronosLocal.cancelPredict()}catch(e){}
WB.fc.abort=true;
if(WB.fc.busy){WB.fc.status="error";WB.fc.error="cancelled";}
try{await KronosLocal.unloadModel()}catch(e){}
WB.fc.busy=false;
WB.refreshBackendPill();WB.renderFc();WB.drawFull();
};
WB.removeLocalCache=async function(){
if(!window.KronosLocal)return;
await KronosLocal.removeCache(WB.fc.model);
try{await KronosLocal.unloadModel()}catch(e){}
toast("cached "+WB.fc.model+" removed");
WB.refreshBackendPill();WB.renderFc();
};
WB.queryCaps=async function(){
var n=document.getElementById("wbProvNote");
if(!window.KronosLocal){if(n)n.textContent="engine missing";return}
try{
var info=await KronosLocal.detect();
var pre=window.KronosPre?KronosPre.selfTest():[];
var bad=pre.filter(function(t){return !t.ok});
if(n)n.textContent="WebGPU secure="+info.secure+" adapter="+info.adapter+" device="+info.device+" cores="+(info.cores||"?")+" · preprocess "+(pre.length-bad.length)+"/"+pre.length+" passing · "+(KronosLocal.state.ready?"model ready":"model not loaded");
WB.fc.readyNote="local readiness checked";
}catch(err){if(n)n.textContent="readiness failed: "+String((err&&err.message)||err).slice(0,160)}
WB.refreshBackendPill();WB.renderFc();
};
WB.defPresets=function(){
return [{name:"Bitcoin 1h",market:"crypto",provider:"auto",symbol:"BTCUSDT",timeframe:"1h",engine:"kronos-local",model:"kronos-mini",lookback:256,displayHistory:200,horizon:24,temp:1.0,top_p:0.9,samples:1,version:3},{name:"Bitcoin 4h",market:"crypto",provider:"auto",symbol:"BTCUSDT",timeframe:"4h",engine:"kronos-local",model:"kronos-mini",lookback:256,displayHistory:200,horizon:24,temp:1.0,top_p:0.9,samples:1,version:3},{name:"Ethereum daily",market:"crypto",provider:"auto",symbol:"ETHUSDT",timeframe:"1d",engine:"kronos-local",model:"kronos-mini",lookback:256,displayHistory:200,horizon:24,temp:0.2,top_p:0.9,samples:1,version:3},{name:"Stocks daily",market:"stocks",provider:"auto",symbol:"SPY",timeframe:"1d",engine:"kronos-local",model:"kronos-mini",lookback:256,displayHistory:200,horizon:24,temp:1.0,top_p:0.9,samples:1,version:3},{name:"Compact phone",market:"crypto",provider:"auto",symbol:"BTCUSDT",timeframe:"1h",engine:"kronos-local",model:"kronos-mini",lookback:64,displayHistory:80,horizon:12,temp:1.0,top_p:0.9,samples:1,version:3,chartH:340}];
};
WB.loadPresets=function(){
try{var pv=JSON.parse(localStorage.getItem("pulse_presets_v3")||"null");if(Array.isArray(pv)&&pv.length&&!JSON.parse(localStorage.getItem("pulse_presets_v4")||"null")){try{localStorage.setItem("pulse_presets_v4",JSON.stringify(pv))}catch(e){}}var p=JSON.parse(localStorage.getItem("pulse_presets_v4")||"null");if(Array.isArray(p)&&p.length){for(var i=0;i<p.length;i++){if(p[i].name==="Stocks daily"&&p[i].provider==="stooq")p[i].provider="auto";if(p[i].engine==="kronos")p[i].engine="kronos-local";if(p[i].engine==="statistical"&&/Bitcoin|Ethereum|Stocks|Compact/.test(p[i].name||"")){p[i].engine="kronos-local";p[i].model="kronos-mini";if(p[i].lookback<200)p[i].lookback=256;if(p[i].temp!==1.0)p[i].temp=1.0;}}WB.presets=p}else{WB.presets=WB.defPresets();localStorage.setItem("pulse_presets_v4",JSON.stringify(WB.presets))}}catch(e){WB.presets=WB.defPresets()}
WB.refreshPresetSel();
};
WB.refreshPresetSel=function(){
var s=document.getElementById("wbPresetSel");if(!s)return;
s.innerHTML=WB.presets.map(function(p,i){return "<option value="+i+">"+p.name+"</option>"}).join("");
};
WB.collectPreset=function(name){
return {name:name,version:3,market:WB.market,provider:WB.provider,symbol:state.sym,timeframe:state.tf,engine:WB.fc.engine,model:WB.fc.model,lookback:WB.fc.lookback,displayHistory:WB.fc.displayHistory,horizon:WB.fc.horizon,temp:WB.fc.temp,top_p:WB.fc.top_p,samples:WB.fc.samples,indicators:JSON.parse(JSON.stringify(WB.ind)),chartH:state.chartH,viewCount:WB.view.count};
};
WB.validatePreset=function(p){
if(!p||p.version!==3)return "need version 3";
if(!p.symbol||!p.timeframe)return "missing symbol/timeframe";
if(["1m","5m","15m","1h","4h","1d","1w"].indexOf(p.timeframe)<0)return "bad timeframe";
if(p.market==="stocks"&&p.provider==="stooq"&&["1m","5m","15m","1h","4h"].indexOf(p.timeframe)>=0)return "Stooq daily-only: "+p.timeframe+" unsupported";
return null;
};
WB.savePreset=function(){
var n=document.getElementById("wbPresetName").value.trim()||("preset "+(WB.presets.length+1));
var p=WB.collectPreset(n);
var err=WB.validatePreset(p);var m=document.getElementById("wbPresetMsg");
if(err){if(m)m.textContent="not saved: "+err;return}
WB.presets.push(p);
try{localStorage.setItem("pulse_presets_v4",JSON.stringify(WB.presets))}catch(e){}
WB.refreshPresetSel();if(m)m.textContent="saved "+n;
};
WB.applyPreset=function(){
var s=document.getElementById("wbPresetSel");var p=WB.presets[+s.value];var m=document.getElementById("wbPresetMsg");
if(!p)return;
var err=WB.validatePreset(p);
WB.market=p.market||"crypto";WB.provider=p.provider||"auto";state.sym=p.symbol;state.tf=p.timeframe;
WB.fc.engine=p.engine||"kronos-local";WB.fc.model=p.model||"kronos-mini";WB.fc.lookback=p.lookback||128;WB.fc.displayHistory=p.displayHistory||200;WB.fc.horizon=p.horizon||24;WB.fc.temp=p.temp!=null?p.temp:0.2;WB.fc.top_p=p.top_p||0.9;WB.fc.samples=p.samples||1;
if(p.indicators)WB.ind=p.indicators;
if(p.chartH)state.chartH=p.chartH;
try{document.getElementById("symSel").value=state.sym}catch(e){}
try{document.getElementById("tfSel").value=state.tf}catch(e){}
WB.refreshSymList();
try{document.getElementById("wbEngineSel").value=WB.fc.engine;document.getElementById("wbModelSel").value=WB.fc.model;document.getElementById("wbLookInput").value=WB.fc.lookback;document.getElementById("wbHistInput").value=WB.fc.displayHistory;document.getElementById("wbHorInput").value=WB.fc.horizon;document.getElementById("wbTempInput").value=WB.fc.temp;document.getElementById("wbTopPInput").value=WB.fc.top_p;document.getElementById("wbSampInput").value=WB.fc.samples}catch(e){}
WB.renderMaRow();WB.renderFc();WB.saveSel();
if(m)m.textContent=err?("applied with warning: "+err):("applied "+p.name+" (no fetch/predict triggered)");
WB.fc.result=null;WB.fc.stale=false;WB.renderFc();
};
WB.updatePreset=function(){
var s=document.getElementById("wbPresetSel");var i=+s.value;var m=document.getElementById("wbPresetMsg");
if(!WB.presets[i])return;
var p=WB.collectPreset(WB.presets[i].name);
var err=WB.validatePreset(p);if(err){if(m)m.textContent="not updated: "+err;return}
WB.presets[i]=p;
try{localStorage.setItem("pulse_presets_v4",JSON.stringify(WB.presets))}catch(e){}
if(m)m.textContent="updated "+p.name;
};
WB.delPreset=function(){
var s=document.getElementById("wbPresetSel");var i=+s.value;
WB.presets.splice(i,1);
try{localStorage.setItem("pulse_presets_v4",JSON.stringify(WB.presets))}catch(e){}
WB.refreshPresetSel();
};
WB.exportPresets=function(){
dl(WB.fname("presets.json"),JSON.stringify({version:3,exportedAt:new Date().toISOString(),presets:WB.presets},null,2),"application/json");toast("presets exported");
};
WB.importPresets=function(e){
var f=e.target.files[0];if(!f)return;var r=new FileReader();
r.onload=function(){try{var j=JSON.parse(String(r.result));var arr=Array.isArray(j)?j:j.presets;if(!Array.isArray(arr))throw new Error("bad file");var ok=0;for(var i=0;i<arr.length;i++){if(!WB.validatePreset(arr[i])){WB.presets.push(arr[i]);ok++}}localStorage.setItem("pulse_presets_v4",JSON.stringify(WB.presets));WB.refreshPresetSel();document.getElementById("wbPresetMsg").textContent="imported "+ok+"/"+arr.length}catch(err){document.getElementById("wbPresetMsg").textContent="import failed: "+String(err.message||err).slice(0,120)}};
r.readAsText(f);
};
WB.pdfEsc=function(s){return String(s==null?"":s).replace(/\\/g,"\\\\").replace(/\(/g,"\\(").replace(/\)/g,"\\)")};
WB.downloadPdf=async function(whole){
toast("building PDF…");
try{
var d=null;try{d=expData()}catch(e){d={meta:{symbol:state.sym,timeframe:state.tf}}}
var jpgBytes=null,jpgW=0,jpgH=0;
try{
var du=cv.toDataURL("image/jpeg",0.82);
var b64=du.split(",")[1];
var bin=atob(b64);
var u8=new Uint8Array(bin.length);
for(var bi=0;bi<bin.length;bi++)u8[bi]=bin.charCodeAt(bi);
if(u8.length>40&&u8[0]===255&&u8[1]===216){jpgBytes=u8;jpgW=cv.width;jpgH=cv.height;if(jpgW>1600){jpgW=1600}}
}catch(e){}
function esc(s){return String(s==null?"":s).replace(/\\/g,"\\\\").replace(/\(/g,"\\(").replace(/\)/g,"\\)")}
var L1=[];
L1.push("Crypto Pulse - "+state.sym+" "+state.tf+" ("+WB.market+"/"+(WB.activeVenue||WB.provider)+")");
L1.push("Exported "+new Date().toISOString()+" - "+(WB.fc.result?WB.fc.result.label+" "+WB.fc.result.rows.length+" rows":"no forecast")+" - Not financial advice");
L1.push("Market "+WB.market+" - venue "+(WB.activeVenue||WB.provider)+" - bars "+(WB.normMeta?WB.normMeta.count:"?")+" - tz "+(WB.normMeta?WB.normMeta.tz:"")+" "+(WB.normMeta?WB.normMeta.session:""));
if(d&&d.price)L1.push("Last "+fmtN(d.price.last)+" - RSI "+(d.indicators?d.indicators.rsi14:"-")+" - Funding "+((d.leverage&&d.leverage.fundingRate)||"n/a")+" @ "+((d.leverage&&d.leverage.venue)||"-"));
if(WB.fc.result){L1.push(WB.fc.result.label+" ("+WB.fc.result.engine+") model "+WB.fc.result.model+" tokenizer "+WB.fc.result.tokenizer);L1.push("Anchor "+new Date(WB.fc.result.anchorTime).toISOString()+" - calendar "+WB.fc.result.calendar);L1.push("Settings lookback "+WB.fc.result.settings.lookback+" horizon "+WB.fc.result.settings.horizon+" temp "+WB.fc.result.settings.temp+" top_p "+WB.fc.result.settings.top_p+" samples "+WB.fc.result.settings.samples);L1.push("Provenance "+JSON.stringify(WB.fc.result.provenance).slice(0,120))}
L1.push("Horizon: "+WB.horizonLabel());
L1.push("Forecasts are model estimates, not observed prices, guarantees, trades or calibrated probabilities.");
var pages=[];
pages.push({lines:L1,img:!!jpgBytes});
if(whole&&WB.fc.result){
var rows=WB.fc.result.rows,per=36;
for(var p0=0;p0<rows.length;p0+=per){
var LL=["Forecast rows "+(p0+1)+"-"+Math.min(rows.length,p0+per)+" of "+rows.length+" (candle-start timestamps, not intrabar turning points)","# start_iso open high low close chg% quality"];
for(var ri=p0;ri<Math.min(rows.length,p0+per);ri++){var r=rows[ri];var ref=ri===0?(WB.fullBars?WB.fullBars[WB.fullBars.length-1].c:null):rows[ri-1].c;var cp=ref&&r.c!=null?(r.c-ref)/ref*100:null;LL.push(r.i+" "+new Date(r.t).toISOString()+" "+(r.o==null?"-":r.o)+" "+(r.h==null?"-":r.h)+" "+(r.l==null?"-":r.l)+" "+(r.c==null?"-":r.c)+" "+(cp==null?"-":cp.toFixed(2)+"%")+" "+r.quality)}
pages.push({lines:LL,img:false});
}
}
var enc=new TextEncoder();
var objs=[];
objs[1]="<< /Type /Catalog /Pages 2 0 R >>";
objs[3]="<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>";
var pageIds=[];
var nextId=4;
var imgId=0;
if(jpgBytes){imgId=99}
for(var pi=0;pi<pages.length;pi++){
var lines=pages[pi].lines;
var cs="BT /F1 13 Tf 36 800 Td ("+esc(lines[0]||"")+") Tj ET\n";
var y=782;
for(var li=1;li<lines.length;li++){var sz=li<4?10:9;if(y<48)break;y-=(sz>9?15:13);cs+="BT /F1 "+sz+" Tf 36 "+y+" Td ("+esc(String(lines[li]).slice(0,115))+") Tj ET\n"}
var imgOp="";
if(pi===0&&jpgBytes){
var maxW=523,maxH=300;
var iw=523,ih=Math.round(523*(cv.height/Math.max(1,cv.width)));
if(ih>maxH){ih=maxH;iw=Math.round(maxH*(cv.width/Math.max(1,cv.height)))}
var ix=Math.round(36+(523-iw)/2),iy=Math.round(y-ih-10);
if(iy<40)iy=40;
imgOp="q "+iw+" 0 0 "+ih+" "+ix+" "+iy+" cm /Im0 Do Q\n";
}
var full=cs+imgOp;
var cb=enc.encode(full);
objs[nextId]= {raw:cb,wrap:true};
var cId=nextId;nextId++;
var rs="/Font << /F1 3 0 R >>";
if(pi===0&&jpgBytes)rs="/Font << /F1 3 0 R >> /XObject << /Im0 "+imgId+" 0 R >>";
objs[nextId]="<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << "+rs+" >> /Contents "+cId+" 0 R >>";
pageIds.push(nextId);nextId++;
}
var kidStr="";
for(var k=0;k<pageIds.length;k++)kidStr+=(k?" ":"")+pageIds[k]+" 0 R";
objs[2]="<< /Type /Pages /Kids ["+kidStr+"] /Count "+pageIds.length+" >>";
var out=[];
function push(b){if(typeof b==="string")out.push(enc.encode(b));else out.push(b)}
var offsets={};
push("%PDF-1.4\n");
var maxId=imgId?imgId:nextId-1;
for(var oid=1;oid<=maxId;oid++){
if(oid===imgId){
offsets[oid]=out.reduce(function(a,p){return a+p.length},0);
push(imgId+" 0 obj << /Type /XObject /Subtype /Image /Width "+cv.width+" /Height "+cv.height+" /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length "+jpgBytes.length+" >> stream\n");
push(jpgBytes);
push("\nendstream endobj\n");
continue;
}
if(!objs[oid])continue;
offsets[oid]=out.reduce(function(a,p){return a+p.length},0);
var body=objs[oid];
if(body&&body.wrap){
push(oid+" 0 obj << /Length "+body.raw.length+" >> stream\n");
push(body.raw);
push("\nendstream endobj\n");
}else{
push(oid+" 0 obj "+body+" endobj\n");
}
}
var xrefPos=out.reduce(function(a,p){return a+p.length},0);
var many=Object.keys(offsets).map(Number).sort(function(a,b){return a-b});
var top=many[many.length-1];
push("xref\n0 "+(top+1)+"\n");
push("0000000000 65535 f \n");
for(var xi=1;xi<=top;xi++){
if(offsets[xi]!=null){var s=String(offsets[xi]);while(s.length<10)s="0"+s;push(s+" 00000 n \n")}
else push("0000000000 00000 f \n");
}
push("trailer << /Size "+(top+1)+" /Root 1 0 R >>\nstartxref\n"+xrefPos+"\n%%EOF");
var total=out.reduce(function(a,p){return a+p.length},0);
var pdf=new Uint8Array(total);
var at=0;
for(var oi=0;oi<out.length;oi++){pdf.set(out[oi],at);at+=out[oi].length}
var blob=new Blob([pdf],{type:"application/pdf"});
var nm=WB.fname("pdf");
var u=URL.createObjectURL(blob);
var aEl=document.createElement("a");aEl.href=u;aEl.download=nm;document.body.appendChild(aEl);aEl.click();setTimeout(function(){URL.revokeObjectURL(u);aEl.remove()},1500);
toast("PDF saved ("+nm+")");
}catch(e){toast("PDF failed: "+String((e&&e.message)||e).slice(0,140))}
};
WB.selfTest=function(){
var out=[];
function t(n,c){out.push({n:n,ok:!!c})}
var r1=WB.parseBinance([[1000,"1","2","0.5","1.5","10","1001","50",0,"6","6","0"],[2000,"1.5","2","1","1.8","5","2001","20",0,"3","3","0"]],{market:"crypto",symbol:"BTCUSDT",tf:"1h"});
t("binance taker preserved",r1.bars.length>=1);
var dup=[{t:1000,tEnd:2000,o:1,h:2,l:0.5,c:1.5,vBase:1,venue:"x"},{t:1000,tEnd:2000,o:1,h:2,l:0.5,c:1.5,vBase:1,venue:"x"}];
t("dedupe",WB.sortDedupe(dup).length===1);
var bad=[{t:1000,tEnd:2000,o:1,h:0.5,l:2,c:1.5,vBase:1}];
t("ohlc bounds reject",WB.sortDedupe(bad).length===0);
t("holiday 2025-12-25 closed",WB.isTradingDay(Date.parse("2025-12-25T12:00:00Z"))===false);
t("weekday open",WB.isTradingDay(Date.parse("2025-06-10T12:00:00Z"))===true);
var sf=WB.statForecast([100,101,102,101,103,104,105,106,107,108,109,110],5);
t("stat close-only",sf.close&&sf.close.length===5);
var cl=[10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30];
var mySma=sma(cl,5).filter(Boolean).pop();
t("sma warmup",sma([1,2],5)[4]==null||sma([1,2],5).length===2);
t("sma value",Math.abs(mySma-28)<1e-9);
return out;
};
window.addEventListener("load",function(){setTimeout(function(){try{var r=WB.selfTest();console.log("WB selfTest",r)}catch(e){}},1500)});
