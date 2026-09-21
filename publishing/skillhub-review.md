# SkillHub 调研与本次改进

调研日期：2026-09-21。实际读取首页、公开列表接口、六个技能的SKILL.md及公开前端中的发布字段；未登录发布后台、未安装或执行这些第三方技能。样本来自下载排序前列及 research/data 检索结果，不代表全站完整排名。接口快照与来源见 [观察记录](skillhub-observations.json)。

| 样本 | 当时展示下载数 | 借鉴点 | 本项目落地 |
|---|---:|---|---|
| [编程专家](https://www.skillhub.cn/skills/indiv-ebandao/dev-expert) | 1,229,137 | 场景明确、验证与交接成闭环 | 首次交付和续作指引；不照搬冗长门禁 |
| [self-improving agent](https://www.skillhub.cn/skills/clawhub_pskoett/self-improving-agent) | 1,222,307 | 把错误与用户反馈转成可追溯改进 | 作者侧反馈、试用和迭代记录；不增加隐藏记忆或遥测 |
| [Find Skills](https://www.skillhub.cn/skills/clawhub_root/find-skills) | 1,004,793 | 自然语言场景、明确安装入口和示例对话 | 三段可复制启动提示词；不猜测用户客户端 |
| [Smart Charts](https://www.skillhub.cn/skills/user_814dbe54/smart-charts) | 92,983 | 明确文件输入、离线HTML产出、黄金示例 | 内置两版合成数据及四个交互预览 |
| [Data Analysis](https://www.skillhub.cn/skills/clawhub_ivangdavila/data-analysis) | 91,513 | 结论连接决策、口径、证据和下一步 | 精简候选卡；保留数据驱动的开放机会发现 |
| [Deep Research Pro](https://www.skillhub.cn/skills/clawhub_parags/deep-research-pro) | 61,027 | 一句话产出、来源引用、报告结构 | 首屏突出选题/机会与审核；不照搬固定本机路径 |

这些数字是平台展示计数，不能当成独立用户或归因于某种文案；不同来源还有同步差异。列表版本与读取文件中的版本不一定一致，例如编程专家与Deep Research Pro的元数据存在差异，未将其描述为某一不可变版本的完整源码审计。

## 可借鉴的共性

1. 首屏先回答“帮谁做什么、输入什么、得到什么”。技术细节和约束移到后续说明。
2. 给用户一条可复制的起步方式，并让成果可预览。可运行样例比长功能清单更容易评估。
3. 安装条件和交付出口要具体；明确无需独立API Key的边界，而不是承诺所有平台零配置。
4. 名称、中文简介、分类与具体搜索场景对应，避免堆入不相关热词。

这些是可验证的产品假设，不是保证提高下载量的排名技巧。高下载技能也存在硬编码路径、范围过宽、默认识别宿主等问题，本项目没有沿用。

## 已实现与待验证

已实现：中文名称/简介、README首屏与启动提示词、原创封面和图标、两版合成数据与交互页面、首次交付与续作规范、发布表单文案、增长与简历证据计划。

待验证：SkillHub实际表单提交、目标用户下载转化、豆包等宿主内完整流程。当前不将私有仓库改为公开，也不声称已获平台认证或下载增长。
