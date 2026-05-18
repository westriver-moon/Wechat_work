# Windows 本地运行与服务化

## 1. 适用范围

本文档适用于 Windows 环境下的本地开发、联调、回环浏览器测试，以及可选的本机服务化运行。

## 2. 当前推荐解释器

本机已验证可用的解释器为：

- `D:\envs\wechat_work\python.exe`

如果使用 Conda：

```powershell
conda activate D:\envs\wechat_work
```

如果使用虚拟环境，则在 `app/backend` 目录下自行创建 `.venv`。

## 3. 进入目录

```powershell
Set-Location .\app\backend
```

Windows 下运行时，必须确保当前目录是 `app/backend`，否则：

- `.env` 可能无法按预期加载
- `modules` 导入路径可能不正确
- 测试脚本可能找不到相对文件

## 4. 安装依赖

使用当前可用解释器：

```powershell
D:\envs\wechat_work\python.exe -m pip install -r .\requirements.txt
```

如需补充 RAG 依赖：

```powershell
D:\envs\wechat_work\python.exe -m pip install -r .\requirements-rag.txt
```

说明：

- 某些 Windows 环境下 GitHub 访问会影响 `bit_login` 安装
- 某些 RAG 版本组合需要兼容性固定，不能盲目升级

## 5. 配置 `.env`

复制模板：

```powershell
Copy-Item .\.env.example .\.env
```

至少填写：

- `SECRET_KEY`
- `WECHAT_TOKEN`
- `DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY`
- `DB_PATH`
- `FEATURE3_*`

地图功能另需修改：

- `app/web/place.html` 中的腾讯地图 Key 占位符

## 6. 启动服务

```powershell
D:\envs\wechat_work\python.exe .\app.py
```

启动后访问：

- `http://127.0.0.1:5000`

## 7. 本地验证建议

### 页面验证

1. 打开 `http://127.0.0.1:5000/login`
2. 确认登录页可渲染
3. 登录后进入 `/chat`
4. 再验证 `/freshman` 和 `/place`

### 自动化验证

```powershell
D:\envs\wechat_work\python.exe .\tests\feature3_smoke_test.py
D:\envs\wechat_work\python.exe .\tests\url_fetch_smoke_test.py https://www.bit.edu.cn --search-query "北京理工大学 选课"
```

## 8. 常见问题

### PowerShell 激活脚本受限

如果 `Activate.ps1` 被执行策略拦住，直接使用解释器绝对路径执行即可，不必强依赖激活脚本。

### 中文 JSON 乱码

PowerShell 某些 `Invoke-RestMethod` 场景下会出现中文乱码。调试 `/api/chat` 时，建议：

- 使用 UTF-8 字节体
- 或直接使用 Python requests

### 5000 端口被占用

如果访问结果和当前代码不一致，优先怀疑本机已有旧服务占用端口。可以：

- 先结束旧进程
- 或临时换端口启动

### 腾讯地图功能无效

优先检查：

- 是否仍是占位 Key
- Key 是否允许当前来源
- 是否触发配额限制

## 9. 可选：用 NSSM 注册 Windows 服务

如果需要本机长期驻留运行，可使用 NSSM。推荐流程：

1. 准备固定的项目目录和解释器路径
2. 使用 `D:\envs\wechat_work\python.exe` 作为程序
3. 参数填写 `app.py`
4. 工作目录填写 `app/backend`
5. 运行前确认 `.env` 已就位

详细参数说明见：

- `deploy/windows/nssm-service.md`

## 10. 不建议的做法

- 不要在错误目录直接运行 `python app.py`
- 不要把临时调试脚本长期保留在 backend 根目录
- 不要把当前 Windows 可用环境假定为对所有机器都可复制
- 不要在未验证地图 Key、登录依赖和 LLM Key 的情况下，把“页面能打开”等同于“全功能可用”
