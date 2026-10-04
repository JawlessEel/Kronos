const KronosPre={};
KronosPre.EPS=1e-5;
KronosPre.CLIP=5;
KronosPre.assemble6=function(bars){
var n=bars.length,mat=[],missV=false,missA=false;
for(var i=0;i<n;i++){var b=bars[i];mat.push([b.o,b.h,b.l,b.c,0,0])}
var anyV=false,anyA=false;
for(var j=0;j<n;j++){var v=bars[j].vBase,a=bars[j].turnover;if(v!=null&&isFinite(v)){anyV=true;mat[j][4]=v}else{mat[j][4]=0}if(a!=null&&isFinite(a)){anyA=true;mat[j][5]=a}else{mat[j][5]=NaN}}
if(!anyV)missV=true;
if(!anyA){missA=true;for(var k=0;k<n;k++){var m=(mat[k][0]+mat[k][1]+mat[k][2]+mat[k][3])/4;var vv=mat[k][4];mat[k][5]=vv*m}}
else{for(var q=0;q<n;q++){if(!isFinite(mat[q][5])){var m2=(mat[q][0]+mat[q][1]+mat[q][2]+mat[q][3])/4;mat[q][5]=mat[q][4]*m2}}}
return {matrix:mat,missingVolume:bars.some(function(b){return b.vBase==null||!isFinite(b.vBase)}),missingAmount:bars.some(function(b){return b.turnover==null||!isFinite(b.turnover)})};
};
KronosPre.meanStd=function(mat){
var n=mat.length,c=mat[0].length,mean=new Array(c).fill(0),std=new Array(c).fill(0);
for(var i=0;i<n;i++)for(var j=0;j<c;j++)mean[j]+=mat[i][j];
for(var k=0;k<c;k++)mean[k]/=n;
for(var i2=0;i2<n;i2++)for(var j2=0;j2<c;j2++){var d=mat[i2][j2]-mean[j2];std[j2]+=d*d}
for(var k2=0;k2<c;k2++){std[k2]=Math.sqrt(std[k2]/n);if(!(std[k2]>0))std[k2]=0}
return {mean:mean,std:std};
};
KronosPre.normalize=function(mat,mean,std,clip){
var n=mat.length,c=mean.length,out=[];
var cl=clip==null?KronosPre.CLIP:clip;
for(var i=0;i<n;i++){var row=[];for(var j=0;j<c;j++){var v=(mat[i][j]-mean[j])/(std[j]+KronosPre.EPS);if(v>cl)v=cl;if(v<-cl)v=-cl;row.push(v)}out.push(row)}
return out;
};
KronosPre.denormalize=function(mat,mean,std){
var n=mat.length,c=mean.length,out=[];
for(var i=0;i<n;i++){var row=[];for(var j=0;j<c;j++)row.push(mat[i][j]*(std[j]+KronosPre.EPS)+mean[j]);out.push(row)}
return out;
};
KronosPre.timeFeaturesUTC=function(tsMs){
var d=new Date(tsMs);
return [d.getUTCMinutes(),d.getUTCHours(),(d.getUTCDay()+6)%7,d.getUTCDate(),d.getUTCMonth()+1];
};
KronosPre.timeFeaturesET=function(tsMs){
if(!Number.isFinite(tsMs))throw new Error("Invalid timestamp");
var fields={};
new Intl.DateTimeFormat("en-US",{timeZone:"America/New_York",hourCycle:"h23",hour:"2-digit",minute:"2-digit",day:"numeric",month:"numeric",weekday:"short"}).formatToParts(new Date(tsMs)).forEach(function(p){fields[p.type]=p.value});
var map={Mon:0,Tue:1,Wed:2,Thu:3,Fri:4,Sat:5,Sun:6};
return [+fields.minute,+fields.hour,map[fields.weekday],+fields.day,+fields.month];
};
KronosPre.mulberry32=function(seed){
var a=seed>>>0;
return function(){a|=0;a=a+0x6D2B79F5|0;var t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296};
};
KronosPre.topKTopPFilter=function(logits,top_k,top_p){
var n=logits.length,out=logits.slice();
if(top_k&&top_k>0){
var k=Math.min(Math.max(top_k,1),n);
var sorted=out.slice().sort(function(a,b){return b-a});
var thr=sorted[k-1];
for(var i=0;i<n;i++)if(out[i]<thr)out[i]=-Infinity;
return out;
}
if(top_p!=null&&top_p<1){
var idx=out.map(function(v,i){return i}).sort(function(a,b){return out[b]-out[a]});
var mx=Math.max.apply(null,out);
var exps=idx.map(function(i){return Math.exp(out[i]-mx)});
var sum=exps.reduce(function(a,b){return a+b},0);
var cum=0,keep={};
for(var j=0;j<idx.length;j++){cum+=exps[j]/sum;keep[idx[j]]=true;if(cum>top_p)break}
if(!keep[idx[0]])keep[idx[0]]=true;
for(var q=0;q<n;q++)if(!keep[q])out[q]=-Infinity;
return out;
}
return out;
};
KronosPre.sampleFromLogits=function(logits,temp,top_k,top_p,rand,greedy){
var t=temp==null?1:temp;
var scaled=logits.map(function(v){return v/t});
var f=KronosPre.topKTopPFilter(scaled,top_k||0,top_p==null?1:top_p);
var mx=Math.max.apply(null,f.filter(function(v){return v!==-Infinity}));
if(!isFinite(mx))mx=0;
var exps=f.map(function(v){return v===-Infinity?0:Math.exp(v-mx)});
var sum=exps.reduce(function(a,b){return a+b},0);
if(!(sum>0))throw new Error("Invalid sampling distribution");
if(greedy){var bi=0,bv=-1;for(var i=0;i<exps.length;i++)if(exps[i]>bv){bv=exps[i];bi=i}return bi}
var r=(rand?rand():Math.random())*sum,acc=0;
for(var j=0;j<exps.length;j++){acc+=exps[j];if(r<acc)return j}
return exps.length-1;
};
KronosPre.selfTest=function(){
var out=[];
function t(n,c){out.push({n:n,ok:!!c})}
var bars=[{o:10,h:11,l:9,c:10.5,vBase:100,turnover:1050},{o:10.5,h:12,l:10,c:11.5,vBase:200,turnover:2200}];
var a=KronosPre.assemble6(bars);
t("assemble cols",a.matrix.length===2&&a.matrix[0].length===6);
t("amount kept",a.matrix[0][5]===1050);
var b2=[{o:1,h:2,l:0.5,c:1.5,vBase:null,turnover:null}];
var a2=KronosPre.assemble6(b2);
t("missing vol zero",a2.matrix[0][4]===0&&a2.matrix[0][5]===0);
var ms=KronosPre.meanStd([[1,2],[3,4]]);
t("mean",Math.abs(ms.mean[0]-2)<1e-12&&Math.abs(ms.mean[1]-3)<1e-12);
t("pop std",Math.abs(ms.std[0]-1)<1e-12);
var nm=KronosPre.normalize([[1],[3]], [2],[1],5);
t("norm",Math.abs(nm[0][0]+1)<1e-4&&Math.abs(nm[1][0]-1)<1e-4);
var dn=KronosPre.denormalize(nm,[2],[1]);
t("denorm roundtrip",Math.abs(dn[0][0]-1)<1e-9);
var tf=KronosPre.timeFeaturesUTC(Date.UTC(2025,5,10,13,45));
t("utc features",tf[0]===45&&tf[1]===13&&tf[4]===6);
var s=KronosPre.sampleFromLogits([10,0,0],1,0,1,null,true);
t("greedy",s===0);
var r1=KronosPre.mulberry32(7),r2=KronosPre.mulberry32(7);
t("prng seeded",r1()===r2());
return out;
};

export {KronosPre};
