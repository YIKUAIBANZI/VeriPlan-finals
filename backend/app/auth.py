"""Password authentication and opaque, database-backed cookie sessions."""
import base64
from collections import deque
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import re
import secrets
from threading import Lock
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.models import AuthSessionRecord, UserRecord
from app.repository import DecisionRepository


COOKIE_NAME = 'veriplan_session'
SESSION_SECONDS = 30 * 24 * 60 * 60
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_FAILURE_LIMIT = 10
USERNAME_PATTERN = re.compile(r'^[0-9A-Za-z_.\-一-鿿]{3,32}$')


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=2**14, r=8, p=1, dklen=64)
    return 'scrypt$16384$8$1$' + base64.b64encode(salt).decode('ascii') + '$' + base64.b64encode(digest).decode('ascii')


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, n, r, p, encoded_salt, encoded_hash = stored.split('$')
        if (algorithm, n, r, p) != ('scrypt', '16384', '8', '1'):
            return False
        salt = base64.b64decode(encoded_salt, validate=True)
        expected = base64.b64decode(encoded_hash, validate=True)
        if len(salt) != 16 or len(expected) != 64:
            return False
        actual = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=2**14, r=8, p=1, dklen=64)
        return hmac.compare_digest(actual, expected)
    except (ValueError, UnicodeError):
        return False


# Unknown usernames still perform the same password work as existing accounts.
_DUMMY_PASSWORD_HASH = hash_password('unused-dummy-password')


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def user_response(user: UserRecord) -> dict:
    created_at = user.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return {'user': {'id': user.id, 'username': user.username, 'created_at': created_at.isoformat()}}


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(LoginRequest):
    invite_code: str | None = None


class AuthRoute(APIRoute):
    """Keep malformed auth input in the same Chinese detail-string contract."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def auth_handler(request: Request):
            try:
                return await handler(request)
            except RequestValidationError as error:
                raise HTTPException(422, '请求参数不合法，请检查用户名、密码和邀请码') from error

        return auth_handler


class AuthService:
    def __init__(self, repository: DecisionRepository, settings: Settings):
        self._sessions = repository._sessions
        self.settings = settings
        self._login_failures: dict[str, deque[float]] = {}
        self._login_lock = Lock()

    @property
    def registration_requires_invite(self) -> bool:
        code = self.settings.registration_invite_code
        return code is not None and bool(code.get_secret_value())

    def register(self, payload: RegisterRequest) -> UserRecord:
        if self.registration_requires_invite:
            expected = self.settings.registration_invite_code.get_secret_value()
            if not hmac.compare_digest((payload.invite_code or '').encode('utf-8'), expected.encode('utf-8')):
                raise HTTPException(403, '邀请码错误或缺失')
        username = payload.username.strip()
        if not USERNAME_PATTERN.fullmatch(username):
            raise HTTPException(422, '用户名须为 3–32 个字符，仅允许字母、数字、下划线、点、短横线和中文')
        if not 8 <= len(payload.password) <= 128:
            raise HTTPException(422, '密码长度须为 8–128 个字符')
        with self._sessions.begin() as session:
            existing = session.scalar(select(UserRecord.id).where(func.lower(UserRecord.username) == username.lower()))
            if existing is not None:
                raise HTTPException(409, '用户名已存在')
            user = UserRecord(username=username, password_hash=hash_password(payload.password), created_at=datetime.now(UTC))
            session.add(user)
            try:
                session.flush()
            except IntegrityError as error:
                raise HTTPException(409, '用户名已存在') from error
        return user

    def login(self, payload: LoginRequest) -> UserRecord:
        key = payload.username.strip().lower()
        # Serialize check + verification + increment so concurrent failures cannot bypass the cap.
        with self._login_lock:
            now = monotonic()
            failures = self._login_failures.get(key, deque())
            while failures and failures[0] <= now - LOGIN_WINDOW_SECONDS:
                failures.popleft()
            if len(failures) >= LOGIN_FAILURE_LIMIT:
                raise HTTPException(429, '登录失败次数过多，请在 15 分钟后重试')
            with self._sessions() as session:
                user = session.scalar(select(UserRecord).where(func.lower(UserRecord.username) == key))
                valid = verify_password(payload.password, user.password_hash if user else _DUMMY_PASSWORD_HASH)
            if user is None or not valid:
                failures.append(monotonic())
                self._login_failures[key] = failures
                if len(failures) >= LOGIN_FAILURE_LIMIT:
                    raise HTTPException(429, '登录失败次数过多，请在 15 分钟后重试')
                raise HTTPException(401, '用户名或密码错误')
            self._login_failures.pop(key, None)
            return user

    def issue_session(self, user: UserRecord, request: Request, response: Response) -> None:
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        with self._sessions.begin() as session:
            previous = request.cookies.get(COOKIE_NAME)
            if previous:
                session.execute(delete(AuthSessionRecord).where(AuthSessionRecord.token_hash == token_hash(previous)))
            session.add(AuthSessionRecord(token_hash=token_hash(token), user_id=user.id, created_at=now,
                                          expires_at=now + timedelta(seconds=SESSION_SECONDS)))
        response.set_cookie(COOKIE_NAME, token, max_age=SESSION_SECONDS, httponly=True,
                            secure=self.settings.session_cookie_secure, samesite='lax', path='/')

    def current_user(self, token: str | None) -> UserRecord | None:
        if not token:
            return None
        with self._sessions.begin() as session:
            auth_session = session.get(AuthSessionRecord, token_hash(token))
            if auth_session is None:
                return None
            expires_at = auth_session.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= datetime.now(UTC):
                session.delete(auth_session)
                return None
            return session.get(UserRecord, auth_session.user_id)

    def logout(self, token: str | None, response: Response) -> None:
        if token:
            with self._sessions.begin() as session:
                session.execute(delete(AuthSessionRecord).where(AuthSessionRecord.token_hash == token_hash(token)))
        response.delete_cookie(COOKIE_NAME, path='/', httponly=True,
                               secure=self.settings.session_cookie_secure, samesite='lax')


def require_user(request: Request) -> UserRecord:
    user = request.app.state.auth.current_user(request.cookies.get(COOKIE_NAME))
    if user is None:
        raise HTTPException(401, '请先登录')
    return user


def create_auth_router(auth: AuthService) -> APIRouter:
    router = APIRouter(prefix='/api/auth', route_class=AuthRoute)

    @router.post('/register', status_code=201)
    def register(payload: RegisterRequest, request: Request, response: Response):
        user = auth.register(payload)
        auth.issue_session(user, request, response)
        return user_response(user)

    @router.post('/login')
    def login(payload: LoginRequest, request: Request, response: Response):
        user = auth.login(payload)
        auth.issue_session(user, request, response)
        return user_response(user)

    @router.post('/logout', status_code=204)
    def logout(request: Request):
        response = Response(status_code=204)
        auth.logout(request.cookies.get(COOKIE_NAME), response)
        return response

    @router.get('/me')
    def me(user: UserRecord = Depends(require_user)):
        return user_response(user)

    return router
