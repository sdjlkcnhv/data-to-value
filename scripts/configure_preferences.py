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
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in weights.values()):
        raise ValueError("Preference weights must be finite positive numbers")
    if not math.isfinite(sum(weights.values())):
        raise ValueError("Total preference weight must be finite")
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
</style></head><body><noscript>请在对话中说明各项权重，或明确表示使用初始权重。</noscript><main>
<header><div id="mode" class="eyebrow"></div><h1>先告诉我，你更看重什么？</h1>
<p>先确认偏好，再依据审核过的数据生成候选方案。看到具体方案后，仍可调整权重。</p>
<p class="muted">拖动滑块或输入相对份额，各项会自动换算为百分比。初始配置仅供起步；接受它时直接确认即可。</p></header>
<section id="weights" class="grid" aria-label="指标权重"></section>
<section class="panel"><h2><label for="constraints">期限、预算或资源限制（选填）</label></h2>
<p class="muted">例如最多投入两周，或只能使用现有数据。这些限制会单独记录，不由综合分抵消。</p>
<textarea id="constraints" maxlength="4000" placeholder="没有明确限制可以留空。"></textarea>
<p class="muted">权重表达你的偏好。数据审核、事实依据和必要的验证不会因权重较低而被跳过。</p></section>
<section class="panel confirm-panel"><h2>确认后开始寻找想法</h2><p id="delivery-note" class="muted"></p>
<div class="toolbar"><button id="confirm" type="button"></button><button id="reset" class="secondary" type="button">恢复初始权重</button></div>
<p id="status" class="status" role="status" aria-live="polite">初始权重尚未确认。</p>
<details id="reply-details"><summary>查看可发送到对话的偏好文字</summary><textarea id="reply" aria-label="偏好确认文字" readonly></textarea></details>
</section></main><script>
"use strict";
const config = __CONFIG__;
const byId = id => document.getElementById(id);
const weights = Object.fromEntries(config.dimensions.map(d => [d.id,d.weight]));
const controls = new Map();
let pending = false, submitted = false;
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
const modeLabel = config.mode === "academic" ? "学术版" : "企业版";
document.title = modeLabel + " · 想法生成前的偏好设置";
byId("mode").textContent = modeLabel + " · 生成候选前";
byId("confirm").textContent = config.submit_path ? "确认偏好并继续" : "复制偏好，回到对话";
byId("delivery-note").textContent = config.submit_path ? "确认后，偏好会直接交回本次任务，无需复制或上传文件。" : "将偏好文字发送到对话后即可继续；单独打开此文件不会自动把选择传回对话。";
for (const dimension of config.dimensions) {
  const card = element("article",undefined,"card"), heading = element("div",undefined,"heading");
  const share = element("output",undefined,"share");
  heading.append(element("h2",dimension.label),share);
  card.append(heading,element("p",dimension.description,"muted description"));
  const row = element("div",undefined,"controls"), slider = element("input"), number = element("input");
  slider.type = "range"; number.type = "number";
  for (const input of [slider,number]) { input.min = "1"; input.max = "100"; input.step = "1"; input.value = dimension.weight; }
  slider.setAttribute("aria-label",dimension.label+"权重滑块"); number.setAttribute("aria-label",dimension.label+"权重份额");
  slider.addEventListener("input",() => {number.value = slider.value; weights[dimension.id] = Number(slider.value); refresh();});
  number.addEventListener("input",() => {weights[dimension.id] = number.value === "" ? NaN : Number(number.value); slider.value = number.value; refresh();});
  row.append(slider,number); card.append(row);
  const track = element("div",undefined,"track"), fill = element("div",undefined,"fill"); track.append(fill); card.append(track);
  byId("weights").append(card); controls.set(dimension.id,{slider,number,share,fill});
}
function validWeights() {return Object.values(weights).every(v => Number.isInteger(v) && v >= 1 && v <= 100);}
function refresh() {
  const valid = validWeights(), sum = Object.values(weights).reduce((a,b) => a+b,0);
  for (const d of config.dimensions) {
    const ui = controls.get(d.id), percent = valid ? 100*weights[d.id]/sum : null;
    ui.share.textContent = percent === null ? "—" : percent.toFixed(1)+"%";
    ui.fill.style.width = percent === null ? "0%" : percent+"%";
  }
  byId("confirm").disabled = pending || submitted || !valid;
  if (!valid) {
    byId("status").textContent = "各项请输入1–100的整数份额，再确认偏好。";
    byId("reply").value = "";
  } else {
    if (!pending && !submitted) byId("status").textContent = "偏好尚未提交；可以直接确认初始权重，也可以先调整。";
    byId("reply").value = "我确认使用"+modeLabel+"。生成候选前的权重份额为："+config.dimensions.map(d => d.label+" "+weights[d.id]).join("、")+"（请统一归一化）。"+(byId("constraints").value.trim() ? "另外有这些约束："+byId("constraints").value.trim()+"。" : "")+"请先核验数据，再按这些偏好寻找和比较实质不同的想法；最终方案仍由我选择。";
  }
}
function freeze(value) {
  for (const ui of controls.values()) {ui.slider.disabled = value; ui.number.disabled = value;}
  byId("constraints").disabled = value; byId("reset").disabled = value;
}
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
    const response = await fetch(config.submit_path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({schema_version:1,mode:config.mode,weights,constraints:byId("constraints").value.trim(),confirmed:true})});
    const payload = await response.json().catch(() => null);
    if (!response.ok || !payload || !payload.saved) throw new Error(payload && payload.error ? payload.error : "Confirmation unavailable");
    submitted = true; pending = false; refresh();
    byId("status").textContent = "偏好已提交，可以返回对话查看后续进展。";
    byId("confirm").textContent = "已确认偏好";
  } catch (error) {
    pending = false; freeze(false); refresh(); byId("reply-details").open = true;
    byId("status").textContent = "暂未收到提交成功的回执（原因：" + (error && error.message ? error.message : "未知") + "）。可以重试，或复制下方偏好文字发送到对话。";
  }
});
refresh();
</script></body></html>"""


def render(mode, submit_path=None):
    config = {
        "mode": mode,
        "dimensions": [dict(zip(("id", "label", "weight", "description"), row)) for row in PROFILES[mode]],
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
                preferences = validate_preferences(json.loads(self.rfile.read(length)), expected_mode=mode)
            except (ValueError, OSError) as error:
                self.respond(400, json.dumps({"error": str(error)}))
                return
            receipt = {
                "schema_version": 1, "mode": mode, "weights": preferences["weights"],
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
    parser.add_argument("--mode", choices=PROFILES, required=True)
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
