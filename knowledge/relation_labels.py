"""图谱关系类型 → 中文说明。

向量索引脚本（knowledge/index/build_vector_index.py）与节点 desc 回填脚本
（scripts/fill_node_desc.py）共用这一份映射，避免两处各存一份导致口径漂移。
新增关系类型时只改这里。

REL_CN：出边方向（从当前节点看出去）的表述，例如
        感冒 --HAS_SYMPTOM--> 发热  →  「常见症状发热」
REV_CN：入边方向（别的节点指过来）的表述，例如
        感冒 --HAS_SYMPTOM--> 发热  →  发热的 desc 里写「可见于感冒」
        叶子节点（症状/科室/药物）只有入边，靠 REV_CN 才能有可用描述。
"""

REL_CN = {
    "HAS_SYMPTOM": "常见症状", "BELONG_DISEASE": "相关疾病", "BELONG_DEPARTMENT": "建议科室",
    "HAS_CAUSE": "病因", "HAS_CURE": "疗法", "HAS_TABOO": "禁忌",
    "FIT_CROWD": "适用人群", "USE_DRUG": "常用药物", "DRUG_SUIT": "适应症",
    "DRUG_SIDE_EFFECT": "副作用", "DRUG_TABOO_CROWD": "禁忌人群", "DRUG_INTERACT": "相互作用",
}

REV_CN = {
    "HAS_SYMPTOM": "可见于",
    "BELONG_DISEASE": "相关疾病有",
    "BELONG_DEPARTMENT": "相关疾病有",
    "HAS_CAUSE": "相关疾病有",
    "HAS_CURE": "作用于",
    "HAS_TABOO": "相关疾病有",
    "FIT_CROWD": "适用人群见于",
    "USE_DRUG": "用于治疗",
    "DRUG_SUIT": "可用药物有",
    "DRUG_SIDE_EFFECT": "作为副作用见于",
    "DRUG_TABOO_CROWD": "禁忌人群见于",
    "DRUG_INTERACT": "与以下药物存在相互作用：",
}
