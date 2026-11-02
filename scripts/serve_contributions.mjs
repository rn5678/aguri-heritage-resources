#!/usr/bin/env node
// Local development uses the production handler with a durable SQLite database.
// The service is deliberately bound to loopback and is never a production host.
import http from 'node:http';
import { readFile, mkdir, chmod, writeFile, stat } from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import { randomBytes } from 'node:crypto';
import { Readable } from 'node:stream';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import worker from '../contributions/worker.mjs';
import { LocalD1 } from '../contributions/local-db.mjs';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const site=path.join(root,'site');
const state=process.env.AGURI_LOCAL_STATE||path.join(root,'contributions','.local');
await mkdir(state,{recursive:true,mode:0o700});
await chmod(state,0o700);
const keyFile=path.join(state,'editor-key.txt');
let key;
try { key=(await readFile(keyFile,'utf8')).trim(); }
catch(error) {
 if(error.code!=='ENOENT')throw error;
 key=randomBytes(32).toString('hex');
 await writeFile(keyFile,key+'\n',{mode:0o600,flag:'wx'});
}
if(key.length<32)throw new Error('The local editor key must contain at least 32 characters.');
const db=new LocalD1(path.join(state,'contributions.sqlite'));
db.exec(await readFile(path.join(root,'contributions/schema.sql'),'utf8'));
const mime={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.json':'application/json; charset=utf-8','.svg':'image/svg+xml','.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png','.webp':'image/webp','.pdf':'application/pdf','.txt':'text/plain; charset=utf-8','.ttf':'font/ttf','.xml':'application/xml; charset=utf-8'};
const assets={async fetch(request){
 let pathname;
 try { pathname=decodeURIComponent(new URL(request.url).pathname); } catch { return new Response('Bad path',{status:400}); }
 if(pathname.split('/').some(part=>part.startsWith('.'))||pathname.includes('\\'))return new Response('Not found',{status:404});
 let file=path.resolve(site,'.'+pathname);
 if(!file.startsWith(site+path.sep))file=path.join(site,'index.html');
 try {
  if((await stat(file)).isDirectory())file=path.join(file,'index.html');
 }catch {
  if(!path.extname(file))file+='.html';
 }
 try {
  const info=await stat(file);
  if(!info.isFile())throw new Error('not file');
  return new Response(request.method==='HEAD'?null:Readable.toWeb(createReadStream(file)),{headers:{'Content-Type':mime[path.extname(file)]||'application/octet-stream','Content-Length':String(info.size),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
 }catch {return new Response('Not found',{status:404});}
}};
const port=Number(process.env.AGURI_PORT||8788);
const origin=`http://127.0.0.1:${port}`;
const environment={CONTRIBUTIONS_DB:db,EDITOR_KEY:key,ASSETS:assets};
const server=http.createServer(async(req,res)=>{
 try {
  if(req.headers.host!==`127.0.0.1:${port}`&&req.headers.host!==`localhost:${port}`){res.writeHead(403);res.end('Local host required');return;}
  const headers=new Headers();
  for(const [name,value] of Object.entries(req.headers))if(value!==undefined)headers.set(name,Array.isArray(value)?value.join(', '):value);
  headers.set('CF-Connecting-IP','127.0.0.1');
  const request=new Request(`http://${req.headers.host}${req.url}`,{method:req.method,headers,...(!['GET','HEAD'].includes(req.method)?{body:Readable.toWeb(req),duplex:'half'}:{})});
  const response=await worker.fetch(request,environment,{waitUntil(promise){promise.catch(()=>{});}});
  res.writeHead(response.status,Object.fromEntries(response.headers));
  if(!response.body)res.end();else Readable.fromWeb(response.body).pipe(res);
 }catch(error){console.error('Local request failed:',error.message);if(!res.headersSent)res.writeHead(500);res.end('Local request failed.');}
});
server.listen(port,'127.0.0.1',()=>{
 console.log(`Local contribution preview: ${origin}/contribute.html`);
 console.log(`Local editor dashboard: ${origin}/review.html`);
 console.log(`Local-only editor key saved at ${keyFile} (not printed or published).`);
});
for(const signal of ['SIGTERM','SIGINT'])process.on(signal,()=>server.close(()=>process.exit(0)));
