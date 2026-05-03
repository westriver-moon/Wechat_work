# 功能三 MVP 运行说明（无登录，H5 主动拉取）

## 1. 准备
1. 复制 `.env.example` 为 `.env`。
2. 按需修改：
   - `FEATURE3_TICKET_MODE=1`
   - `FEATURE3_AUTO_AI_ANSWER=0`（仅人工回复）
   - `FEATURE3_SENIOR_KEY=你自己的密钥`
   - `DB_PATH=./feature3.db`

## 2. 启动
在 `feature2-ai/backend` 目录执行：

```powershell
.venv\Scripts\python app.py
```

## 3. 页面入口
- 首页：`/`
- 新生“我的问题”：`/freshman`
- 学长处理台：`/senior`

## 4. 公众号文本交互（工单模式）
- 用户发送普通问题：系统回“问题编号 + 查询码 + H5 查看指引”。
- 用户发送查询命令：`查 问题编号 查询码`（例如 `查 12 AB12CD34`）。

## 5. API 概览
- `POST /api/questions`
- `GET /api/questions/mine?client_id=...`
- `GET /api/questions/track?qid=...&code=...`
- `PUT /api/questions/<id>/close`
- `GET /api/tasks/pending?q=...`（Header: `X-Senior-Key`）
- `GET /api/tasks/answered?q=...`（Header: `X-Senior-Key`）
- `POST /api/answers`（Header: `X-Senior-Key`）
- `GET /api/feature3_status`

## 6. 前端增强
- 学长端：已增加“已回答列表”和关键字搜索。
- 新生端：已增加自动轮询（12秒）与新回答高亮提醒。

## 7. 快速自检脚本

```powershell
.venv\Scripts\python feature3_smoke_test.py
```
