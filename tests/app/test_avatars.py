"""Private image upload, normalization, replacement and safe removal."""
import os
import pytest
if not os.getenv('TEST_DATABASE_URL'):pytest.skip('Disposable DB required',allow_module_level=True)
from test_profiles import client,student,VALID
from test_db import clean_db
from fastapi.testclient import TestClient
from app.main import app
from app.infrastructure.database.session import Session
from app.models import User
from app.infrastructure.storage.objects import LocalStorage,S3Storage
from sqlalchemy import select
from io import BytesIO
from PIL import Image
import app.main as main


def photo(color='red'):
    out=BytesIO();Image.new('RGBA',(400,300),color).save(out,'PNG');return out.getvalue()


def test_avatar_private_normalized_replace_and_remove(client,student,tmp_path,monkeypatch):
    monkeypatch.setattr('app.modules.profiles.router.storage',lambda:LocalStorage(tmp_path))
    with TestClient(app) as guest:
        assert guest.post('/me/avatar',files={'file':('a.png',photo())}).status_code==401
        assert guest.get('/me/avatar').status_code==401
    assert student.get('/me/avatar').status_code==404
    assert student.post('/me/avatar',files={'file':('a.png',photo())},headers={'X-CSRF-Token':'bad'}).status_code==403
    response=student.post('/me/avatar',files={'file':('a.png',photo())});assert response.status_code==200,response.text
    url=response.json()['avatar_url'];assert url.startswith('/me/avatar?v=')
    assert student.get('/me').json()['avatar_url']==url
    im=Image.open(BytesIO(student.get(url).content));assert im.size==(256,256) and im.format=='JPEG' and not im.getexif()
    assert client.get(url).status_code==404
    assert len(list(tmp_path.rglob('*.jpg')))==1
    response=student.post('/me/avatar',files={'file':('a.png',photo('blue'))});assert response.status_code==200
    assert response.json()['avatar_url']!=url
    assert len(list(tmp_path.rglob('*.jpg')))==2  # Orphan awaits common quarantine collector.
    assert student.delete('/me/avatar',headers={'X-CSRF-Token':'bad'}).status_code==403
    assert student.delete('/me/avatar').json()['avatar_url'] is None
    assert student.get('/me/avatar').status_code==404
    assert len(list(tmp_path.rglob('*.jpg')))==2  # Removing a reference does not delete immediately.
    assert student.delete('/me/avatar').status_code==200


@pytest.mark.parametrize('blob',[b'<svg/>',b'not image',b'x'*(5*1024*1024+1)])
def test_invalid_avatar_preserves_current(student,tmp_path,monkeypatch,blob):
    monkeypatch.setattr('app.modules.profiles.router.storage',lambda:LocalStorage(tmp_path))
    before=student.post('/me/avatar',files={'file':('a.png',photo())}).json()['avatar_url']
    response=student.post('/me/avatar',files={'file':('bad.png',blob)})
    assert response.status_code==422
    assert student.get('/me/profile').json()['avatar_url']==before


def test_avatar_storage_failure_and_s3_prefix(student,monkeypatch):
    class S3:
        fail=False
        objects={}
        def put_object(self,**kw):
            if self.fail:raise OSError('offline')
            self.objects[kw['Key']]=kw['Body']
        def get_object(self,**kw):return {'Body':BytesIO(self.objects[kw['Key']])}
        def delete_object(self,**kw):del self.objects[kw['Key']]
    s3=S3();monkeypatch.setattr('app.modules.profiles.router.storage',lambda:S3Storage(s3,'fixture','labseat/media'))
    assert student.post('/me/avatar',files={'file':('a.png',photo())}).status_code==200
    before=student.get('/me/profile').json()['avatar_url']
    assert all(k.startswith('labseat/media/users/') for k in s3.objects)
    s3.fail=True
    assert student.post('/me/avatar',files={'file':('a.png',photo())}).status_code==503
    assert student.get('/me/profile').json()['avatar_url']==before
