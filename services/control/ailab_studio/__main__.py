"""Portable control entrypoint; heavy environments are downloaded only on request."""
import argparse
from contextlib import asynccontextmanager
import hmac
import json
import os
from pathlib import Path
import secrets
import socket
import threading
import time
import psutil
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import uvicorn
from .api import router
from .dataset_api import router as dataset_router
from .service import Studio


def create_app(root, token, environment=None):
    studio = Studio(root, environment)

    @asynccontextmanager
    async def lifespan(app):
        try: yield
        finally: studio.close()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.studio = studio

    @app.middleware('http')
    async def boundary(request: Request, next):
        if request.headers.get('host', '').split(':')[0] not in ('localhost', '127.0.0.1') or request.headers.get('origin'):
            return JSONResponse({'error': {'message': '只允许受保护的本机宿主访问'}}, status_code=403)
        if request.url.path != '/health' and not hmac.compare_digest(request.headers.get('authorization', ''), 'Bearer ' + token):
            return JSONResponse({'error': {'message': '本机会话认证失败'}}, status_code=401)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 2 * 1024 * 1024:
                return JSONResponse({'error': {'message': '请求超过 2 MiB，请减少会话或图片大小'}}, status_code=413)
        request._body = bytes(body)
        return await next(request)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({'error': {'code': 'INVALID_REQUEST', 'message': str(exc)}}, status_code=400)

    @app.exception_handler(RequestValidationError)
    async def validation(request, exc):
        fields = '; '.join('.'.join(map(str, e['loc'][1:])) + ': ' + e['msg'] for e in exc.errors())
        return JSONResponse({'error': {'code': 'INVALID_CONFIG', 'message': fields}}, status_code=422)

    @app.get('/health')
    def health(): return {'status': 'ok', 'version': '3.2.0'}

    app.include_router(router(studio))
    app.include_router(dataset_router(studio))
    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', required=True, type=Path)
    parser.add_argument('--port', default=0, type=int)
    parser.add_argument('--token-file', type=Path)
    parser.add_argument('--parent-pid', type=int)
    parser.add_argument('--environment-dir', type=Path)
    args = parser.parse_args()
    token = secrets.token_urlsafe(48)
    import sys
    environment = args.environment_dir or (Path(sys.executable).parent / 'environment' if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[3] / 'environment')
    app = create_app(args.data_dir, token, environment)
    listener = socket.socket(); listener.bind(('127.0.0.1', args.port)); listener.listen(128)
    info = {'port': listener.getsockname()[1], 'token': token, 'pid': os.getpid()}
    server = uvicorn.Server(uvicorn.Config(app, access_log=False, log_level='warning', timeout_graceful_shutdown=10))
    if args.token_file:
        args.token_file.parent.mkdir(parents=True, exist_ok=True)
        args.token_file.write_text(json.dumps(info), encoding='utf-8')
        if os.name != 'nt': args.token_file.chmod(0o600)
    if args.parent_pid:
        if args.parent_pid != os.getppid(): raise ValueError('父进程身份不匹配')
        parent_started = psutil.Process(args.parent_pid).create_time()
        def watch():
            while not server.should_exit:
                time.sleep(0.5)
                try: alive = psutil.Process(args.parent_pid).create_time() == parent_started
                except psutil.Error: alive = False
                if not alive: server.should_exit = True
        threading.Thread(target=watch, daemon=True).start()
    print(json.dumps(info), flush=True)
    try: server.run(sockets=[listener])
    finally:
        listener.close()
        if args.token_file and args.token_file.is_file():
            if json.loads(args.token_file.read_text(encoding='utf-8')).get('token') == token: args.token_file.unlink()


if __name__ == '__main__': main()
