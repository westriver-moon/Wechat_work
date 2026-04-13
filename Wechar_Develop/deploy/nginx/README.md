# Nginx 部署步骤（Windows Server）

## 1. 准备 Nginx

1. 下载并解压 Nginx 到 `C:\nginx`。
2. 打开 `C:\nginx\conf\nginx.conf`，确保 `http {}` 内包含：

```nginx
include conf.d/*.conf;
```

3. 新建目录：`C:\nginx\conf\conf.d`（如果不存在）。

## 2. 放置站点配置

将 `deploy/nginx/wechat_assistant.conf` 复制到：

```text
C:\nginx\conf\conf.d\wechat_assistant.conf
```

## 3. 修改配置中的关键项

- `server_name example.com` 改为你的真实域名
- `ssl_certificate` 和 `ssl_certificate_key` 改为证书路径（示例 `C:/certs/...`）

## 4. 检查并重载 Nginx

在 PowerShell 中执行：

```powershell
cd C:\nginx
.\nginx.exe -t
.\nginx.exe
.\nginx.exe -s reload
```

停止 Nginx：

```powershell
.\nginx.exe -s quit
```

## 5. 启动 Python 后端（Windows）

后端建议使用 Waitress：

```powershell
cd C:\path\to\Wechar_Develop\feature2-ai\backend
py -m pip install -r requirements.txt
py -m waitress --host=127.0.0.1 --port=5000 app:app
```

## 6. 配置公众号地址

- 公众号服务器 URL: `https://你的域名/wechat`
- 菜单统一入口: `https://你的域名/`
- 或者拆分菜单:
  - `https://你的域名/chat`
  - `https://你的域名/place`

## 7. 建议：把后端做成 Windows 服务

推荐用 NSSM 将 Waitress 注册为 Windows 服务，避免手动启动。
