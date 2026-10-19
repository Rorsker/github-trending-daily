# GitHub Trending 中文日报

使用 Python 标准库采集 GitHub Trending daily，优先关注 AI Agent、开发工具、Skills / 插件与模型基础设施，通过 Codex CLI 或 JSON 导入生成中文 Markdown 日报。

## 功能

- 实时采集并归档原始页面、观察快照和内容哈希，保留页面排名及可见指标。
- 每期目标 8 个新项目；不足 8 个时按实际数量生成，已收录仓库按 owner/repo 不区分大小写永久去重。
- 日报只包含日期标题、项目名称与 GitHub 链接、Trending 排名、Stars、Forks、今日新增星标、功能简介和推荐理由，不出现星号字符。
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
{"items":[{"name":"owner/repo","summary_zh":"根据采集描述概括功能。","reason_zh":"说明关注理由，不宣称未经验证的能力。"}]}
```

```powershell
python -B ./trending.py analyze --snapshot ./output/2026-10-19/snapshots/SNAPSHOT.json --output-dir ./output/2026-10-19 --backend json --analysis-file ./analysis.json
```

将 SNAPSHOT.json 和 owner/repo 替换为真实快照文件名与该快照中尚未收录的仓库。输入必须包含 1–8 个不同项目，两个文本字段均含中文；未知项目、历史项目、重复名称、额外字段及无效 JSON 会被拒绝。结构见 analysis.schema.json。

## 数据与历史

输出包括 raw、snapshots、content、reports、receipts、logs 和锁文件；这些都是本地运行数据，不应提交到 Git。reports 下每份完整报告包含 report.md、analysis.json 和 manifest.json。缓存会校验报告及分析内容，复用同一份成功缓存只返回原文件，不算生成另一份日报。

历史从最终 github-trending-YYYY-MM-DD.md，以及带 no-repeat-v1 标记的成功报告归档读取。启用去重前未采用的分析草稿不计入历史。只过滤分析候选，不修改原始快照或重排来源排名。请保留历史日报和归档。

GitHub daily 是滚动视图，不提供可核实的官方历史榜单日期。Stars 和新增星标只代表采集时点的页面值；缺失或缩写指标记为 null，不猜测为零。功能简介限于捕获的仓库自述，推荐理由属于 AI 判断，项目不下载 README 或实测仓库能力。

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

支持 -Backend json、-AnalysisFile、-Model 与 -Python。项目不创建定时任务、不发送消息，也不自动发布日报。错误和锁恢复见 RUNBOOK.md，格式和协作约定见 AGENTS.md。

## 许可证

MIT，见 LICENSE。
