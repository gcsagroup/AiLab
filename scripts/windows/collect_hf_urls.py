"""Collect version-pinned Hugging Face model URLs from the official Hub API. Python 3.10+."""
import argparse
import concurrent.futures
from contextlib import closing
import gzip
from http.client import IncompleteRead
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen

HUB = "https://huggingface.co"
TASKS = ("text-generation", "text2text-generation")
WEIGHT = re.compile(r"\.(safetensors|gguf|bin|pt|pth|onnx|h5|msgpack|ckpt|tflite|npz|ggml|mlmodel|onnx_data)$", re.I)
ROOT = Path(__file__).resolve().parents[2]


def page(url):
    parsed = urlsplit(url)
    if parsed.netloc != "huggingface.co" or parsed.scheme != "https" or parsed.path != "/api/models":
        raise ValueError("Unexpected Hub pagination URL")
    for attempt in range(8):
        try:
            request = Request(url, headers={"Accept-Encoding": "gzip", "User-Agent": "AiLab-Catalog/1"})
            with urlopen(request, timeout=95) as response:
                data = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                link = re.search(r'<([^>]+)>;\s*rel="next"', response.headers.get("Link", ""))
                return json.loads(data), urljoin(HUB, link[1]) if link else ""
        except (OSError, URLError, EOFError, IncompleteRead, json.JSONDecodeError) as error:
            if isinstance(error, HTTPError) and error.code < 500 and error.code != 429:
                raise
            if attempt == 7:
                raise
            delay = error.headers.get("Retry-After", "") if isinstance(error, HTTPError) else ""
            time.sleep(int(delay) if delay.isdigit() else min(60, 2 ** attempt))


def record(model, query):
    repo = model["id"]
    revision = model.get("sha")
    if not revision or not re.fullmatch("[a-f0-9]{40,64}", revision):
        raise ValueError(f"Missing revision for {repo}")
    source = f"{HUB}/{quote(repo, safe='/')}"
    files = [f["rfilename"] for f in model.get("siblings", []) if WEIGHT.search(f["rfilename"])]
    item = {"repo": repo, "publisher": repo.partition("/")[0], "task": model.get("pipeline_tag") or (query if query in TASKS else None), "revision": revision,
            "licenses": [tag[8:] for tag in model.get("tags", []) if tag.startswith("license:")],
            "gated": model.get("gated", False), "source_url": source,
            "files_url": f"{source}/tree/{revision}",
            "weight_urls": [f"{source}/resolve/{revision}/{quote(name, safe='/')}" for name in files]}
    if query not in TASKS:
        item["other_file_urls"] = [f"{source}/resolve/{revision}/{quote(f['rfilename'], safe='/')}"
                                   for f in model.get("siblings", []) if not WEIGHT.search(f["rfilename"])]
    return item


def database(cache, task):
    name = "tag-text2text-generation" if task == "text2text-generation" else task.replace(":", "-")
    return cache / f"{name}.sqlite"


def scan(task, cache):
    db = sqlite3.connect(database(cache, task))
    db.execute("CREATE TABLE IF NOT EXISTS cursor(url TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS models(repo TEXT PRIMARY KEY, row BLOB)")
    state = db.execute("SELECT url FROM cursor").fetchone()
    params = {"full": "true", "limit": 1000, "sort": "createdAt", "direction": 1}
    if task != "all-public":
        params["pipeline_tag" if task == "text-generation" else "filter"] = task
    url = state[0] if state else HUB + "/api/models?" + urlencode(params)
    pages = 0
    while url:
        models, following = page(url)
        if following == url:
            raise ValueError("Repeated Hub cursor")
        with db:
            for model in models:
                if model.get("private"):
                    continue
                item = record(model, task)
                row = json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode()
                db.execute("INSERT OR REPLACE INTO models VALUES (?,?)", (item["repo"], gzip.compress(row, compresslevel=1, mtime=0)))
            db.execute("DELETE FROM cursor")
            db.execute("INSERT INTO cursor VALUES (?)", (following,))
        url = following
        pages += 1
        if pages == 1 or pages % 25 == 0 or not url:
            print(task, db.execute("SELECT count(*) FROM models").fetchone()[0], "repositories", flush=True)
    db.close()


