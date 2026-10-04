"""Inference-only export. Upstream model files and environments stay unchanged."""
import argparse, hashlib, json, sys
from pathlib import Path
import numpy as np
import onnx
import onnxruntime as ort
import torch
from torch import nn

class Encode(nn.Module):
    def __init__(self,tok):
        super().__init__(); self.tok=tok
        self.register_buffer('powers',2.0**torch.arange(tok.tokenizer.s1_bits))
    def forward(self,x):
        z=self.tok.embed(x)
        for layer in self.tok.encoder: z=layer(z)
        # Binary spherical normalization preserves signs. Float tokens avoid
        # bitwise GPU kernels; these small integers are exactly representable.
        z=(self.tok.quant_embed(z)>0).float(); n=self.tok.tokenizer.s1_bits
        return (z[...,:n]*self.powers).sum(-1),(z[...,n:]*self.powers).sum(-1)

class Decode(nn.Module):
    def __init__(self,tok):
        super().__init__(); self.tok=tok
        self.register_buffer('powers',2.0**torch.arange(tok.tokenizer.s1_bits))
    def forward(self,s1_ids,s2_ids):
        def bits(ids):
            d=torch.floor(ids.unsqueeze(-1)/self.powers)
            return d-torch.floor(d/2)*2
        z=(torch.cat([bits(s1_ids),bits(s2_ids)],-1)*2-1)
        z=self.tok.post_quant_embed(z/self.tok.codebook_dim**0.5)
        for layer in self.tok.decoder: z=layer(z)
        return self.tok.head(z)

class S1(nn.Module):
    def __init__(self,model): super().__init__(); self.model=model
    def forward(self,s1_ids,s2_ids,stamp):
        # Embedding accepts int32. Avoid ORT WebGPU float-to-int64 Cast/Gather;
        # time_emb.forward casts to int64, so perform its five gathers directly.
        embedding=self.model.embedding([s1_ids,s2_ids])
        te=self.model.time_emb
        time_embedding=te.hour_embed(stamp[:,:,1])+te.weekday_embed(stamp[:,:,2])+te.day_embed(stamp[:,:,3])+te.month_embed(stamp[:,:,4])+te.minute_embed(stamp[:,:,0])
        x=self.model.token_drop(embedding+time_embedding)
        for layer in self.model.transformer:x=layer(x)
        ctx=self.model.norm(x)
        return self.model.head(ctx)[:,-1,:],ctx,embedding[:,-1,:],time_embedding[:,-1,:]

class S2(nn.Module):
    def __init__(self,model): super().__init__(); self.model=model
    def forward(self,context,s1_ids):
        return self.model.decode_s2(context,s1_ids)[:,-1,:]

def reset_rope(module):
    for m in module.modules():
        if hasattr(m,'seq_len_cached'):
            m.seq_len_cached=None; m.cos_cached=None; m.sin_cached=None

def main():
    ap=argparse.ArgumentParser()
    for arg in ('kronos-root','model','tokenizer','out'): ap.add_argument('--'+arg,required=True)
    args=ap.parse_args(); sys.path.insert(0,args.kronos_root)
    from model import Kronos,KronosTokenizer
    torch.set_num_threads(4); torch.manual_seed(9)
    tok=KronosTokenizer.from_pretrained(args.tokenizer).eval()
    mdl=Kronos.from_pretrained(args.model).eval()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    x=torch.randn(1,16,6); a=torch.arange(16).reshape(1,16).float(); b=a*3
    stamp=torch.tensor([0,10,0,4,10]).float().repeat(1,16,1)
    ctx=torch.randn(1,16,mdl.d_model)
    seq={'s1_ids':{1:'length'},'s2_ids':{1:'length'}}
    specs=[
      ('tokenizer-encode',Encode(tok),(x,),['x'],['s1_ids','s2_ids'],dict(seq,x={1:'length'})),
      ('tokenizer-decode',Decode(tok),(a,b),['s1_ids','s2_ids'],['x'],dict(seq,x={1:'length'})),
      ('predictor-s1',S1(mdl),(a.int(),b.int(),stamp.int()),['s1_ids','s2_ids','stamp'],['logits','context','embedding','time_embedding'],dict(seq,stamp={1:'length'},context={1:'length'})),
      ('predictor-s2',S2(mdl),(ctx,a[:,-1:].int()),['context','s1_ids'],['logits'],{'context':{1:'length'}})]
    reports=[]; files=[]
    for name,wrapper,inputs,names,outputs,axes in specs:
        wrapper.eval(); reset_rope(wrapper); path=out/(name+'.onnx')
        with torch.no_grad():
            torch.onnx.export(wrapper,inputs,str(path),input_names=names,output_names=outputs,dynamic_axes=axes,opset_version=18,dynamo=False)
        onnx.checker.check_model(str(path))
        opts=ort.SessionOptions(); opts.intra_op_num_threads=4
        sess=ort.InferenceSession(str(path),opts,providers=['CPUExecutionProvider'])
        for length in (16,32,256):
            if name=='tokenizer-encode': test=(torch.randn(1,length,6),)
            elif name=='tokenizer-decode': test=(torch.randint(0,1024,(1,length)).float(),torch.randint(0,1024,(1,length)).float())
            elif name=='predictor-s1': test=(torch.randint(0,1024,(1,length),dtype=torch.int32),torch.randint(0,1024,(1,length),dtype=torch.int32),stamp[:,:1].repeat(1,length,1).int())
            else: test=(torch.randn(1,length,mdl.d_model),torch.tensor([[123]],dtype=torch.int32))
            with torch.no_grad(): expected=wrapper(*test)
            if isinstance(expected,torch.Tensor): expected=(expected,)
            actual=sess.run(None,{k:v.numpy() for k,v in zip(names,test)})
            for i,(ref,got) in enumerate(zip(expected,actual)):
                np.testing.assert_allclose(got,ref.numpy(),rtol=2e-4,atol=3e-5)
                reports.append({'graph':name,'length':length,'output':outputs[i],'maxAbsError':float(np.max(np.abs(got-ref.numpy())))})
        files.append({'name':name,'url':'./models/'+path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        print(name,path.stat().st_size,'validated',flush=True)
    with torch.no_grad():
        reference=tok.encode(x,half=True); encoded=specs[0][1](x)
        for ref,got in zip(reference,encoded): torch.testing.assert_close(got.long(),ref)
        torch.testing.assert_close(specs[1][1](*encoded),tok.decode(reference,half=True),rtol=1e-5,atol=1e-6)
        native_logits,native_context=mdl.decode_s1(a.int(),b.int(),stamp)
        exported=specs[2][1](a.int(),b.int(),stamp.int())
        torch.testing.assert_close(exported[0],native_logits[:,-1,:])
        torch.testing.assert_close(exported[1],native_context)
    (out/'graph-parity.json').write_text(json.dumps({'passed':True,'torch':torch.__version__,'onnxruntime':ort.__version__,'checks':reports},indent=2))
    manifest={'schema':2,'runtime':{'onnxruntimeWeb':'1.22.0','url':'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.22.0/dist/ort.webgpu.min.mjs'},'models':[{'id':'kronos-mini','tokenizer':'Kronos-Tokenizer-2k','status':'graph-validated','browserDefaults':{'lookback':256,'horizon':24,'samples':1},'maxContext':2048,'files':files}]}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))

if __name__=='__main__': main()
