# AI 问答与知识库开发手册

## 1. 功能目标

AI 模块负责回答新生问题。当前实现不是单纯的 FAQ 检索，也不是只依赖大模型，而是采用“网页抓取优先，知识库回退兜底”的混合链路。

当前回答路径：

1. 优先尝试全网搜索与公开网页抓取
2. 若抓取成功，则根据抓取网页组织回答
3. 若网页证据不足，则回退到本地 FAQ / 知识库
4. 若配置了 LLM，则在检索内容之上生成更自然的回答
5. 若未配置 LLM，则直接输出知识库参考答案或兜底说明

## 2. 代码入口

### 路由入口

`app/backend/modules/ai/routes.py`

提供以下接口：

- `POST /api/chat`
- `POST /api/rebuild_index`
- `GET /api/kb_query`
- `GET /api/demo_status`

### 业务入口

`app/backend/modules/ai/service.py`

关键能力：

- FAQ 读取
- 高频问题缓存命中
- 检索结果格式化
- LLM 调用
- 网页抓取回答构建
- 聊天响应总装

### 检索与索引

`app/backend/modules/ai/kb.py`

关键能力：

- 读取 `app/data/*.md`
- Markdown 切块
- 词法检索
- 可选向量索引构建
- 查询接口

### 网页抓取

`app/backend/modules/ai/web_fetcher.py`

关键能力：

- 全网搜索候选抓取
- 公网安全校验
- `robots.txt` 校验
- HTML 正文抽取
- 网页摘要与来源格式化

## 3. 数据来源

### 知识库数据目录

`app/data/`

当前目录下的 Markdown 文档属于 AI 的原始知识数据，不属于项目开发文档。它们直接影响：

- FAQ 命中
- 知识库检索结果
- 回退回答质量

### FAQ 文件

- `app/data/faq.md`

### 综合知识手册

- `app/data/bit_freshman_rag_handbook.md`

### 专题文档

- 入学准备
- 教务服务
- 校园生活
- 奖助学金
- 校园安全
- 医疗
- 社团活动等主题文档

## 4. 聊天请求处理流程

### `POST /api/chat`

请求体：

```json
{
  "question": "北京理工大学奖学金申请条件有哪些？"
}
```

处理流程概括：

1. 校验问题非空
2. 调用 `build_chat_response(question, markdown=True)`
3. 若网页抓取可用，则优先返回基于网页的回答
4. 若网页抓取不可用，则回退 `build_answer`
5. 返回 `answer`、`steps`、`web_sources`、`mode`

### `mode` 说明

当前主要模式：

- `web`：主要基于网页抓取回答
- `kb`：主要基于本地知识库回答

## 5. 索引构建与回退逻辑

### `POST /api/rebuild_index`

作用：

- 重新读取 `app/data/` 文档
- 重建词法或向量索引
- 更新索引状态文件

### 索引状态文件

位于 `app/backend/`：

- `kb_meta.json`
- `kb_state.json`
- `kb_texts.json`
- 可选 `kb_index.faiss`

### `KB_FORCE_LEXICAL`

- `1`：强制使用词法检索，适合网络受限环境
- `0`：优先尝试向量检索，若外部模型不可用再回退

## 6. LLM 配置

当前支持两类配置：

### DeepSeek

- `DEEPSEEK_BASE_URL`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_MODEL`

### OpenAI 兼容接口

- `OPENAI_BASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`

### 通用生成参数

- `OPENAI_TIMEOUT`
- `LLM_TEMPERATURE`
- `LLM_TOP_P`
- `LLM_MAX_TOKENS`
- `LLM_MIN_CONFIDENCE`

若未配置可用 Key，系统仍可工作，但回答会更多依赖知识库和固定兜底逻辑。

## 7. 网页抓取配置

关键变量：

- `WEB_FETCH_ENABLED`
- `WEB_FETCH_TIMEOUT`
- `WEB_FETCH_MAX_URLS`
- `WEB_FETCH_MAX_CHARS`
- `WEB_FETCH_MIN_CONTENT_LENGTH`
- `WEB_FETCH_ROBOTS_CACHE_TTL`
- `WEB_SEARCH_ENABLED`
- `WEB_SEARCH_TIMEOUT`
- `WEB_SEARCH_MAX_RESULTS`
- `WEB_SEARCH_FETCH_LIMIT`

### 安全边界

当前抓取实现明确拒绝：

- 本机地址
- 内网地址
- 保留地址
- 不安全或不规范 URL

因此如果某次抓取失败，不应直接认为是 bug，也可能是安全策略生效。

## 8. 典型维护动作

### 更新知识库内容

1. 修改 `app/data/` 下的 Markdown 文档
2. 调用 `/api/rebuild_index`
3. 查看 `/api/demo_status`
4. 用 `/api/chat` 做问题回归

### 调整回答风格

优先修改：

- `service.py` 中的系统提示词
- Markdown 输出格式
- 兜底文案

### 调整抓取策略

优先修改：

- `web_fetcher.py` 中的搜索候选与抓取逻辑
- 不要在没有必要时扩大抓取边界
- 修改后必须回归 `/api/chat` 和 `tests/url_fetch_smoke_test.py`

## 9. 排障建议

### `/api/chat` 返回空答案

先检查：

- 问题是否为空
- `/api/demo_status` 中 `llm_enabled` 与 `kb_index_ready`
- 网页抓取是否全部失败
- `faq.md` 或知识库是否没有匹配内容

### `/api/rebuild_index` 很慢

可能原因：

- 首次加载模型
- 网络不稳定
- 正在走向量索引构建

可以先把 `KB_FORCE_LEXICAL=1` 验证功能，再决定是否恢复向量模式。

### 网页抓取质量差

先检查：

- 搜索结果站点是否可靠
- 目标站点是否允许抓取
- 提取到的 HTML 正文是否足够
- 问题是否过于模糊

## 10. 自动化验证

### 冒烟测试

```powershell
Set-Location .\app\backend
D:\envs\wechat_work\python.exe .\tests\url_fetch_smoke_test.py https://www.bit.edu.cn --search-query "北京理工大学 选课"
```

### 最低回归要求

修改 AI 模块后，至少执行：

1. `/api/demo_status`
2. `/api/rebuild_index`
3. 一条登录态下的 `/api/chat`
4. 一次网页抓取冒烟测试

## 11. 后续演进方向

- 为 AI 回答补充更细的来源质量评估
- 支持更稳定的向量模型缓存策略
- 引入结构化来源打分或站点优先级策略
- 让前端根据回答模式提供更合适的展示，而不是堆叠调试信息
