# Nginx 配置说明

本目录保存当前项目的 Nginx 站点配置模板与相关说明。

## 文件

- `wechat_assistant.conf`：项目站点配置模板

## 适用场景

- Ubuntu / Linux 生产部署
- Nginx 作为 HTTPS 入口和反向代理
- Gunicorn / Flask 监听 `127.0.0.1:5000`

## 推荐拓扑

```text
Browser / WeChat
      |
      v
    Nginx
      |
      v
  127.0.0.1:5000
      |
      v
 Gunicorn / Flask
```

## 使用步骤

### 1. 复制站点配置

```bash
sudo cp deploy/nginx/wechat_assistant.conf /etc/nginx/sites-available/wechat_assistant.conf
sudo ln -sf /etc/nginx/sites-available/wechat_assistant.conf /etc/nginx/sites-enabled/wechat_assistant.conf
```

### 2. 修改关键项

至少确认：

- `server_name` 为真实域名
- `ssl_certificate` 为真实证书路径
- `ssl_certificate_key` 为真实私钥路径
- `proxy_pass` 指向 `http://127.0.0.1:5000`

### 3. 验证并重载

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 当前配置中的关键点

### HTTP 强制跳转 HTTPS

站点默认把 80 端口全部跳转到 443，满足公众号和正式访问的 HTTPS 要求。

### `/healthz` 健康检查

配置里保留了简单健康检查路径，可用于探活。

### 反向代理超时

当前配置保留了较长的超时：

- `proxy_connect_timeout 15s`
- `proxy_read_timeout 180s`
- `proxy_send_timeout 180s`
- `send_timeout 180s`

原因是 AI 问答链路可能会经历：

1. 全网搜索
2. 候选网页抓取
3. 正文提取
4. LLM 生成

如果超时预算过短，浏览器可能直接表现为 HTTP2 协议错误，而不是应用层 JSON 报错。

## 推荐搭配文档

- `docs/deployment/Linux生产部署手册.md`
- `deploy/linux/systemd-service.md`
