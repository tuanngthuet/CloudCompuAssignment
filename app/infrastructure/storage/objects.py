import os
from pathlib import Path
from io import BytesIO
import uuid
import warnings
import tempfile
from PIL import Image, ImageOps, UnidentifiedImageError
from app.errors import Problem

MAX_BYTES = 5 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 20_000_000

def normalize(data):
    if len(data) > MAX_BYTES:
        raise Problem(422, 'invalid_image', 'Ảnh tối đa 5 MB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            im = Image.open(BytesIO(data))
        with im:
            if im.format not in ('JPEG','PNG','WEBP'):
                raise ValueError()
            im.load()
            out = BytesIO()
            im.convert('RGB').save(out, 'JPEG', quality=90)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise Problem(422, 'invalid_image', 'Nội dung ảnh không hợp lệ') from None

def normalize_poster(data):
    # Validate first, then preserve orientation/aspect ratio and crop centrally.
    normalize(data)
    with Image.open(BytesIO(data)) as source:
        image=ImageOps.exif_transpose(source).convert('RGBA')
        background=Image.new('RGB',image.size,'white')
        background.paste(image,mask=image.getchannel('A'))
        image=ImageOps.fit(background,(1280,720),method=Image.Resampling.LANCZOS)
        out=BytesIO();image.save(out,'JPEG',quality=90)
        return out.getvalue()


def normalize_avatar(data):
    normalize(data)
    with Image.open(BytesIO(data)) as source:
        image=ImageOps.exif_transpose(source).convert('RGBA')
        background=Image.new('RGB',image.size,'white')
        background.paste(image,mask=image.getchannel('A'))
        image=ImageOps.fit(background,(256,256),method=Image.Resampling.LANCZOS)
        out=BytesIO();image.save(out,'JPEG',quality=90)
        return out.getvalue()


def new_key():
    return f'rooms/{uuid.uuid4()}.jpg'

class LocalStorage:
    def __init__(self, root=None):
        self.root = Path(root or os.getenv('LOCAL_STORAGE_PATH', './.local/images')).resolve()
    def path(self, key):
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root) or not key.startswith(('rooms/', 'events/', 'users/')):
            raise ValueError('Invalid storage key')
        return path
    def put(self, key, data, content_type='image/jpeg'):
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.upload-', delete=False) as handle:
                temp = Path(handle.name)
                handle.write(data)
            temp.replace(path)
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
    def get(self, key):
        return self.path(key).read_bytes()
    def delete(self, key):
        self.path(key).unlink(missing_ok=True)

class S3Storage:
    def __init__(self, client, bucket, prefix=''):
        self.client, self.bucket, self.prefix = client, bucket, prefix.strip('/')
    def key(self, key):
        if not key.startswith(('rooms/', 'events/', 'users/')) or '..' in key:
            raise ValueError('Invalid storage key')
        return '/'.join(filter(None, (self.prefix,key)))
    def put(self, key, data, content_type='image/jpeg'):
        self.client.put_object(Bucket=self.bucket, Key=self.key(key), Body=data, ContentType=content_type)
    def get(self, key):
        body = self.client.get_object(Bucket=self.bucket, Key=self.key(key))['Body']
        try:
            return body.read()
        finally:
            body.close()
    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=self.key(key))

def storage():
    backend = os.getenv('STORAGE_BACKEND','local')
    if backend == 'local':
        return LocalStorage()
    if backend != 's3':
        raise ValueError('Unknown storage backend')
    import boto3
    return S3Storage(boto3.client('s3', region_name=os.getenv('AWS_REGION','us-east-1')), os.environ['S3_BUCKET'], os.getenv('S3_PREFIX',''))
