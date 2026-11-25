"""Resolve the CMake and Ninja programs for the Linux-to-Windows builds."""
import hashlib
import json
import shutil
from urllib.request import urlopen
import zipfile

WHEELS = {
    "cmake": ("3.31.6", "2297e9591307d9c61e557efe737bcf4d7c13a30f1f860732f684a204fee24dca", "cmake/data/bin/cmake"),
    "ninja": ("1.11.1.3", "a27e78ca71316c8654965ee94b286a98c83877bfebe2607db96897bbfe458af0", "ninja-1.11.1.3.data/scripts/ninja"),
}

def resolve_tool(name, requested, work):
    installed = shutil.which(requested)
    if installed:
        return installed
    version, digest, member = WHEELS[name]
    directory = work / "tools"
    binary = directory / member
    if not binary.exists():
        with urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=60) as source:
            wheel = next(f for f in json.load(source)["urls"] if f["digests"]["sha256"] == digest)
        archive = work / wheel["filename"]
        with urlopen(wheel["url"], timeout=120) as src, archive.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
            raise ValueError("Unexpected build tool " + name)
        with zipfile.ZipFile(archive) as z:
            z.extractall(directory)
        binary.chmod(0o755)
    return str(binary)
