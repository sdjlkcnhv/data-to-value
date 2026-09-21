#!/usr/bin/env python3
"""Create an offline preference form; optionally collect confirmation on localhost."""

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
from pathlib import Path
import secrets
import time
import webbrowser
from console_utils import configure_console


PROFILES = {
    "academic": [
        ("novelty", "创新度", 30, "相对已有研究，提出有实质新增量的问题、测量、设计或方法。"),
        ("significance", "研究意义", 25, "研究结果能够改变对重要领域问题的理解或实践。"),
        ("data_fit", "数据适配", 20, "现有数据的变量、覆盖范围与独立样本适合研究问题。"),
        ("feasibility", "实施可行性", 15, "所需时间、能力、算力和协作条件与现有资源匹配。"),
        ("validation", "验证设计", 10, "能够用合适对照、评价和确认资料检验主要主张。"),
    ],
    "business": [
        ("value", "潜在净价值", 30, "计入实施和运营成本后，仍有可解释的增收、降本或决策改善空间。"),
        ("time", "见效时间", 20, "更早获得可用验证结果，或达到共同约定的业务里程碑。"),
        ("cost", "执行成本", 20, "启动、接入、人工和持续维护的投入更容易承受。"),
        ("action", "落地条件", 15, "具备使用者、执行责任、行动渠道和维护条件。"),
        ("measure", "效果可测量性", 15, "能够记录结果并判断相对现状是否产生实际改善。"),
    ],
}


def validate_preferences(data, expected_mode=None, dimension_ids=None):
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Preference data must use schema_version 1")
    mode = data.get("mode")
    if not isinstance(mode, str) or mode not in PROFILES or (expected_mode is not None and mode != expected_mode):
        raise ValueError("Preference mode does not match this task")
    if data.get("confirmed") is not True:
        raise ValueError("Preferences have not been explicitly confirmed")
    expected_ids = set(dimension_ids if dimension_ids is not None else (row[0] for row in PROFILES[mode]))
    weights = data.get("weights")
    if not isinstance(weights, dict) or set(weights) != expected_ids:
        raise ValueError("Preference dimensions must exactly match the report")
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in weights.values()):
        raise ValueError("Preference weights must be finite nonnegative numbers")
    if not math.isfinite(sum(weights.values())) or sum(weights.values()) <= 0:
        raise ValueError("Total preference weight must be finite and positive")
    constraints = data.get("constraints", "")
    if not isinstance(constraints, str) or len(constraints) > 4000:
        raise ValueError("Constraints must be text of at most 4000 characters")
    return data


