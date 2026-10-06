import datetime
import json
import uuid


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:6]}"


def rows_to_dicts(rows) -> list[dict]:
    return [dict(r) for r in rows]


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(value, default):
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default