# Exact Hub tag spellings. Inclusion reports the repository declaration only.
LICENSE_TAGS = """apache-2.0 mit bsd-3-clause bsd-2-clause bsd-3-clause-clear bsd afl-3.0 gpl-3.0 agpl-3.0
artistic-2.0 unlicense bsl-1.0 gpl-2.0 lgpl-3.0 mpl-2.0 osl-3.0 ecl-2.0 ms-pl epl-2.0 eupl-1.2 eupl-1.1
lppl-1.3c zlib isc epl-1.0 lgpl-2.1 ncsa postgresql ofl-1.1 cc-by-4.0 cc-by-3.0 cc-by-2.5 cc-by-2.0
cc-by-sa-4.0 cc-by-sa-3.0 cc0-1.0 openmdw-1.1 openmdw-1.0 cdla-permissive-2.0 cdla-permissive-1.0
cdla-sharing-1.0 odc-by odbl pddl etalab-2.0 gpl lgpl wtfpl""".split()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / ".artifacts/hf-url-index")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--all-public", action="store_true", help="Collect every listed public repository and every file, including custom or missing licenses")
    scope.add_argument("--declared-licenses", action="store_true", help="Collect across all tasks for the listed Hub license tags")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    tasks = tuple("license:" + tag for tag in LICENSE_TAGS) if args.declared_licenses else TASKS
    prefix = "hf-declared-license" if args.declared_licenses else "hf-language"
    if args.all_public:
        tasks = ("all-public",)
        prefix = "hf-public"
    args.output = args.output or ROOT / "downloads" / f"{prefix}-model-urls.jsonl.gz"
    args.cache.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(5, len(tasks))) as executor:
        list(executor.map(lambda task: scan(task, args.cache), tasks))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".partial")
    counts = {}
    weight_count = 0
    other_count = 0
    seen = set()
    names_file = args.output.with_name(f"{prefix}-repos.txt.gz")
    names_tmp = names_file.with_suffix(".partial")
    with gzip.open(temporary, "wb", compresslevel=5) as out, gzip.open(names_tmp, "wt", encoding="utf8") as names:
        for task in tasks:
            count = 0
            with closing(sqlite3.connect(database(args.cache, task))) as db:
                query = "SELECT row FROM models"
                for (row,) in db.execute(query + " ORDER BY repo"):
                    item = json.loads(gzip.decompress(row))
                    if item["repo"] in seen:
                        continue
                    seen.add(item["repo"])
                    other_count += len(item.get("other_file_urls", []))
                    item["manifest_url"] = f"{HUB}/api/models/{quote(item['repo'], safe='/')}/revision/{item['revision']}?blobs=true"
                    weight_count += len(item["weight_urls"])
                    names.write(item["repo"] + "\n")
                    out.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode() + b"\n")
                    count += 1
            counts[task] = count
    os.replace(temporary, args.output)
    os.replace(names_tmp, names_file)
    summary = {"completed_at": datetime.now(timezone.utc).isoformat(), "source": f"{HUB}/api/models",
               "scope": "Public text-generation pipeline or text2text-generation tag. Overlapping repositories counted once. Licenses as declared by publisher.",
               "repositories": sum(counts.values()), "unique_by_query": counts, "weight_urls": weight_count,
               "file_url_scope": "Common weight extensions; manifest_url returns the complete pinned file list for other formats."}
    if args.declared_licenses or args.all_public:
        summary.update(other_file_urls=other_count,
                       file_url_scope="All files from the pinned Hub sibling list, grouped by common weight extensions and other files.")
    if args.declared_licenses:
        summary.update(scope="Public repositories across all tasks matching the listed publisher-declared Hub license tags. Overlapping repositories counted once.", license_tags=LICENSE_TAGS)
    if args.all_public:
        summary.update(scope="All public repositories listed by the Hub. Publisher-declared license tags are recorded when available.")
    args.output.with_name(f"{prefix}-urls-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf8")
    print("Complete:", counts, args.output, flush=True)


if __name__ == "__main__":
    main()
