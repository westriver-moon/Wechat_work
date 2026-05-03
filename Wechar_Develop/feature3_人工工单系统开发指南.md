# 功能三 — 人工工单系统（新生→学长学姐问答）开发指南（以 H5 “我的问题” 拉取为主）

本文档基于你选择的实现策略：H5 “我的问题” 拉取（用户主动打开页面查看答案）。文档详细说明实现步骤、接口、数据库、前端行为、/wechat 的被动回复策略与异步答案生成（后台 worker），并以 SQLite 作为 MVP 存储。
---


## 概述
- 目标：实现“新生提问 → 后端入库与异步生成答案 → 用户主动在 H5（公众号菜单→我的问题）拉取查看”的工作流。
- 要点：
  - 使用 SQLite 存储用户、问题、答案与任务队列（开发/小流量场景）。
  - `/wechat` 端点在收到用户文本时立即返回 "success" 并把问题入库，同时向用户返回一条被动回复文本提示（包含问题ID和查看指引）。
  - 后台 worker 异步生成答案（调用 `build_answer` 或由学长提交），但不依赖公众号主动推送；用户通过 H5 页面主动调用 `GET /api/questions/mine` 查看答案。
  - 前端包括 `freshman.html`（我的问题：提交/查看）与 `senior.html`（学长任务处理）。

---

## 1. 新增文件与目录（建议）
- `feature2-ai/backend/db.py` — 数据访问层（SQLite 封装）。
- `feature2-ai/backend/wechat_utils.py` — optional：access_token 缓存与 `send_customer_message`（非必需，H5 拉取方案可先仅记录答案）。
- `feature2-ai/backend/worker.py`（可选）— 异步 worker；简单做法：把 worker 逻辑放入 `app.py` 启动的守护线程。
- `feature2-ai/backend/data.db` — SQLite 数据库文件（运行时生成）。
- `feature2-ai/backend/migrations/` — 可放置初始建表 SQL（可选）。
- `feature2-ai/frontend/freshman.html`、`feature2-ai/frontend/senior.html` — 前端页面模板（MVP）。

---

## 2. 环境与依赖（SQLite MVP）
- Python: 3.10+（与仓库现有要求兼容）。
- 依赖（在 `feature2-ai/backend/requirements.txt` 补充）：
  - `PyJWT`（若选择用 JWT）
  - `SQLAlchemy`（推荐，亦可使用内置 `sqlite3`）
  - `Flask` 等（已有）

示例安装命令（Windows PowerShell）：
```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install SQLAlchemy PyJWT
```

必要环境变量（写入 `.env`）：
- `WECHAT_TOKEN`：微信公众号配置的 Token
- `WECHAT_APPID`：公众号 AppID
- `WECHAT_APPSECRET`：公众号 AppSecret
- `DB_PATH`：SQLite 文件路径（默认 `./data.db`）
- `JWT_SECRET`：JWT 签名密钥（如果使用 JWT）
- `PORT`：后端监听端口（默认 5000）

权限与文件系统：确保后端进程对 `feature2-ai/backend/` 下文件有读写权限（data.db、access_token 缓存）。

---

## 3. 数据库设计（SQLite，建表 SQL）
推荐在后端启动时执行建表逻辑（若表不存在则创建）。建表 SQL：

```sql
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  openid TEXT UNIQUE NOT NULL,
  role TEXT NOT NULL DEFAULT 'freshman', -- freshman|senior|admin
  nickname TEXT,
  avatar TEXT,
  created_at INTEGER
);

CREATE TABLE IF NOT EXISTS questions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  from_user_id INTEGER NOT NULL,
  title TEXT,
  content TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', -- pending|answered|closed
  created_at INTEGER
);

CREATE TABLE IF NOT EXISTS answers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  question_id INTEGER UNIQUE NOT NULL,
  answerer_id INTEGER NOT NULL,
  content TEXT NOT NULL,
  created_at INTEGER
);

CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT,
  payload TEXT, -- JSON encoded payload
  status TEXT DEFAULT 'queued', -- queued|processing|done|failed
  attempts INTEGER DEFAULT 0,
  last_error TEXT,
  created_at INTEGER
);
```

说明：`tasks` 表用于可靠地存放待处理任务（如 `answer_question`），可以在失败时重试并记录 attempts 与 last_error。

---

## 4. 数据访问层（`db.py`）要点
建议使用 `SQLAlchemy` 或最小封装 `sqlite3`。核心函数接口（伪签名）：

- `init_db(db_path)`：创建连接并建表
- `get_or_create_user(openid, nickname=None)` -> user dict
- `get_user_by_openid(openid)` -> user dict or None
- `save_question(from_user_id, title, content)` -> question_id
- `list_pending_questions(limit=50)` -> list
- `save_answer(question_id, answerer_id, content)` -> answer_id
- `enqueue_task(type, payload_dict)` -> task_id
- `fetch_next_task()` -> task row (并将 status 更新为 processing)
- `mark_task_done(task_id)` / `mark_task_failed(task_id, error)`

