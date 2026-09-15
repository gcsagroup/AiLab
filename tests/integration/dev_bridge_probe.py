"""针对真实 Vite 开发桥接的只读反例检查，不输出连接令牌。"""

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[2]
    connection_file = root / ".artifacts/dev/control-connection.json"
    token = json.loads(connection_file.read_text())["token"].encode()
    private_path = urllib.parse.quote(str(connection_file), safe="/")
    cases = [
        ("工作台可读项目", "/api/v1/projects", {"X-AiLab-Request": "1"}, 200),
        ("缺少页面请求标记", "/api/v1/projects", {}, 403),
        ("外站来源", "/api/v1/projects", {"X-AiLab-Request": "1", "Origin": "https://example.test"}, 403),
        ("跨站抓取", "/api/v1/projects", {"X-AiLab-Request": "1", "Sec-Fetch-Site": "cross-site"}, 403),
        ("错误主机名", "/api/v1/projects", {"X-AiLab-Request": "1", "Host": "example.test:1420"}, 403),
        ("禁止自建读取授权", "/api/v1/import-grants", {"X-AiLab-Request": "1"}, 403),
        ("禁止自建写入授权", "/api/v1/export-grants", {"X-AiLab-Request": "1"}, 403),
        ("禁止页面激活恢复库", "/api/v1/restores/restore-test/activation", {"X-AiLab-Request": "1"}, 403),
        ("禁止编码路径绕过", "/api/v1/%69mport-grants", {"X-AiLab-Request": "1"}, 403),
        ("禁止页面改执行器路径", "/api/v1/settings", {"X-AiLab-Request": "1"}, 403, "PATCH"),
        ("禁止路径转义", "/api/v1/%2e%2e/projects", {"X-AiLab-Request": "1"}, 403),
        ("私有文件不公开", f"/@fs{private_path}", {}, 403),
        ("私有文件 raw 不公开", f"/@fs{private_path}?raw", {}, 403),
    ]
    results = []
    for name, path, headers, expected, *method in cases:
        request = urllib.request.Request("http://127.0.0.1:1420" + path, headers=headers, method=method[0] if method else "GET")
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read()
            status = response.status
        result = {"case": name, "status": status, "expected": expected, "token_exposed": token in body}
        results.append(result)
    output = root / ".artifacts/frontend/dev-bridge-probe.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    failures = [item for item in results if item["status"] != item["expected"] or item["token_exposed"]]
    print(json.dumps({"checks": len(results), "passed": len(results) - len(failures), "failures": failures}, ensure_ascii=False))
    raise SystemExit(bool(failures))


if __name__ == "__main__":
    main()
