# 部署与运维手册

面向"从零把整套系统跑起来"和"出问题怎么查"。开发细节见 `README.md`。

---

## 1. 前置条件

| 项 | 要求 |
|---|---|
| Docker Desktop | 已启动（含 compose v2） |
| `.env` | 从 `.env.example` 复制并填好 `LLM_API_KEY` |
| 向量索引 | **必须先构建**：`python knowledge/index/build_vector_index.py`（索引文件在 `.gitignore` 中，不会随仓库提供） |
| 知识图谱数据 | 用 `knowledge/crawl/` + `scripts/neo4j_*.cql` 灌入；空库也能启动，但检索无内容 |
| 磁盘 | 首次构建 + 模型约 6~8 GB（镜像 ~3 GB，BGE-M3 ~2.2 GB） |

> 索引为什么要挂载而不是打进镜像？因为它 10 MB 级、且依赖你爬到的数据，
> 属于"环境产物"而不是"源码"。挂载后重建索引不需要重新 build 镜像。

---

## 2. 一键启动

```bash
# 首次（会构建镜像，时间较长）
docker compose up -d --build

# 之后
docker compose up -d

# 看状态（重点看 STATUS 列是否为 healthy）
docker compose ps

# 跟后端结构化日志（JSON 单行）
docker compose logs -f backend

# 停止（保留数据卷）
docker compose down

# 停止并清空数据（慎用：会删图谱/业务库/模型缓存）
docker compose down -v
```

---

## 3. 端口与访问入口

| 服务 | 宿主机 | 说明 |
|---|---|---|
| 前端（Nginx 网关） | **http://localhost:8080** | 唯一对外入口，`/api` 反代到后端 |
| 后端 API | http://localhost:8000 | 也直接暴露，便于调试与接口文档 `/docs` |
| Neo4j Browser | http://localhost:7474 | 账号 `neo4j` / `123456` |
| MySQL | `localhost:3307` | 本机 3306 常被占用，故映射 3307 |
| Redis | `localhost:6379` | |

---

## 4. 启动顺序是怎么保证的

不靠 `sleep` 猜，而是靠健康检查 + 依赖条件：

```
neo4j healthy ┐
mysql healthy ├─→ backend ready(/readyz 200) ─→ web healthy(nginx /healthz)
redis healthy ┘
```

- 后端的 compose 健康检查打的是 **`/readyz`**（Neo4j / 向量索引 / Redis / MySQL / LLM 全通才 200），
  而不是 `/healthz`（只证明进程活着）。
- 因此 `web` 只有在后端"真能接客"之后才会启动，避免用户一上来就拿到 503。

---

## 5. 上线验证清单

按顺序执行，任一步不符就是没起来：

```bash
# ① 五个容器全部 healthy
docker compose ps --format "table {{.Name}}\t{{.Status}}"

# ② 存活探针（不查依赖，永远应该 200）
curl -fsS http://localhost:8000/healthz
# 期望 {"status":"alive",...}

# ③ 就绪探针（依赖全通才 200，503 说明有组件没起来）
curl -fsS http://localhost:8000/readyz
# 期望 {"status":"ready","checks":{"neo4j":true,"vectorIndex":true,...,"llm":true},"breaker":{...}}

# ④ 前端能打开、接口能通（走 Nginx 反代）
curl -fsS http://localhost:8080/healthz          # ok
curl -fsS http://localhost:8080/api/system/status | head -c 200

# ⑤ 流式是否真的"流"（SSE 不能被 Nginx 缓冲住）
curl -N -X POST http://localhost:8080/api/chat/stream \
     -H "Content-Type: application/json" \
     -d '{"message":"头痛挂什么科"}'
# 期望逐帧出现 meta → delta×N → done；若一次性吐出全部，说明 proxy_buffering 没关

# ⑥ 出问题后能按 traceId 回放
curl -fsS http://localhost:8080/api/trace/stats
curl -fsS "http://localhost:8080/api/trace/recent?limit=5"
```

---

## 6. 安全配置（对外前必做）

### 6.1 管理令牌 `ADMIN_TOKEN`

`/api/eval`（触发评估会烧大量 token）、`/api/kg`（可看全库）、`/api/trace`（含 question 原文）
统一要求请求头 `X-Admin-Token`。

**默认行为**：`ADMIN_TOKEN` 留空时**只允许本机访问**这些接口 ——
这是"默认安全"：本地开发零配置可用，但绝不会因为忘了配而对外敞开。

```bash
# 生成一个强令牌
python -c "import secrets;print(secrets.token_urlsafe(32))"
# 写进 .env
ADMIN_TOKEN=上面生成的值
```

验证：

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/api/trace/recent
# 期望 403（未带令牌）

curl -s -o /dev/null -w "%{http_code}\n" \
     -H "X-Admin-Token: 你的令牌" http://localhost:8080/api/trace/recent
