# 智慧问诊 Agent 系统

一套「**领域知识 + 安全问答**」的端到端智慧问诊 Agent 系统。

## 项目一句话

爬取医疗数据 → 大模型抽取实体关系建知识图谱 → 向量 + 图谱双路混合检索（GraphRAG）→ LangGraph 多 Agent 协作问答 → FastAPI + Vue3 流式前端。回答强制绑定检索证据，并叠加确定性安全规则（免责声明 / 急症预警 / 用药提醒）。

## 界面预览

![智慧问诊界面原型](images/prototype.png)

## 技术栈

| 层 | 技术 |
|---|---|
| 数据层 | Neo4j 5.26（8 类节点 / 12 类关系）、FAISS（IndexFlatIP，内积=余弦）、BGE-M3（1024 维） |
| 智能体层 | LangChain 0.1.x + LangGraph 0.0.x |
| 大模型 | OpenAI 兼容接口（默认 DeepSeek；`.env` 一行切换本地 vLLM） |
| 会话存储 | Redis 热缓存（最近 12 轮 / TTL 24h）；MySQL 全量持久化（P4） |
| API 层 | FastAPI + SSE 流式输出 |
| 前端层 | Vue3 + Vite + Element Plus（axios 统一请求封装 + Vite 代理） |
| 基础设施 | docker-compose（Neo4j / Redis / MySQL） |

## 已实现功能（截至 P3）

- **核心对话**：SSE 流式逐字输出、多轮上下文、回车发送、自动滚动到底
- **真实 LLM**：接入大模型（DeepSeek），回答简洁要点化、**不使用 emoji**
- **会话历史**：Redis 热缓存（最近 12 轮 / TTL 24h）+ **MySQL 全量持久化**（重启/缓存过期后历史仍可恢复）、左栏列表、点击切换复原、删除会话
- **持久化分层**：喂模型的上下文取 Redis（未命中回 MySQL 并回填，截断最近 12 轮控制 token）；前端看的历史走 MySQL 全量；会话列表以 MySQL 为准。MySQL 不可用时自动退回 Redis，不影响对话主流程
- **医疗安全层**：确定性规则引擎 —— 所有回答强制附带免责声明；用药类问题追加用药提醒
- **医疗 UI**：免责警示条、响应耗时、一键复制、症状标签 / 推荐科室（已由检索证据推导）
- **知识图谱**：Neo4j 8 类实体 / 12 类关系，47 节点 52 关系；只读查询 + 五层防护（白名单 / 参数化 / 写关键词拦截 / 数值钳制 / 长度上限）
- **向量检索**：BGE-M3 + FAISS（`IndexFlatIP`，1024 维），索引文本取节点 `desc`（图谱出边 + 入边自动生成的语义句）
- **GraphRAG 混合检索**：向量语义召回 + 以命中实体为种子扩展图谱双向三元组，双路合并去重
- **回答可溯源**：证据拼进 system 上下文做 grounded 作答，响应回传 `evidence`（`source` = `vector` / `kg`）；`symptoms` / `department` 均由证据推导，非硬编码
- **多 Agent 编排**：LangGraph 状态图 —— 意图识别 → 条件路由到 6 个分支（症状 / 科室 / 用药 / 医学知识 / 就医指导 / 通用）→ 强制汇聚安全检查
- **Tool Calling**：五个医疗分支内由大模型自主决定调用 `vector_search` / `kg_search` / `kg_expand`（可多工具、多轮），工具执行结果既回灌给模型也写入 `evidence`；模型未调工具时自动兜底走固定混合检索
- **急症预警**：确定性关键词表（胸痛 / 呼吸困难 / 剧烈头痛 / 言语不清 / 抽搐 / 大出血等）命中即置顶**红色警示卡片**，并强制模型先提示拨打 120 或急诊、不给用药建议；关键词刻意收窄，普通「头痛」「肚子疼」不误触发
- **高危问题风控**：剂量 / 禁忌 / 联合用药 / 孕哺儿童等关键词命中时，强制模型不给具体剂量与方案、只做原则性说明并引导咨询医师药师
- **自动化评估门禁**：86 条金标集分 9 类（急症 / 科室 / 用药 / 症状 / 知识 / 检查 / 拒答 / 超范围 / 闲聊），四层评估 —— 硬规则（免责声明覆盖率、急症召回率、拒答合规率）**一票否决** + 关键词命中 + 检索 Recall@5/MRR + LLM 裁判；产出 Markdown 评测报告（含失败用例 trace）并回写 `eval_record` 表
- **相对基线门禁（CI 门禁第二层）**：绝对阈值只能兜住「明显坏了」，指标从 0.97 静悄悄掉到 0.85 它不会吭声。因此把上一版结果存为 `baseline.json`，逐项比对跌幅（任务成功率 ±3pt / Recall@5 ±0.05 / MRR ±0.05），超容差即 `gate=BLOCKED` 且进程退出码 1 —— 可直接接 CI 流水线阻断合并
- **可观测性（请求级 trace）**：每次对话落一条链路 —— 意图、工具调用及成败、召回实体、编排耗时 / 生成耗时 / 总耗时、是否走了降级；`GET /api/trace/{traceId}` 可回放单次请求，`/api/trace/stats` 给请求量、降级率、分阶段平均耗时
- **单元测试**：25 个纯逻辑用例（标准库 unittest，无额外依赖），覆盖指标判定、急症/高危识别（含反例）、意图路由、相关性下限、同族去重、基线门禁；`cd backend && python -m unittest discover -s tests`

