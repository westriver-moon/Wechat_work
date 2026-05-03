# 功能三 Linux 服务器部署文档（Ubuntu + Nginx + systemd）

本文档针对功能三（无登录版）部署，已按现网域名 bitist.top 填写关键配置。

## 1. 部署目标

需要在线提供以下地址：
- https://bitist.top/
- https://bitist.top/freshman
- https://bitist.top/senior
- https://bitist.top/wechat
- https://bitist.top/api/feature3_status

建议架构：
- Flask/Gunicorn 监听 127.0.0.1:5000
- Nginx 对外提供 80/443
- systemd 守护 Gunicorn

## 2. 前置准备

1. Ubuntu 22.04/24.04
2. bitist.top 已解析到服务器公网 IP
3. 安全组和防火墙已放通 80/443
4. 安装基础依赖

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip nginx
```

## 3. 代码与 Python 环境

```bash
sudo mkdir -p /opt/wechar_develop
sudo chown -R $USER:$USER /opt/wechar_develop

# 上传或拉取代码后进入后端目录
cd /opt/wechar_develop/Wechar_Develop/feature2-ai/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

## 4. .env 关键配置

```bash
cp .env.example .env
```

建议值（按需替换 token/key）：

```env
FLASK_ENV=production
PORT=5000
WECHAT_TOKEN=replace_with_your_token

DB_PATH=./feature3.db
FEATURE3_TICKET_MODE=1
FEATURE3_AUTO_AI_ANSWER=0
FEATURE3_ENABLE_WORKER=1
FEATURE3_WORKER_POLL_SECONDS=1.5
FEATURE3_SENIOR_KEY=replace_with_strong_secret
FEATURE3_HELP_URL=https://bitist.top/freshman
FEATURE3_ENABLE_WECHAT_PUSH=0

DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=replace_with_your_api_key
DEEPSEEK_MODEL=deepseek-chat
KB_FORCE_LEXICAL=1
```

## 5. Gunicorn 手动验证

```bash
cd /opt/wechar_develop/Wechar_Develop/feature2-ai/backend
source .venv/bin/activate
gunicorn -w 2 -b 127.0.0.1:5000 app:app
```

另开终端检查：

```bash
curl http://127.0.0.1:5000/api/demo_status
curl http://127.0.0.1:5000/api/feature3_status
```

## 6. systemd 持久化

```bash
sudo tee /etc/systemd/system/wechar-feature3.service > /dev/null <<'EOF'
[Unit]
Description=Wechar Feature3 Flask Service
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/wechar_develop/Wechar_Develop/feature2-ai/backend
Environment="PATH=/opt/wechar_develop/Wechar_Develop/feature2-ai/backend/.venv/bin"
ExecStart=/opt/wechar_develop/Wechar_Develop/feature2-ai/backend/.venv/bin/gunicorn -w 2 -b 127.0.0.1:5000 app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo chown -R www-data:www-data /opt/wechar_develop/Wechar_Develop/feature2-ai/backend
sudo systemctl daemon-reload
sudo systemctl enable wechar-feature3
sudo systemctl restart wechar-feature3
sudo systemctl status wechar-feature3
```

## 7. Nginx 配置

站点配置建议使用 deploy/nginx/wechat_assistant.conf，并确保以下值：
- server_name bitist.top
- ssl_certificate /etc/letsencrypt/live/bitist.top/fullchain.pem
- ssl_certificate_key /etc/letsencrypt/live/bitist.top/privkey.pem

启用与检查：

```bash
sudo ln -sf /etc/nginx/sites-available/wechat_assistant.conf /etc/nginx/sites-enabled/wechat_assistant.conf
sudo nginx -t
sudo systemctl reload nginx
```

## 8. HTTPS 证书（Let's Encrypt）

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d bitist.top
sudo certbot renew --dry-run
```

## 9. 微信后台配置

1. 服务器 URL 设置为 https://bitist.top/wechat
2. Token 与 .env 中 WECHAT_TOKEN 一致
3. 菜单建议：
- 我的问题: https://bitist.top/freshman
- 智能问答: https://bitist.top/chat
- 地点查询: https://bitist.top/place

## 10. 验收清单

```bash
curl -I https://bitist.top/
curl -I https://bitist.top/chat
curl -I https://bitist.top/place
curl https://bitist.top/api/feature3_status
```

人工验收：
1. 访问 freshman 提交问题
2. 访问 senior 回答问题
3. 回到 freshman 确认轮询和高亮
4. 公众号发送查 编号 查询码验证回查

## 11. 运维建议

数据库备份：

```bash
cd /opt/wechar_develop/Wechar_Develop/feature2-ai/backend
cp feature3.db feature3.db.bak.$(date +%F-%H%M%S)
```

安全建议：
1. 立即更换 FEATURE3_SENIOR_KEY
2. 对 /senior 增加 Nginx IP 白名单
3. 禁止公开 .env 与日志目录
