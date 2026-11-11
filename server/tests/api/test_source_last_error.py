"""B-001: last_error у источника — ошибка последней обработки, видна только у failed."""

NOW = "2026-01-01T00:00:00"


def _fail_last_process_job(container, uid: str, error: str) -> None:
    """process_source job сразу в failed (enqueue+update в одной транзакции:
    воркер не видит его в queued)."""
    lib = container.library
    with lib._uow() as uow:  # noqa: SLF001
        job_id = lib._jobs.enqueue(uow.session, kind="process_source", target=uid, total=1, now=NOW)
        lib._jobs.update(uow.session, job_id, status="failed", error=error)


def test_last_error_shown_for_failed_source(client, container):
    lib = container.library
    src = lib.add_source("video", "https://youtu.be/err98765432", url="https://youtu.be/err98765432")
    _fail_last_process_job(
        container, src["uid"], "субтитры не найдены (ru-orig,en-orig,ru,en) | HTTP Error 429"
    )
    with lib._uow() as uow:  # noqa: SLF001
        lib._sources.update(uow.session, src["id"], status="failed", updated_at=NOW)

    detail = client.get(f"/api/sources/{src['uid']}").json()
    assert detail["status"] == "failed"
    assert "субтитры не найдены" in detail["last_error"]

    listing = client.get("/api/sources").json()
    row = next(s for s in listing if s["uid"] == src["uid"])
    assert "субтитры не найдены" in row["last_error"]
    others = [s for s in listing if s["uid"] != src["uid"]]
    assert all(s.get("last_error") is None for s in others)


def test_last_error_none_when_source_not_failed(client, container):
    """Источник не в failed — старая ошибка job не показывается (статус важнее истории)."""
    lib = container.library
    src = lib.add_source("video", "https://youtu.be/ok987654321", url="https://youtu.be/ok987654321")
    _fail_last_process_job(container, src["uid"], "старая ошибка")

    detail = client.get(f"/api/sources/{src['uid']}").json()
    assert detail["status"] == "chosen"
    assert detail["last_error"] is None
