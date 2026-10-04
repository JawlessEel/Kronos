"""Compare a complete greedy ONNX forecast against upstream Python inference."""
import argparse, importlib, json, sys, urllib.request
from pathlib import Path
import numpy as np
import pandas as pd
import torch
import onnxruntime as ort

def main():
    ap=argparse.ArgumentParser()
    for key in ('kronos-root','model','tokenizer','assets'):ap.add_argument('--'+key,required=True)
    args=ap.parse_args();sys.path.insert(0,args.kronos_root)
    from model import Kronos,KronosTokenizer,KronosPredictor
    torch.set_num_threads(4)
    root=Path(args.assets)
    req=urllib.request.Request('https://www.okx.com/api/v5/market/candles?instId=BTC-USDT&bar=1H&limit=300',headers={'User-Agent':'Kronos-browser-validation'})
    payload=json.load(urllib.request.urlopen(req,timeout=30))
    if payload.get('code')!='0':raise ValueError('OKX data fetch failed')
    bars=[{'t':int(v[0]),'o':float(v[1]),'h':float(v[2]),'l':float(v[3]),'c':float(v[4]),'v':float(v[5]),'turnover':float(v[7])} for v in payload['data'] if v[8]=='1']
    bars=sorted(bars,key=lambda b:b['t'])[-256:]
    if len(bars)!=256:raise ValueError('Need 256 completed actual candles')
    future=[bars[-1]['t']+(i+1)*3600000 for i in range(24)]
    x=np.array([[b[k] for k in ('o','h','l','c','v','turnover')] for b in bars],dtype=np.float32)
    mean=x.mean(0);std=x.std(0);norm=np.clip((x-mean)/(std+1e-5),-5,5).astype(np.float32)
    dates=pd.to_datetime([b['t'] for b in bars]+future,unit='ms',utc=True)
    stamps=np.array([[d.minute,d.hour,d.weekday(),d.day,d.month] for d in dates],dtype=np.float32)
    opts=ort.SessionOptions();opts.intra_op_num_threads=4
    sessions={n:ort.InferenceSession(str(root/'models'/(n+'.onnx')),opts,providers=['CPUExecutionProvider']) for n in ('tokenizer-encode','tokenizer-decode','predictor-s1','predictor-s2')}
    a,b=sessions['tokenizer-encode'].run(None,{'x':norm[None]})
    for step in range(24):
        out=sessions['predictor-s1'].run(None,{'s1_ids':a.astype(np.int32),'s2_ids':b.astype(np.int32),'stamp':stamps[None,:len(b[0])].astype(np.int32)})
        logits,ctx=out[:2]
        token=np.argmax(logits,-1).reshape(1,1).astype(np.float32)
        logits2=sessions['predictor-s2'].run(None,{'context':ctx,'s1_ids':token.astype(np.int32)})[0]
        a=np.concatenate([a,token],1);b=np.concatenate([b,np.argmax(logits2,-1).reshape(1,1).astype(np.float32)],1)
    decoded=sessions['tokenizer-decode'].run(None,{'s1_ids':a,'s2_ids':b})[0][0,-24:]
    result=decoded*(std+1e-5)+mean
    tok=KronosTokenizer.from_pretrained(args.tokenizer).eval();model=Kronos.from_pretrained(args.model).eval()
    upstream=importlib.import_module('model.kronos')
    original=upstream.sample_from_logits
    # Only the test process uses argmax. Production sampling remains unchanged.
    upstream.sample_from_logits=lambda logits,**kwargs:torch.argmax(logits,dim=-1,keepdim=True)
    try:
        pred=KronosPredictor(model,tok,device='cpu',max_context=2048)
        df=pd.DataFrame(x,columns=['open','high','low','close','volume','amount'])
        expected=pred.predict(df,pd.Series(dates[:256]),pd.Series(dates[256:]),pred_len=24,T=1.0,top_k=0,top_p=1.0,sample_count=1,verbose=False).values
    finally:upstream.sample_from_logits=original
    np.testing.assert_allclose(result,expected,rtol=2e-4,atol=0.003)
    fixture={'provider':'OKX public spot REST','symbol':'BTC-USDT','timeframe':'1h','completedOnly':True,'request':{'model':'kronos-mini','lookback':256,'horizon':24,'samples':1,'temperature':1,'top_p':1,'top_k':0,'seed':7,'greedy':True,'timeMode':'UTC','candles':bars,'futureTimes':future},'expected':expected.tolist(),'onnxCpu':result.tolist(),'normalization':{'mean':mean.tolist(),'std':std.tolist()},'maxAbsError':float(np.max(np.abs(result-expected)))}
    (root/'parity'/'python-reference.json').write_text(json.dumps(fixture,indent=2))
    print('Complete 256-to-24 greedy parity passed; max absolute error:',fixture['maxAbsError'])

if __name__=='__main__':main()