实现要点：
- 在简单实现中，把 `payload` 存为 JSON 字符串。
- 使用事务（BEGIN/COMMIT）确保任务获取到锁并避免重复处理（SQLite 的实现有限，使用单写线程或轻量锁更稳妥）。

---

## 5. `/wechat` 修改（立即返回 + 被动提示 + 入库/异步生成答案）
当前 `app.py` 的 `/wechat` 端点会同步调用 `build_answer`，在 H5 拉取方案下需改为：

处理流程：
1. 验证微信签名（保持现有逻辑）。
2. 解析用户消息（文本消息）并立即返回 Response("success").
3. 在后台（新线程或短事务）执行：
   - 调用 `get_or_create_user(openid)`。
   - 将用户消息写入 `questions`（title 可为空或从内容推断）。
   - 将 `answer_question` 任务 `enqueue_task("answer_question", {"question_id": <id>})`（交由 worker 异步生成答案）。
4. 同次被动回复（立即返回给微信的 XML 文本）向用户说明：
   - 提示已收到并告知问题编号（例如：问题编号 `123`），
   - 指引用户通过“公众号菜单 → 我的问题”或访问 H5 页面查看（并可发送关键词 `查 123` 拉取答案）。

注意要点：
- 被动回复必须在 5 秒内完成，且仅包含短文本指引。不要在同步路径中调用 LLM。被动回复示例：
  "已收到，你的问题编号：123。请点击菜单→我的问题 查看进展，或稍后发送 '查 123' 拉取答案。"

示例实现要点（伪代码）：

```python
from threading import Thread

def handle_incoming_text(openid, content):
  user = db.get_or_create_user(openid)
  qid = db.save_question(user['id'], title=None, content=content)
  db.enqueue_task('answer_question', {'question_id': qid})

@app.route('/wechat', methods=['POST'])
def wechat_post():
  # 验签与 xml 解析
  Thread(target=handle_incoming_text, args=(from_user, content), daemon=True).start()
  # 立即返回被动回复 XML（包含 qid 与查看指引）
  return Response(xml_reply_with_qid, mimetype='application/xml')
```

---

## 6. 异步 Worker（生成答案并写入 DB；不强制主动推送）
在 H5 拉取方案下，worker 的职责是：生成答案并把结果写入 `answers` 表与更新 `questions.status='answered'`，但不依赖主动推送（除非未来开通）。

处理 `answer_question` 的流程：
1. `task = fetch_next_task()` 将 task 状态置为 `processing`。
2. 从 task.payload 中读取 `question_id`；查询 `questions` 与 `users` 获取 openid 与内容。
3. 调用 `build_answer(content)`（现有函数）获得 answer_text。
4. 写入 `answers` 表，更新 `questions.status='answered'` 与 `answered_at` 字段（如有）。
5. `mark_task_done(task_id)`。

可选：若公众号可主动推送（未来认证后），再调用 `wechat_utils.send_customer_message(openid, answer_text)`。在未认证状态下，该调用应被禁用或写入日志以避免调用失败。

防错与重试策略：若异常发生，记录 `last_error`、增加 `attempts`，并在 `attempts` 超阈值（例如 5 次）后人工介入。

示例守护线程伪码与轮询逻辑同前，仅省略默认主动推送步骤。

---

## 7. 客服消息发送与 access_token 缓存（可选）
在 H5 拉取首选方案中，主动推送并非必要；但为未来兼容，保留 `wechat_utils.py` 作为可选模块：
- `get_access_token()`：从内存/本地文件缓存 access_token 与过期时间；到期前刷新（使用 `WECHAT_APPID` + `WECHAT_APPSECRET` 调用 token 接口）。
- `send_customer_message(openid, text)`：构建 JSON payload 并 POST 到客服消息接口。该函数在未认证公众号上应禁用或仅写日志记录以避免失败。

开发流程建议：先不启用真实推送；仅在认证号或测试号上验证该路径。

---


## 8. REST API 设计（给前端使用，针对 H5 拉取）
下面为 H5 拉取方案的 MVP API 设计与示例：

- `POST /api/questions` — 新生提交问题（H5 提交）
  - Auth: `Authorization: Bearer <jwt>`（可选）或在开发阶段使用前端存储的 `client_id`（localStorage）作为弱绑定。
  - Body (json): `{ "title": "可选", "content": "问题正文" }`
  - Response: `201 { "id": <qid>, "status": "pending", "message": "已收到，问题编号：<qid>。请到 菜单→我的问题 查看进展。" }`

- `GET /api/questions/mine` — 获取当前用户自己提交的问题（用于 H5 列表）
  - Auth: 同上（或以 `client_id` 查询）
  - Response: `200 [ {"id":..., "title":..., "content":..., "status":..., "answer": "可选", "created_at": 168... } ]`

- `GET /api/questions/<id>` — 获取单条问题详情（包括 answer 字段）
  - Auth: 同上
  - Response: `200 { "id":..., "title":..., "content":..., "status":..., "answer": "..." }`

- `GET /api/tasks/pending` — 学长获取待办（受 role 校验）
  - Auth: `Authorization`（学长或 admin）
  - Response: `200 [ {"question_id":..., "title":..., "content":..., "from_user": {...}} ]`

