"""Neo4j 知识图谱查询（只读）。

只读防护（对应接口文档「Text2Cypher 五层防护」中本项目已落地的部分）：
  1. 白名单：实体类型只能取 ENTITY_LABELS 里的 8 类，不在白名单直接拒绝；
  2. 参数化：所有查询一律走 $param 占位符，用户输入不拼接进 Cypher；
  3. 只读关键词黑名单：语句中出现 CREATE/MERGE/DELETE/SET 等写操作直接抛错；
  4. 数值校验：深度只接受 1~3 的整数（Cypher 变长路径不支持参数化，故必须钳制）；
  5. 长度限制：语句长度与实体名长度设上限，避免超长输入。
"""
from neo4j import GraphDatabase

from app.config import settings

_driver = None

# 实体类型枚举 → Neo4j 标签（白名单，防注入）
ENTITY_LABELS = {
    "disease": "Disease", "symptom": "Symptom", "drug": "Drug", "department": "Department",
    "crowd": "Crowd", "taboo": "Taboo", "cure": "Cure", "cause": "Cause",
}

# 写操作关键词黑名单（只读防护；将来接 Text2Cypher 时的兜底）
_WRITE_KEYWORDS = ["CREATE", "MERGE", "DELETE", "SET ", "REMOVE", "DROP", "LOAD CSV", "CALL DB."]

MAX_CYPHER_LEN = 2000   # 语句长度上限（第五层防护）
MAX_NAME_LEN = 64       # 实体名长度上限
MAX_DEPTH = 3           # 图谱扩展的最大深度


def get_driver():
    """懒加载 driver（整个进程复用同一个连接池）。"""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
    return _driver


def run_read(cypher: str, **params) -> list:
    """只读执行：先做写操作关键词校验与长度校验，再执行并返回 dict 列表。"""
    if len(cypher) > MAX_CYPHER_LEN:
        raise ValueError(f"只读防护：语句过长（{len(cypher)} > {MAX_CYPHER_LEN}），已拒绝")
    upper = cypher.upper()
    for kw in _WRITE_KEYWORDS:
        if kw in upper:
            raise ValueError(f"只读防护：检测到写操作关键词 {kw!r}，已拒绝")
    with get_driver().session() as session:
        return session.run(cypher, **params).data()


def _check_name(name: str) -> str:
    """实体名校验：非空 + 长度上限。"""
    name = (name or "").strip()
    if not name:
        raise ValueError("实体名不能为空")
    if len(name) > MAX_NAME_LEN:
        raise ValueError(f"实体名过长（{len(name)} > {MAX_NAME_LEN}）")
    return name


def _clamp_depth(depth) -> int:
    """深度校验：非法值一律回落为 1，超出上限截断（防变长路径爆炸）。"""
    try:
        depth = int(depth)
    except (TypeError, ValueError):
        return 1
    return max(1, min(depth, MAX_DEPTH))


def node_exists(name: str):
    """实体是否存在：返回 {name, type, desc} 或 None。"""
    rows = run_read(
        "MATCH (n {name: $name}) RETURN n.name AS name, labels(n)[0] AS type, n.desc AS desc",
        name=_check_name(name),
    )
    if not rows:
        return None
    row = rows[0]
    row["type"] = (row["type"] or "").lower()
    return row


def get_entity(entity_type: str, name: str):
    """实体详情 + 关联关系（接口15）。类型不在白名单 → 返回 None。"""
    label = ENTITY_LABELS.get((entity_type or "").lower())
    if not label:                       # 类型不在白名单 → 直接拒绝
        return None
    rows = run_read(
        f"""
        MATCH (n:{label} {{name: $name}})
        OPTIONAL MATCH (n)-[r]->(m)
        RETURN n.name AS name, n.desc AS desc,
               collect(CASE WHEN r IS NULL THEN null
                            ELSE {{relation: type(r), target: m.name,
                                   targetType: labels(m)[0]}}
                       END) AS relations
        """,
        name=_check_name(name),
    )
    if not rows:
        return None
    row = rows[0]
    relations = [
        {"relation": x["relation"],
         "target": {"name": x["target"], "type": (x["targetType"] or "").lower()}}
        for x in row["relations"] if x
    ]
    return {
        "name": row["name"],
        "type": (entity_type or "").lower(),
        "desc": row["desc"] or "",
        "relations": relations,
    }


def search_nodes(keyword: str, limit: int = 20) -> list:
    """按关键词模糊搜索实体（接口16）。

    用 CONTAINS 而不是 medical_fulltext 全文索引：Neo4j 默认分析器不切分中文，
    全文索引对「头痛」这类无空格中文词匹配不到，CONTAINS 反而更可靠。
    """
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 20
    rows = run_read(
        """
        MATCH (n)
        WHERE n.name CONTAINS $kw
        RETURN n.name AS name, labels(n)[0] AS type, n.desc AS desc
        LIMIT $limit
        """,
        kw=_check_name(keyword), limit=limit,
    )
    for r in rows:
        r["type"] = (r["type"] or "").lower()
        r["desc"] = r["desc"] or ""
    return rows


def expand_entity(name: str, depth: int = 1):
    """按实体名做结构化关系扩展（接口14 的图谱那一路）。

    depth 为扩展深度：1 = 直接出边，2~3 = 变长路径可达关系（去重）。
    Cypher 的变长路径长度不支持参数化，因此 depth 先经整数校验与钳制再拼接。
    """
    name = _check_name(name)
    depth = _clamp_depth(depth)
    if node_exists(name) is None:
        return None
    rows = run_read(
        f"""
        MATCH p = (n {{name: $name}})-[*1..{depth}]->(m)
        UNWIND relationships(p) AS r
        RETURN DISTINCT type(r) AS relation,
               endNode(r).name AS target,
               labels(endNode(r))[0] AS targetType
        ORDER BY relation, target
        """,
        name=name,
    )
    return {
        "entity": name,
        "relations": [
            {"relation": r["relation"], "target": r["target"],
             "targetType": (r["targetType"] or "").lower()}
            for r in rows
        ],
    }


def get_stats() -> dict:
    """图谱统计（接口17）：节点/关系总数 + 各类分布。"""
    node_count = run_read("MATCH (n) RETURN count(n) AS c")[0]["c"]
    rel_count = run_read("MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
    node_types = run_read("MATCH (n) RETURN labels(n)[0] AS type, count(*) AS count ORDER BY count DESC")
    rel_types = run_read("MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count ORDER BY count DESC")
    for r in node_types:
        r["type"] = (r["type"] or "").lower()
    return {
        "nodeCount": node_count,
        "relationCount": rel_count,
        "nodeTypes": node_types,
        "relationTypes": rel_types,
    }
