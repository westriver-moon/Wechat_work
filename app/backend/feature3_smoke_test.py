import os
import time

from app import app
from auth import PERM_ANSWER, build_owner_identity


def set_session_user(client, student_code: str, name: str, permissions: int) -> None:
    with client.session_transaction() as sess:
        sess["auth_user"] = {
            "student_code": student_code,
            "name": name,
            "permissions": permissions,
            "permission_labels": [],
            "owner_identity": build_owner_identity(student_code),
            "is_privileged": bool(permissions & PERM_ANSWER),
        }


def main() -> None:
    client = app.test_client()
    ts = int(time.time())
    asker_student_code = f"smoke-user-{ts}"
    senior_student_code = f"smoke-senior-{ts}"

    set_session_user(client, asker_student_code, "Smoke User", permissions=1)

    print("[1/8] create question")
    create_resp = client.post(
        "/api/questions",
        json={
            "title": "smoke-title",
            "content": f"smoke-content-{ts}",
        },
    )
    assert create_resp.status_code == 201, create_resp.get_data(as_text=True)
    create_data = create_resp.get_json()
    qid = int(create_data["id"])
    code = str(create_data["view_code"])
    print(f"created qid={qid}, code={code}")

    print("[2/8] list my questions")
    mine_resp = client.get("/api/questions/mine")
    assert mine_resp.status_code == 200, mine_resp.get_data(as_text=True)
    mine_data = mine_resp.get_json()
    assert mine_data["items"], "my questions should not be empty"

    print("[3/8] submit senior answer")
    set_session_user(client, senior_student_code, "Smoke Senior", permissions=PERM_ANSWER | 1)
    answer_resp = client.post(
        "/api/answers",
        json={"question_id": qid, "content": "这是 smoke 人工回复"},
    )
    assert answer_resp.status_code == 200, answer_resp.get_data(as_text=True)

    print("[4/8] track question with id+code")
    set_session_user(client, asker_student_code, "Smoke User", permissions=1)
    track_resp = client.get(f"/api/questions/track?qid={qid}&code={code}")
    assert track_resp.status_code == 200, track_resp.get_data(as_text=True)
    track_data = track_resp.get_json()
    assert track_data.get("status") == "answered", "question should be answered"
    assert track_data.get("answer"), "answer should not be empty"

    print("[5/8] query answered list with search")
    set_session_user(client, senior_student_code, "Smoke Senior", permissions=PERM_ANSWER | 1)
    answered_resp = client.get(
        f"/api/tasks/answered?q={ts}",
    )
    assert answered_resp.status_code == 200, answered_resp.get_data(as_text=True)
    answered_items = (answered_resp.get_json() or {}).get("items") or []
    assert any(int(item.get("id") or 0) == qid for item in answered_items), "answered search should include current question"

    print("[6/8] close question")
    set_session_user(client, asker_student_code, "Smoke User", permissions=1)
    close_resp = client.put(f"/api/questions/{qid}/close", json={"view_code": code})
    assert close_resp.status_code == 200, close_resp.get_data(as_text=True)
    close_data = close_resp.get_json()
    assert close_data.get("status") == "closed"

    print("[7/8] closed question should still appear in resolved list")
    set_session_user(client, senior_student_code, "Smoke Senior", permissions=PERM_ANSWER | 1)
    answered_after_close = client.get(
        f"/api/tasks/answered?q={ts}",
    )
    assert answered_after_close.status_code == 200, answered_after_close.get_data(as_text=True)
    answered_after_close_items = (answered_after_close.get_json() or {}).get("items") or []
    assert any(int(item.get("id") or 0) == qid for item in answered_after_close_items), "closed answered question should remain visible"

    print("[8/8] closed question should reject new answers")
    retry_answer_resp = client.post(
        "/api/answers",
        json={"question_id": qid, "content": "关闭后不应再回复"},
    )
    assert retry_answer_resp.status_code == 409, retry_answer_resp.get_data(as_text=True)

    print("feature3 smoke test passed")


if __name__ == "__main__":
    main()
