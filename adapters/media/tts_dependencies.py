"""为固定 TTS 环境准备官方发行包；用 PyPI JSON 绕开不稳定的 simple 索引。"""

from concurrent.futures import ThreadPoolExecutor
import importlib.metadata as metadata
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import InvalidVersion, Version

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from download_parts import download_parts

ROOTS = ["kokoro==0.9.4", "misaki[en,zh]==0.9.4", "torch==2.14.0", "transformers==4.57.6", "soundfile==0.13.1", "spacy==3.8.16", "pydantic==2.11.7", "wheel==0.45.1", "spacy-curated-transformers==0.3.1"]
TAGS = set(sys_tags())
ENVIRONMENT = default_environment()


def requirements():
    constraints, extras, visited = {}, {}, set()
    queue = [Requirement(value) for value in ROOTS]
    for requirement in queue:
        constraints.setdefault(canonicalize_name(requirement.name), set()).add(str(requirement.specifier))
    while queue:
        requirement = queue.pop()
        name = canonicalize_name(requirement.name)
        constraints.setdefault(name, set()).add(str(requirement.specifier))
        extras.setdefault(name, set()).update(requirement.extras)
        key = name, tuple(sorted(extras[name]))
        if key in visited:
            continue
        visited.add(key)
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        if distribution.version not in SpecifierSet(",".join(value for value in constraints[name] if value)):
            continue
        for raw in distribution.requires or []:
            dependency = Requirement(raw)
            if dependency.marker is None or any(dependency.marker.evaluate({**ENVIRONMENT, "extra": extra}) for extra in {"", *extras[name]}):
                queue.append(dependency)
    return constraints, extras


def project(name, directory, version=None):
    target = directory / (name + ("-" + version if version else "") + ".json")
    if target.exists():
        return json.loads(target.read_text())
    for attempt in range(4):
        try:
            with urllib.request.urlopen("https://pypi.org/pypi/" + name + ("/" + version if version else "") + "/json", timeout=30) as response:
                value = json.load(response)
            if version:
                if value["info"]["version"] != version:
                    raise ValueError("官方发行版本与请求不一致")
                value = {"releases": {version: value["urls"]}}
            target.write_text(json.dumps(value, ensure_ascii=False) + "\n")
            return value
        except OSError:
            if attempt == 3:
                raise
            time.sleep(1)


def select(name, constraints, directory):
    allowed = SpecifierSet(",".join(item for item in constraints if item))
    pinned = {item.version for item in allowed if item.operator == "==" and "*" not in item.version}
    data = project(name, directory, next(iter(pinned)) if len(pinned) == 1 else None)
    versions = []
    for raw in data["releases"]:
        try:
            versions.append((Version(raw), raw))
        except InvalidVersion:
            continue
    for value, raw in sorted(versions, reverse=True):
        if value.is_prerelease or value.is_devrelease or value not in allowed:
            continue
        candidates = []
        for item in data["releases"][raw]:
            if item.get("yanked") or (item.get("requires_python") and ENVIRONMENT["python_full_version"] not in SpecifierSet(item["requires_python"])):
                continue
            if item["filename"].endswith(".whl"):
                if parse_wheel_filename(item["filename"])[3] & TAGS:
                    candidates.append(item)
            elif name == "docopt" and item["packagetype"] == "sdist":
                candidates.append(item)
        if candidates:
            item = next((item for item in candidates if item["filename"].endswith(".whl")), candidates[0])
            if not item["url"].startswith("https://files.pythonhosted.org/") or item["size"] > 50 * 1024 * 1024:
                raise ValueError("发行文件超出官方主机或本次新增依赖大小限制")
            return {"name": name, "version": str(value), "filename": item["filename"], "url": item["url"], "size": item["size"], "sha256": item["digests"]["sha256"], "constraints": sorted(constraints)}
    raise ValueError("没有兼容 Python 与本机平台的固定发行文件：" + name + str(allowed))


def main():
    directory = Path(sys.argv[1]).resolve()
    if not directory.is_dir() or Path(sys.prefix).resolve() != directory / "venv":
        raise ValueError("只能通过本次 TTS 隔离环境运行，并指向其资料目录")
    sources, wheels = directory / "pypi-json", directory / "wheels"
    sources.mkdir(exist_ok=True)
    wheels.mkdir(exist_ok=True)
    installed = []
    history = set()
    for _ in range(24):
        constraints, extras = requirements()
        missing = {}
        for name, values in constraints.items():
            try:
                if metadata.version(name) in SpecifierSet(",".join(value for value in values if value)):
                    continue
            except metadata.PackageNotFoundError:
                pass
            missing[name] = values
        if not missing:
            subprocess.run([sys.executable, "-B", "-m", "pip", "check"], check=True)
            (directory / "requirements.lock.txt").write_text(subprocess.check_output([sys.executable, "-B", "-m", "pip", "freeze"], text=True))
            (directory / "dependency-closure.json").write_text(json.dumps({"roots": ROOTS, "requirements": {name: {"version": metadata.version(name), "extras": sorted(extras[name]), "constraints": sorted(values)} for name, values in sorted(constraints.items())}, "downloaded": installed, "status": "all_declared_requirements_satisfied"}, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps({"status": "ready", "packages": len(constraints)}, ensure_ascii=False), flush=True)
            return
        fingerprint = json.dumps({name: sorted(values) for name, values in sorted(missing.items())})
        if fingerprint in history:
            raise ValueError("依赖组合重复，未继续安装：" + fingerprint)
        history.add(fingerprint)
        with ThreadPoolExecutor(max_workers=3) as pool:
            selected = list(pool.map(lambda item: select(item[0], item[1], sources), missing.items()))
        if sum(item["size"] for item in installed + selected) > 180 * 1024 * 1024:
            raise ValueError("新增依赖下载超过本次 180 MiB 限制")
        print(json.dumps({"phase": "prepare_dependencies", "packages": selected}, ensure_ascii=False), flush=True)

        def fetch(item):
            download_parts(item["url"], wheels / item["filename"], item["size"], item["sha256"], workers=4, chunk_size=256 * 1024)
            return str(wheels / item["filename"])

        with ThreadPoolExecutor(max_workers=3) as pool:
            paths = list(pool.map(fetch, selected))
        subprocess.run([sys.executable, "-B", "-m", "pip", "install", "--disable-pip-version-check", "--no-index", "--no-deps", "--no-compile", "--no-build-isolation", *paths], check=True)
        installed.extend(selected)
    raise ValueError("依赖层级超过本次固定环境限制")


if __name__ == "__main__":
    main()
