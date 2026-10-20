# GitHub Trending 中文日报

独立 Python 3.12+ 项目。每日采集 GitHub Trending，使用 DeepSeek API 对尚未收录的仓库生成中文介绍与关注理由，保存 Markdown 报告，并可通过 AstrBot OpenAPI 推送到 QQ 群。无需 Codex CLI、Docker 或第三方 Python 包。

## 安装

```sh
git clone https://github.com/Rorsker/github-trending-daily.git
cd github-trending-daily
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

编辑 `.env`，至少填写 `DEEPSEEK_API_KEY`。`.env` 是配置模板，不会由程序自动读取；手动运行前用 `set -a; . ./.env; set +a` 加载，或由 systemd 的 `EnvironmentFile` 加载。Key 不写入命令参数和日志。DeepSeek 模型默认 `deepseek-chat`，可用 `DEEPSEEK_MODEL` 指定。

## 运行

```sh
set -a; . ./.env; set +a
python daily.py
python -m unittest -q
```

`daily.py` 按北京时间确定日期，输出到 `TRENDING_OUTPUT_ROOT/YYYY-MM-DD/`。缺省根目录是当前目录的 `data/`。报告位于 `reports/<分析身份>/report.md`；同时保留原始 HTML、快照、分析 JSON、清单与诊断记录。当天重跑会复用已有有效报告，成功推送的同一日报不会重复发送。无新仓库时返回 `no-new-projects`，不生成重复日报。

可单独运行 `python trending.py collect --output-dir data/YYYY-MM-DD` 采集，或 `python trending.py analyze --snapshot <snapshot.json> --output-dir data/YYYY-MM-DD` 分析。离线验证可使用 `--backend json --analysis-file <analysis.json>`；导入内容仍受来源、中文字段及历史去重校验。

采集的是 GitHub Trending 滚动页面在执行时的观察，不是可回溯的官方历史榜单。Stars 等指标只代表采集时页面展示的值。已入选仓库按 owner/repo 永久去重；因此应备份整个 `data/`，不要清空历史来补数据。

## Linux 定时运行

示例单元在 `deploy/`。朋友需要先获得该 Private 仓库的读取权限。以有 `sudo` 权限的用户操作，完成上述安装后，将仓库放在 `/opt/github-trending-daily`，并执行：

```sh
sudo useradd --system --home /var/lib/github-trending-daily --shell /usr/sbin/nologin github-trending
sudo install -d -m 700 /etc/github-trending-daily
sudo install -m 600 .env.example /etc/github-trending-daily/env
sudoedit /etc/github-trending-daily/env
sudo install -m 644 deploy/github-trending-daily.service /etc/systemd/system/
sudo install -m 644 deploy/github-trending-daily.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start github-trending-daily.service
sudo systemctl enable --now github-trending-daily.timer
```

在私有环境文件中填写 DeepSeek Key，并将 `TRENDING_OUTPUT_ROOT` 设为 `/var/lib/github-trending-daily`。确认 `github-trending` 用户能读取 `/opt/github-trending-daily` 和其中的虚拟环境。`StateDirectory` 为服务用户建立可写的数据目录。

timer 使用 `Asia/Shanghai` 明确指定北京时间每天 09:00，与服务器本地时区无关。`Persistent=true` 会在机器错过计划时间后补跑；日报日期按实际北京时间计算，不伪造历史榜单日期。查看 `systemctl status github-trending-daily.service` 和 `journalctl -u github-trending-daily.service`。

AstrBot 参数和版本核对见 [docs/astrbot.md](docs/astrbot.md)。不配置 AstrBot 时，日报生成照常完成，不会发送消息。

## 组成

- `trending.py`：原有的采集、解析、快照校验、永久去重、报告渲染与归档；分析后端改为 DeepSeek HTTP API。
- `daily.py`：单次无人值守执行、当日缓存与可选发送。
- `astrbot_delivery.py`：独立 AstrBot OpenAPI 发送与本地防重回执。
- `test_trending.py`、`test_delivery.py`：离线测试，不使用真实 API Key。

MIT 许可，见 `LICENSE`。
