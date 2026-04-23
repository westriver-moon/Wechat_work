# Nginx 部署步骤（Ubuntu 24.04 LTS）

## 1. 安装 Nginx

在 Ubuntu 24.04 LTS 上执行：

```bash
sudo apt update
sudo apt install -y nginx
```

## 2. 放置站点配置

将 `deploy/nginx/wechat_assistant.conf` 复制到：

```text
/etc/nginx/sites-available/wechat_assistant.conf
```

并创建软链接：

```bash
sudo ln -sf /etc/nginx/sites-available/wechat_assistant.conf /etc/nginx/sites-enabled/wechat_assistant.conf
```

## 3. 修改配置中的关键项

- `server_name example.com` 改为你的真实域名
- `ssl_certificate` 和 `ssl_certificate_key` 改为证书路径（示例 `/etc/letsencrypt/live/...`）

## 4. 检查并重载 Nginx

执行：

```bash
sudo nginx -t
sudo systemctl restart nginx
```

停止 Nginx：

```bash
sudo systemctl stop nginx
```

## 5. 启动 Python 后端（Ubuntu）

后端建议使用 Gunicorn：

```bash
cd /opt/Wechar_Develop/feature2-ai/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
gunicorn -w 2 -b 127.0.0.1:5000 app:app
```

## 6. 配置公众号地址

- 公众号服务器 URL: `https://你的域名/wechat`
- 菜单统一入口: `https://你的域名/`
- 或者拆分菜单:
  - `https://你的域名/chat`
  - `https://你的域名/place`

## 7. 建议：把后端做成 systemd 服务

推荐用 systemd 将 Gunicorn 注册为系统服务，避免手动启动。参考 `deploy/linux/systemd-service.md`。

## 8. RAG 状态验证（建议）

部署后执行：

```bash
curl -X POST 'https://你的域名/api/rebuild_index'
curl 'https://你的域名/api/demo_status'
```

预期：
- `kb_index_ready=true`
- 当 `.env` 里 `KB_FORCE_LEXICAL=0` 且 HuggingFace 网络可达时，`kb_backend=faiss`
