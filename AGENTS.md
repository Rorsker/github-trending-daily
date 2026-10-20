# Agent 部署指南（Linux + AstrBot）

本文件面向受托在 Linux 服务器部署本仓库的 coding agent。项目是独立 Python 程序，不需要 Codex CLI。先读 `README.md` 和 `docs/astrbot.md`；以服务器上实际安装的 AstrBot OpenAPI 契约为准。

## 输入与边界

- 部署前确认目标服务器、可用的 Python 3.12+、systemd，以及操作者是否已提供 DeepSeek API Key。需要 QQ 推送时，还需 AstrBot API 地址、具备 `im` scope 的 API Key、目标群 UMO 和 AstrBot 版本。
- 在 `/opt/github-trending-daily` 放代码，在 `/etc/github-trending-daily/env` 放密钥和配置，在 `/var/lib/github-trending-daily` 放运行数据。已有部署先检查并保留数据及回执；不要用重新克隆、清空目录或换输出根目录绕过去重。
- 不把密钥写入仓库、命令参数、提交、终端输出或工单。不要复制开发者本机的日报、认证文件和 Windows 任务配置。
- AstrBot 未配置时可以先完成生成部署；不要宣称 QQ 推送已验证。任何发送结果不确定的回执需要先核对群消息，再决定是否人工恢复。

## 部署步骤

1. 确认 `/opt/github-trending-daily` 是否已有受管理的 checkout。新部署时直接克隆到该最终路径；已有部署时核对远端和当前改动，保留运行数据后按正常 Git 流程更新。不要在别处建虚拟环境再搬迁到 `/opt`。
2. 在最终路径创建 `.venv`，执行 `.venv/bin/python -m pip install -r requirements.txt` 和 `.venv/bin/python -m unittest -q`。`requirements.txt` 当前无需第三方包，但仍需验证 Python 版本与测试结果。
3. 建立系统用户 `github-trending`。从 `.env.example` 创建 `/etc/github-trending-daily/env`，权限设为仅管理员可读，填写 `DEEPSEEK_API_KEY` 和 `TRENDING_OUTPUT_ROOT=/var/lib/github-trending-daily`。不要在仓库中保留真实 `.env`。
4. 如需 QQ 推送，先对照该服务器的 AstrBot OpenAPI 确认消息路由、认证头、响应状态和目标 UMO；再填写 `ASTRBOT_API_URL`、`ASTRBOT_API_KEY`、`ASTRBOT_TARGET_UMO`，必要时调整 `ASTRBOT_MESSAGE_PATH`。仓库当前适配的契约见 `docs/astrbot.md`。
5. 将 `deploy/github-trending-daily.service` 和 `.timer` 安装到 `/etc/systemd/system/`，执行 `systemctl daemon-reload`。先用 `systemd-analyze verify` 检查两个单元，并确认 timer 的 `Asia/Shanghai` 每天 09:00 计划与服务器环境兼容。
6. 在完成密钥和 AstrBot 目标核对后，手动启动 service 一次。这会生成日报，配置了 AstrBot 时也会真实发送。检查 `systemctl status`、`journalctl -u github-trending-daily.service`、当日 `reports/*/report.md` 和 `delivery/` 回执；确认成功后再启用 timer。

## 验收与交接

- 报告 `python -m unittest -q`、手动 service 运行及 timer 状态的实际结果；没有 Key 或网络时明确写“未验证”，不要把 Mock 测试当成真实发送。
- 核对 `systemctl list-timers github-trending-daily.timer` 的下次触发时间，并确认本机时区显示与北京时间 09:00 的换算。`Persistent=true` 可能在启用后补跑错过的计划。
- 记录代码版本、报告文件路径及推送状态，不记录密钥、完整环境文件、聊天内容或群 UMO 明文。
