"""确定性安全层：免责声明 + 用药提醒（纯规则引擎，不依赖 LLM）。"""

# 标准免责声明（所有医疗回答强制附带）
DISCLAIMER = "本回答仅供健康咨询与就医指导，不能替代专业医疗诊断。身体不适请及时就医，切勿自行用药。"

# 用药提醒（用药类问题强制追加）
MED_REMINDER = "用药请严格遵医嘱或咨询药师，切勿自行调整剂量、随意联用药物。"

# 用药相关关键词（命中则追加用药提醒）
DRUG_KEYWORDS = [
    "药", "服用", "口服", "剂量", "几片", "胶囊", "片剂", "冲剂",
    "布洛芬", "阿莫西林", "二甲双胍", "奥美拉唑", "氨氯地平", "对乙酰氨基酚",
    "感冒灵", "抗生素", "止痛药", "消炎药", "退烧药", "中药", "西药",
]


def is_drug_question(text: str) -> bool:
    """是否用药相关问题。"""
    return any(k in text for k in DRUG_KEYWORDS)


def safety_fields(question: str) -> dict:
    """安全字段：免责声明（恒定非空）+ 用药提醒（用药问题才非空）。"""
    return {
        "disclaimer": DISCLAIMER,
        "medReminder": MED_REMINDER if is_drug_question(question) else "",
    }