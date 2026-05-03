# 北京理工大学新生助手

一个面向微信公众号场景的课程项目，现已整理为统一仓库结构。项目包含 3 类能力：

- 地点查询：腾讯地图地点检索、定位与静态预览
- 智能问答：FAQ + RAG 检索 + 可选 DeepSeek / OpenAI 兼容模型
- 人工工单：新生提问、学长处理、公众号查询码回查

## 目录结构

```text
.
├── app/
│   ├── backend/   # Flask 后端、数据库与运行时文件
│   ├── data/      # RAG 知识库文档
│   └── web/       # H5 页面（首页、问答、地点、工单）
├── deploy/        # Nginx / systemd / Windows 服务配置与部署参考
├── docs/
│   ├── development/  # 开发说明与实现过程
│   ├── deployment/   # 服务器部署指南
│   ├── reports/      # 阶段报告与总结
│   └── testing/      # 测试步骤与测试清单
└── README.md
```

## 页面与接口

- 首页：`/`
- 地点查询：`/place`
- 智能问答：`/chat`
- 新生工单页：`/freshman`
- 学长处理台：`/senior`
- 微信回调：`/wechat`

常用接口：

- `POST /api/chat`
- `POST /api/rebuild_index`
- `GET /api/demo_status`
- `POST /api/questions`
- `GET /api/tasks/pending`

## 本地启动

在项目根目录执行：

```bash
cd app/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Windows PowerShell：

```powershell
Set-Location .\app\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python .\app.py
```

## 依赖说明

- `requirements.txt`：基础运行依赖，足够本地启动项目
- `requirements-prod.txt`：部署附加依赖，当前只补充 `gunicorn`
- `requirements-rag.txt`：可选 RAG 向量检索依赖，会引入 `sentence-transformers` 与 `faiss-cpu`

默认配置使用词法检索，未安装 `requirements-rag.txt` 也可以启动和运行项目。

## 配置提示

- 腾讯地图 Key 需要写入 [app/web/place.html](/mnt/d/Workspace/Wechat_work/app/web/place.html) 中的 `__TENCENT_MAP_KEY__`
- 后端环境变量放在 `app/backend/.env`
- RAG 数据文件位于 `app/data/`

## 文档入口

- 开发说明：`docs/development/`
- 部署指南：`docs/deployment/`
- 测试文档：`docs/testing/`
- 阶段报告：`docs/reports/`
