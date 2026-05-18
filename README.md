# 北京理工大学新生助手

北京理工大学新生助手是一个面向公众号和 Web 场景的校园服务项目，当前提供三类核心能力：地点查询、智能问答和人工工单。项目采用 Flask 作为统一后端，前端页面由后端静态托管，支持登录鉴权、知识库检索、公开网页抓取、人工答复和微信回调。

## 功能概览

- 地点查询：基于腾讯地图完成地点搜索、坐标定位和地图预览。
- 智能问答：优先利用公开网页抓取结果生成回答，必要时回退到本地知识库。
- 人工工单：支持新生提交问题、学长答复、查询码回查和问题关闭。
- 登录与权限：统一接入 BIT 登录，并通过本地权限位控制学长处理台等受限能力。

## 技术栈

### 后端

- Python 3.10+
- Flask
- SQLite
- requests
- python-dotenv
- 可选 Gunicorn
- 可选 sentence-transformers + faiss-cpu

### 前端

- 原生 HTML / CSS / JavaScript
- 腾讯地图 JavaScript API / WebService API

### 外部服务

- BIT 统一身份认证
- DeepSeek 或 OpenAI 兼容接口
- 微信公众号服务器回调
- 公开网页搜索与抓取来源

## 仓库结构

```text
Wechat_work/
├── README.md
├── 项目结构总览.md
├── 项目框架详解.md
├── app/
│   ├── backend/
│   │   ├── app.py
│   │   ├── modules/
│   │   ├── tests/
│   │   ├── .env.example
│   │   ├── requirements.txt
│   │   ├── requirements-rag.txt
│   │   └── requirements-prod.txt
│   ├── data/
│   └── web/
├── deploy/
└── docs/
    ├── development/
    ├── deployment/
    ├── testing/
    └── history/
```

## 快速开始

### 1. 进入后端目录

```powershell
Set-Location .\app\backend
```

### 2. 准备 Python 环境

当前机器已验证可用的解释器：

```powershell
conda activate D:\envs\wechat_work
```

如果使用虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. 配置环境变量

```powershell
Copy-Item .\.env.example .\.env
```

按实际情况填写：

- `SECRET_KEY`
- `WECHAT_TOKEN`
- `DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY`
- `DB_PATH`
- `FEATURE3_*`

### 4. 启动服务

```powershell
D:\envs\wechat_work\python.exe .\app.py
```

启动后访问：

- `http://127.0.0.1:5000`

## 配置说明

### BIT 登录

项目默认接入 BIT 登录。未登录时，主要页面和 API 会被重定向或返回 401。

### 腾讯地图

地图页面依赖腾讯地图 Key，需要手动写入 `app/web/place.html`。未配置时页面可以打开，但地点查询不会成功。

### AI 配置

支持两类 LLM 配置：

- `DEEPSEEK_*`
- `OPENAI_*`

若未配置 Key，系统仍可通过 FAQ / 知识库提供有限回答。

### 知识库模式

通过 `KB_FORCE_LEXICAL` 控制：

- `1`：优先词法检索，适合网络受限场景
- `0`：优先尝试向量检索

## 测试

### 自动化冒烟测试

```powershell
Set-Location .\app\backend
D:\envs\wechat_work\python.exe .\tests\feature3_smoke_test.py
D:\envs\wechat_work\python.exe .\tests\url_fetch_smoke_test.py https://www.bit.edu.cn --search-query "北京理工大学 选课"
```

### 本地浏览器验证建议

1. 访问 `/login`，确认登录页可用。
2. 登录后进入 `/chat`，提交一条问题。
3. 进入 `/freshman`，提交并查看自己的问题。
4. 进入 `/place`，确认页面可加载。

## 部署

生产环境推荐：

- Ubuntu 24.04
- Nginx
- Gunicorn
- systemd
- HTTPS

详细说明见：

- `docs/deployment/部署总览.md`
- `docs/deployment/Linux生产部署手册.md`
- `deploy/nginx/README.md`
- `deploy/linux/systemd-service.md`

## 文档导航

### 当前有效文档

- `项目结构总览.md`
- `项目框架详解.md`
- `docs/development/开发总览.md`
- `docs/development/接口参考文档.md`
- `docs/development/后端开发手册.md`
- `docs/development/前端与页面开发手册.md`
- `docs/development/AI问答与知识库开发手册.md`
- `docs/development/人工工单与微信开发手册.md`
- `docs/deployment/部署总览.md`
- `docs/deployment/Linux生产部署手册.md`
- `docs/deployment/Windows本地运行与服务化.md`
- `docs/testing/测试与验收手册.md`

### 历史资料

历史开发过程记录、专项调试说明和旧版部署文档已统一整理到 `docs/history/`，并按以下主题分组：

- `01-功能方案与阶段说明`
- `02-开发过程记录`
- `03-部署过程记录`
- `04-测试与排障记录`

## 当前状态

当前代码结构和测试状态已经满足以下条件：

- backend 已按功能目录拆分
- backend 根目录不再保留兼容转发层
- 自动化测试脚本已统一收口到 `app/backend/tests/`
- 登录、AI、工单和微信回调主链路已完成回归验证

## 注意事项

- 地图页的真实地点搜索依赖腾讯地图 Key。
- 真实 BIT 登录测试依赖有效账号密码。
- 如果 GitHub 访问受限，`bit_login` 的安装方式需要单独处理。
