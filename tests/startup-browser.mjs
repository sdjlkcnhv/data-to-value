// Optional actual-browser check: node tests/startup-browser.mjs <Edge/Chrome executable>
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
  await call('Emulation.setDeviceMetricsOverride',{width:1200,height:1100,deviceScaleFactor:1,mobile:false});
  await call('Page.navigate',{url:pathToFileURL(path.join(root,'examples/start.html')).href});
  for(let i=0;i<50;i++){
    if(await evaluate('Boolean(document.getElementById("confirm"))')) break;
    await new Promise(r=>setTimeout(r,100));
  }
  assert.equal(await evaluate('document.getElementById("confirm").disabled'),true);
  assert.equal(await evaluate('document.querySelectorAll("[aria-pressed=true]").length'),0);
  await evaluate('document.querySelectorAll("#mode-options button")[0].click()');
  assert.equal(await evaluate('document.querySelectorAll("#weights input[type=number]").length'),5);
  await evaluate('(()=>{const x=document.querySelector("#weights input[type=number]"); x.value=0; x.dispatchEvent(new Event("input"));})()');
  assert.equal(await evaluate('document.getElementById("confirm").disabled'),false);
  await evaluate('document.querySelectorAll("#mode-options button")[1].click()');
  assert.match(await evaluate('document.getElementById("reply").value'), /企业版/);
  await evaluate('document.querySelectorAll("#mode-options button")[0].click()');
  assert.equal(await evaluate('document.querySelector("#weights input[type=number]").value'),'0');
  await evaluate('document.querySelectorAll("#weights input[type=number]").forEach(x=>{x.value=0;x.dispatchEvent(new Event("input"));})');
  assert.equal(await evaluate('document.getElementById("confirm").disabled'),true);
  await evaluate('document.getElementById("reset").click()');
  assert.equal(await evaluate('document.getElementById("confirm").disabled'),false);
  assert.match(await evaluate('document.getElementById("reply").value'), /学术版/);
  const shot=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
  await fs.writeFile(path.join(profile,'startup.png'),Buffer.from(shot.data,'base64'));
  assert.deepEqual(errors,[]);
  console.log('PASS: unselected start, both modes, draft preservation, zero/all-zero, reset, reply and browser rendering.');
  console.log('Screenshot: '+path.join(profile,'startup.png'));
} finally {if(ws)ws.close();browser.kill();}