HTML = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>想法生成前的偏好设置</title><style>
:root{color-scheme:light;--ink:#173042;--muted:#586d7b;--line:#d9e4e9;--blue:#236c90}
*{box-sizing:border-box}body{margin:0;background:#f1f5f7;color:var(--ink);font:15px/1.65 system-ui,"Microsoft YaHei",sans-serif}
main{max-width:1050px;margin:auto;padding:36px 24px 48px}h1{font-size:30px;line-height:1.35;margin:10px 0}h2{font-size:18px;margin:0}p{margin:8px 0}
.eyebrow{color:var(--blue);font-weight:700}.muted{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,290px),1fr));gap:16px;margin:24px 0}
.card,.panel{border:1px solid var(--line);background:#fff;border-radius:14px;padding:20px;min-width:0}.panel{margin-top:18px}
.heading{display:flex;justify-content:space-between;align-items:center;gap:12px}.share{font-size:22px;color:var(--blue);font-weight:700}
.description{min-height:50px;font-size:14px}.controls{display:flex;align-items:center;gap:12px;margin-top:18px}
input[type=range]{min-width:0;flex:1;accent-color:var(--blue)}input[type=number]{width:76px;padding:8px;border:1px solid #a7bdc9;border-radius:7px;font:inherit}
.track{background:#edf1f4;height:7px;border-radius:8px;overflow:hidden;margin:16px 0 4px}.fill{height:100%;background:var(--blue);width:0}
textarea{width:100%;min-height:80px;resize:vertical;padding:12px;border:1px solid #a7bdc9;border-radius:8px;font:inherit;margin-top:10px}
.toolbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:16px}button{border:0;border-radius:7px;background:var(--blue);color:#fff;padding:11px 18px;font:inherit;cursor:pointer}
button.secondary{background:#e7f0f5;color:var(--ink)}button:disabled{opacity:.5;cursor:default}.status{margin:14px 0 0;color:var(--blue)}.confirm-panel{border:2px solid #bed8e5}
details{margin-top:14px}summary{cursor:pointer}.error{color:#92382f}noscript{display:block;padding:20px;background:#fff2d5}
@media(max-width:640px){main{padding:22px 14px}h1{font-size:25px}.card,.panel{padding:17px}}

:root{--ink:#163932;--muted:#60766f;--line:#dce6df;--blue:#166b62}
body{background:radial-gradient(ellipse at 85% 0%,#e0eee4 0,transparent 50%),#f7f7f2;font-family:system-ui,"Microsoft YaHei",sans-serif}
main{max-width:1140px;padding:42px 28px 70px}header{padding:12px 0 24px}h1{font-size:clamp(28px,4vw,44px);letter-spacing:-1px;margin:14px 0}.eyebrow{font-size:12px;letter-spacing:2px;text-transform:uppercase}
.panel,.card{border-radius:20px;box-shadow:0 6px 24px #193d2b05}.panel{padding:26px}.grid{grid-template-columns:1fr;margin:18px 0;gap:10px}.card{display:grid;grid-template-columns:1fr 1fr;column-gap:32px;padding:20px 24px}.heading{grid-column:1}.description{grid-column:1;min-height:0;margin-bottom:0;font-size:13px}.controls{grid-column:2;grid-row:1/3;margin:0}.track{display:none}.share{font-size:20px;font-variant-numeric:tabular-nums}.controls input[type=number]{width:72px;background:#f6f9f5;border:1px solid var(--line);text-align:center}.controls input[type=range]{height:30px;cursor:pointer}
button{border-radius:12px;font-weight:600;transition:background .15s,box-shadow .15s}button:hover:not(:disabled){box-shadow:0 3px 12px #17433720}button.secondary{background:#edf3ed}button:focus-visible,input:focus-visible,textarea:focus-visible,summary:focus-visible{outline:3px solid #d3a44b;outline-offset:3px}
#mode-options{display:grid;grid-template-columns:1fr 1fr;gap:16px}#mode-options button{padding:24px;text-align:left;border:2px solid var(--line);background:#fff;color:var(--ink);font-size:21px;position:relative}#mode-options button[aria-pressed=true]{border-color:var(--blue);background:#eef7f1}#mode-options button[aria-pressed=true]:after{content:'✓';position:absolute;right:20px;top:22px;color:var(--blue)}.mode-detail{display:block;font-size:13px;font-weight:400;color:var(--muted);margin-top:8px;padding-right:14px}
.section-title{display:flex;justify-content:space-between;gap:18px;align-items:center;margin-top:28px}.section-title span{color:var(--muted);font-size:13px}.presets{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}.presets button{font-size:13px;padding:8px 14px}.confirm-panel{border:1px solid #b9d3c5;background:#f1f7f0}.connection{display:inline-flex;padding:5px 12px;border-radius:30px;background:#e6eee5;font-size:12px;color:#446353;margin-bottom:10px}.allocation{height:8px;display:flex;overflow:hidden;border-radius:8px;background:#e5ece4;margin:18px 0 10px}.allocation span{transition:width .15s}.summary{font-size:13px;color:var(--muted)}[hidden]{display:none!important}textarea{background:#fff;border-color:var(--line)}.brand{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:20px;margin-bottom:28px;font-size:12px;letter-spacing:1px}.brand strong{letter-spacing:2px}.step{color:var(--muted)}
@media(max-width:640px){main{padding:24px 16px 40px}.panel{padding:20px}#mode-options{grid-template-columns:1fr;gap:10px}#mode-options button{padding:18px}.card{display:block;padding:18px}.controls{margin-top:16px}.section-title{align-items:start;flex-direction:column;gap:3px}.brand{font-size:10px;align-items:flex-start;gap:12px}.brand strong{white-space:nowrap}.brand .step{text-align:right;max-width:160px}.toolbar button{flex-grow:1}}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
</style></head><body><noscript>请在对话中说明各项权重，或明确表示使用初始权重。</noscript><main>
<div class="brand"><strong>DATA-TO-VALUE</strong><span class="step">01 设置偏好　 /　 02 审核数据　 /　 03 发现想法</span></div><header><div id="mode" class="eyebrow"></div><h1>从你的目标开始。</h1>
<p>选择方向，告诉我们什么更重要。审核数据之后，再一起找到值得验证的想法。</p>
<p class="muted">一次确认版本与权重；看到候选方案后，你仍然可以调整。</p></header>
<section class="panel"><h2>第一步 · 版本与权重</h2><p>两项同等展示，不替你选择。切换版本会显示对应指标，并保留各自尚未提交的权重。</p><div id="mode-options" class="toolbar" role="group" aria-label="选择学术版或企业版"></div></section>
<div id="weight-section" hidden><div class="section-title"><h2>什么对你更重要？</h2><span>拖动或输入份额，自动换算占比</span></div><div id="presets" class="presets"></div><div id="allocation" class="allocation" aria-hidden="true"></div><p id="weight-summary" class="summary"></p></div>
<section id="weights" class="grid" aria-label="指标权重"></section>
<section class="panel"><h2><label for="constraints">期限、预算或资源限制（选填）</label></h2>
<p class="muted">例如最多投入两周，或只能使用现有数据。这些限制会单独记录，不由综合分抵消。</p>
<textarea id="constraints" maxlength="4000" placeholder="没有明确限制可以留空。"></textarea>
<p class="muted">权重表达你的偏好。数据审核、事实依据和必要的验证不会因权重较低而被跳过。</p></section>
<section class="panel confirm-panel"><div id="connection" class="connection"></div><h2>准备好，就从这里开始</h2><p id="delivery-note" class="muted"></p>
<div class="toolbar"><button id="confirm" type="button"></button><button id="download" class="secondary" type="button" disabled>保存设置文件</button><button id="reset" class="secondary" type="button">恢复初始权重</button></div>
<p id="status" class="status" role="status" aria-live="polite">初始权重尚未确认。</p>
<details id="reply-details"><summary>查看可发送到对话的偏好文字</summary><textarea id="reply" aria-label="偏好确认文字" readonly></textarea></details>
</section></main><script>
"use strict";
const config = __CONFIG__;
const byId = id => document.getElementById(id);
const drafts = Object.fromEntries(Object.entries(config.profiles).map(([mode, dimensions]) => [mode,Object.fromEntries(dimensions.map(d => [d.id,d.weight]))]));
let weights = config.mode ? drafts[config.mode] : {};
const controls = new Map();
let pending = false, submitted = false;
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
let modeLabel = "尚未选择版本";
const modeButtons = new Map();
for (const [mode,label] of [["academic","学术版"],["business","企业版"]]) {
  const button = element("button",label,"secondary"); button.type="button";
  button.append(element("span",mode === "academic" ? "从已有数据发现研究问题与论文选题" : "从存量数据发现降本、增收与决策机会","mode-detail"));
  button.addEventListener("click",() => {if (!pending && !submitted) selectMode(mode);});
  byId("mode-options").append(button); modeButtons.set(mode,button);
}
function selectMode(mode) {
  config.mode = mode; config.dimensions = mode ? config.profiles[mode] : [];
  weights = mode ? drafts[mode] : {};
  modeLabel = mode === "academic" ? "学术版" : mode === "business" ? "企业版" : "尚未选择版本";
  byId("weights").replaceChildren(); controls.clear();
  byId("weight-section").hidden = !mode;
  byId("presets").replaceChildren();
  if (mode) {
    const options = mode === "academic" ? [["均衡考虑",[20,20,20,20,20]],["探索创新",[40,25,15,10,10]],["优先可行",[15,15,25,30,15]]] : [["均衡考虑",[20,20,20,20,20]],["尽快验证",[20,35,15,10,20]],["控制投入",[20,15,35,20,10]]];
    for (const [label,values] of options) {const b=element("button",label,"secondary"); b.type="button"; b.addEventListener("click",()=>{if(pending||submitted)return;config.dimensions.forEach((d,i)=>{weights[d.id]=values[i];controls.get(d.id).slider.value=values[i];controls.get(d.id).number.value=values[i];});refresh();}); byId("presets").append(b);}
  }
  for (const [key,button] of modeButtons) {button.setAttribute("aria-pressed",String(key===mode)); button.className = key===mode ? "" : "secondary";}
document.title = modeLabel + " · 想法生成前的偏好设置";
byId("mode").textContent = modeLabel + " · 生成候选前";
byId("confirm").textContent = config.submit_path ? "确认并继续 →" : "复制设置，回到对话 →";
byId("connection").textContent = config.submit_path ? "本机任务连接 · 可直接提交" : "离线页面 · 尚未连接对话";
byId("delivery-note").textContent = config.submit_path ? "点击后设置将保存到本次任务，助手读取后继续；无需手动复制。" : "此页面无法直接发送消息。复制后在对话中粘贴发送，或保存设置文件并交给助手；也可以直接在对话中说出版本与权重。";
for (const dimension of config.dimensions) {
  const card = element("article",undefined,"card"), heading = element("div",undefined,"heading");
  const share = element("output",undefined,"share");
  heading.append(element("h2",dimension.label),share);
  card.append(heading,element("p",dimension.description,"muted description"));
  const row = element("div",undefined,"controls"), slider = element("input"), number = element("input");
  slider.type = "range"; number.type = "number";
  for (const input of [slider,number]) { input.min = "0"; input.max = "100"; input.step = "1"; input.value = weights[dimension.id]; }
  slider.setAttribute("aria-label",dimension.label+"权重滑块"); number.setAttribute("aria-label",dimension.label+"权重份额");
  slider.addEventListener("input",() => {number.value = slider.value; weights[dimension.id] = Number(slider.value); refresh();});
  number.addEventListener("input",() => {weights[dimension.id] = number.value === "" ? NaN : Number(number.value); slider.value = number.value; refresh();});
  row.append(slider,number); card.append(row);
  const track = element("div",undefined,"track"), fill = element("div",undefined,"fill"); track.append(fill); card.append(track);
  byId("weights").append(card); controls.set(dimension.id,{slider,number,share,fill});
}
refresh();
}
function validWeights() {return config.mode !== null && Object.values(weights).every(v => Number.isInteger(v) && v >= 0 && v <= 100) && Object.values(weights).reduce((a,b)=>a+b,0)>0;}
function refresh() {
  const valid = validWeights(), sum = Object.values(weights).reduce((a,b) => a+b,0);
  for (const d of config.dimensions) {
    const ui = controls.get(d.id), percent = valid ? 100*weights[d.id]/sum : null;
    ui.share.textContent = percent === null ? "—" : percent.toFixed(1)+"%";
    ui.fill.style.width = percent === null ? "0%" : percent+"%";
  }
  byId("confirm").disabled = pending || submitted || !valid;
  byId("download").disabled = pending || submitted || !valid;
  byId("reset").disabled = pending || submitted || !config.mode;
  byId("allocation").replaceChildren();
  const colors=["#166b62","#578677","#8daa89","#bea97a","#dfcca3"];
  config.dimensions.forEach((d,i)=>{const part=element("span");part.style.width=valid ? 100*weights[d.id]/sum+"%" : "0%";part.style.background=colors[i];byId("allocation").append(part);});
  byId("weight-summary").textContent=valid ? config.dimensions.map(d=>d.label+" "+(100*weights[d.id]/sum).toFixed(1)+"%").join(" · ") : "至少保留一个大于0的权重。";
  if (!valid) {
    byId("status").textContent = "请选择版本；各项可设0–100的整数份额，至少一项大于0。";
    byId("reply").value = "";
  } else {
    if (!pending && !submitted) byId("status").textContent = "偏好尚未提交；可以直接确认初始权重，也可以先调整。";
    byId("reply").value = "我确认使用"+modeLabel+"。生成候选前的权重份额为："+config.dimensions.map(d => d.label+" "+weights[d.id]).join("、")+"（请统一归一化）。"+(byId("constraints").value.trim() ? "另外有这些约束："+byId("constraints").value.trim()+"。" : "")+"请先核验数据，再按这些偏好寻找和比较实质不同的想法；最终方案仍由我选择。";
  }
}
function freeze(value) {
  for (const button of modeButtons.values()) button.disabled = value;
  for (const ui of controls.values()) {ui.slider.disabled = value; ui.number.disabled = value;}
  for(const b of byId("presets").querySelectorAll("button")) b.disabled=value;
  byId("constraints").disabled = value; byId("reset").disabled = value;
}
function preferencePayload() {return {schema_version:1,mode:config.mode,weights:{...weights},constraints:byId("constraints").value.trim(),confirmed:true};}
byId("download").addEventListener("click",()=>{if(!validWeights()||pending||submitted)return;const data={...preferencePayload(),source:"user_download",confirmed_at:new Date().toISOString()};const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:"application/json"}));const a=element("a");a.href=url;a.download="data-to-value-preferences.json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);byId("status").textContent="已请求保存设置文件；请将它交给当前对话，尚未自动提交。";});
byId("constraints").addEventListener("input",refresh);
byId("reset").addEventListener("click",() => {
  for (const d of config.dimensions) {weights[d.id] = d.weight; controls.get(d.id).slider.value = d.weight; controls.get(d.id).number.value = d.weight;}
  refresh();
});
byId("confirm").addEventListener("click",async () => {
  if (!validWeights() || pending || submitted) return;
  if (!config.submit_path) {
    try {await navigator.clipboard.writeText(byId("reply").value); byId("status").textContent = "已复制偏好，请发送到对话后继续。";}
    catch (_) {byId("reply-details").open = true; byId("reply").focus(); byId("reply").select(); byId("status").textContent = "请复制已选中的偏好文字并发送到对话。";}
    return;
  }
  pending = true; freeze(true); refresh(); byId("status").textContent = "正在提交偏好……";
  try {
    const controller = new AbortController();
    const timeout = setTimeout(()=>controller.abort(),10000);
    let response;
    try {response = await fetch(config.submit_path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(preferencePayload()),signal:controller.signal});} finally {clearTimeout(timeout);}
    const payload = await response.json().catch(() => null);
    if (!response.ok || !payload || !payload.saved) throw new Error(payload && payload.error ? payload.error : "Confirmation unavailable");
    submitted = true; pending = false; refresh();
    byId("status").textContent = "设置已保存到本次任务。返回对话后，助手将依据这份设置继续。";
    byId("confirm").textContent = "已确认偏好";
  } catch (error) {
    pending = false; freeze(false); refresh(); byId("reply-details").open = true;
    byId("status").textContent = "暂未收到提交成功的回执（原因：" + (error && error.message ? error.message : "未知") + "）。可以重试，或复制下方偏好文字发送到对话。";
  }
});
selectMode(config.mode);
</script></body></html>"""


def render(mode=None, submit_path=None):
    if mode is not None and mode not in PROFILES:
        raise ValueError("Unknown mode")
    config = {
        "mode": mode,
        "profiles": {key: [dict(zip(("id", "label", "weight", "description"), row)) for row in rows] for key, rows in PROFILES.items()},
        "submit_path": submit_path,
    }
    return HTML.replace("__CONFIG__", json.dumps(config, ensure_ascii=True).replace("<", r"\u003c"))


def request_browser(url):
    try:
        requested = webbrowser.open(url, new=2)
    except (OSError, webbrowser.Error):
        requested = False
    print(("Browser open requested: " if requested else "Open or preview this page: ") + url, flush=True)


def collect(mode, result_path, timeout, open_browser):
    token_path = "/" + secrets.token_urlsafe(24) + "/"
    state = {"saved": False}

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(3)
            super().setup()

        def log_message(self, *_args):
            pass

        def respond(self, status, body, content_type="application/json"):
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path != token_path:
                self.respond(404, '{"error":"Not found"}')
                return
            self.respond(200, render(mode, token_path + "confirm"), "text/html")

        def do_POST(self):
            if self.path != token_path + "confirm" or self.headers.get("Origin") != origin:
                self.respond(403, '{"error":"Invalid confirmation origin or path"}')
                return
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                self.respond(415, '{"error":"JSON required"}')
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 32768:
                    raise ValueError("Invalid request size")
                preferences = validate_preferences(json.loads(self.rfile.read(length)), expected_mode=None)
            except (ValueError, OSError) as error:
                self.respond(400, json.dumps({"error": str(error)}))
                return
            receipt = {
                "schema_version": 1, "mode": preferences["mode"], "weights": preferences["weights"],
                "constraints": preferences.get("constraints", ""), "confirmed": True,
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
                "source": "local_interactive_confirmation",
            }
            try:
                with result_path.open("x", encoding="utf-8") as handle:
                    json.dump(receipt, handle, ensure_ascii=False, allow_nan=False, indent=2)
            except OSError as error:
                self.respond(500, json.dumps({"error": str(error)}))
                return
            state["saved"] = True
            self.respond(200, '{"saved":true}')

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        origin = "http://127.0.0.1:" + str(server.server_port)
        url = origin + token_path
        server.timeout = 0.5
        print("Preference page: " + url, flush=True)
        print("Waiting for explicit confirmation; result: " + str(result_path), flush=True)
        if open_browser:
            request_browser(url)
        deadline = time.monotonic() + timeout
        while not state["saved"] and time.monotonic() < deadline:
            server.handle_request()
    if state["saved"]:
        print("Confirmed preferences: " + str(result_path), flush=True)
        return 0
    print("No preferences confirmed. Continue waiting in the conversation; do not assume defaults.", flush=True)
    return 3


def main():
    configure_console()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=PROFILES, help="Only preselect a mode already explicitly chosen by the user")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--result", type=Path, help="Collect confirmation locally and save JSON here")
    parser.add_argument("--open", action="store_true", dest="open_browser")
    parser.add_argument("--timeout", type=int, default=600, help="Local confirmation timeout in seconds (1-3600)")
    args = parser.parse_args()
    try:
        if not 1 <= args.timeout <= 3600:
            raise ValueError("Timeout must be between 1 and 3600 seconds")
        if args.result:
            if args.result.resolve() == args.output.resolve():
                raise ValueError("HTML and confirmation output paths must differ")
            if args.result.exists():
                raise ValueError("Confirmation file already exists; reuse it or choose a new path")
            args.result.parent.mkdir(parents=True, exist_ok=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render(args.mode), encoding="utf-8")
        print("Generated: " + str(args.output.resolve()), flush=True)
        if args.result:
            return collect(args.mode, args.result.resolve(), args.timeout, args.open_browser)
        if args.open_browser:
            request_browser(args.output.resolve().as_uri())
        return 0
    except (OSError, ValueError) as error:
        parser.exit(2, "Error: " + str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
