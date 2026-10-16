"""Single-owner local web UI. No public bind, account database or secret form."""
import asyncio
from contextlib import asynccontextmanager
import secrets
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .telemetry import snapshot

STATIC = Path(__file__).parent / 'static'


class Message(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message: str = Field(min_length=1, max_length=12000)


class Answers(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question_id: str = Field(max_length=64)
    answers: dict[str, str | list[str] | None]


class LocalBoundary:
    """Host, origin, cookie and streamed body checks before JSON parsing."""
    def __init__(self, app, token, port, access=None):
        self.app, self.token = app, token
        self.hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        self.access = access
        if access:
            self.hosts.add(access.host)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        host = headers.get(b'host', b'').decode('latin1')
        async def reject(status, detail):
            await JSONResponse({'detail': detail}, status_code=status, headers={'Cache-Control':'no-store'})(scope, receive, send)
        if host not in self.hosts:
            return await reject(400, 'Loopback host required')
        if self.access:
            assertion = headers.get(b'cf-access-jwt-assertion', b'').decode('latin1')
            if not await self.access.allows(assertion):
                return await reject(401, 'A valid Cloudflare Access session is required')
        if scope['path'].startswith('/api/'):
            from http.cookies import SimpleCookie
            cookie = SimpleCookie()
            try:
                cookie.load(headers.get(b'cookie', b'').decode('latin1'))
                value = cookie.get('hsuh_session')
                good = value is not None and secrets.compare_digest(value.value, self.token)
            except Exception:
                good = False
            if not good:
                return await reject(401, 'Open HSUH in this browser first')
        if scope['method'] not in {'GET', 'HEAD'}:
            origin = self.access.origin if self.access and host == self.access.host else f'http://{host}'
            if headers.get(b'origin') != origin.encode() or headers.get(b'x-hsuh-request') != b'1':
                return await reject(403, 'Same-origin request required')
            body = bytearray()
            while True:
                part = await receive()
                if part['type'] == 'http.disconnect':
                    return
                body.extend(part.get('body', b''))
                if len(body) > 65536:
                    return await reject(413, 'Request exceeds 64 KiB')
                if not part.get('more_body'):
                    break
            sent = False
            original_receive = receive
            async def bounded_receive():
                nonlocal sent
                if not sent:
                    sent = True
                    return {'type':'http.request', 'body':bytes(body), 'more_body':False}
                return await original_receive()
            receive = bounded_receive
        async def safe_send(message):
            if message['type'] == 'http.response.start':
                message.setdefault('headers', []).extend([
                    (b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff'),
                    (b'referrer-policy', b'no-referrer'),
                    (b'content-security-policy', b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
                    (b'permissions-policy', b'camera=(), microphone=(), geolocation=()'),
                ])
            await send(message)
        await self.app(scope, receive, safe_send)


def create_app(port=8110, public_origin=None, access_team=None, access_audience=None, owner_email=None):
    from .chat import ChatManager
    from .quota import QuotaReader
    from .access import AccessGate
    manager = ChatManager()
    quota = QuotaReader()
    token = secrets.token_urlsafe(32)
    public_origin = public_origin or os.environ.get('HSUH_PUBLIC_ORIGIN')
    access = AccessGate(public_origin, access_team or os.environ.get('HSUH_ACCESS_TEAM'),
                        access_audience or os.environ.get('HSUH_ACCESS_AUDIENCE'),
                        owner_email or os.environ.get('HSUH_OWNER_EMAIL')) if public_origin else None

    @asynccontextmanager
    async def lifespan(app):
        yield
        await manager.shutdown()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.manager = manager
    app.add_middleware(LocalBoundary, token=token, port=port, access=access)

    @app.get('/')
    async def index():
        r = FileResponse(STATIC / 'index.html')
        # HTTP is only allowed over loopback / an encrypted SSH tunnel. No public TLS proxy trust.
        r.set_cookie('hsuh_session', token, httponly=True, samesite='strict', secure=bool(access), path='/')
        return r

    @app.get('/assets/{name}')
    async def asset(name: str):
        if name not in {'app.js', 'style.css', 'mascot.svg', 'icon-192.png', 'icon-512.png'}:
            raise HTTPException(404)
        return FileResponse(STATIC / name)

    @app.get('/manifest.webmanifest')
    async def manifest():
        return FileResponse(STATIC / 'manifest.webmanifest', media_type='application/manifest+json')

    @app.get('/sw.js')
    async def service_worker():
        return FileResponse(STATIC / 'sw.js', media_type='text/javascript', headers={'Service-Worker-Allowed':'/'})

    @app.get('/api/status')
    async def status():
        return {'integration': 'Hermes Python library', 'mode':'Conversation + clarify only',
                'storage':'VPS process memory; cleared on restart', 'max_parallel':2,
                'credentials': {'enabled':False, 'reason':'Native vault bridge is not wired. Do not enter secrets in chat.'},
                'model': manager.model, 'active': manager.active_count,
                'background_jobs':{'scope':'HSUH conversation turns only', 'native_delegated_jobs':'unavailable: no gateway job bridge connected'},
                'access':'Cloudflare Access JWT' if access else 'Loopback only'}

    @app.get('/api/quota')
    async def get_quota():
        return await quota.read()

    @app.get('/api/telemetry')
    async def telemetry():
        return await asyncio.to_thread(snapshot)

    @app.get('/api/chats')
    async def chats():
        return manager.list()

    @app.post('/api/chats')
    async def create_chat():
        return manager.create()

    @app.get('/api/chats/{chat_id}')
    async def get_chat(chat_id: str):
        return manager.get(chat_id)

    @app.delete('/api/chats/{chat_id}')
    async def delete_chat(chat_id: str):
        await manager.delete(chat_id)
        return {'deleted':True}

    @app.post('/api/chats/{chat_id}/messages', status_code=202)
    async def message(chat_id: str, payload: Message):
        return manager.submit(chat_id, payload.message)

    @app.post('/api/chats/{chat_id}/answers')
    async def answers(chat_id: str, payload: Answers):
        return await manager.answer(chat_id, payload.question_id, payload.answers)

    @app.post('/api/chats/{chat_id}/stop')
    async def stop(chat_id: str):
        await manager.stop(chat_id)
        return manager.get(chat_id)

    @app.post('/api/credentials')
    async def credentials():
        # Deliberately do not read, parse, forward or retain any request payload.
        raise HTTPException(501, 'Credential entry disabled until an audited native vault bridge is connected')

    return app
