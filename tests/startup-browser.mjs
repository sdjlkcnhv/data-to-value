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
  await evaluate('document.querySelectorAll("#presets button")[1].click()');
  assert.equal(await evaluate('document.querySelector("#weights input[type=number]").value'),'40');
  const shot=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
  await fs.writeFile(path.join(profile,'startup.png'),Buffer.from(shot.data,'base64'));
  for(const [name,relative] of [['listing','publishing/preview.html'],['comparison','examples/business-comparison.html']]) {
    await call('Page.navigate',{url:pathToFileURL(path.join(root,relative)).href});
    for(let i=0;i<40;i++){if(await evaluate('document.readyState === "complete" && document.querySelector("h1") !== null'))break;await new Promise(r=>setTimeout(r,100));}
    assert.equal(await evaluate('document.documentElement.scrollWidth <= innerWidth'),true);
    const image=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
    await fs.writeFile(path.join(profile,name+'.png'),Buffer.from(image.data,'base64'));
  }
  // Test the real local receiver through a browser, including its Origin validation.
  const receipt=path.join(profile,'confirmed.json');
  collector=spawn(process.env.PYTHON || 'python',[path.join(root,'scripts/configure_preferences.py'),
    '--output',path.join(profile,'local.html'),'--result',receipt,'--timeout','45'],{windowsHide:true,stdio:['ignore','pipe','pipe']});
  const localUrl=await new Promise((resolve,reject)=>{
    let output='';const timer=setTimeout(()=>reject(new Error('Collector startup timed out')),10000);
    collector.stdout.on('data',chunk=>{output+=chunk.toString();const match=output.match(/Preference page: (http:\/\/[^\s]+)/);if(match){clearTimeout(timer);resolve(match[1]);}});
    collector.on('error',e=>{clearTimeout(timer);reject(e);});
  });
  await call('Page.navigate',{url:localUrl});
  for(let i=0;i<50;i++){
    if(await evaluate('Boolean(document.getElementById("connection")) && document.getElementById("connection").textContent.includes("可直接提交")')) break;
    await new Promise(r=>setTimeout(r,100));
  }
  await evaluate('document.querySelectorAll("#mode-options button")[1].click(); document.querySelectorAll("#presets button")[1].click(); document.getElementById("confirm").click()');
  let saved;
  for(let i=0;i<50;i++){
    try{saved=JSON.parse(await fs.readFile(receipt,'utf8'));break;}catch{}
    await new Promise(r=>setTimeout(r,100));
  }
  assert.equal(saved.mode,'business');assert.equal(saved.confirmed,true);assert.equal(saved.weights.time,35);
  assert.equal(saved.source,'local_interactive_confirmation');
  for(let i=0;i<30;i++){
    if(await evaluate('document.getElementById("status").textContent.includes("设置已保存")')) break;
    await new Promise(r=>setTimeout(r,100));
  }
  assert.match(await evaluate('document.getElementById("status").textContent'), /设置已保存/);
  assert.equal(await evaluate('document.getElementById("confirm").disabled'),true);
  assert.deepEqual(errors,[]);
  console.log('PASS: both modes, draft preservation, zero/all-zero, presets, desktop layout, real browser POST and saved receipt.');
  console.log('Screenshot: '+path.join(profile,'startup.png'));
} finally {if(ws)ws.close();browser.kill();if(collector)collector.kill();}
