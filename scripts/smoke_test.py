"""인프로세스 스모크 테스트 — 서버 기동 없이 API를 검증한다.

실행: python scripts/smoke_test.py
(Firebase 미설정 상태의 인메모리 스토어 모드에서 동작한다)
"""

import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402

client = TestClient(app)


def check(name: str, condition: bool, extra: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {extra}" if extra else ""))
    if not condition:
        sys.exit(1)


def main() -> None:
    r = client.get("/api/health")
    check("GET /api/health", r.status_code == 200, str(r.json()))

    r = client.get("/api/data/summary")
    check("GET /api/data/summary (empty)", r.status_code == 200, str(r.json())[:120])

    r = client.post(
        "/api/data",
        json={
            "date": "2026-07-08",
            "value": 20,
            "memo": "유튜브 동요 2곡",
            "skill": "listening",
            "reaction": "just_right",
        },
    )
    check("POST /api/data", r.status_code in (200, 201), str(r.json())[:120])
    rid = r.json().get("id")

    r = client.get("/api/data")
    check("GET /api/data", r.status_code == 200 and len(r.json()) == 1)

    r = client.put(
        f"/api/data/{rid}",
        json={"date": "2026-07-08", "value": 25, "memo": "시간 수정"},
    )
    check("PUT /api/data/{id}", r.status_code == 200)

    r = client.get("/api/data")
    check("record updated", r.json()[0].get("value") == 25)

    r = client.get("/api/data/summary")
    body = r.json()
    check(
        "summary counts record",
        r.status_code == 200 and body.get("count") == 1,
        str(body)[:120],
    )

    r = client.put(
        "/api/profile",
        json={"age_band": "18+", "level": "L2", "goals": "리딩을 잘하고 싶다"},
    )
    check("PUT /api/profile", r.status_code == 200, str(r.json())[:120])

    r = client.get("/api/profile")
    check("GET /api/profile", r.status_code == 200 and r.json().get("level") == "L2")

    r = client.post(
        "/api/conversations",
        json={"title": "레벨 확인 대화", "messages": [{"role": "user", "content": "레벨 알려줘"}]},
    )
    check("POST /api/conversations", r.status_code in (200, 201), str(r.json())[:120])
    cid = r.json().get("id")

    r = client.get("/api/conversations")
    check("GET /api/conversations", r.status_code == 200 and len(r.json()) == 1)

    r = client.get(f"/api/conversations/{cid}")
    check("GET /api/conversations/{id}", r.status_code == 200 and "messages" in r.json())

    r = client.delete(f"/api/data/{rid}")
    check("DELETE /api/data/{id}", r.status_code in (200, 204))

    r = client.delete(f"/api/conversations/{cid}")
    check("DELETE /api/conversations/{id}", r.status_code in (200, 204))

    r = client.get("/")
    check("GET / (frontend)", r.status_code == 200 and "Compass" in r.text)

    print("\nAll smoke tests passed.")


if __name__ == "__main__":
    main()
