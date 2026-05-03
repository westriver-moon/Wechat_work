# Ubuntu 24.04 LTS 上线前检查与一键部署（腾讯云）

适用项目：当前仓库根目录（功能1+功能2）

## 1. 上线前检查清单

- [ ] 域名已解析到腾讯云服务器公网 IP
- [ ] 安全组已放行 TCP 22/80/443
- [ ] 微信公众号后台 URL 已准备：`https://你的域名/wechat`
- [ ] 腾讯地图 Key 已准备，并已配置允许域名
- [ ] DeepSeek Key（可选）已准备
- [ ] 服务器为 Ubuntu 24.04 LTS，具备 sudo 权限
- [ ] 代码目录已放置到服务器上的项目根目录（例如 `/opt/wechat_work`）

## 2. 一键部署命令（按顺序执行）

在服务器执行以下命令。以下示例先将项目根目录写入变量，后续统一使用相对路径：

```bash
set -e

# 0) 进入项目根目录（示例路径请按实际情况替换）
PROJECT_ROOT=/opt/wechat_work
cd "$PROJECT_ROOT"

# 1) 安装系统依赖
sudo apt update
sudo apt install -y nginx python3 python3-venv python3-pip

# 2) 安装后端依赖
cd app/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3) 写入环境变量文件（按需改值）
cat > .env << 'EOF'
FLASK_ENV=development
PORT=5000
WECHAT_TOKEN=replace_with_your_token
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=replace_with_your_api_key
DEEPSEEK_MODEL=deepseek-chat
OPENAI_TIMEOUT=15
LLM_TEMPERATURE=0.2
LLM_TOP_P=0.9
LLM_MAX_TOKENS=400
LLM_MIN_CONFIDENCE=0.60
KB_FORCE_LEXICAL=0
EOF

# 4) 配置 systemd 服务
sudo tee /etc/systemd/system/wechat-assistant.service > /dev/null << 'EOF'
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

sudo systemctl daemon-reload
sudo systemctl enable --now wechat-assistant

# 5) 配置 Nginx（先确保你已把证书路径改成真实值）
cd "$PROJECT_ROOT"
sudo cp deploy/nginx/wechat_assistant.conf /etc/nginx/sites-available/wechat_assistant.conf
sudo ln -sf /etc/nginx/sites-available/wechat_assistant.conf /etc/nginx/sites-enabled/wechat_assistant.conf
sudo nginx -t
sudo systemctl restart nginx
```

其中，systemd 服务中的绝对路径需要替换为你自己的项目根目录，例如：

```ini
WorkingDirectory=/opt/wechat_work/app/backend
EnvironmentFile=/opt/wechat_work/app/backend/.env
ExecStart=/opt/wechat_work/app/backend/.venv/bin/gunicorn -w 2 -b 127.0.0.1:5000 app:app
```

## 3. 必改项（不改会失败）

- `app/web/place.html` 中 `__TENCENT_MAP_KEY__` 替换为你的腾讯地图 Key
- `/etc/nginx/sites-available/wechat_assistant.conf` 中：
  - `server_name example.com` 改为你的域名
  - `ssl_certificate` 改为真实证书路径
  - `ssl_certificate_key` 改为真实私钥路径
- `app/backend/.env` 中：
  - `WECHAT_TOKEN` 必须与公众号后台一致
  - `DEEPSEEK_API_KEY` 填真实值
  - `KB_FORCE_LEXICAL=0` 为 HuggingFace + FAISS 模式；网络异常时改 `1` 回退词法模式

## 4. 上线验收命令

```bash
sudo systemctl status wechat-assistant --no-pager
sudo systemctl status nginx --no-pager
curl -I https://你的域名/
curl -I https://你的域名/chat
curl -I https://你的域名/place
curl -X POST 'https://你的域名/api/rebuild_index'
curl 'https://你的域名/api/demo_status'
curl -X POST 'https://你的域名/api/chat' -H 'Content-Type: application/json' -d '{"question":"新生什么时候选课"}'
```

## 5. 回滚与排障

查看后端日志：

```bash
sudo journalctl -u wechat-assistant -f
```

重启服务：

```bash
sudo systemctl restart wechat-assistant
sudo systemctl restart nginx
```

常见问题：

- 502 Bad Gateway：先看 `wechat-assistant` 是否启动成功
- 微信校验失败：核对 `WECHAT_TOKEN` 与公众号后台一致
- 地图查询失败：检查腾讯地图 Key 是否替换、域名白名单与配额
- `kb_backend` 不是 `faiss`：检查 HuggingFace 网络连通、`.env` 是否为 `KB_FORCE_LEXICAL=0`
