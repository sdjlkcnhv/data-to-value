#!/usr/bin/env python3
"""Render both built-in synthetic demos with the production page renderers (stdlib only)."""

import argparse
from pathlib import Path

from configure_preferences import PROFILES, render as render_preferences
from console_utils import configure_console
from render_candidate_scores import render as render_scores


CASES = {
    "academic": [
        ("同一学生的练习与成绩变化", "按学生描述周内变化，提出关联问题。", "student_id、week、practice_minutes、quiz_score；4名合成学生各3周。", "练习时长不是随机分配；不能解释为因果。", "先做学生内变化图，并检查个体差异。", [None, 3, 2, 4, 2]),
        ("按学生划分的泛化评估设计", "比较按行与按学生划分所对应的预测目标。", "同一student_id重复出现；记录数与独立学生数不同。", "仅4位学生，估计波动大；没有新学校数据。", "先明确预测新学生还是同一学生的后续测验，再设计验证。", [None, 3, 2, 3, 3]),
        ("缺失练习记录的敏感性分析", "检查缺失处理是否改变探索性判断。", "S03第2周practice_minutes为空；样例只有1处缺失。", "不能从1处缺失推断真实缺失机制。", "比较保留缺失与明确假设下的敏感性结果。", [None, 2, 2, 4, 3]),
    ],
    "business": [
        ("履约异常复盘清单", "给运营团队列出需要复盘的迟交订单。", "12个订单中5个delivery_days大于promised_days。", "交付天数为事后字段；不能作为下单时预警输入。", "先用SQL或筛选生成清单，核对异常原因与责任渠道。", [None, 4, 4, 3, 3]),
        ("退货原因补录试点", "为售后增加结构化原因记录，支持后续改进。", "4个return_flag=1，但缺少原因和处理记录。", "没有售后触达记录；原因标签与采集责任需确认。", "先明确原因分类、采集人和覆盖率，再评估试点。", [None, 3, 3, 2, 3]),
        ("交付承诺规则检查", "复核不同渠道的承诺天数与履约差异。", "channel、category、promised_days、delivery_days可作分组描述。", "样例很小，缺少旺淡季、库存与物流信息。", "先复核现有承诺规则，不直接调整生产承诺。", [None, 3, 4, 2, 2]),
    ],
}


def demo_report(mode):
    dimensions = [dict(id=r[0], label=r[1], weight=r[2]) for r in PROFILES[mode]]
    candidates = []
    for index, (name, summary, data, risk, next_step, values) in enumerate(CASES[mode], 1):
        scores = {}
        for dimension, value in zip(dimensions, values):
            unknown = value is None
            scores[dimension["id"]] = {
                "value": value,
                "basis": "未知" if unknown else "假设",
                "reason": ("未检索文献，不能确认创新度。" if mode == "academic" else "无成本、毛利及增量效果证据，不能评估净价值。") if unknown else "为演示分项取舍而设置的假设分数，不代表真实项目评估。",
                "evidence": "examples/README.md中的数据边界；真实任务须补证据。" if unknown else "演示设定：已有分析人员和可读CSV；按评分细则作假设性估分。",
            }
        candidates.append(dict(id=f"{mode}-{index}", name=name, summary=summary,
            data_basis="合成样例：" + data, risks=risk, next_step=next_step,
            time="演示假设：1–3人日；实际日历周期待核。", cost="演示假设：复用现有人员；金额与持续成本未知。",
            maturity="机会假设", eligibility="conditional", scores=scores))
    label = "学术版" if mode == "academic" else "企业版"
    return dict(mode=mode, title=label + " · 合成样例，非真实成果",
        decision="比较三个演示候选；正式任务须实际审核、确认偏好并重新评分。",
        weight_basis="仅供演示的初始权重，未替用户确认；任一关键维度未知时不显示完整总分。",
        dimensions=dimensions, candidates=candidates,
        recommendation="这里没有预选方案。请观察分项与未知，再在对话中明确选择；本页不会自动开始实验或业务试点。")


def main():
    configure_console()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    banner = '<aside style="padding:14px;background:#fff2d5;color:#573f16;text-align:center">合成样例演示 · 非真实项目成果 · 页面操作不代表真实任务确认</aside>'
    (args.output_dir / "start.html").write_text(render_preferences(), encoding="utf-8")
    for mode in PROFILES:
        for kind, html in [("preferences", render_preferences(mode)), ("comparison", render_scores(demo_report(mode)))]:
            target = args.output_dir / f"{mode}-{kind}.html"
            target.write_text(html.replace("<body>", "<body>" + banner), encoding="utf-8")
            print("Generated: " + str(target.resolve()))


if __name__ == "__main__":
    main()
