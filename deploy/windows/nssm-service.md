# Windows NSSM 服务化说明

本文件说明如何在 Windows 环境下使用 NSSM 把当前项目注册为本机服务。

## 1. 适用场景

适用于：

- 本机长期驻留运行
- 局域网演示
- 不方便每次手动启动终端时

不适用于：

- 正式公网生产部署
- 需要 Nginx / HTTPS / 微信公网接入的场景

正式上线仍建议使用 Linux + Nginx + Gunicorn + systemd。

## 2. 前提条件

- 已安装 NSSM
- 项目已放在固定路径
- 可用解释器已确认，例如 `D:\envs\wechat_work\python.exe`
- `app/backend/.env` 已配置完成
- 已验证 `python app.py` 可以手动跑通

## 3. 推荐配置

### 程序路径

```text
D:\envs\wechat_work\python.exe
```

### 启动参数

```text
app.py
```

### 工作目录

```text
C:\Users\pbrii\Desktop\wechat\Wechat_work\app\backend
```

## 4. 通过图形界面配置

执行：

```powershell
nssm install wechat-assistant
```

然后填写：

- Path：解释器路径
- Startup directory：backend 工作目录
- Arguments：`app.py`

保存后启动服务。

## 5. 通过命令行配置

```powershell
nssm install wechat-assistant "D:\envs\wechat_work\python.exe" "app.py"
nssm set wechat-assistant AppDirectory "C:\Users\pbrii\Desktop\wechat\Wechat_work\app\backend"
nssm start wechat-assistant
```

## 6. 维护命令

```powershell
nssm status wechat-assistant
nssm restart wechat-assistant
nssm stop wechat-assistant
nssm remove wechat-assistant confirm
```

## 7. 注意事项

- 工作目录必须是 `app/backend`，否则相对路径会出问题
- 更新代码后需要重启 NSSM 服务
- 如果 5000 端口已被旧进程占用，服务会启动失败或行为异常
- 地图页是否可用仍取决于腾讯地图 Key，和 NSSM 无关

## 8. 推荐搭配文档

- `docs/deployment/Windows本地运行与服务化.md`
