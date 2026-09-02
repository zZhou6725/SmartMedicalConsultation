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
├── docs/                    # 项目文档
├── scripts/                 # Neo4j/MySQL 初始化脚本
├── docker-compose.yml       # 一键拉起 Neo4j/MySQL/Redis
├── requirements.txt         # 后端锁定依赖
└── .env                     # 连接配置（不入库）
```

## 快速开始（环境准备）

1. `docker compose up -d` → 启动 Neo4j（7474/7687）、MySQL（3307）、Redis（6379）。
2. 执行 `scripts/neo4j_seed.cql`（先灌种子）与 `scripts/neo4j_schema.cql`（后建约束）。
3. 执行 `scripts/mysql_init.sql` 建三张业务表。
4. 创建 Python 3.12 虚拟环境并 `pip install -r requirements.txt`。
5. 复制 `.env` 填入 `LLM_API_KEY`。

> 详细开发路线见 `docs/智慧问诊Agent系统-开发总手册（实习版）.md`，接口定义见 `docs/智慧问诊Agent系统-接口文档.md`。

*本系统仅供健康咨询与就医指导，不能替代专业医疗诊断。身体不适请及时就医，切勿自行用药。*
