from datetime import datetime, timezone, timedelta
from io import BytesIO
import pytest
from PIL import Image
from pydantic import ValidationError
from app.infrastructure.storage.objects import LocalStorage, S3Storage, normalize, MAX_BYTES
from app.errors import Problem
from app.schemas import LabInput, HoldInput, LoginInput

@pytest.mark.parametrize('fmt',['PNG','JPEG','WEBP'])
def test_image_normalization(fmt):
    data=BytesIO(); Image.new('RGB',(2,2),'red').save(data,fmt)
    result=normalize(data.getvalue())
    with Image.open(BytesIO(result)) as image:
        assert image.format=='JPEG' and image.size==(2,2)

@pytest.mark.parametrize('data',[b'not an image',b'x'*(MAX_BYTES+1),b'<svg/>'])
def test_reject_image(data):
    with pytest.raises(Problem) as exc:
        normalize(data)
    assert exc.value.status==422

def test_local_roundtrip_and_traversal(tmp_path):
    storage=LocalStorage(tmp_path)
    storage.put('rooms/test.jpg',b'content')
    assert storage.get('rooms/test.jpg')==b'content'
    with pytest.raises(ValueError):
        storage.put('rooms/../../outside',b'bad')
    storage.delete('rooms/test.jpg')
    with pytest.raises(FileNotFoundError):
        storage.get('rooms/test.jpg')

class FakeS3:
    def __init__(self):
        self.objects={}
    def put_object(self,**kwargs):
        assert kwargs['Bucket']=='MOCK_ONLY'
        assert kwargs['ContentType']=='image/jpeg'
        self.objects[kwargs['Key']]=kwargs['Body']
    def get_object(self,**kwargs):
        return {'Body':BytesIO(self.objects[kwargs['Key']])}
    def delete_object(self,**kwargs):
        del self.objects[kwargs['Key']]

def test_s3_stub_roundtrip():
    client=FakeS3(); storage=S3Storage(client,'MOCK_ONLY','lab')
    storage.put('rooms/test.jpg',b'content')
    assert list(client.objects)==['lab/rooms/test.jpg']
    assert storage.get('rooms/test.jpg')==b'content'
    storage.delete('rooms/test.jpg')
    assert not client.objects
    with pytest.raises(ValueError):
        storage.put('releases/app',b'bad')

def test_s3_failure_propagates():
    class Broken(FakeS3):
        def put_object(self,**kwargs):
            raise OSError('unavailable')
    with pytest.raises(OSError):
        S3Storage(Broken(),'MOCK_ONLY').put('rooms/test.jpg',b'a')

def test_aware_ordered_session():
    t=datetime.now(timezone.utc)
    good=dict(room_id='00000000-0000-0000-0000-000000000001',open_at=t,close_at=t+timedelta(minutes=1),start_at=t+timedelta(minutes=2),end_at=t+timedelta(minutes=3))
    assert LabInput(**good).start_at.tzinfo is not None
    with pytest.raises(ValidationError):
        LabInput(**(good|{'end_at':t}))
    with pytest.raises(ValidationError):
        LabInput(**(good|{'open_at':t.replace(tzinfo=None)}))

def test_invalid_ids_and_extra_input():
    with pytest.raises(ValidationError):
        HoldInput(session_id='invalid',seat_id='invalid')
    with pytest.raises(ValidationError):
        LoginInput(username='a',password='b',role='admin')

def test_gif_content_rejected_despite_image_container():
    image=BytesIO();Image.new('RGB',(2,2)).save(image,'GIF')
    with pytest.raises(Problem):
        normalize(image.getvalue())

def test_decompression_bomb_warning_becomes_validation_error(monkeypatch):
    image=BytesIO();Image.new('RGB',(3,2)).save(image,'PNG')
    monkeypatch.setattr(Image,'MAX_IMAGE_PIXELS',4)
    with pytest.raises(Problem) as exc:
        normalize(image.getvalue())
    assert exc.value.code=='invalid_image'

def test_corrupt_image_payload_is_rejected():
    image=BytesIO();Image.new('RGB',(20,20)).save(image,'JPEG')
    with pytest.raises(Problem):
        normalize(image.getvalue()[:30])

def test_local_atomic_replacement_with_concurrent_writers(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    storage=LocalStorage(tmp_path);key='rooms/shared.jpg'
    options=[bytes([n])*10000 for n in range(8)]
    storage.put(key,options[0])
    def write_read(i):
        storage.put(key,options[i%len(options)])
        assert storage.get(key) in options
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write_read,range(80)))
    assert not list((tmp_path/'rooms').glob('.upload-*'))

def test_local_symlink_cannot_escape_storage(tmp_path):
    root=tmp_path/'root';external=tmp_path/'external'
    (root/'rooms').mkdir(parents=True);external.mkdir()
    (root/'rooms'/'linked').symlink_to(external,target_is_directory=True)
    with pytest.raises(ValueError):
        LocalStorage(root).put('rooms/linked/image.jpg',b'bad')
    assert not list(external.iterdir())

def test_s3_stream_closed_even_when_read_fails():
    class Body:
        closed=False
        def read(self):raise OSError('stream interrupted')
        def close(self):self.closed=True
    body=Body()
    class Client:
        def get_object(self,**kwargs):return {'Body':body}
    with pytest.raises(OSError):
        S3Storage(Client(),'MOCK_ONLY').get('rooms/x.jpg')
    assert body.closed

def test_blank_names_and_out_of_order_session():
    from app.schemas import RoomInput,SeatInput
    for schema,field in [(RoomInput,'name'),(SeatInput,'seat_code')]:
        with pytest.raises(ValidationError):schema(**{field:'   '})
    with pytest.raises(ValidationError):
        LoginInput(username='a',password='x'*1025)

def test_password_whitespace_preserved():
    assert LoginInput(username='user',password=' spaced password ').password==' spaced password '
