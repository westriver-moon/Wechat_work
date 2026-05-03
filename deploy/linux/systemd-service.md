# Ubuntu 24.04 LTS：使用 systemd 将后端注册为服务

## 1. 准备运行环境

1. 安装 Python 与基础工具：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

2. 进入项目根目录后，再进入后端目录并安装依赖：

```bash
cd /opt/wechat_work
cd app/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. 创建 systemd 服务

新建文件 `/etc/systemd/system/wechat-assistant.service`：

将下面示例里的 `/opt/wechat_work` 替换成你自己的项目根目录绝对路径。

```ini
[Unit]
Description=Wechat Assistant Backend (Gunicorn)
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/wechat_work/app/backend
Environment="WECHAT_TOKEN=replace_with_your_token"
Environment="DEEPSEEK_BASE_URL=https://api.deepseek.com"
Environment="DEEPSEEK_API_KEY=replace_with_your_api_key"
Environment="DEEPSEEK_MODEL=deepseek-chat"
Environment="OPENAI_TIMEOUT=15"
Environment="KB_FORCE_LEXICAL=0"
ExecStart=/opt/wechat_work/app/backend/.venv/bin/gunicorn -w 2 -b 127.0.0.1:5000 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## 3. 启动与开机自启

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wechat-assistant
```

## 4. 常用维护命令

```bash
sudo systemctl status wechat-assistant
sudo systemctl restart wechat-assistant
sudo systemctl stop wechat-assistant
sudo journalctl -u wechat-assistant -f
```

## 5. 验证

浏览器访问：

- `https://你的域名/`
- `https://你的域名/chat`
- `https://你的域名/place`

接口验证：

```bash
curl -X POST 'https://你的域名/api/rebuild_index'
curl 'https://你的域名/api/demo_status'
```

预期：
- `kb_index_ready=true`
- 当 `KB_FORCE_LEXICAL=0` 且网络正常时，`kb_backend=faiss`
