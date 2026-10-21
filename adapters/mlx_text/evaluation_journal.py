"""逐题落盘与恢复校验；只恢复控制层已经确认的完整记录。"""

import json
import os
from pathlib import Path

from .benchmark import identity


def read_prefix(path, count, head, rows, variant, recipe_digest):
    if type(count) is not int or not 0 <= count <= len(rows):
        raise ValueError("评测恢复题数无效")
    records, previous = [], None
    if count == 0:
        if head is not None:
            raise ValueError("空评测进度不能含记录摘要")
        return records
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError("逐题记录缺失或超过读取预算")
    with path.open() as stream:
        for index in range(count):
            raw = stream.readline(256 * 1024)
            if not raw.endswith("\n"):
                raise ValueError("逐题记录不完整")
            record = json.loads(raw)
            value = {k: v for k, v in record.items() if k != "digest"}
            if (record.get("digest") != identity(value) or record.get("previous") != previous
                    or record.get("sample_id") != rows[index]["id"] or record.get("variant") != variant
                    or record.get("recipe_digest") != recipe_digest or record.get("row_digest") != identity(rows[index])
                    or not isinstance(record.get("output"), str) or not isinstance(record.get("observation"), dict)):
                raise ValueError("逐题记录摘要、顺序或评测身份已变化")
            records.append(record)
            previous = record["digest"]
    if previous != head:
        raise ValueError("逐题记录与控制层保存的进度不一致")
    return records


def append(path, row, variant, recipe_digest, output, observation, previous):
    value = {"sample_id": row["id"], "row_digest": identity(row), "variant": variant,
             "recipe_digest": recipe_digest, "output": output, "observation": observation, "previous": previous}
    value["digest"] = identity(value)
    with Path(path).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return value
