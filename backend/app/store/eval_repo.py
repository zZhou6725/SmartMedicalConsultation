"""eval_record 表读写（接口 19 / 20 的数据来源）。"""
from sqlalchemy import func, select

from app.store.db import SessionLocal
from app.store.models import EvalRecord


def _to_row(m: EvalRecord) -> dict:
    return {
        "id": m.id,
        "question": m.question,
        "answer": m.answer,
        "passStatus": int(m.pass_status or 0),
        "evalScore": float(m.eval_score or 0),
        "createTime": m.create_time.isoformat() if m.create_time else "",
    }


def insert_records(summary: dict) -> int:
    """一次评估的每条用例落一行 eval_record。"""
    items = summary.get("items") or []
    with SessionLocal() as db:
        for x in items:
            db.add(EvalRecord(
                question=x["question"],
                answer=x["answer"],
                pass_status=1 if x["pass"] else 0,
                eval_score=float(x["score"]),
            ))
        db.commit()
    return len(items)


def list_records(page: int = 1, page_size: int = 10, pass_status: int | None = None):
    """分页查评估记录，可按通过状态过滤。返回 (total, rows)。"""
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 10), 100))

    with SessionLocal() as db:
        stmt = select(EvalRecord)
        cnt = select(func.count()).select_from(EvalRecord)
        if pass_status is not None:
            stmt = stmt.where(EvalRecord.pass_status == pass_status)
            cnt = cnt.where(EvalRecord.pass_status == pass_status)

        total = db.execute(cnt).scalar() or 0
        rows = db.execute(
            stmt.order_by(EvalRecord.id.desc())
            .offset((page - 1) * page_size).limit(page_size)
        ).scalars().all()

    return total, [_to_row(r) for r in rows]


def get_record(record_id: int) -> dict | None:
    """按主键取单条评估记录。"""
    with SessionLocal() as db:
        m = db.get(EvalRecord, record_id)
        return _to_row(m) if m else None
