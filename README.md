# FurryLoaderMC_Telegram_Bot

FurryLoaderMC 服务器专用 Telegram 机器人

## 配置文件示例 `config.json`：
（删掉注释）
```json
{
  "bot_token": "从 @BotFather 处获取的 机器人token",
  "group_id": "群组ID",
  "proxy_enabled": true,  //是否启用代理
  "proxy": "代理地址 例如 http://127.0.0.1:9000",  //不启用代理则""即可
  "bot_username": "bot用户名 需要加@",
  "bot_name": "bot名称",
  "server_ip": "服务器IP（用于机器人获取状态）",
  "server_port": 11451, //服务器端口（用于机器人获取状态）
  "server_ip_export": "服务器IP（给玩家看的）",
  "server_name": "服务器名称",
  "websocket_url": "WebSocket地址",
  "admin_id": "0" //管理员ID（私聊发送机器人 /getID 获取）
}
```
