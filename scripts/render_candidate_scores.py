#!/usr/bin/env python3
"""Render evidence-backed candidate scores as an offline interactive HTML report."""

import argparse
import json
import math
import webbrowser
from console_utils import configure_console
from pathlib import Path


BASES = {"已核验事实", "文献依据", "估算", "假设", "未知"}
MATURITIES = {"机会假设", "可验证方案", "已获支持方案"}


def require_text(obj, key, context):
    if not isinstance(obj.get(key), str) or not obj[key].strip():
        raise ValueError(f"{context}.{key}: requires nonempty text")


def validate(data):
    if not isinstance(data, dict):
        raise ValueError("Input must be a JSON object")
    for key in ("title", "decision", "weight_basis"):
        require_text(data, key, "report")
    if data.get("mode") not in ("academic", "business"):
        raise ValueError("mode must be academic or business")
    dimensions = data.get("dimensions")
    candidates = data.get("candidates")
    if not isinstance(dimensions, list) or not dimensions:
        raise ValueError("dimensions must be a nonempty array")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidates must be a nonempty array")
    dimension_ids = set()
    for dimension in dimensions:
        if not isinstance(dimension, dict):
            raise ValueError("Each dimension must be an object")
        for key in ("id", "label"):
            require_text(dimension, key, "dimension")
        if dimension["id"] in dimension_ids:
            raise ValueError("Duplicate dimension id: " + dimension["id"])
        dimension_ids.add(dimension["id"])
        weight = dimension.get("weight")
        if type(weight) not in (int, float) or not math.isfinite(weight) or weight <= 0:
            raise ValueError("Dimension weights must be finite positive numbers")
    if not math.isfinite(sum(item["weight"] for item in dimensions)):
        raise ValueError("Total dimension weight must be finite")
    candidate_ids = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("Each candidate must be an object")
        for key in (
            "id", "name", "summary", "data_basis", "risks", "time", "cost", "next_step"
        ):
            require_text(candidate, key, "candidate")
        if candidate["id"] in candidate_ids:
            raise ValueError("Duplicate candidate id: " + candidate["id"])
        candidate_ids.add(candidate["id"])
        if candidate.get("maturity") not in MATURITIES:
            raise ValueError("Unknown candidate maturity")
        if candidate.get("eligibility") not in ("ready", "conditional", "blocked"):
            raise ValueError("eligibility must be ready, conditional, or blocked")
        scores = candidate.get("scores")
        if not isinstance(scores, dict) or set(scores) != dimension_ids:
            raise ValueError("Each candidate must include exactly the same score dimensions")
        for dimension_id, score in scores.items():
            if not isinstance(score, dict) or "value" not in score:
                raise ValueError("Each score requires an explicit value or null")
            value = score["value"]
            if value is not None and (type(value) is not int or not 1 <= value <= 5):
                raise ValueError("Score values must be integers 1-5 or null")
            for key in ("reason", "evidence", "basis"):
                require_text(score, key, candidate["id"] + "." + dimension_id)
            if score["basis"] not in BASES:
                raise ValueError("Unknown score basis")
            if (value is None) != (score["basis"] == "未知"):
                raise ValueError("Unknown scores must use null and basis 未知 together")
    if "recommendation" in data and not isinstance(data["recommendation"], str):
        raise ValueError("recommendation must be text")
    return data


HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>候选方案比较</title>
<style>
:root{color-scheme:light;--ink:#173042;--muted:#586d7b;--line:#d9e4e9;--blue:#236c90;--paper:#fff}
*{box-sizing:border-box}body{margin:0;background:#f1f5f7;color:var(--ink);font:15px/1.65 system-ui,"Microsoft YaHei",sans-serif}
[hidden]{display:none!important}
main{max-width:1240px;margin:auto;padding:36px 28px 52px}h1{font-size:30px;line-height:1.3;margin:10px 0 14px}h2{font-size:20px;margin:0 0 16px}h3{font-size:18px;margin:12px 0}
p{margin:8px 0}.muted{color:var(--muted)}.eyebrow{font-weight:700;color:var(--blue)}.panel,.card{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:22px;margin-top:20px}
.weights{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:14px}
.weight{display:grid;gap:6px}.weight input{width:100%;padding:9px 11px;border:1px solid #a7bdc9;border-radius:7px;font:inherit}
.weight output{color:var(--blue);font-size:13px}.toolbar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:14px}
button{background:var(--blue);color:white;border:0;border-radius:7px;padding:10px 15px;cursor:pointer;font:inherit}
button:disabled{opacity:.45;cursor:default}button.secondary{background:#e7f0f5;color:var(--ink)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:16px}.card{margin:0;min-width:0}
.badges{display:flex;gap:7px;flex-wrap:wrap}.badge{display:inline-block;border-radius:5px;padding:3px 8px;background:#edf3f6;font-size:12px}
.conditional{background:#fff2d5;color:#73530d}.blocked{background:#fbe7e5;color:#92382f}.ready{background:#e4f3ed;color:#246246}
.track{height:12px;background:#edf1f4;border-radius:8px;margin:10px 0 4px;overflow:hidden}.fill{height:100%;background:var(--blue);width:0}
.axis{display:flex;justify-content:space-between;font-size:12px;color:var(--muted)}.total{font-size:25px;font-weight:700}
.fact{margin:12px 0;overflow-wrap:anywhere}.fact strong{display:block;font-size:13px;color:var(--muted)}
.choice{display:flex;align-items:center;gap:8px;padding:10px;background:#f1f6f8;border-radius:8px;margin-top:16px}
.choice input{width:18px;height:18px;flex-shrink:0}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:550px}
th,td{border-bottom:1px solid var(--line);text-align:left;padding:12px;vertical-align:top;overflow-wrap:anywhere}th{background:#f4f8fa}
.rating{display:inline-block;min-width:50px;text-align:center;padding:4px 9px;border-radius:6px;font-weight:700}
.s1{background:#f4e9de}.s2{background:#eeeade}.s3{background:#e2edf0}.s4{background:#cce5ee}.s5{background:#aed6e5}.unknown{background:#f0f0f0;color:#59626a}
.basis{font-size:12px;color:var(--muted);margin-top:4px}details{margin-top:14px;border-top:1px solid var(--line);padding-top:12px}summary{cursor:pointer;font-weight:600}
.evidence-item{margin-top:12px;border-left:3px solid #c9dce6;padding-left:12px;overflow-wrap:anywhere}
textarea{width:100%;min-height:105px;font:inherit;border:1px solid #a7bdc9;border-radius:8px;padding:12px;margin-top:12px;resize:vertical}
.warning{color:#894d10}.status{padding:8px 0}.selection{border:2px solid #bed8e5}
noscript{display:block;padding:20px;background:#fff2d5}
@media(max-width:640px){main{padding:20px 14px}.panel,.card{padding:16px}h1{font-size:24px}.weights{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media print{body{background:#fff}main{padding:0;max-width:none}.panel,.card{break-inside:avoid}.toolbar,.choice,.selection{display:none}.scroll{overflow:visible}.cards{display:block}.card{margin:12px 0}}
</style>
</head>
<body><noscript>此交互报告需要JavaScript。请查看随报告提供的评分表及证据说明。</noscript>
<main>
<header><div id="mode" class="eyebrow"></div><h1 id="title"></h1>
<p id="intro" class="muted">评分帮助理解取舍，最终方案由你选择。综合分不是成功概率。</p></header>
<section class="panel"><h2>调整比较偏好</h2><p id="weight-basis" class="muted"></p>
<div id="weights" class="weights"></div>
<div class="toolbar"><button id="reset" class="secondary" type="button">恢复初始权重</button>
<span class="muted">输入权重份额，系统统一归一化；分项评分和证据保持不变。</span></div>
<div id="ranking" class="status" role="status" aria-live="polite"></div></section>
<section class="panel"><h2>方案比较</h2><div id="cards" class="cards"></div></section>
<section class="panel"><h2>评分矩阵</h2><p id="matrix-note" class="muted">各维度均为1–5分，越高越有利。未知单独显示。</p>
<div class="scroll"><table id="matrix"></table></div></section>
<section id="advice-panel" class="panel" hidden><h2>建议与取舍</h2><p id="advice"></p></section>
<section class="panel selection"><h2>由你决定下一步</h2>
<p>可以选择一个方案，也可以先补证据、调整比较条件或暂不选择。选择后复制下方文字并发送到对话，才会继续推进。</p>
<p id="selection-status" class="muted" role="status">尚未选择方案。</p>
<textarea id="selection-text" aria-label="待发送的方案选择" readonly placeholder="选择方案后，这里会生成回复文字。"></textarea>
<div class="toolbar"><button id="copy" type="button" disabled>复制选择</button><button id="clear" type="button" class="secondary">清除选择</button><span id="copy-status" class="muted" role="status"></span></div>
</section>
</main>
<script>
"use strict";
const report = __REPORT_DATA__;
const eligibilityLabels = {ready:"可比较", conditional:"条件性参考", blocked:"暂不参与"};
const byId = (id) => document.getElementById(id);
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function totalScore(candidate, weights) {
  if (candidate.eligibility === "blocked") return null;
  let result = 0, sum = 0;
  for (const dimension of report.dimensions) {
    const score = candidate.scores[dimension.id].value;
    const weight = weights[dimension.id];
    if (score === null || !Number.isFinite(weight) || weight <= 0) return null;
    result += score * weight;
    sum += weight;
  }
  return Number.isFinite(result) && sum > 0 ? result / sum : null;
}
const weights = Object.fromEntries(report.dimensions.map(d => [d.id,d.weight]));
const inputs = new Map(), weightLabels = new Map(), totalLabels = new Map(), fills = new Map();
let selectedCandidate = null;
function updateSelection() {
  if (!selectedCandidate) return;
  const sum = Object.values(weights).reduce((a,b) => a+b,0);
  const valid = Number.isFinite(sum) && sum > 0 && Object.values(weights).every(v => Number.isFinite(v) && v > 0);
  byId("selection-status").textContent = "待发送的选择："+selectedCandidate.id+" · "+selectedCandidate.name;
  const preference = valid ? report.dimensions.map(d => d.label+" "+(100*weights[d.id]/sum).toFixed(1)+"%").join("、") : "权重待修正";
  byId("selection-text").value = "我选择方案 "+selectedCandidate.id+"（"+selectedCandidate.name+"）。本次比较偏好："+preference+"。请在当前授权范围内推进下一步："+selectedCandidate.next_step;
  byId("copy").disabled = !valid;
  byId("copy-status").textContent = valid ? "" : "请先修正权重，再复制选择。";
}
document.title = report.title;
const academic = report.mode === "academic";
byId("title").textContent = report.title;
byId("mode").textContent = (academic ? "学术版" : "企业版") + " · " + report.decision;
byId("intro").textContent = academic ? "评分用于比较研究取舍，最终研究方向由你选择。综合分不代表论文录用概率。" : "评分帮助理解业务取舍，最终方案由你选择。综合分不是成功概率或收益保证。";
byId("matrix-note").textContent = academic ? "各维度均为1–5分，越高越有利。创新度依据相关工作比较，未知项单独显示；评分与证据成熟度分别判断。" : "各维度均为1–5分，越高越有利。时间越短、成本越低，对应得分越高。未知单独显示。";
byId("weight-basis").textContent = "初始权重依据：" + report.weight_basis;
for (const dimension of report.dimensions) {
  const label = element("label", undefined, "weight");
  label.append(element("span",dimension.label));
  const input = element("input"); input.type = "number"; input.min = "0.1"; input.step = "any";
  input.value = dimension.weight; input.setAttribute("aria-label", dimension.label + "权重");
  const share = element("output"); label.append(input, share); byId("weights").append(label);
  inputs.set(dimension.id, input); weightLabels.set(dimension.id, share);
  input.addEventListener("input", () => { weights[dimension.id] = Number(input.value); refresh(); });
}
function fact(parent, label, value) {
  const block = element("div",undefined,"fact");
  block.append(element("strong",label),element("span",value)); parent.append(block);
}
for (const candidate of report.candidates) {
  const card = element("article",undefined,"card");
  const badges = element("div",undefined,"badges");
  badges.append(element("span",candidate.maturity,"badge"),element("span",eligibilityLabels[candidate.eligibility],"badge "+candidate.eligibility));
  card.append(badges,element("h3",candidate.id+" · "+candidate.name),element("p",candidate.summary));
  const total = element("div",undefined,"total"); totalLabels.set(candidate.id,total); card.append(total);
  const track = element("div",undefined,"track"); const fill = element("div",undefined,"fill");
  fills.set(candidate.id,fill); track.append(fill); card.append(track);
  const axis = element("div",undefined,"axis"); axis.append(element("span","0"),element("span","5")); card.append(axis);
  fact(card,"数据依据",candidate.data_basis); fact(card,academic ? "研究周期估算" : "时间估算",candidate.time); fact(card,academic ? "资源投入估算" : "成本估算",candidate.cost);
  fact(card,"关键风险与未知",candidate.risks); fact(card,"下一步",candidate.next_step);
  const details = element("details"); details.append(element("summary","查看评分依据"));
  for (const dimension of report.dimensions) {
    const score = candidate.scores[dimension.id];
    const item = element("div",undefined,"evidence-item");
    item.append(element("strong",dimension.label+" · "+(score.value === null ? "未知" : score.value+"/5")));
    item.append(element("p",score.reason),element("p","依据类型："+score.basis,"basis"),element("p","证据："+score.evidence,"basis"));
    details.append(item);
  }
  card.append(details);
  const choice = element("label",undefined,"choice"), radio = element("input");
  radio.type = "radio"; radio.name = "candidate"; radio.value = candidate.id;
  radio.disabled = candidate.eligibility === "blocked"; radio.setAttribute("aria-label","选择方案 "+candidate.id);
  choice.append(radio,element("span",radio.disabled ? "先解决阻断项" : "选择方案 "+candidate.id));
  radio.addEventListener("change",() => {
    selectedCandidate = candidate;
    updateSelection();
  });
  card.append(choice); byId("cards").append(card);
}
const thead = element("thead"), header = element("tr");
header.append(element("th","维度 / 当前权重"));
for (const candidate of report.candidates) header.append(element("th",candidate.id+" · "+candidate.name));
thead.append(header); byId("matrix").append(thead);
const tbody = element("tbody"), rowLabels = new Map();
for (const dimension of report.dimensions) {
  const row = element("tr"), label = element("th"); rowLabels.set(dimension.id,label); row.append(label);
  for (const candidate of report.candidates) {
    const score = candidate.scores[dimension.id], cell = element("td");
    cell.append(element("span",score.value === null ? "未知" : score.value+"/5","rating "+(score.value === null ? "unknown" : "s"+score.value)));
    cell.append(element("div",score.basis,"basis")); row.append(cell);
  }
  tbody.append(row);
}
byId("matrix").append(tbody);
function refresh() {
  const sum = Object.values(weights).reduce((a,b) => a+b,0);
  const valid = Number.isFinite(sum) && sum > 0 && Object.values(weights).every(v => Number.isFinite(v) && v > 0);
  for (const dimension of report.dimensions) {
    const share = valid ? (100*weights[dimension.id]/sum).toFixed(1)+"%" : "—";
    weightLabels.get(dimension.id).textContent = "当前占比 "+share;
    rowLabels.get(dimension.id).textContent = dimension.label+" / "+share;
  }
  const ranked = [];
  for (const candidate of report.candidates) {
    const total = valid ? totalScore(candidate,weights) : null;
    totalLabels.get(candidate.id).textContent = !valid ? "权重待修正" : candidate.eligibility === "blocked" ? "暂不参与" : total === null ? "待补证据" : total.toFixed(1)+"/5"+(candidate.eligibility === "conditional" ? " · 条件性参考" : "");
    fills.get(candidate.id).style.width = total === null ? "0%" : (100*total/5)+"%";
    fills.get(candidate.id).parentElement.hidden = total === null;
    fills.get(candidate.id).parentElement.nextElementSibling.hidden = total === null;
    if (candidate.eligibility === "ready" && total !== null) ranked.push({id:candidate.id,score:Number(total.toFixed(1))});
  }
  if (!valid) byId("ranking").textContent = "请输入各维度的正数权重；当前暂停综合比较。";
  else if (!ranked.length) byId("ranking").textContent = "目前没有可作正式总分比较的方案；请查看分项依据与待补条件。";
  else {
    const best = Math.max(...ranked.map(item => item.score));
    const top = ranked.filter(item => item.score === best).map(item => item.id);
    byId("ranking").textContent = "当前可比较方案中分数最高："+top.join("、")+"（"+best.toFixed(1)+"/5）。"+(top.length > 1 ? "按显示精度并列。" : "")+"这仅表示评分排序，方案仍由你选择。";
  }
  updateSelection();
}
byId("reset").addEventListener("click",() => {
  for (const d of report.dimensions) { weights[d.id] = d.weight; inputs.get(d.id).value = d.weight; }
  refresh();
});
byId("clear").addEventListener("click",() => {
  selectedCandidate = null;
  document.querySelectorAll('input[name="candidate"]').forEach(r => {r.checked = false;});
  byId("selection-text").value = ""; byId("selection-status").textContent = "尚未选择方案。";
  byId("copy").disabled = true; byId("copy-status").textContent = "";
});
byId("copy").addEventListener("click",async () => {
  try { await navigator.clipboard.writeText(byId("selection-text").value); byId("copy-status").textContent = "已复制，请发送到对话。"; }
  catch (_) { byId("selection-text").focus(); byId("selection-text").select(); byId("copy-status").textContent = "请手动复制选中的文字并发送到对话。"; }
});
if (report.recommendation) { byId("advice-panel").hidden = false; byId("advice").textContent = report.recommendation; }
refresh();
</script></body></html>"""


def render(data):
    validate(data)
    payload = json.dumps(data, ensure_ascii=True, allow_nan=False).replace("<", r"\u003c")
    return HTML.replace("__REPORT_DATA__", payload)


def main():
    configure_console()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--preferences-file", type=Path, help="Apply explicitly confirmed weights from the initial preference form")
    parser.add_argument(
        "--open", dest="open_report", action="store_true",
        help="Request opening the finished report in the local desktop browser; "
             "use the host application's preview instead in remote environments",
    )
    args = parser.parse_args()
    try:
        if args.input.resolve() == args.output.resolve():
            raise ValueError("Input and output paths must differ")
        if args.preferences_file and args.preferences_file.resolve() == args.output.resolve():
            raise ValueError("Preferences and output paths must differ")
        data = json.loads(args.input.read_text(encoding="utf-8-sig"))
        if args.preferences_file:
            from configure_preferences import validate_preferences

            validate(data)
            preferences = validate_preferences(
                json.loads(args.preferences_file.read_text(encoding="utf-8-sig")),
                expected_mode=data["mode"], dimension_ids=[d["id"] for d in data["dimensions"]],
            )
            for dimension in data["dimensions"]:
                dimension["weight"] = preferences["weights"][dimension["id"]]
            data["weight_basis"] = "用户在想法生成前确认的权重；各项按相对份额统一归一化。"
            if preferences.get("constraints"):
                data["weight_basis"] += "另有约束：" + preferences["constraints"]
        result = render(data)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
    except (OSError, ValueError) as error:
        parser.exit(2, "Error: " + str(error) + "\n")
    print("Generated: " + str(args.output.resolve()))
    if args.open_report:
        report_uri = args.output.resolve().as_uri()
        try:
            requested = webbrowser.open(report_uri, new=2)
        except (OSError, webbrowser.Error) as error:
            print("Browser launch unavailable: " + str(error))
            requested = False
        if requested:
            print("Browser open requested: " + report_uri)
        else:
            print("Report saved; use the host preview or open this file: " + report_uri)


if __name__ == "__main__":
    main()