## 目录结构

```
smart-medical-consultation/
├── backend/
│   ├── app/
│   │   ├── api/            # 接口层：system(/health)、chat、sessions、search、kg、eval_api
│   │   ├── services/       # 业务服务：llm（大模型调用）、safety（安全规则）
│   │   ├── store/          # 数据访问：session_store（Redis+MySQL）、kg_store（Neo4j 只读）、eval_repo
│   │   ├── agent/          # 多 Agent 编排：state（状态）、tools（Tool Calling）、nodes（节点）、graph（状态图）
│   │   ├── eval/           # 评估引擎：golden（金标集）、metrics（指标）、judge（LLM 裁判）、runner（执行）
│   │   └── retrieval/      # embeddings（BGE-M3）、vector_store（FAISS）、hybrid（GraphRAG）
│   └── main.py             # 入口：CORS + 路由挂载
├── knowledge/
│   ├── relation_labels.py  # 关系类型 → 中文说明（建索引与 desc 回填共用）
│   ├── build_desc.py       # 用图谱已有关系回填节点 desc（不引入外部医学知识）
│   ├── crawl/              # 知识库采集流水线：爬取 → 解析 → 写入 Neo4j
│   │   ├── crawl_diseases.py   # 从有来医生疾病库抓结构化字段（限速 1.5s/请求）
│   │   └── load_graph.py       # 幂等 MERGE 写入 Neo4j（与种子数据共存）
│   └── index/              # 向量索引构建脚本（产物 .index/.json 不入库，可重建）
├── eval/
│   ├── golden_set.json     # 53 条金标集（入库，版本化）
│   └── reports/            # 评测报告产物（不入库，可重建）

├── frontend/               # Vue3 + Vite + Element Plus
│   └── src/{api,utils}/    # 接口集中管理 + axios 统一请求封装
├── docker-compose.yml      # Neo4j(7474/7687) / MySQL(3307) / Redis(6379)
└── requirements.txt        # 后端锁定依赖
```

## 知识库构建（从零重建）

