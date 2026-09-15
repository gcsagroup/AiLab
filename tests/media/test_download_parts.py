"""真实本地 HTTP 验证分段续传及摘要失败；不访问外网或模型。"""

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapters" / "media"))
from download_parts import download_parts


class DownloadPartsTests(unittest.TestCase):
    def test_interrupted_response_resumes_the_received_segment(self):
        data = bytes(range(256)) * 64
        requested = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                start, end = map(int, self.headers["Range"].removeprefix("bytes=").split("-"))
                requested.append((start, end))
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
                self.send_header("Content-Length", str(end - start + 1))
                self.end_headers()
                self.wfile.write(data[start:start + 4096] if len(requested) <= 3 else data[start:end + 1])
                self.close_connection = True
            def log_message(self, *_):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "weights.safetensors"
                url = f"http://127.0.0.1:{server.server_port}/weights"
                with self.assertRaises(subprocess.CalledProcessError):
                    download_parts(url, target, len(data), hashlib.sha256(data).hexdigest())
                self.assertFalse(target.exists())
                download_parts(url, target, len(data), hashlib.sha256(data).hexdigest())
                self.assertEqual(target.read_bytes(), data)
                self.assertEqual(requested, [(0, len(data) - 1), (4096, len(data) - 1), (8192, len(data) - 1), (12288, len(data) - 1)])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_resume_prefix_and_reject_corrupt_prefix(self):
        data = bytes(range(256)) * 64
        requested = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                start, end = map(int, self.headers["Range"].removeprefix("bytes=").split("-"))
                requested.append((start, end))
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
                self.send_header("Content-Length", str(end - start + 1))
                self.end_headers()
                self.wfile.write(data[start:end + 1])
            def log_message(self, *_):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "weights.safetensors"
                partial = target.with_name(target.name + ".partial")
                partial.write_bytes(data[:17])
                parts = target.with_name(target.name + ".parts")
                parts.mkdir()
                piece = parts / f"{17:012d}-{len(data) - 1:012d}"
                piece.with_suffix(".headers").write_text(f"HTTP/1.0 206 Partial Content\nContent-Range: bytes 17-{len(data) - 1}/{len(data)}\n")
                piece.with_suffix(".tail").write_bytes(data[17:41])
                url = f"http://127.0.0.1:{server.server_port}/weights"
                download_parts(url, target, len(data), hashlib.sha256(data).hexdigest(), workers=2)
                self.assertEqual(target.read_bytes(), data)
                self.assertEqual(requested, [(41, len(data) - 1)])
                self.assertFalse(partial.exists())
                target.unlink()
                partial.write_bytes(b"corrupt prefix")
                with self.assertRaisesRegex(ValueError, "摘要"):
                    download_parts(url, target, len(data), hashlib.sha256(data).hexdigest(), workers=2)
                self.assertFalse(target.exists())
                self.assertTrue(partial.exists())
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
