from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
from typing import Any, Iterable


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, Path):
        return value.as_posix()
    return value


def dumps_json(value: Any) -> str:
    return json.dumps(to_jsonable(value), indent=2, sort_keys=True)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_json(value) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
    return records


def write_jsonl_records(path: Path, records: Iterable[Any], key_field: str | None = None) -> None:
    existing = read_jsonl(path) if key_field else []
    by_key = {
        str(record[key_field]): record
        for record in existing
    } if key_field else {}

    if key_field:
        for record in records:
            jsonable = to_jsonable(record)
            by_key[str(jsonable[key_field])] = jsonable
        output_records = [by_key[key] for key in sorted(by_key)]
    else:
        output_records = [to_jsonable(record) for record in records]

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in output_records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