- `POST /api/answers` — 学长提交解答（通过学长 H5）
  - Auth: 学长
  - Body: `{ "question_id": 123, "content": "这是解答" }`
  - Response: `200 { "status": "ok" }`（系统会将答案写入 DB，用户通过 H5 拉取）。

- `PUT /api/questions/<id>/close` — 新生确认关闭
  - Auth: question.owner
  - Response: `200 { "status": "closed" }`

实现要点：
- 因公众号未认证可能无法使用 OAuth 获取 openid，MVP 可先用 `client_id`（前端生成并存在 localStorage）作为弱绑定；生产须改为 OAuth + JWT。 
- 对输入进行必要的长度/内容检测并返回友好错误码。

---


## 9. 前端（H5：`freshman.html` 与 `senior.html`）

`freshman.html`（我的问题）要点：
- 初次访问：前端生成并保存一个 `client_id`（UUID）到 `localStorage`，用于弱绑定（若公众号支持 OAuth，可替换为 openid/JWT）。
- 页面功能：
  - 提交问题表单（POST `/api/questions`），提交后显示系统返回的 `qid` 与提示文本；
  - 列表：周期性或手动刷新 `GET /api/questions/mine` 展示用户所有问题及状态（pending/answered/closed）；
  - 查看详情：点击问题可调用 `GET /api/questions/<id>` 查看答案；
  - 关闭按钮：针对已回答的问题调用 `PUT /api/questions/<id>/close`。

`senior.html`（学长后台）要点：
- 学长登录（可用简单密码或由管理员手动填写 `role='senior'` 的用户在 DB 中）
- 页面功能：
  - 获取待办：`GET /api/tasks/pending`（或 `GET /api/questions?status=pending`）
  - 打开问题详情并填写答案，然后 `POST /api/answers` 提交；
  - 可选：提交后生成一次性查看链接并通过微信客服消息发送（若可用），或在界面上复制链接给用户。

用户体验说明：
- 当用户在公众号发送问题时，/wechat 被动回复将包含问题编号与提示："请到 公众号菜单→我的问题 查看进度"；用户可点击菜单或在浏览器中打开 H5 页面查看答案。

备注：若你后续完成公众号认证，可把 `client_id` 替换为标准 OAuth(openid) + 后端 JWT 流程。

---

## 10. 本地测试流程（针对 H5 拉取方案）
1. 启动后端（开发模式）：
```powershell
cd feature2-ai/backend
.venv\Scripts\python app.py
```
2. 打开 H5 页面（`freshman.html`），在本地或通过服务器地址访问并提交问题。也可模拟 `/wechat` 收到消息：POST 到 `/wechat`（测试时可跳过签名验证或用测试号）。
3. 确认 `questions` 表写入新记录，并且 `tasks` 表生成 `answer_question` 任务（供 worker 使用）。
4. 启动 worker（或确保守护线程在 `app.py` 中运行），等待其将答案写入 `answers` 并更新 `questions.status='answered'`。
5. 在 H5 页面点击“我的问题”或刷新列表，验证 `GET /api/questions/mine` 能显示答案。

示例 curl（通过 API 提交问题）：
```bash
curl -X POST http://127.0.0.1:5000/api/questions -H "Content-Type: application/json" -d '{"content":"新生如何选课？"}'
```

---

## 11. 部署建议与注意事项
- 微信回调必须是 HTTPS：在生产使用 Nginx 反代并配置 TLS（Let’s Encrypt）。
- SQLite 并发写入有限：若并发上升或读写冲突频繁，应迁移到 MySQL/Postgres。SQLite 适合低并发或单实例场景。
- access_token 应缓存且仅在到期时刷新，避免频繁调用 token 接口。
- 客服消息频率受限：实现节流（如同一用户每天推送频率限制）并记录发送结果与错误。

---

## 12. 风险、限制与后续优化
- 风险：未认证公众号无法使用网页授权（需要测试号或完成认证）。这会影响 H5 登录体验与用户身份绑定。
- 限制：LLM 调用耗时、客服消息频率限制、SQLite 并发瓶颈。
- 后续优化：使用 Redis/Celery 做队列、MySQL 做持久 DB、实现管理员后台（用户/角色管理）、对答案做人工审核与标签化、添加监控与错误告警。

---


## 11. 交付清单（H5 拉取 MVP）
- 新增文件：`db.py`、`worker.py`（或将 worker 嵌入 `app.py`）、`freshman.html`、`senior.html`。
- 可选文件：`wechat_utils.py`（仅用于将来启用主动推送时）
- 更新：`feature2-ai/backend/requirements.txt`（添加 SQLAlchemy / PyJWT 可选）
- 运行产物：`feature2-ai/backend/data.db`（SQLite）。

---


## 12. 我可以代劳的下一步
- 我可以在仓库内实现 H5 拉取的 MVP：创建 `db.py`、实现 worker 并修改 `app.py`、添加 `freshman.html` 与 `senior.html`、并更新 `requirements.txt`。

请确认：是否现在让我开始在仓库里生成 H5 拉取 MVP 的代码补丁（SQLite 方案）？
