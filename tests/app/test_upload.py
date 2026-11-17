import asyncio
import pytest
from app.upload_limit import UploadLimit

def run_upload(chunks,limit,method='POST',path='/admin/rooms/test/image'):
    received=[]; sent=[]
    async def downstream(scope,receive,send):
        while True:
            message=await receive();received.append(message['body'])
            if not message.get('more_body',False):break
    queue=[{'type':'http.request','body':body,'more_body':i<len(chunks)-1} for i,body in enumerate(chunks)]
    async def receive():return queue.pop(0)
    async def send(message):sent.append(message)
    asyncio.run(UploadLimit(downstream,limit)({'type':'http','method':method,'path':path,'state':{'request_id':'test'}},receive,send))
    return received,sent

def test_chunked_limit_before_parser():
    received,sent=run_upload([b'123',b'456'],5)
    assert not received
    assert sent[0]['status']==422
    assert b'"request_id":"test"' in sent[1]['body']

def test_body_replay():
    received,sent=run_upload([b'12',b'34'],4)
    assert received==[b'12',b'34'] and not sent

def test_disconnect_never_calls_parser():
    called=[]
    async def app(scope,receive,send):called.append(True)
    async def receive():return {'type':'http.disconnect'}
    async def send(message):raise AssertionError('No response after disconnect')
    asyncio.run(UploadLimit(app)({'type':'http','method':'POST','path':'/admin/rooms/x/image'},receive,send))
    assert not called

def test_non_upload_request_is_not_buffered():
    called=[]
    async def app(scope,receive,send):called.append(True)
    async def receive():raise AssertionError('Must not buffer other routes')
    async def send(message):pass
    asyncio.run(UploadLimit(app)({'type':'http','method':'GET','path':'/rooms'},receive,send))
    assert called==[True]


@pytest.mark.parametrize('method,path',[('POST','/admin/events'),('PATCH','/admin/events/ca-id')])
def test_ca_multipart_bounded_before_parser(method,path):
    received,sent=run_upload([b'123',b'456'],5,method,path)
    assert not received and sent[0]['status']==422
