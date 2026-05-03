import os
import time

from app import app


def main() -> None:
    client = app.test_client()
    ts = int(time.time())
    client_id = f"smoke-{ts}"
    senior_key = os.getenv("FEATURE3_SENIOR_KEY", "dev-senior-key")

    print("[1/6] create question")
    create_resp = client.post(
        "/api/questions",
        json={
            "client_id": client_id,
            "title": "smoke-title",
            "content": f"smoke-content-{ts}",
        },
        headers={"X-Client-Id": client_id},
    )
    assert create_resp.status_code == 201, create_resp.get_data(as_text=True)
    create_data = create_resp.get_json()
    qid = int(create_data["id"])
    code = str(create_data["view_code"])
    print(f"created qid={qid}, code={code}")

    print("[2/6] list my questions")
    mine_resp = client.get(f"/api/questions/mine?client_id={client_id}")
    assert mine_resp.status_code == 200, mine_resp.get_data(as_text=True)
    mine_data = mine_resp.get_json()
    assert mine_data["items"], "my questions should not be empty"

    print("[3/6] submit senior answer")
    answer_resp = client.post(
        "/api/answers",
        json={"question_id": qid, "content": "这是 smoke 人工回复"},
        headers={"X-Senior-Key": senior_key, "X-Senior-Name": "smoke_senior"},
    )
    assert answer_resp.status_code == 200, answer_resp.get_data(as_text=True)

    print("[4/6] track question with id+code")
    track_resp = client.get(f"/api/questions/track?qid={qid}&code={code}")
    assert track_resp.status_code == 200, track_resp.get_data(as_text=True)
    track_data = track_resp.get_json()
    assert track_data.get("status") == "answered", "question should be answered"
    assert track_data.get("answer"), "answer should not be empty"

    print("[5/6] query answered list with search")
    answered_resp = client.get(
        f"/api/tasks/answered?q={ts}",
        headers={"X-Senior-Key": senior_key},
    )
    assert answered_resp.status_code == 200, answered_resp.get_data(as_text=True)
    answered_items = (answered_resp.get_json() or {}).get("items") or []
    assert any(int(item.get("id") or 0) == qid for item in answered_items), "answered search should include current question"

    print("[6/6] close question")
    close_resp = client.put(f"/api/questions/{qid}/close", json={"client_id": client_id, "view_code": code})
    assert close_resp.status_code == 200, close_resp.get_data(as_text=True)
    close_data = close_resp.get_json()
    assert close_data.get("status") == "closed"

    print("feature3 smoke test passed")


if __name__ == "__main__":
    main()
