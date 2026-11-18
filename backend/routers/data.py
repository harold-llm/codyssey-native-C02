"""학습 기록 CRUD + 요약 (시계열 데이터)."""
from fastapi import APIRouter, HTTPException

from models.schemas import RecordIn
from services import store
from services.analysis import build_summary

router = APIRouter(prefix="/api/data", tags=["data"])


@router.post("", status_code=201)
def create_record(rec: RecordIn):
    body = rec.model_dump(exclude_none=True)
    rid = store.add_record(body)
    return {"id": rid, **body}


@router.get("")
def list_records():
    return store.list_records()


@router.get("/summary")
def summary():
    """데이터 요약 — 프롬프트 주입용 + UI 요약 화면용."""
    return build_summary(store.list_records(), store.get_profile())


@router.put("/{rid}")
def update_record(rid: str, rec: RecordIn):
    if not store.update_record(rid, rec.model_dump(exclude_none=True)):
        raise HTTPException(404, "존재하지 않는 기록입니다")
    return {"id": rid, **rec.model_dump(exclude_none=True)}


@router.delete("/{rid}")
def delete_record(rid: str):
    if not store.delete_record(rid):
        raise HTTPException(404, "존재하지 않는 기록입니다")
    return {"ok": True}
