# Windows Server：使用 NSSM 将后端注册为服务

## 1. 安装 NSSM

1. 下载 NSSM 并解压，例如到 `C:\tools\nssm`。
2. 以管理员身份打开 PowerShell。

## 2. 注册服务

```powershell
cd C:\tools\nssm\win64
.\nssm.exe install WechatAssistant
```

在弹窗中配置：

- Application path: `C:\Windows\py.exe`
- Startup directory: `C:\path\to\Wechar_Develop\feature2-ai\backend`
- Arguments: `-m waitress --host=127.0.0.1 --port=5000 app:app`

在 Environment 页签添加（可选，但推荐）：

- `WECHAT_TOKEN=replace_with_your_token`
- `OPENAI_BASE_URL=replace_with_your_base_url`
- `OPENAI_API_KEY=replace_with_your_api_key`
- `OPENAI_MODEL=replace_with_your_model`

保存后执行：

```powershell
.\nssm.exe start WechatAssistant
```

## 3. 常用维护命令

```powershell
.\nssm.exe status WechatAssistant
.\nssm.exe restart WechatAssistant
.\nssm.exe stop WechatAssistant
.\nssm.exe remove WechatAssistant confirm
```

## 4. 验证

浏览器访问：

- `https://你的域名/healthz`
- `https://你的域名/chat`
- `https://你的域名/place`
