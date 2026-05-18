# Linux 生产部署手册

## 1. 适用范围

本文档适用于当前项目在 Ubuntu 24.04 或兼容 Linux 环境上的生产部署，目标是让以下能力同时可用：

- 登录与权限控制
- AI 问答
- 地点查询页面
- 人工工单与微信回调

## 2. 推荐部署形态

- 操作系统：Ubuntu 24.04 LTS
- Web 层：Nginx
- 应用层：Gunicorn + Flask
- 进程托管：systemd
- 存储：SQLite
- HTTPS：Let's Encrypt 或现有证书

## 3. 前置准备

### 服务器条件

- 具备 sudo 权限
- 已解析的公网域名
- 放通 80 / 443
- 可以访问代码仓库或已经完成代码上传

### 项目放置建议

建议项目根目录：

```text
/opt/wechat_work
```

### 必需外部配置

- 腾讯地图 Key
- `WECHAT_TOKEN`
- 可选 `DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY`
- 可选 `WECHAT_APPID` / `WECHAT_APPSECRET`

## 4. 安装系统依赖

```bash
sudo apt update
sudo apt install -y nginx python3 python3-venv python3-pip certbot python3-certbot-nginx
```

## 5. 准备 Python 环境

```bash
cd /opt/wechat_work/app/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

如需显式安装生产附加依赖，可再执行：

```bash
pip install -r requirements-prod.txt
```

## 6. 配置环境变量

复制模板：

```bash
cp .env.example .env
```

建议至少填写：

```env
FLASK_ENV=production
PORT=5000
SECRET_KEY=replace_with_random_secret
AUTH_OWNER_SALT=replace_with_private_salt
AUTH_SESSION_HOURS=8
WECHAT_TOKEN=replace_with_your_token
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=replace_with_your_api_key
DEEPSEEK_MODEL=deepseek-chat
KB_FORCE_LEXICAL=1
DB_PATH=./feature3.db
FEATURE3_TICKET_MODE=1
FEATURE3_AUTO_AI_ANSWER=0
FEATURE3_ENABLE_WORKER=1
FEATURE3_WORKER_POLL_SECONDS=1.5
FEATURE3_HELP_URL=https://你的域名/freshman
FEATURE3_ENABLE_WECHAT_PUSH=0
```

说明：

- 生产环境默认建议先用 `KB_FORCE_LEXICAL=1` 保证可用性，确认外网模型链路稳定后再切到 `0`
- 如果要启用主动微信推送，再补 `WECHAT_APPID` 和 `WECHAT_APPSECRET`

## 7. 页面与前端关键配置

### 腾讯地图 Key

需要手动替换：

- `app/web/place.html` 中的 `__TENCENT_MAP_KEY__`

未替换时：

- 地图页仍能打开
- 真实地点查询会鉴权失败

## 8. 先本机验证 Gunicorn

```bash
cd /opt/wechat_work/app/backend
source .venv/bin/activate
gunicorn -w 2 -b 127.0.0.1:5000 app:app
```

另开终端验证：

```bash
curl -I http://127.0.0.1:5000/
curl http://127.0.0.1:5000/api/demo_status
```

说明：

- `/` 未登录时返回重定向是正常现象
- `/api/demo_status` 未登录时返回 401 也是正常现象

## 9. 配置 systemd

参考 `deploy/linux/systemd-service.md`，创建服务：

```bash
sudo tee /etc/systemd/system/wechat-assistant.service > /dev/null <<'EOF'
[Unit]
Description=Wechat Assistant Backend (Gunicorn)
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/wechat_work/app/backend
EnvironmentFile=/opt/wechat_work/app/backend/.env
ExecStart=/opt/wechat_work/app/backend/.venv/bin/gunicorn -w 2 -b 127.0.0.1:5000 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

启用：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wechat-assistant
sudo systemctl status wechat-assistant --no-pager
```

## 10. 配置 Nginx

使用现成配置文件：

- `deploy/nginx/wechat_assistant.conf`

复制并启用：

```bash
sudo cp /opt/wechat_work/deploy/nginx/wechat_assistant.conf /etc/nginx/sites-available/wechat_assistant.conf
sudo ln -sf /etc/nginx/sites-available/wechat_assistant.conf /etc/nginx/sites-enabled/wechat_assistant.conf
```

至少确认以下项：

- `server_name` 为真实域名
- `ssl_certificate` 和 `ssl_certificate_key` 为真实证书路径
- `proxy_pass` 指向 `127.0.0.1:5000`
- `proxy_read_timeout 180s`
- `proxy_send_timeout 180s`

检查并重载：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 11. 申请或绑定 HTTPS 证书

如果使用 Let's Encrypt：

```bash
sudo certbot --nginx -d 你的域名
sudo certbot renew --dry-run
```

## 12. 配置微信公众号后台

### 服务器配置

- URL：`https://你的域名/wechat`
- Token：与 `.env` 中 `WECHAT_TOKEN` 一致

### 菜单建议

- 首页：`https://你的域名/`
- 智能问答：`https://你的域名/chat`
- 地点查询：`https://你的域名/place`
- 我的问题：`https://你的域名/freshman`

## 13. 部署后验证

### 自动化验证

```bash
cd /opt/wechat_work/app/backend
/opt/wechat_work/app/backend/.venv/bin/python ./tests/feature3_smoke_test.py
/opt/wechat_work/app/backend/.venv/bin/python ./tests/url_fetch_smoke_test.py https://www.bit.edu.cn --search-query "北京理工大学 选课"
```

### 接口与页面验证

```bash
curl -I https://你的域名/
curl -I https://你的域名/login
curl https://你的域名/api/demo_status
```

手工验证：

1. 打开登录页
2. 登录后进入 `/chat`
3. 提交一条 AI 问题
4. 进入 `/freshman` 提交工单
5. 有权限账号进入 `/senior` 回答
6. 微信后台完成 `/wechat` 校验

## 14. 常见问题

### 502 Bad Gateway

优先检查：

- `wechat-assistant` 服务是否运行
- Gunicorn 是否监听 `127.0.0.1:5000`
- Nginx 配置是否生效

### 浏览器出现 `ERR_HTTP2_PROTOCOL_ERROR`

优先检查：

- Nginx 代理超时是否过低
- AI 请求是否被提前截断
- 是否保持了 180 秒级别的超时配置

### `/api/demo_status` 看起来异常

注意：

- 未登录返回 401 属于正常行为
- 真正的 AI 状态检查建议在登录态下进行

### 工单页面打不开或无权限

优先检查：

- 是否已登录
- 学长账号是否在身份白名单中拥有 `answer` 权限
- `auth_identities.json` 是否已同步到数据库

## 15. 维护命令

```bash
sudo systemctl status wechat-assistant
sudo systemctl restart wechat-assistant
sudo systemctl status nginx
sudo systemctl reload nginx
sudo journalctl -u wechat-assistant -f
```

## 16. 备份建议

当前运行依赖本地 SQLite 和索引状态文件，至少定期备份：

- `feature3.db`
- `kb_meta.json`
- `kb_state.json`
- `kb_texts.json`
- `.env`