```bash
# 1. 采集：抓 559 个疾病的结构化字段（挂号科室/相关症状/相关药品/相关疾病…）
python knowledge/crawl/crawl_diseases.py            # 产物落 data/raw/diseases.json
# 2. 入库：幂等 MERGE 进 Neo4j，可与原种子数据共存
python knowledge/crawl/load_graph.py
# 3. 描述：用关系拼出每个节点的一句话 desc（向量索引与接口 15/16 都用它）
python knowledge/build_desc.py
# 4. 索引：BGE-M3 编码 + FAISS 建索引
python knowledge/index/build_vector_index.py
```

> 数据来源：[有来医生疾病库](https://www.youlai.cn/dise/)，其 `robots.txt` 仅禁止少量路径，
> 疾病页允许抓取。只取页面中已结构化的字段，不抓正文自由文本，因此无需 LLM 抽取、结果可复核。
> 抓取限速 1.5 秒/请求。当前规模：**2489 节点 / 6772 关系**。

## 接口（已实现）

| 方法与路径 | 说明 |
|---|---|
| `GET /health` | 健康检查 |
| `GET /api/system/status` | 系统状态：6 组件真实探活 + 业务运行指标 |
| `POST /api/chat` | 发送对话（非流式） |
| `POST /api/chat/stream` | 发送对话（SSE 流式） |
| `GET /api/chat/messages` | 会话消息列表 |
| `GET /api/sessions` | 会话列表 |
| `DELETE /api/sessions/{sessionId}` | 删除会话 |
| `POST /api/search/hybrid` | GraphRAG 混合检索（向量 + 图谱双路） |
| `POST /api/search/vector` | 向量语义检索 |
| `POST /api/search/kg` | 图谱结构化检索（按实体名扩展关系） |
| `GET /api/kg/entity/{type}/{name}` | 实体详情 + 关联关系 |
| `GET /api/kg/search` | 图谱关键词搜索 |
| `GET /api/kg/stats` | 图谱统计 |
| `POST /api/eval/run` | 触发自动化评估（返回通过率 / 分层指标 / 门禁结论） |
| `GET /api/eval/records` | 评估记录分页查询 |
| `GET /api/eval/records/{id}` | 评估记录详情 |
| `GET /api/trace/stats` | 近 N 小时运行指标（请求量 / 降级率 / 分阶段耗时） |
| `GET /api/trace/recent` | 最近 N 条请求链路 |
| `GET /api/trace/{traceId}` | 单条链路回放 |

## 快速开始

### 1. 启动基础中间件
```bash
docker compose up -d        # 启动 Neo4j / MySQL(3307) / Redis
```

### 2. 配置后端
```bash
cp .env.example .env         # 复制并填写 LLM_API_KEY（本仓库 .env 不入库）
# Python 3.12 虚拟环境
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
cd backend
python main.py               # 服务运行在 http://127.0.0.1:8000
```

> 健康检查：`GET http://127.0.0.1:8python.exe knowledge\index\build_vector_index.pypython.exe knowledge\index\build_vector_index.py000/health`

### 3. 启动前端
```bash
cd frontend
npm install
npm run dev                  # 运行在 http://localhost:5173
```

## 里程碑

- [x] P0 项目骨架搭建（前端 Vue3 + 后端 FastAPI + /health）
- [x] P1 核心对话交互（消息收发 + SSE 流式）              ← P1-1 ~ P1-5
- [x] P2 业务功能完善（真实 LLM、会话缓存、安全规则）      ← P2-1 ~ P2-5 + 会话删除
- [x] P3 核心技术壁垒（向量检索 / 图谱只读查询 / GraphRAG 混合检索与证据溯源 / 多 Agent 编排 + Tool Calling / 急症预警与高危风控）← P3-1 ~ P3-5 全部完成
- [x] P4 工程化收尾 —— MySQL 全量持久化 ✅（P4-1）/ 自动化评估门禁 ✅（P4-2）/ 微调、一键部署待做

*本系统仅供健康咨询与就医指导，不能替代专业医疗诊断。身体不适请及时就医，切勿自行用药。*
