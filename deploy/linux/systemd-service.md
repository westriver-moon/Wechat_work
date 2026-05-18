# systemd 服务说明

本文件用于说明如何把当前项目的 Gunicorn 进程注册为 Linux systemd 服务。

## 1. 前提条件

- 项目已部署到服务器，例如 `/opt/wechat_work`
- 已在 `app/backend` 下创建虚拟环境并安装依赖
- `.env` 已按实际环境配置完成
- Gunicorn 已能手动启动成功

## 2. 推荐服务文件

创建：

```text
/etc/systemd/system/wechat-assistant.service
```

示例内容：

```ini
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
```

## 3. 配置说明

### `WorkingDirectory`

必须指向：

```text
/opt/wechat_work/app/backend
```

原因：

- 后端需要从该目录读取 `.env`
- 相对路径运行文件基于 backend 根目录
- tests 和运行期文件都以该目录为基准

### `EnvironmentFile`

推荐直接指向 backend 下的 `.env`，避免把密钥硬编码在服务文件里。

### `ExecStart`

推荐显式写绝对路径，避免环境歧义：

```text
/opt/wechat_work/app/backend/.venv/bin/gunicorn -w 2 -b 127.0.0.1:5000 app:app
```

## 4. 启用服务

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wechat-assistant
```

## 5. 常用命令

```bash
sudo systemctl status wechat-assistant
sudo systemctl restart wechat-assistant
sudo systemctl stop wechat-assistant
sudo journalctl -u wechat-assistant -f
```

## 6. 修改后生效流程

如果你修改了服务文件：

```bash
sudo systemctl daemon-reload
sudo systemctl restart wechat-assistant
```

如果你只是修改了代码或 `.env`：

```bash
sudo systemctl restart wechat-assistant
```

## 7. 常见问题

### 服务启动失败

优先检查：

- `WorkingDirectory` 是否正确
- `.venv` 是否存在
- `.env` 是否存在
- `ExecStart` 路径是否正确
- `www-data` 是否对 backend 目录有读写权限

### 启动了但页面 502

优先检查：

- systemd 服务是否实际监听 5000
- Nginx `proxy_pass` 是否指向相同地址
- Gunicorn 是否因为导入错误启动后立即退出

## 8. 推荐搭配文档

- `docs/deployment/Linux生产部署手册.md`
- `deploy/nginx/README.md`
