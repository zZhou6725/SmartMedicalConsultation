"""评估管理接口：接口18 触发评估 / 接口19 记录分页 / 接口20 记录详情。

接口18 是同步执行的：一次全量评估（53 条）需要数分钟，
因此额外提供了 limit / useJudge 两个可选参数，便于快速冒烟与 CI 分档调用。
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.eval import runner
from app.store import eval_repo

router = APIRouter(prefix="/api/eval", tags=["评估管理"])


class EvalRunRequest(BaseModel):
    datasetId: str = Field("golden53", description="金标数据集ID")
    limit: int | None = Field(None, description="只跑前 N 条（附加参数，便于快速验证）")
    useJudge: bool = Field(True, description="是否启用 LLM 裁判（附加参数）")


@router.post("/run")
def run_eval(req: EvalRunRequest | None = None):
    """接口18：触发一次自动化评估，返回通过率、综合得分与逐条明细。"""
    req = req or EvalRunRequest()
    try:
        s = runner.run_eval(req.datasetId, req.limit, req.useJudge)
    except Exception as e:
        return {"code": 0, "msg": f"评估失败：{e}", "data": None}

    return {
        "code": 1,
        "msg": "success",
        "data": {
            # —— 接口文档定义的字段
            "taskId": s["taskId"],
            "total": s["total"],
            "passCount": s["passCount"],
            "failCount": s["failCount"],
            "passRate": s["passRate"],
            "score": s["score"],
            "items": [{"question": x["question"], "pass": x["pass"], "score": x["score"]}
                      for x in s["items"]],
            # —— 附加字段（超集）：分层指标与门禁结论，供 CI 与前端使用
            "metrics": s["metrics"],
            "gate": s["gate"],
            "reportPath": s["reportPath"],
        },
    }


@router.get("/records")
def list_eval_records(page: int = 1, pageSize: int = 10, passStatus: int | None = None):
    """接口19：评估记录分页查询（对应 MySQL eval_record 表）。"""
    try:
        total, rows = eval_repo.list_records(page, pageSize, passStatus)
    except Exception as e:
        return {"code": 0, "msg": f"查询评估记录失败：{e}", "data": None}
    return {"code": 1, "msg": "success", "data": {"total": total, "rows": rows}}


@router.get("/records/{record_id}")
def get_eval_record(record_id: int):
    """接口20：评估记录详情。"""
    try:
        row = eval_repo.get_record(record_id)
    except Exception as e:
        return {"code": 0, "msg": f"查询评估记录失败：{e}", "data": None}
    if row is None:
        return {"code": 0, "msg": "记录不存在", "data": None}
    return {"code": 1, "msg": "success", "data": row}
