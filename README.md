# 智慧问诊 Agent 系统

一套「**领域知识 + 安全问答**」的端到端智慧问诊 Agent 系统。

## 项目一句话

爬取医疗数据 → 大模型抽取实体关系建知识图谱 → 向量 + 图谱双路混合检索（GraphRAG）→ LangGraph 多 Agent 协作问答 → FastAPI + Vue3 流式前端。回答强制绑定检索证据，并叠加确定性安全规则（免责声明 / 急症预警 / 用药提醒）。

## 技术栈

| 层 | 技术 |
|---|---|
| 数据层 | Neo4j 5.26（8 类节点 / 12 类关系）、FAISS（IndexIVFFlat）、BGE-M3 |
| 智能体层 | LangChain 0.1.x + LangGraph 0.0.x |
| API 层 | FastAPI + SSE 流式输出 |
| 前端层 | Vue3 + Element Plus |
| 基础设施 | docker-compose（Neo4j / Redis / MySQL） |

## 目录结构

```
smart-medical-consultation/
├── backend/                 # FastAPI 后端（app/api、agent、retrieval、store）
│   └── main.py              # 入口：CORS + 路由挂载
├── frontend/                # Vue3 + Vite + Element Plus 前端
├── docker-compose.yml       # 一键拉起 Neo4j(7474/7687) / MySQL(3307) / Redis(6379)
├── requirements.txt         # 后端锁定依赖
└── .env                     # 连接配置（不入库，需自行复制填写）
```

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

> 健康检查：`GET http://127.0.0.1:8000/health` 返回 `{"code":1,...,"data":{"status":"ok",...}}`

### 3. 启动前端
```bash
cd frontend
npm install
npm run dev                  # 运行在 http://localhost:5173
```

## 里程碑

- [x] P0 项目骨架搭建（前端 Vue3 + 后端 FastAPI + /health）
- [ ] P1 核心对话交互（消息收发 + SSE 流式）
- [ ] P2 业务功能完善（真实 LLM、会话缓存、安全规则）
- [ ] P3 核心技术壁垒（GraphRAG + 多 Agent）
- [ ] P4 工程化收尾（持久化、评估门禁、微调、部署）

*本系统仅供健康咨询与就医指导，不能替代专业医疗诊断。身体不适请及时就医，切勿自行用药。*
