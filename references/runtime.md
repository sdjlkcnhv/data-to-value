# 安装与运行环境

用于安装、发布验收和环境变更恢复；普通数据任务复用已验收环境。导入文件、初始化依赖、页面交互通过是三个不同状态。安装器是否执行初始化由宿主决定；技能文本不能创建宿主没有的执行权限或安装钩子。

## 安装配置

默认选common，一次准备常用格式，不等用户上传后再决定安装哪些库。格式清单、读取范围和错误状态见 [数据读取](data-formats.md)。

| 配置 | 安装内容 | 验收 |
|---|---|---|
| core | Python标准库，无第三方包 | CSV/TSV、JSON/JSONL/NDJSON、文本、SQLite、ZIP清单样例 |
| tabular | requirements-tabular.txt | core样例加XLSX、pandas读取；含NumPy在内的全部直接依赖版本约束 |
| common | requirements-common.txt，包含tabular | 增加ODS、Parquet/Feather、DOCX、文本PDF、HTML/XML合成样例；XLS/XLSB/XLSM实现状态另记，不冒充已测 |
| ocr | requirements-ocr.txt，包含common | 还检查Tesseract程序、指定语言数据、图片识别和PDF渲染识别 |

Python最低3.10。版本范围和二进制wheel可用性不等于所有系统架构都兼容；本次实测和CI记录见 [兼容性矩阵](compatibility.md)。Tesseract系统程序与语言数据需在选配OCR的安装阶段由平台/管理员准备，脚本不静默安装系统包或下载模型。

## 首次初始化

由负责安装的助手在技能目录执行；其他工作目录使用脚本绝对路径。用户安装指令可以包含这一步，不应要求每次使用都手动处理：

```text
python scripts/setup_environment.py --profile common --install
```

不带 `--install` 只检查、不装包。已有环境的版本及样例都通过时直接复用；否则在 `--state-dir` 下的venv中安装，不改系统Python。默认状态目录 `~/.cache/data-to-value`，不可写时由助手选择用户授权的持久可写目录并显式传入 `--state-dir`；先检查可写性再安装，不反复盲换目录。不复制其他机器的venv作为跨平台安装方案。

安装前台等待完成再验收，不把后台进程启动当作完成。一次pip最多600秒，失败不无限重试；当前配置写失败回执。网络不可达、缺适配wheel、权限不足时保留具体原因，不以模型猜测替代。

输出 `runtime-core.json`、`runtime-tabular.json`、`runtime-common.json` 或 `runtime-ocr.json`，各配置分别保存，避免只验核心功能后覆盖常用数据环境记录。旧版runtime.json可作为解释器候选，但须按新版重新验收。

回执记录Python绝对路径、包版本、配置、时间、技能版本、逐格式样例结果、ready及失败原因。`reader_available_not_fixture_tested`不是实测通过；`not_in_profile`是不在该配置。每次升级技能/依赖或更换环境需重新验收；正常任务不反复运行pip。

## 按回执执行

后续页面、读取和分析均使用对应配置回执里的 `python`，无需shell激活venv：

```text
<回执中的Python> <技能目录>/scripts/read_data.py --input <数据文件> --output <工作区>/读取结果.json
```

不要安装到venv后又用另一个系统Python读取。缺少依赖时先判断是否用了错误解释器；确实未准备则报告具体缺口，切回安装维护任务处理，不在数据任务中临时安装。特殊格式/数据库权限不在common全包范围；不能替用户解密、猜连接信息或声称任何上传都可处理。

## 页面和平台能力

页面生成仍只依赖标准库，不等待common/OCR安装。两版偏好与评分页面使用宿主可交付目录，优先原生预览；本地桌面才能使用可达的回环接收器或浏览器打开。云端localhost不是用户的本机。沙箱可能禁止HTML脚本、剪贴板、回传；有原生输入则用原生输入，否则用对话明确确认。

环境回执固定标注 `page_display_and_callback: not_tested_by_environment_setup`。安装助手另测模式选择、偏好页展示和确认、权重沿用、比较页展示和最终选择；不能由本机成功推断豆包账号或另一宿主成功。每次重建沙箱的平台若不提供持久环境，技能不能保证依赖跨任务保留。
