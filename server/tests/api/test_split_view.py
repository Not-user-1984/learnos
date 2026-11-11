"""B-006: split-view — сегменты видео-таймкодов и get-or-create разговора главы."""

import importlib.util
from pathlib import Path

SKILL_RUN = Path(__file__).resolve().parents[2] / "skills" / "youtube-to-summary" / "run.py"

VTT = """WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:03.000
hello world

00:00:04.000 --> 00:00:06.000
second line

00:00:07.000 --> 00:00:09.000
third one

00:00:10.000 --> 00:00:12.000
fourth line

00:00:13.000 --> 00:00:15.000
fifth line
"""


def _skill():
    spec = importlib.util.spec_from_file_location("yt_run", SKILL_RUN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parse_vtt_segments_monotonic_and_grouped():
    """Сегменты: старт монотонен, группировка по 4 реплики совпадает с текстом."""
    mod = _skill()
    segments = mod._parse_vtt_segments(VTT)
    assert [s["start"] for s in segments] == sorted(s["start"] for s in segments)
    # 5 реплик → 2 сегмента (4 + 1), старт первого — 1 с, второго — 13 с
    assert len(segments) == 2
    assert segments[0]["start"] == 1.0
    assert segments[0]["text"] == "hello world second line third one fourth line"
    assert segments[1]["start"] == 13.0

    # текст тем же группировкам — абзацы совпадают с сегментами
    text = mod._parse_vtt(VTT)
    assert text.split("\n\n") == [s["text"] for s in segments]


def test_ts_to_seconds_formats():
    mod = _skill()
    assert mod._ts_to_seconds("00:01:02.500") == 62.5
    assert mod._ts_to_seconds("01:02.500") == 62.5
    assert mod._ts_to_seconds("00:00:10,000") == 10.0  # srt-запятая
    assert mod._ts_to_seconds("мусор") == 0.0


def test_chapter_conversation_get_or_create(client, container):
    """Разговор главы: повторное открытие возвращает тот же разговор."""
    src = container.library.add_source("book", "Книга split", url=None)
    from app.modules.library.infra.tables import chapters as chapters_table

    with container.uow() as uow:
        uow.session.execute(
            chapters_table.insert().values(
                source_id=src["id"], idx=1, title="Глава 1", path="/tmp/sv.md", tokens_est=100
            )
        )

    first = client.post(f"/api/sources/{src['uid']}/chapters/1/conversation").json()
    second = client.post(f"/api/sources/{src['uid']}/chapters/1/conversation").json()
    assert first["uid"] == second["uid"]
    assert first["context_ref"] == f"{src['uid']}:1"
    assert first["chapter_idx"] == 1

    detail = client.get(f"/api/conversations/{first['uid']}").json()
    assert detail["uid"] == first["uid"]


def test_segments_endpoint_empty_for_old_video(client, container):
    """Старое видео без segments.json — пустой список, без ошибки."""
    src = container.library.add_source("video", "Старое видео", url="https://youtu.be/old")
    with container.uow() as uow:
        from app.modules.library.infra.tables import sources as sources_t

        uow.session.execute(
            sources_t.update().where(sources_t.c.uid == src["uid"]).values(meta_json='{"video_id": "old123"}')
        )
    r = client.get(f"/api/sources/{src['uid']}/segments")
    assert r.status_code == 200
    assert r.json()["segments"] == []
    assert r.json()["video_id"] == "old123"
