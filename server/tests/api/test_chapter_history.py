"""История разговоров по главе: GET /conversations?source=&chapter=."""

from app.llm.providers.fake import FakeTurn


def _seed_chapter_talk(
    client, fake_llm, source_uid: str, chapter: int, title: str, with_messages: bool
) -> str:
    act = client.post("/api/activities", json={"source": source_uid}).json()
    conv = client.post(
        "/api/conversations",
        json={"mode": "quick", "activity": act["uid"], "chapter": chapter, "title": title},
    ).json()
    if with_messages:
        fake_llm.queue(FakeTurn(text="разбор готов"), FakeTurn(text="заголовок"))
        with client.stream(
            "POST", f"/api/conversations/{conv['uid']}/messages", json={"content": "разбери"}
        ) as resp:
            assert resp.status_code == 200
    return conv["uid"]


def test_conversations_filtered_by_source_and_chapter(client, fake_llm):
    src = client.post("/api/sources", json={"kind": "book", "title": "Книга тестов"}).json()
    ch1 = _seed_chapter_talk(client, fake_llm, src["uid"], 1, "Разбор: глава 1", with_messages=True)
    _seed_chapter_talk(client, fake_llm, src["uid"], 2, "Разбор: глава 2", with_messages=False)
    free = client.post("/api/conversations", json={"mode": "free"}).json()

    # глава 1 — только её разговор, с числом сообщений
    only1 = client.get(f"/api/conversations?source={src['uid']}&chapter=1").json()
    assert [c["uid"] for c in only1] == [ch1]
    assert only1[0]["messages_count"] >= 2

    # глава 2 — свой разговор, пустой
    only2 = client.get(f"/api/conversations?source={src['uid']}&chapter=2").json()
    assert len(only2) == 1 and only2[0]["uid"] != ch1
    assert only2[0]["messages_count"] == 0

    # весь источник — оба разговора, свободный не попал
    by_src = client.get(f"/api/conversations?source={src['uid']}").json()
    assert {c["uid"] for c in by_src} == {ch1, only2[0]["uid"]}

    # без фильтра — есть и свободный
    everyone = client.get("/api/conversations").json()
    assert free["uid"] in {c["uid"] for c in everyone}
