"""저장소 추상화: Firestore(FIREBASE_SERVICE_ACCOUNT_JSON 설정 시) 또는 인메모리(개발용)."""
import itertools
import json
from typing import Optional

from config import FIREBASE_SERVICE_ACCOUNT_JSON

_db = None
_mem: dict = {"data": {}, "conversations": {}, "profile": {}}
_ids = itertools.count(1)


def _new_id() -> str:
    return f"m{next(_ids)}"


def _fs():
    """Firestore 클라이언트 (lazy 초기화)."""
    global _db
    if _db is None:
        import firebase_admin
        from firebase_admin import credentials, firestore

        cred = credentials.Certificate(json.loads(FIREBASE_SERVICE_ACCOUNT_JSON))
        try:
            firebase_admin.get_app()
        except firebase_admin.exceptions.FirebaseError:
            firebase_admin.initialize_app(cred)
        _db = firestore.client()
    return _db


def firebase_enabled() -> bool:
    return bool(FIREBASE_SERVICE_ACCOUNT_JSON)


# ── 학습 기록 (data) ────────────────────────────────────────────

def add_record(data: dict) -> str:
    if firebase_enabled():
        doc = _fs().collection("data").document()
        doc.set(data)
        return doc.id
    rid = _new_id()
    _mem["data"][rid] = dict(data)
    return rid


def list_records() -> list[dict]:
    if firebase_enabled():
        rows = [dict(r.to_dict(), id=r.id) for r in _fs().collection("data").stream()]
    else:
        rows = [dict(v, id=k) for k, v in _mem["data"].items()]
    rows.sort(key=lambda r: r.get("date", ""), reverse=True)
    return rows


def update_record(rid: str, data: dict) -> bool:
    if firebase_enabled():
        doc = _fs().collection("data").document(rid)
        if not doc.exists():
            return False
        doc.set(data, merge=True)
        return True
    if rid not in _mem["data"]:
        return False
    _mem["data"][rid] = dict(data)
    return True


def delete_record(rid: str) -> bool:
    if firebase_enabled():
        doc = _fs().collection("data").document(rid)
        if not doc.exists():
            return False
        doc.delete()
        return True
    return _mem["data"].pop(rid, None) is not None


# ── 대화 (conversations) ────────────────────────────────────────

def save_conversation(conv: dict, conv_id: Optional[str] = None) -> str:
    if firebase_enabled():
        col = _fs().collection("conversations")
        cid = conv_id or col.document().id
        col.document(cid).set(conv)
        return cid
    cid = conv_id or _new_id()
    _mem["conversations"][cid] = dict(conv)
    return cid


def list_conversations() -> list[dict]:
    if firebase_enabled():
        rows = [
            {"id": c.id, "title": c.get("title", ""), "created_at": c.get("created_at", "")}
            for c in _fs().collection("conversations").stream()
        ]
    else:
        rows = [
            {"id": k, "title": v.get("title", ""), "created_at": v.get("created_at", "")}
            for k, v in _mem["conversations"].items()
        ]
    rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return rows


def get_conversation(cid: str) -> Optional[dict]:
    if firebase_enabled():
        doc = _fs().collection("conversations").document(cid)
        if not doc.exists():
            return None
        return dict(doc.to_dict(), id=cid)
    v = _mem["conversations"].get(cid)
    return dict(v, id=cid) if v else None


def delete_conversation(cid: str) -> bool:
    if firebase_enabled():
        doc = _fs().collection("conversations").document(cid)
        if not doc.exists():
            return False
        doc.delete()
        return True
    return _mem["conversations"].pop(cid, None) is not None


# ── 프로필 (profile) ────────────────────────────────────────────

def get_profile() -> dict:
    if firebase_enabled():
        doc = _fs().collection("profile").document("main")
        return doc.to_dict() or {} if doc.exists() else {}
    return dict(_mem["profile"])


def set_profile(fields: dict) -> dict:
    if firebase_enabled():
        _fs().collection("profile").document("main").set(fields, merge=True)
        return get_profile()
    _mem["profile"].update(fields)
    return dict(_mem["profile"])
