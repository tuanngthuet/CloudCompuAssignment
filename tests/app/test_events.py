"""LABSEAT image contract and transactional creation on real PostgreSQL."""
import json
import uuid
from io import BytesIO
import pytest
from test_event_management import client, payload, poster, create, update
from sqlalchemy import select
from app.infrastructure.database.session import Session
from app.models import Event
from app.infrastructure.storage.objects import S3Storage
import app.main as main


def test_ca_images_auth_and_atomic_storage(client,monkeypatch):
    class S3:
        objects={}
        failing=False
        def put_object(self,**kw):
            if self.failing:raise OSError('offline')
            self.objects[kw['Key']]=kw['Body']
        def get_object(self,**kw):return {'Body':BytesIO(self.objects[kw['Key']])}
    s3=S3();monkeypatch.setattr('app.modules.admin.service.storage',lambda:S3Storage(s3,'test-bucket','prefix'))
    monkeypatch.setattr('app.modules.admin.router.storage',lambda:S3Storage(s3,'test-bucket','prefix'))
    data=payload()
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as guest:
        assert create(guest,data).status_code==401
    response=create(client,data);assert response.status_code==201,response.text
    e=response.json();assert e['session_type']=='exam';assert 'banner_url' not in e
    assert client.get(e['poster_url']).status_code==200
    assert client.get(e['poster_url'].replace('/poster','/banner')).status_code==404
    assert all(k.startswith('prefix/events/'+e['id']+'/poster/') for k in s3.objects)
    old=e['poster_url'];s3.failing=True
    failed=payload();assert create(client,failed).status_code==503
    with Session() as db:assert db.scalar(select(Event).where(Event.name==failed['name'])) is None
    response=client.patch('/admin/events/'+e['id'],data={'data':json.dumps(data|{'name':'Rollback'})},files={'poster':('ca.png',poster(),'image/png')})
    assert response.status_code==503
    with Session() as db:assert db.get(Event,uuid.UUID(e['id'])).name==data['name']
    s3.failing=False
    assert update(client,e['id'],data|{'name':'Renamed'}).json()['poster_url']==old


@pytest.mark.parametrize('size',[(1280,719),(1281,720),(720,958),(320,180),(2000,400)])
def test_any_dimensions_are_normalized_for_ca(client,size):
    data=payload()
    response=client.post('/admin/events',data={'data':json.dumps(data)},files={'poster':('ca.png',poster(size),'image/png')})
    assert response.status_code==201,response.text
    from PIL import Image
    image=Image.open(BytesIO(client.get(response.json()['poster_url']).content))
    assert image.size==(1280,720) and image.format=='JPEG'


def test_required_image_type_schedule_and_no_online(client):
    data=payload()
    assert client.post('/admin/events',data={'data':json.dumps(data)}).status_code==422
    for change in [{'session_type':'music'},{'mode':'online'},{'featured':True},{'category':'Workshop'},{'schedule':None}]:
        assert create(client,data|change).status_code==422
    response=client.post('/admin/events',data={'data':json.dumps(data)},files={'poster':('bad.png',b'bad','image/png')})
    assert response.status_code==422


def test_poster_keeps_aspect_crops_center_and_strips_exif():
    from PIL import Image,ImageDraw
    from app.infrastructure.storage.objects import normalize_poster
    image=Image.new('RGB',(400,400),'green');d=ImageDraw.Draw(image)
    d.rectangle((0,0,399,79),fill='red');d.rectangle((0,320,399,399),fill='blue')
    source=BytesIO();image.save(source,'PNG')
    normalized=Image.open(BytesIO(normalize_poster(source.getvalue())))
    assert normalized.size==(1280,720)
    for xy in [(0,0),(640,360),(1279,719)]:
        r,g,b=normalized.getpixel(xy);assert g>100 and r<20 and b<20
    source=BytesIO();exif=Image.Exif();exif[274]=6;image.save(source,'JPEG',exif=exif)
    normalized=Image.open(BytesIO(normalize_poster(source.getvalue())))
    assert normalized.size==(1280,720) and not normalized.getexif()
