# RAG 可用化实施与实测报告（BIT 新生助手）

## 1. 背景与目标

当前项目的核心问题是：
- `kb_index_ready=false` 导致检索链路不稳定。
- 来源字段在回答中不稳定，影响追溯。
- 选课、宿舍、校园网等高频问题回答偏泛化。

本次目标：
1. 让 RAG 在当前网络环境下稳定可用，并优先启用 HuggingFace 向量检索。
2. 保证回答可追溯到具体来源文件。
3. 针对高频问题提供可执行、可落地的步骤型回答。

---

## 2. 互联网信息来源（BIT 相关）

本次知识整理基于北京理工大学公开网站入口信息，重写为可检索问答内容（未直接复制原文）：

- 学校官网：https://www.bit.edu.cn/
- 本科招生网：https://admission.bit.edu.cn/
- 图书馆网站：https://lib.bit.edu.cn/
- 留学生中心网站：https://isc.bit.edu.cn/
- 教务网站入口：https://jwc.bit.edu.cn/

额外采用了学校公开导航中的高频入口：
- 迎新网：https://hi.bit.edu.cn/
- 智慧北理：https://ehall.bit.edu.cn/
- 综合服务：http://online.bit.edu.cn/
- 校园网络入口：https://webvpn.bit.edu.cn/

---

## 3. 本次落地的数据文件

新增/更新了以下 RAG 数据文件：

- `app/data/bit_freshman_rag_handbook.md`
  - 结构化内容：常用入口、入学清单、选课/宿舍/校园网/图书馆 FAQ、回答策略。
- `app/data/faq.md`
  - 优化为更具体的 Q/A，减少“只有一句话”的空泛回答。
- `app/data/01_报到与入学准备.md`
- `app/data/02_学习与教务服务.md`
- `app/data/03_校园生活与住宿网络.md`
- `app/data/04_奖助学金与学生资助.md`
- `app/data/05_交通出行与校区导航.md`
- `app/data/06_医疗服务与健康保障.md`
- `app/data/07_校园安全与反诈指南.md`
- `app/data/08_军训与国防教育.md`
- `app/data/09_社团活动与成长路径.md`

当前知识文档已经形成“报到、学业、生活、奖助、交通、医疗、安全、军训、社团”九大主题覆盖。

---

## 4. 关键代码改造

### 4.1 索引构建：从“只能向量”改为“混合可用”

文件：`app/backend/kb.py`

改造点：
- 新增索引状态文件与状态读取能力。
- 新增 `KB_FORCE_LEXICAL=1` 模式：在外网受限时强制使用词法检索，避免卡在 HuggingFace 下载。
- 保留 FAISS 路径：当环境允许时可切回向量检索。
- `query_index` 支持自动降级：FAISS 查询异常时自动回退词法检索。

### 4.2 后端接口：可运维、可观测

文件：`app/backend/app.py`

新增接口：
- `POST /api/rebuild_index`：重建索引。
- `GET /api/demo_status`：返回 `kb_index_ready`、`kb_backend`、`kb_doc_count`、`kb_error`。

### 4.3 回答质量与追溯改造

- 增强中文匹配（字符 n-gram 相似度）。
- 增加高频问题缓存（选课/校园网/宿舍）并优先命中。
- 增加来源补全逻辑：若模型遗漏来源则自动追加来源标签。

---

## 5. 运行方式（当前可直接执行）

在 `app/backend/.env` 推荐配置：

```env
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=你的key
DEEPSEEK_MODEL=deepseek-chat
OPENAI_TIMEOUT=15
LLM_TEMPERATURE=0.2
KB_FORCE_LEXICAL=0
```

说明：
- `KB_FORCE_LEXICAL=0`：优先构建 HuggingFace + FAISS 向量索引。
- `KB_FORCE_LEXICAL=1`：网络不稳定时回退词法检索，保障可用性。

启动（Windows）：

```powershell
Set-Location <项目根目录>
Set-Location .\app\backend
.\.venv\Scripts\python.exe .\app.py
```

重建索引：

```bash
curl -X POST http://127.0.0.1:5000/api/rebuild_index
```

检查状态：

```bash
curl http://127.0.0.1:5000/api/demo_status
```

---

## 6. 本次实测记录（已执行）

说明：本次最终验证按要求在 `5000` 端口执行。

### 6.1 索引重建

请求：`POST http://127.0.0.1:5000/api/rebuild_index`

返回要点：
- `ok: true`
- `ready: true`
- `backend: faiss`
- `doc_count: 13`

### 6.2 状态检查

请求：`GET http://127.0.0.1:5000/api/demo_status`

返回要点：
- `kb_index_ready: true`
- `kb_backend: faiss`
- `kb_doc_count: 13`
- `provider: deepseek`

补充复测（5000 端口）：
- `/api/rebuild_index` 在同环境再次执行，实测耗时约 19.02 秒，返回 200 且 `ok=true`。
- 首次重建通常更慢（如约 30~90 秒），后续重建会因缓存与已下载模型而明显缩短。

### 6.3 问答效果（示例）

请求：`POST /api/chat`，问题“校园网怎么开通”（使用 Python requests 测）

结果要点：
- 返回了可执行步骤（激活账号、认证、异常处理）
- 回答附带来源 `bit_freshman_rag_handbook.md`

请求：`POST /api/chat`，问题“绿色通道怎么申请”（使用 Python requests 测）

结果要点：
- 返回了可执行步骤（报到前关注通知、报到日窗口办理、按要求提交材料）
- 回答附带来源 `01_报到与入学准备.md`、`04_奖助学金与学生资助.md`

请求：`GET /api/kb_query?q=宿舍入住流程是什么`

结果要点：
- `retrieved` 包含明确来源文件名
- `answer` 包含“按学院安排到指定宿舍楼办理入住”等操作级内容

补充复测（编码验证）：
- 在 Windows PowerShell 环境直接提交中文 JSON 可能出现编码干扰（问句显示为问号）。
- 使用 UTF-8 字节体发送后，`POST /api/chat` 可稳定返回中文问题答案。
- 示例问题“新生军训一般有哪些安排？”返回内容命中 `08_军训与国防教育.md`，来源可追溯。

---
## 8. 后续建议

1. 若服务器可稳定访问 HuggingFace，可将 `KB_FORCE_LEXICAL` 切为 `0`，启用向量索引提升语义召回。
2. 将 `faq.md` 按“一个问题一条”继续细化到学院级业务。
3. 新增“学工、教务、后勤”分域文档，降低跨主题召回噪声。
4. 引入定期重建任务（如每日凌晨）保证知识更新。
