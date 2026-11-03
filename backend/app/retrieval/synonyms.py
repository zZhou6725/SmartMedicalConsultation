"""口语归一：把用户怎么说的，映射到图谱里怎么存的。

为什么需要：
  用户说「我现在肩膀有点痛」，图谱里的实体叫「肩痛」——
  字面不一致，向量能沾一点边，关键词（CONTAINS）直接 0 命中，
  于是症状标签和科室双双为空。

做法：识别「部位词 + 修饰 + 痛/疼」的口语模式，归一成规范症状名。
  肩膀有点痛  → 肩痛
  膝盖疼      → 膝痛
  脖子酸痛    → 颈痛（"酸痛"里的"痛"同样命中）
  我腰疼      → 腰痛

只覆盖**部位性疼痛**这一类（范围小、规则明确、误伤低），
不做通用同义词扩展 —— 那需要医学词表，属于另一个量级的工作。
"""
import re

# 部位词 → 规范部位（长的优先匹配，避免"肩关节"被"肩"吃掉）
PART_WORDS = {
    "肩关节": "肩", "肩膀": "肩", "肩部": "肩", "肩": "肩",
    "膝关节": "膝", "膝盖": "膝", "膝部": "膝", "膝": "膝",
    "颈椎": "颈", "脖子": "颈", "颈部": "颈", "颈": "颈",
    "腰部": "腰", "腰": "腰",
    "踝关节": "踝", "脚踝": "踝", "踝部": "踝", "踝": "踝",
    "肘关节": "肘", "手肘": "肘", "胳膊肘": "肘", "肘部": "肘", "肘": "肘",
    "手腕": "腕", "腕部": "腕", "腕": "腕",
    "髋关节": "髋", "胯骨": "髋", "髋部": "髋", "髋": "髋",
}

_PARTS_ALT = "|".join(sorted(PART_WORDS, key=len, reverse=True))
# 部位词后允许 0~4 个非标点字符（"有点""一直""特别"），然后必须出现 痛/疼
_PAIN_RE = re.compile(rf"({_PARTS_ALT})[^，。,.!?！？]{{0,4}}?(?:痛|疼)")


def normalize_query(text: str) -> str:
    """把口语化部位疼痛归一为规范症状名；其它内容原样保留。"""
    if not text:
        return text

    def _repl(m: re.Match) -> str:
        part = m.group(1)
        return f"{PART_WORDS.get(part, part)}痛"

    return _PAIN_RE.sub(_repl, text)


def expand_terms(text: str) -> list:
    """归一后额外产出可直接用于关键词检索的候选词。

    kg_store.search_nodes 是 CONTAINS 匹配，用规范名才能命中实体。
    """
    normalized = normalize_query(text or "")
    terms = []
    for m in _PAIN_RE.finditer(text or ""):
        canon = f"{PART_WORDS.get(m.group(1), m.group(1))}痛"
        if canon not in terms:
            terms.append(canon)
    if not terms and normalized and normalized != text:
        terms.append(normalized)
    return terms
