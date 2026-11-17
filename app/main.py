import logging
import os
import time
import uuid
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, DBAPIError
from starlette.exceptions import HTTPException
from . import __version__
import app.modules.auth.service as auth
import app.modules.booking.service as svc
from .upload_limit import UploadLimit

app = FastAPI(title='LABSEAT', version=__version__)
app.add_middleware(UploadLimit)
root = Path(__file__).parent
app.mount('/static', StaticFiles(directory=root / 'static'), name='static')
templates = Jinja2Templates(directory=root / 'templates')
logger = logging.getLogger('labseat')


from .shared.http import DB

def error(request, status, code, message):
    return JSONResponse({'code': code, 'message': message, 'request_id': getattr(request.state, 'request_id', str(uuid.uuid4()))}, status_code=status)

@app.middleware('http')
async def request_context(request, call_next):
    request.state.request_id = str(uuid.uuid4())
    started = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        response = error(request, 500, 'internal_error', 'Lỗi nội bộ')
    if os.getenv('COOKIE_SECURE','false').lower()=='true':response.headers['Strict-Transport-Security']='max-age=31536000'
    response.headers['X-Request-ID'] = request.state.request_id
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'"
    from .infrastructure.observability.metrics import emit
    path = request.url.path
    operation = 'Hold' if path == '/holds' else 'Confirm' if path.startswith('/holds/') and path.endswith('/confirm') else None
    if operation and request.method == 'POST':
        emit(operation + ('Success' if response.status_code < 400 else 'Failure'))
    route = getattr(request.scope.get('route'), 'path', 'unmatched')
    logger.info('request_id=%s method=%s route=%s status=%s duration_ms=%.1f', request.state.request_id, request.method, route, response.status_code, (time.monotonic()-started)*1000)
    return response

@app.exception_handler(svc.Problem)
async def problem_handler(request, exc):
    return error(request, exc.status, exc.code, exc.message)

@app.exception_handler(RequestValidationError)
async def validation_handler(request, exc):
    if request.url.path=='/me/profile':
        field=exc.errors()[0]['loc'][-1]
        message={'full_name':'Họ tên không hợp lệ (tối đa 150 ký tự).','cccd':'CCCD phải gồm 12 chữ số.','phone':'Nhập số điện thoại Việt Nam hợp lệ.','email':'Email là trường bắt buộc. Nhập địa chỉ email hợp lệ.'}.get(field,'Thông tin hồ sơ không hợp lệ.')
        return error(request,422,'invalid_input',message)
    return error(request, 422, 'invalid_input', 'Dữ liệu đầu vào không hợp lệ')

@app.exception_handler(HTTPException)
async def http_handler(request, exc):
    return error(request, exc.status_code, 'http_error', 'Không tìm thấy tài nguyên' if exc.status_code == 404 else 'Yêu cầu không hợp lệ')

@app.exception_handler(IntegrityError)
async def integrity_handler(request, exc):
    return error(request, 409, 'conflict', 'Xung đột dữ liệu')

@app.exception_handler(DBAPIError)
async def database_handler(request, exc):
    return error(request, 503, 'db_unavailable', 'Cơ sở dữ liệu chưa sẵn sàng')

@app.get('/healthz')
def health():
    return {'status': 'ok', 'version': __version__, 'deployment': 'labseat', 'release': os.getenv('RELEASE_ID', 'local')}

@app.get('/readyz')
def ready(db=DB):
    db.execute(text('SELECT 1'))
    return {'status':'ready', 'version':__version__}



@app.get('/')
def home(request: Request):
    response = templates.TemplateResponse(request=request, name='index.html', context={'version':__version__})
    if not request.cookies.get('labseat_pre_csrf'):
        auth.cookie(response, 'labseat_pre_csrf', auth.secrets.token_urlsafe(32), httponly=False)
    return response




# All application nodes expose the same routes.
from .modules.auth.router import router as auth_router
app.include_router(auth_router)
from .modules.profiles.router import router as profiles_router
app.include_router(profiles_router)
from .modules.queue.router import router as queue_router
app.include_router(queue_router)
from .modules.sessions.router import router as sessions_router
app.include_router(sessions_router)
from .modules.rooms.router import router as rooms_router
app.include_router(rooms_router)
from .modules.booking.router import router as booking_router
app.include_router(booking_router)
from .modules.tickets.router import router as tickets_router
app.include_router(tickets_router)
from .modules.checkin.router import router as checkin_router
app.include_router(checkin_router)
from .modules.admin.router import router as admin_router
app.include_router(admin_router)

from .modules.notifications.router import router as notifications_router
app.include_router(notifications_router)

from .modules.accounts.router import router as accounts_router
app.include_router(accounts_router)
from .modules.checkin.staff import router as staff_router
app.include_router(staff_router)
from .modules.admin.lifecycle import router as lifecycle_router
app.include_router(lifecycle_router)
from .modules.notifications.jobs import router as email_jobs_router
app.include_router(email_jobs_router)
from .realtime import router as realtime_router
app.include_router(realtime_router)
