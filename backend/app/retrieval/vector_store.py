"""FAISS 向量索引：构建 / 保存 / 加载 / 检索。"""
import json

import faiss
import numpy as np



from app.config import BASE_DIR

INDEX_DIR = BASE_DIR / "knowledge" / "index"
INDEX_PATH = INDEX_DIR / "medical_faiss.index"
META_PATH = INDEX_DIR / "medical_faiss_meta.json"

_index = None # 全局变量：进程里缓存faiss索引，避免重复加载磁盘
_metas = None # 全局变量：缓存元数据列表，和向量顺序一一对应



def build(vector: np.ndarray, metas: list):
    """构建并保存索引。vectors 形状 (N, dim)，需已归一化。"""
    dim = vector.shape[1]
    index = faiss.IndexFlatIP(dim)     # 内积索引（精确检索）
    index.add(vector.astype("float32"))
    INDEX_DIR.mkdir(parents=True, exist_ok=True) #创建文件夹，parents自动创建多级目录，exist_ok=True目录存在也不报错
    # 写入磁盘二进制文件
    faiss.write_index(index, str(INDEX_PATH))
    # 打开元数据文件，w模式写入，utf-8 编码防止中文乱码
    with open(META_PATH, "w", encoding="utf-8") as f:
        # 将元数据列表写入json文件，ensure_ascii=False中文不转义；indent美化换行
        json.dump(metas, f, ensure_ascii=False, indent=2)

    return index


def load():
    """加载索引（进程内只加载一次）。"""
    # 声明：函数内修改的_index、_metas是模块顶层的全局变量
    global _index, _metas
    if _index is None:
        # 如果索引文件不存在
        if not INDEX_PATH.exists():
            return None
        # 从磁盘读取faiss索引到内存全局变量_index
        _index = faiss.read_index(str(INDEX_PATH))
        with open(META_PATH, "r", encoding="utf-8") as f:
            # 读取json内容，转成python列表，存入全局_metas
            _metas = json.load(f)
    return _index

def get_metas() -> list:
    """获取全部元数据列表，先保证索引已经加载"""
    # 调用load，确保_metas已经加载到内存
    load()
    # 如果_metas是None，返回空列表，防止后续下标访问报错
    return _metas or []

def search(query_vector: np.ndarray, top_k: int = 10)-> list:
    """检索：返回 [{score, meta}, ...]，按相似度从高到低。"""
    index = load()
    # 如果索引为空，直接返回空结果列表
    if index is None:
        return []
    # 把单条查询向量包装成二维数组 [ [向量值] ]，转float32，FAISS要求输入二维
    q = np.asarray([query_vector], dtype="float32")
    scores, idxs = index.search(q, top_k)
    # 定义空列表，存放最终组装好的结果
    out = []
    # scores[0]第一条查询的分数；idxs[0]第一条查询匹配到的下标；zip配对遍历
    for score, i in zip(scores[0], idxs[0]):
        # FAISS找不到足够结果时下标填充-1，遇到-1跳过
        if i == -1:
            continue
        # 把分数转普通python float，通过下标i取出对应的元数据，追加进结果列表
        out.append({"score": float(score), "meta": get_metas()[i]})
    # 返回检索结果
    return out