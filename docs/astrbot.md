# AstrBot 接入

本项目只调用 AstrBot OpenAPI，不直接连接 QQ 协议。适配模块依据 AstrBot 官方发布的 `/openapi.json`：`POST /api/v1/im/messages`，`X-API-Key` 请求头，请求体为 `{"umo":"...","message":"..."}`，成功响应包含 `"status":"ok"`。部署者仍需确认朋友服务器上的 AstrBot 版本、OpenAPI 开关和实际路由；若该版本的路由不同，设置 `ASTRBOT_MESSAGE_PATH`，并核对其认证与响应契约。

1. 在 AstrBot 管理界面启用 OpenAPI，创建具备 `im` scope、仅用于推送的 Key，并确认服务地址可从日报主机访问。生产环境优先 HTTPS；同机可用 `http://127.0.0.1:端口`。
2. 从 AstrBot 的会话列表或 API 获取目标 QQ 群 UMO，填入 `ASTRBOT_TARGET_UMO`。不要把普通 QQ 群号直接当作 UMO。
3. 在服务器私有环境文件中设置 `ASTRBOT_API_URL`、`ASTRBOT_API_KEY`、`ASTRBOT_TARGET_UMO`；确认 `ASTRBOT_MESSAGE_PATH` 与该版本 OpenAPI 一致。
4. 手动运行一次 `python daily.py`，检查输出中的 `delivery.status` 和 `data/YYYY-MM-DD/delivery/` 下的回执，再启用 timer。

未填写三个 AstrBot 参数时仅生成 Markdown，不发送。缺少其中任一参数会报错。日报按最多 1800 字符分段；每个分段获得 AstrBot `status: ok` 才记为已发送。网络超时与 429、502、503、504 最多尝试 3 次；若结果仍不确定，回执标为 `uncertain`，后续运行停止自动重发，需人工核对 QQ 群后处理。回执只保存日报与目标的哈希和分段计数，不保存 Key 或 UMO 明文。

官方文档：https://docs.astrbot.app/dev/openapi.html
