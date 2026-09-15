"""显式选择回环 HTTP 或直接 HTTPS；每个执行目录固定一种连接方式。"""

import argparse
import ipaddress
import json
import os
from pathlib import Path
import signal
import socket
import ssl
import stat
import sys

import uvicorn

from .server import create_app


def tls_context(certificate, private_key):
    """监听前验证证书、密钥和权限，读取同一已打开文件描述符。"""
    descriptors = []
    try:
        for path, secret in ((certificate, False), (private_key, True)):
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            descriptors.append(descriptor)
            metadata = os.fstat(descriptor)
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or not 1 <= metadata.st_size <= 1024 * 1024
                    or (secret and (metadata.st_mode & 0o077 or metadata.st_uid != os.geteuid()))):
                raise ValueError("TLS 文件无效；私钥须为当前用户拥有、无组及其他用户权限的普通文件")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        # 空口令防止加密私钥等待交互输入；当前入口只接受权限受限的无口令服务密钥。
        context.load_cert_chain(f"/dev/fd/{descriptors[0]}", f"/dev/fd/{descriptors[1]}", password="")
        return context
    finally:
        for descriptor in descriptors:
            os.close(descriptor)


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--port", type=int, default=0)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--loopback-contract-only", action="store_true")
    mode.add_argument("--https", action="store_true")
    parser.add_argument("--bind")
    parser.add_argument("--cert-file", type=Path)
    parser.add_argument("--key-file", type=Path)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("port 超出范围")
    transport, bind, context = "loopback_http", "127.0.0.1", None
    if args.https:
        if not args.bind or not args.cert_file or not args.key_file:
            parser.error("HTTPS 必须显式给出 bind、cert-file 和 key-file")
        try:
            bind = str(ipaddress.ip_address(args.bind))
            if bind != args.bind or "%" in args.bind:
                raise ValueError()
            context = tls_context(args.cert_file, args.key_file)
        except (ValueError, OSError, ssl.SSLError):
            parser.error("HTTPS 绑定地址、证书、私钥或文件权限验证失败；未开始监听")
        transport = "https"
    elif args.bind or args.cert_file or args.key_file:
        parser.error("回环 HTTP 模式不接受网络绑定或 TLS 文件参数")
    try:
        descriptor = os.open(args.token_file, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "r") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077 or metadata.st_size > 513:
                raise ValueError()
            token = stream.read().removesuffix("\n")
            if not 32 <= len(token) <= 512 or not all(33 <= ord(char) <= 126 for char in token):
                raise ValueError()
    except (ValueError, OSError, UnicodeError):
        parser.error("凭证须为权限受限的小型普通文件，包含 32 至 512 位可见英文字符")
    app, listener = None, None
    try:
        app = create_app(args.data_dir, token, transport)
        config = uvicorn.Config(app, host=bind, port=args.port, access_log=False, log_level="warning",
                                proxy_headers=False, timeout_graceful_shutdown=3)
        config.load()
        config.ssl = context
        listener = socket.socket(socket.AF_INET6 if ":" in bind else socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((bind, args.port))
        listener.listen(64)
        server = uvicorn.Server(config)
        signal.signal(signal.SIGTERM, lambda *_: setattr(server, "should_exit", True))
        signal.signal(signal.SIGINT, lambda *_: setattr(server, "should_exit", True))
        print(json.dumps({"port": listener.getsockname()[1], "executor_id": app.state.executor.executor_id,
                          "transport": transport, "validation_scope": app.state.executor.validation_scope, "pid": os.getpid()}), flush=True)
        server.run(sockets=[listener])
    finally:
        if app:
            app.state.executor.close()
        if listener:
            listener.close()


if __name__ == "__main__":
    main()
