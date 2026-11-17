"""Bound multipart bodies before Starlette parses or spools uploaded files."""
from starlette.responses import JSONResponse

class UploadLimit:
    def __init__(self, app, limit=6*1024*1024):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        path=scope.get('path','')
        webhook=path=='/webhooks/brevo'
        limit=128*1024 if webhook else self.limit
        if scope['type']!='http' or scope.get('method') not in ('POST','PATCH') or not (webhook or path=='/me/avatar' or (path.startswith('/admin/rooms/') and path.endswith('/image')) or (path=='/admin/events' or path.startswith('/admin/events/'))):
            return await self.app(scope,receive,send)
        chunks=[]; size=0
        while True:
            message=await receive()
            if message['type']=='http.disconnect':
                return
            size+=len(message.get('body',b''))
            if size>limit:
                request_id=scope.get('state',{}).get('request_id','unknown')
                response=JSONResponse({'code':'invalid_image','message':'Payload quá lớn' if webhook else 'Ảnh tối đa 5 MB; multipart tối đa 6 MB','request_id':request_id},status_code=422)
                return await response(scope,receive,send)
            chunks.append(message)
            if not message.get('more_body',False):
                break
        async def replay():
            if chunks:
                return chunks.pop(0)
            return await receive()
        return await self.app(scope,replay,send)
