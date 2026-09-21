// Capture actual desktop UI assets: node tests/capture-preview.mjs <Edge/Chrome executable>
// Node 22+; uses built-in CDP WebSocket, no npm packages or network dependencies.
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {pathToFileURL, fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'data-to-value-browser-'));
const browser = spawn(process.argv[2], ['--headless=new', '--disable-gpu', '--no-first-run',
  '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], {windowsHide:true, stdio:'ignore'});
let ws;
let collector;
try {
  let port;
  for (let i=0; i<100; i++) {
    try {port = (await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]; break;} catch {}
    await new Promise(r=>setTimeout(r,100));
  }
  assert.ok(port, 'Browser debugging endpoint unavailable');
  const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  ws = new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
  let seq=0; const waiting=new Map(); const errors=[];
  ws.addEventListener('message', e=>{
    const d=JSON.parse(e.data);
    if(d.method==='Runtime.exceptionThrown') errors.push(d.params.exceptionDetails);
    const pending=waiting.get(d.id);
    if(pending){waiting.delete(d.id);clearTimeout(pending.timer);d.error?pending.reject(d.error):pending.resolve(d.result);}
  });
  const call=(method,params={})=>new Promise((resolve,reject)=>{
    const id=++seq;const timer=setTimeout(()=>{waiting.delete(id);reject(new Error('CDP timeout: '+method));},10000);
    waiting.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));
  });
  const evaluate=async expression=>{
    const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
    assert.equal(r.exceptionDetails,undefined,JSON.stringify(r.exceptionDetails));return r.result.value;
  };
  await call('Runtime.enable');await call('Page.enable');
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1080,deviceScaleFactor:1,mobile:false});
  for(const [name,relative] of [['startup-preview','examples/start.html'],['comparison-preview','examples/business-comparison.html']]){
    await call('Page.navigate',{url:pathToFileURL(path.join(root,relative)).href});
    for(let i=0;i<50;i++){if(await evaluate('document.readyState === "complete" && document.querySelector("h1") !== null'))break;await new Promise(r=>setTimeout(r,100));}
    if(name==='startup-preview')await evaluate('document.querySelectorAll("#mode-options button")[0].click()');
    await evaluate('document.fonts.ready'); await new Promise(r=>setTimeout(r,500));
    const shot=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await fs.writeFile(path.join(root,'assets',name+'.png'),Buffer.from(shot.data,'base64'));
  }
  assert.deepEqual(errors,[]);
  console.log('Captured actual desktop pages.');
} finally {if(ws)ws.close();browser.kill();if(collector)collector.kill();}
