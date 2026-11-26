"""저장소 추상화 — file(로컬 기본) · memory · firestore.

STORE_BACKEND=auto 일 때:
  FIREBASE_SERVICE_ACCOUNT_JSON 있음 → firestore
  Vercel(읽기 전용 파일시스템)      → memory
  그 외(로컬 실행)                  → file  (DATA_FILE, 기본 .data/compass.json — 재시작해도 유지)
"""
import copy
import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

import config

COLLECTIONS = ("data", "conversations", "profile")
_lock = threading.RLock()
_mem: dict = {c: {} for c in COLLECTIONS}
_loaded = False
_db = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def backend() -> str:
    choice = config.STORE_BACKEND
    if choice in ("memory", "file", "firestore"):
        return choice
    if config.FIREBASE_SERVICE_ACCOUNT_JSON:
        return "firestore"
    return "memory" if config.IS_VERCEL else "file"


def firebase_enabled() -> bool:
    return backend() == "firestore"


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


# ── file / memory ───────────────────────────────────────────────

def _load() -> None:
    global _loaded, _mem
    if _loaded:
        return
    _loaded = True
    if backend() != "file" or not os.path.isfile(config.DATA_FILE):
        return
    try:
        with open(config.DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _mem = {c: dict(data.get(c) or {}) for c in COLLECTIONS}
    except (OSError, ValueError) as exc:
        # 깨진 파일 때문에 서버가 뜨지 않는 일은 막고, 원본은 보존한다
        print(f"[compass] 데이터 파일을 읽지 못해 빈 상태로 시작합니다: {exc}")
        try:
            os.replace(config.DATA_FILE, config.DATA_FILE + ".broken")
        except OSError:
            pass


def _save() -> None:
    if backend() != "file":
        return
    folder = os.path.dirname(config.DATA_FILE) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".compass-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(_mem, f, ensure_ascii=False, indent=1)
        os.replace(tmp, config.DATA_FILE)  # 원자적 교체 — 쓰다가 죽어도 파일이 깨지지 않음
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _local(collection: str) -> dict:
    _load()
    return _mem[collection]


# ── firestore ───────────────────────────────────────────────────

def _fs():
    """Firestore 클라이언트 (lazy 초기화)."""
    global _db
    if _db is None:
        import firebase_admin
        from firebase_admin import credentials, firestore

        try:
            firebase_admin.get_app()
        except ValueError:  # 기본 앱이 아직 없음
            cred = credentials.Certificate(json.loads(config.FIREBASE_SERVICE_ACCOUNT_JSON))
            firebase_admin.initialize_app(cred)
        _db = firestore.client()
    return _db


def _fs_exists(collection: str, doc_id: str) -> bool:
    return _fs().collection(collection).document(doc_id).get().exists


# ── 공통 CRUD ───────────────────────────────────────────────────

def _add(collection: str, data: dict) -> str:
    if firebase_enabled():
        doc = _fs().collection(collection).document()
        doc.set(data)
        return doc.id
    with _lock:
        rid = _new_id()
        _local(collection)[rid] = copy.deepcopy(data)
        _save()
        return rid


def _get(collection: str, doc_id: str) -> Optional[dict]:
    if firebase_enabled():
        snap = _fs().collection(collection).document(doc_id).get()
        return dict(snap.to_dict() or {}, id=doc_id) if snap.exists else None
    with _lock:
        v = _local(collection).get(doc_id)
        return dict(copy.deepcopy(v), id=doc_id) if v is not None else None


def _list(collection: str) -> list[dict]:
    if firebase_enabled():
        return [dict(s.to_dict() or {}, id=s.id) for s in _fs().collection(collection).stream()]
    with _lock:
        return [dict(copy.deepcopy(v), id=k) for k, v in _local(collection).items()]


def _put(collection: str, doc_id: str, data: dict, *, must_exist: bool) -> bool:
    if firebase_enabled():
        if must_exist and not _fs_exists(collection, doc_id):
            return False
        _fs().collection(collection).document(doc_id).set(data)
        return True
    with _lock:
        col = _local(collection)
        if must_exist and doc_id not in col:
            return False
        col[doc_id] = copy.deepcopy(data)
        _save()
        return True


def _delete(collection: str, doc_id: str) -> bool:
    if firebase_enabled():
        if not _fs_exists(collection, doc_id):
            return False
        _fs().collection(collection).document(doc_id).delete()
        return True
    with _lock:
        removed = _local(collection).pop(doc_id, None) is not None
        if removed:
            _save()
        return removed


# ── 학습 기록 (data) ────────────────────────────────────────────

def add_record(data: dict) -> str:
    return _add("data", {**data, "created_at": now_iso()})


def get_record(rid: str) -> Optional[dict]:
    return _get("data", rid)


def list_records() -> list[dict]:
    rows = _list("data")
    rows.sort(key=lambda r: (r.get("date", ""), r.get("created_at", "")), reverse=True)
    return rows


def update_record(rid: str, data: dict) -> bool:
    old = _get("data", rid)
    if old is None:
        return False
    body = {**data, "created_at": old.get("created_at") or now_iso(), "updated_at": now_iso()}
    return _put("data", rid, body, must_exist=True)


def delete_record(rid: str) -> bool:
    return _delete("data", rid)


# ── 대화 (conversations) ────────────────────────────────────────

def save_conversation(conv: dict, conv_id: Optional[str] = None) -> str:
    stamp = now_iso()
    if conv_id:
        old = _get("conversations", conv_id)
        body = {**conv, "created_at": (old or {}).get("created_at") or stamp, "updated_at": stamp}
        _put("conversations", conv_id, body, must_exist=False)
        return conv_id
    return _add("conversations", {**conv, "created_at": stamp, "updated_at": stamp})


def list_conversations() -> list[dict]:
    rows = [
        {
            "id": c["id"],
            "title": c.get("title", ""),
            "created_at": c.get("created_at", ""),
            "updated_at": c.get("updated_at") or c.get("created_at", ""),
            "message_count": len(c.get("messages") or []),
        }
        for c in _list("conversations")
    ]
    rows.sort(key=lambda r: r["updated_at"], reverse=True)
    return rows


def get_conversation(cid: str) -> Optional[dict]:
    return _get("conversations", cid)


def delete_conversation(cid: str) -> bool:
    return _delete("conversations", cid)


# ── 프로필 (profile, 단일 문서 main) ─────────────────────────────

def get_profile() -> dict:
    p = _get("profile", "main") or {}
    p.pop("id", None)
    return p


def set_profile(fields: dict) -> dict:
    merged = {**get_profile(), **fields, "updated_at": now_iso()}
    _put("profile", "main", merged, must_exist=False)
    return get_profile()


def reset_all() -> None:
    """테스트·시드용: 현재 백엔드의 로컬 데이터를 비운다 (Firestore는 건드리지 않음)."""
    if firebase_enabled():
        raise RuntimeError("Firestore 데이터는 reset_all로 지우지 않습니다")
    with _lock:
        global _mem, _loaded
        _mem = {c: {} for c in COLLECTIONS}
        _loaded = True
        _save()
