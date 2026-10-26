# GitHub Trending 中文日报

使用 Python 标准库采集 GitHub Trending daily，优先关注 AI Agent、开发工具、Skills / 插件与模型基础设施，通过 Codex CLI 或 JSON 导入生成中文 Markdown 日报。

## 功能

- 实时采集并归档原始页面、观察快照和内容哈希，保留页面排名及可见指标。
- 每期目标 8 个新项目；不足 8 个时按实际数量生成，已收录仓库按 owner/repo 不区分大小写永久去重。
- 日报只包含纯文本日期标题、项目名称与 GitHub 链接、Trending 排名、Stars、Forks、今日新增星标和单段项目介绍，不出现星号或井号字符。
- 分析元数据、来源证据与回执独立归档，不进入读者版 Markdown。
- Codex 与 JSON 导入使用相同校验；没有新候选时返回 no-new-projects，不调用模型或生成重复日报。

## 环境

Python 3.12 或以上，无第三方 Python 依赖。默认分析后端需要在 PATH 中可用、已完成认证的 Codex CLI；使用 JSON 导入后端不需要 Codex。Windows 可通过 run_once.ps1 启动，Python 入口也可直接运行。

## 实时生成

从项目目录运行，日期目录应对应北京时间当日；下面日期仅为命令示例：

```powershell
python -B ./trending.py run --output-dir ./output/2026-10-19 --timeout 180
```

可用 --model 指定模型；省略时使用 CLI 默认模型。timeout 分别约束 HTTP 与模型阶段，而不是整条流水线的总耗时。成功时 stdout 返回包含 snapshot、report、analysis 绝对路径的 JSON。诊断输出到 stderr。

日常运行必须沿用同一个输出根目录；日期子目录采用 YYYY-MM-DD，以跨天共享历史。已有日报用户应继续使用原输出根目录，不要通过换目录清空去重历史。

## 分离采集与分析

仅采集实时页面：

```powershell
python -B ./trending.py collect --output-dir ./output/2026-10-19
```

针对已保存的 snapshot 使用 Codex 分析，不重复联网采集：

```powershell
python -B ./trending.py analyze --snapshot ./output/2026-10-19/snapshots/SNAPSHOT.json --output-dir ./output/2026-10-19 --timeout 180
```

也可由外部程序生成分析 JSON，通过已有接口导入：

```json
{"items":[{"name":"owner/repo","summary_zh":"说明项目的目的、适用场景、具体功能以及用户如何使用这些功能达成结果。","reason_zh":"解释所解决的工作流痛点，以及采用该项目后任务为何更易完成。"}]}
```

```powershell
python -B ./trending.py analyze --snapshot ./output/2026-10-19/snapshots/SNAPSHOT.json --output-dir ./output/2026-10-19 --backend json --analysis-file ./analysis.json
```

将 SNAPSHOT.json 和 owner/repo 替换为真实快照文件名与该快照中尚未收录的仓库。输入必须包含 1–8 个不同项目，两个文本字段均含中文；未知项目、历史项目、重复名称、额外字段及无效 JSON 会被拒绝。结构见 analysis.schema.json。

## 数据与历史

输出包括 raw、snapshots、content、reports、receipts、logs 和锁文件；这些都是本地运行数据，不应提交到 Git。reports 下每份完整报告包含 report.md、analysis.json 和 manifest.json。缓存会校验报告及分析内容，复用同一份成功缓存只返回原文件，不算生成另一份日报。

历史从最终 github-trending-YYYY-MM-DD.md，以及带 no-repeat-v1 标记的成功报告归档读取。启用去重前未采用的分析草稿不计入历史。只过滤分析候选，不修改原始快照或重排来源排名。请保留历史日报和归档。

GitHub daily 是滚动视图，不提供可核实的官方历史榜单日期。Stars 和新增星标只代表采集时点的页面值；缺失或缩写指标记为 null，不猜测为零。项目介绍的事实部分限于捕获的仓库自述，关注理由属于 AI 判断；描述稀疏时不补造细节。项目不下载 README 或实测仓库能力。

仓库文本作为不可信输入处理；Codex 提示禁止工具、命令和文件访问，仅传入公开仓库字段。分析子进程采用只读沙箱，产品不保存完整 CLI 会话或认证信息。

## 离线验证

```powershell
python -B -m unittest -v
```

测试使用公开仓库字段归一化的 HTML fixture、合成输入和 mock，不访问实时 GitHub 或模型服务。fixture 是离线样例，不代表当日榜单；上游 JSON 样例仅用于核对仓库名称，指标以 HTML fixture 为准。

## PowerShell 入口

```powershell
./run_once.ps1 -OutputDir ./output/2026-10-19 -TimeoutSeconds 180
```

支持 -Backend json、-AnalysisFile、-Model 与 -Python。`run_daily.ps1` 是 09:00 中国标准时间计划任务 `Codex-GitHub-Trending-Daily` 的入口：沿用项目内 `output/YYYY-MM-DD`，先确认当日已生成报告，再调用现有 `trending.py run`，最后通过飞书模块发送。运行状态和诊断日志位于当日 `automation/`，飞书回执位于当日 `delivery/`。同日重启会复用已生成报告，成功发送过的同版本不会重发。错误和锁恢复见 RUNBOOK.md，格式和协作约定见 AGENTS.md。

## Coolify 容器入口

`Dockerfile` 使用 Python 3.12 与固定版本的 Codex CLI。容器本身只运行轻量等待进程，不自动生成或推送日报；由 Coolify 的 Scheduled Task 执行 `python -B /app/daily.py --send`，时区为 `Asia/Shanghai`，计划时间为 09:00。正式切换前不要启用此任务。无推送测试使用 `python -B /app/daily.py`。`/data/output` 必须挂载 Coolify 持久卷，迁移既有 `output/` 的完整历史目录后再做正式生成。

在 Coolify 的私密环境变量中配置 `DEEPSEEK_API_KEY`。容器的 Codex CLI 默认使用 `deepseek-flash` 和 `https://api.deepseek.com/` 的 Responses API，可通过 `CODEX_MODEL_NAME`、`CODEX_MODEL_BASE_URL` 覆盖；设置 `TRENDING_REASONING_EFFORT=high` 以提高分析深度。本机 Windows 任务仍沿用本机 Codex 提供方和原推理设置。飞书推送仅在显式传入 `--send` 时启用，Linux 凭据从 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_OPEN_ID` 读取。不得将凭据放入 Git、镜像或日志。

## 许可证

MIT，见 LICENSE。
