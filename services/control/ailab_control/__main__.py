"""回环服务入口，stdout 首行只有宿主握手。"""

import argparse
import json
import os
import secrets
import signal
import socket
import sys
import threading
import traceback
from pathlib import Path

import uvicorn

from .api import create_app
from .service import Settings
from .storage import Fault


def main():
    parser = argparse.ArgumentParser(description="启动 AI Lab 本机控制服务")
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--import-root", action="append", type=Path, default=[])
    parser.add_argument("--worker-python", type=Path)
    parser.add_argument("--worker-script", type=Path)
    parser.add_argument("--preflight-script", type=Path)
    parser.add_argument("--bundled-worker", type=Path)
    parser.add_argument('--media-python', type=Path)
    parser.add_argument('--audio-python', type=Path)
    parser.add_argument('--media-worker-script', type=Path)
    parser.add_argument('--media-preflight-script', type=Path)
    parser.add_argument('--audio-worker-script', type=Path)
    parser.add_argument('--audio-preflight-script', type=Path)
    parser.add_argument('--bundled-media-worker', type=Path)
    parser.add_argument('--bundled-audio-worker', type=Path)
    parser.add_argument('--market-fixture-origin', help='仅登记本次受控回环数据来源')
    parser.add_argument("--export-root", action="append", type=Path, default=[])
    parser.add_argument("--allow-origin", action="append", default=[])
    parser.add_argument("--parent-pid", type=int)
    args = parser.parse_args()
    market_providers = [('fixture-provider', args.market_fixture_origin)] if args.market_fixture_origin else []
    if not 0 <= args.port <= 65535:
        parser.error("port 必须位于 0 至 65535")
    if args.parent_pid is not None and (args.parent_pid <= 1 or args.parent_pid != os.getppid()):
        parser.error("parent-pid 必须与当前父进程一致")
    token = secrets.token_urlsafe(48)
    host_token = secrets.token_urlsafe(48)
    try:
        app = create_app(Settings(args.data_dir, token, args.import_root, args.worker_python, args.worker_script, args.allow_origin, args.parent_pid, args.preflight_script, args.bundled_worker, args.export_root, host_token=host_token, media_python=args.media_python, audio_python=args.audio_python, media_worker_script=args.media_worker_script, media_preflight_script=args.media_preflight_script, audio_worker_script=args.audio_worker_script, audio_preflight_script=args.audio_preflight_script, bundled_media_worker=args.bundled_media_worker, bundled_audio_worker=args.bundled_audio_worker, market_providers=market_providers))
    except Fault as error:
        if error.code == "DATABASE_MIGRATION_FAILED":
            # 宿主收到失败首行后会回收进程；先刷新原始诊断，避免被终止时丢失。
            traceback.print_exception(error)
            sys.stderr.flush()
            # stdout 只传白名单错误码与本进程身份，不携带内部异常正文。
            print(json.dumps({"status": "failed", "code": "DATABASE_MIGRATION_FAILED", "pid": os.getpid()}), flush=True)
            raise SystemExit(1) from None
        raise
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", args.port))
    listener.listen(128)
    connection = {"port": listener.getsockname()[1], "token": token, "pid": os.getpid()}
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=connection["port"], access_log=False, log_level="warning", timeout_graceful_shutdown=7))
    # Uvicorn 会在恢复旧处理器后重新投递信号；保留清理控制权以撤销连接文件。
    signal.signal(signal.SIGTERM, lambda *_: setattr(server, "should_exit", True))
    signal.signal(signal.SIGINT, lambda *_: setattr(server, "should_exit", True))

    def watch_parent():
        while not app.state.service.closed.wait(0.5):
            if os.getppid() != args.parent_pid:
                server.should_exit = True
                return

    if args.parent_pid:
        threading.Thread(target=watch_parent, daemon=True).start()
    if args.token_file:
        args.token_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(args.token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(connection, stream)
    # 宿主专属凭据只交给启动握手，开发连接文件不包含它。
    print(json.dumps({**connection, "host_token": host_token}), flush=True)
    try:
        server.run(sockets=[listener])
    finally:
        app.state.service.close()
        listener.close()
        if args.token_file and args.token_file.is_file():
            try:
                current = json.loads(args.token_file.read_text())
                if current.get("token") == token:
                    args.token_file.unlink()
            except (OSError, ValueError):
                pass


if __name__ == "__main__":
    main()