# 期望 200
```

### 6.2 会话令牌 `X-Session-Key`

每次对话首次创建会话时，服务端签发 `sessionKey`（32 字符，不可猜）。之后读写该会话
（读消息 / 删会话 / 列表）都必须带上它。

> 为什么必须：之前只要知道 `sessionId` 就能读光别人的问诊记录 —— 健康数据不能这样裸奔。
> 前端已把令牌按会话存在 `localStorage`，并在请求头自动携带，刷新后仍能恢复自己的历史。

直接验证越权会被拒：

```bash
SID=某个会话id
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8080/api/chat/messages?sessionId=$SID"
# 期望 403
```

非管理员调 `GET /api/sessions` 只能看到**自己持有令牌**的会话（需带 `X-Session-Keys`）。

### 6.3 限流

在 Nginx 层按 IP 限流（`frontend/nginx.conf`）：

| 路径 | 限制 | 说明 |
|---|---|---|
`/api/chat/` | 10 次/分钟，突发 5 | 一次问诊 3~5 秒且花额度，必须卡住 |
`/api/` | 120 次/分钟，突发 40 | 其它接口 |
超限返回 **429**。

> 后端 8000 端口在 compose 里已绑定 `127.0.0.1`，**对外只走 Nginx** ——
> 否则可以直接绕过限流和后端日志。

### 6.4 启用 HTTPS

`frontend/nginx.conf` 末尾已备好 443 的 server 块（取消注释即可）：

```bash
# 本机演示：自签证书
mkcert localhost 127.0.0.1      # 生成 localhost.pem / localhost-key.pem
mkdir -p frontend/certs && mv *.pem frontend/certs/
```

然后：
1. `frontend/nginx.conf` 里取消 443 块注释；把 80 的 server 改成 `return 301 https://$host$request_uri;`
2. `docker-compose.yml` 的 `web` 服务取消 `- "8443:443"` 与 `./frontend/certs` 挂载的注释
3. `docker compose up -d --build`

有域名时用 certbot 申请证书，挂载 `/etc/letsencrypt` 即可（HSTS 头已写在 443 块里）。

## 7. 常见故障

| 现象 | 原因 | 处理 |
|---|---|---|
| `backend` 一直是 `unhealthy` | `/readyz` 里某项 false | `curl localhost:8000/readyz` 看是哪一项；`docker compose logs backend` |
| 启动即报 `vectorIndex not ready` | 索引没挂上或没构建 | 确认 `knowledge/index/medical_faiss.index` 存在；容器内路径 `/app/knowledge/index` |
| 报模型加载失败 / 卡住 | `EMBEDDING_LOCAL_ONLY=1` 但缓存卷是空的 | 确认 compose 里该值为 `0` 首次下载；或预先往 `hf-cache` 卷灌缓存 |
| `web` 起不来 | 后端未 healthy（依赖条件不满足） | 先修后端 |
| 回答"一次蹦出来"而非逐字 | Nginx 缓冲了 SSE | 检查 `frontend/nginx.conf` 的 `proxy_buffering off` |
| 大模型报错但系统没崩 | 熔断器打开 | `curl localhost:8000/readyz` 看 `breaker.state`，冷却 60s 自动半开 |

---

## 8. 运维要点

**日志**：后端输出 JSON 单行，含 `traceId / intent / latency_ms / retrieve_ms / generate_ms / fallback`，
可直接被 Loki/ELK 采集。本地想看人类可读格式：`.env` 里设 `LOG_JSON=0`。

**改阈值不用改代码**：`EVIDENCE_MAX_ITEMS` / `RELEVANCE_FLOOR` / `LEXICAL_BOOST` / `LLM_TIMEOUT`
等都在 `.env`，改完 `docker compose up -d` 即生效。

**更新基线（谨慎）**：只有确认本次指标没有回归才执行，否则等于把回归"合法化"：
```bash
docker compose exec backend python -m app.eval --update-baseline
```

**数据备份**（业务数据在卷里）：
```bash
docker compose exec mysql mysqldump -uroot -p123456 medical_consult > backup.sql
docker run --rm -v smartmedicalconsultation_neo4j-data:/data -v %cd%:/backup alpine \
  tar czf /backup/neo4j-data.tar.gz -C /data .
```

**重建索引后**：不需要重启后端（下次检索会读新文件），但若后端已缓存旧索引则需 `docker compose restart backend`。

---

## 9. 与本地开发的差异

| 项 | 本地开发 | 容器 |
|---|---|---|
| 项目根 | 仓库根目录 | `/app`（`PROJECT_ROOT` 覆盖） |
| 中间件地址 | `localhost:xxxx` | 服务名 `neo4j/mysql/redis` |
| 索引 | 直接读 `knowledge/index/` | 只读挂载到 `/app/knowledge/index` |
| 模型缓存 | `%USERPROFILE%\.cache\huggingface` | 命名卷 `hf-cache` |
| 前端 | Vite dev server（5173） | Nginx 托管构建产物（8080） |

---

## 10. 已知限制

- 镜像未做多阶段瘦身（`sentence-transformers` + `torch` 体积大）；生产可换 `python:3.12-slim` +
  预装 CPU 版 torch 并固定版本。
- **鉴权是"最小可用"级别**：管理令牌 + 会话能力令牌，**没有用户体系**（无注册/登录/角色）。
  适合个人项目与小规模内部使用；要支撑多用户运营，需要引入真实身份（OIDC/JWT）+ 会话归属到用户。
- **HTTPS 需手动启用**（见第 6.4 节），默认仍是 HTTP —— 只在 `localhost` 演示时可接受，
  一旦跨机器访问必须先开。
- 限流是**按 IP 的粗粒度**：NAT 后的多人会共享额度；要按用户维度限流需在应用层用 Redis 令牌桶。
- 本编排**未在容器里实测**（编写时所在环境不能启动 Docker），首次 `up` 可能需要按第 7 节微调。
