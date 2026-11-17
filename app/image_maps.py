"""Closed quadrilateral rooms: shared-wall detection and validated editable polygons."""
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import quote
import uuid
import warnings
import cv2 as cv
import numpy as np
cv.setNumThreads(1)
from PIL import Image, ImageOps
from pydantic import Field
from sqlalchemy import select
from .errors import Problem
from .schemas import Input
from app.infrastructure.storage.objects import MAX_BYTES, storage
from typing import Literal

MAX_SIDE = 2048
MAX_RUNS = 100000


def decode_image(data):
    if len(data)>MAX_BYTES:raise Problem(422,'invalid_image','Ảnh sơ đồ tối đa 5 MB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in ('PNG','JPEG','WEBP') or max(source.size)>MAX_SIDE:raise ValueError()
                image=ImageOps.exif_transpose(source).convert('RGBA')
                base=Image.new('RGBA',image.size,'white');base.alpha_composite(image)
                return base.convert('RGB')
    except (OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise Problem(422,'invalid_image','Dùng PNG/JPEG/WebP tối đa 2048 px mỗi chiều') from None


def validate_quad(points,width,height):
    if len(set(map(tuple,points)))!=4 or any(not(0<=x<width and 0<=y<height) for x,y in points):
        raise Problem(422,'invalid_polygon','Phòng phải là tứ giác nằm trong ảnh')
    polygon=np.array(points,dtype=np.int32)
    if not cv.isContourConvex(polygon) or abs(cv.contourArea(polygon))<16:
        raise Problem(422,'invalid_polygon','Phòng phải là tứ giác lồi, không tự cắt và đủ lớn')
    return polygon


def region_geometry(identifier,points,width,height):
    polygon=validate_quad(points,width,height)
    x,y,w,h=cv.boundingRect(polygon)
    mask=np.zeros((h,w),np.uint8);cv.fillConvexPoly(mask,polygon-np.array([x,y]),1)
    runs=[]
    for row in range(h):
        hit=np.flatnonzero(mask[row])
        if len(hit):runs.append([y+row,x+int(hit[0]),x+int(hit[-1])+1])
    return dict(id=identifier,points=polygon.tolist(),runs=runs,x=x,y=y,width=w,height=h,area=int(mask.sum()))


def detect(data,min_area=400):
    image=decode_image(data);pixels=np.array(image);height,width=pixels.shape[:2]
    # Edges are found independently in all RGB channels: no prescribed background
    # or foreground color. Closed faces sharing a wall remain separate contours.
    edges=np.zeros((height,width),np.uint8)
    for channel in range(3):edges|=cv.Canny(pixels[:,:,channel],35,100)
    edge_support=cv.dilate(edges,np.ones((5,5),np.uint8))
    edges=cv.morphologyEx(edges,cv.MORPH_CLOSE,np.ones((3,3),np.uint8))
    contours,_=cv.findContours(edges,cv.RETR_TREE,cv.CHAIN_APPROX_SIMPLE)
    gray=cv.cvtColor(pixels,cv.COLOR_RGB2GRAY)
    ink=cv.adaptiveThreshold(gray,255,cv.ADAPTIVE_THRESH_MEAN_C,cv.THRESH_BINARY_INV,31,7)
    ink_contours,_=cv.findContours(ink,cv.RETR_TREE,cv.CHAIN_APPROX_SIMPLE)
    contours=list(contours)+list(ink_contours)
    if len(contours)>20000:raise Problem(422,'complex_image','Sơ đồ quá nhiều chi tiết; hãy giảm chi tiết hoặc kích thước ảnh')
    candidates=[]
    for contour in contours:
        if abs(cv.contourArea(contour))<min_area:continue
        polygon=cv.approxPolyDP(contour,.02*cv.arcLength(contour,True),True)
        if len(polygon)!=4 or not cv.isContourConvex(polygon):continue
        polygon=polygon.reshape(4,2)
        if min(float(np.linalg.norm(polygon[i]-polygon[(i+1)%4])) for i in range(4))<6:continue
        supported=True
        for i in range(4):
            samples=np.rint(polygon[i]+np.linspace(.1,.9,20)[:,None]*(polygon[(i+1)%4]-polygon[i])).astype(int)
            if np.mean(edge_support[samples[:,1],samples[:,0]]>0)<.6:supported=False;break
        if supported:candidates.append((abs(cv.contourArea(polygon)),polygon))
    if len(candidates)>5000:raise Problem(422,'too_many_regions','Sơ đồ quá nhiều tứ giác; tăng diện tích tối thiểu')
    kept=[]
    for area,polygon in sorted(candidates,key=lambda item:item[0]):
        duplicate_or_parent=False
        for small_area,small in kept:
            overlap,_=cv.intersectConvexConvex(polygon.astype(np.float32),small.astype(np.float32))
            contains=overlap/max(1,small_area)>.97
            duplicate=overlap/max(1,small_area)>.98 and area/max(1,small_area)<1.15
            if contains or duplicate:duplicate_or_parent=True;break
        if not duplicate_or_parent:kept.append((area,polygon))
    if len(kept)>500:raise Problem(422,'too_many_regions','Tối đa 500 phòng; tăng diện tích tối thiểu')
    kept.sort(key=lambda item:(int(item[1][:,1].min()),int(item[1][:,0].min())))
    regions=[region_geometry(f'r{i+1}',p.tolist(),width,height) for i,(_,p) in enumerate(kept)]
    if sum(len(r['runs']) for r in regions)>MAX_RUNS:raise Problem(422,'complex_image','Sơ đồ có quá nhiều vùng; giảm chi tiết ảnh')
    output=BytesIO();image.save(output,format='PNG')
    return dict(width=width,height=height,detector='quadrilateral-v1',regions=regions),output.getvalue()


class RegionInput(Input):
    id: str = Field(min_length=1,max_length=40)
    kind: Literal['zone'] = 'zone'
    label: str = Field(min_length=1,max_length=30)
    capacity: int = Field(ge=1,le=100000)
    points: list[tuple[int,int]] = Field(min_length=4,max_length=4)


class ImageMapInput(Input):
    revision: int = Field(ge=0)
    image_key: str = Field(max_length=300)
    min_area: int = Field(default=400,ge=16,le=10000)
    regions: list[RegionInput] = Field(min_length=1,max_length=500)


def valid_key(room_id,key):
    return key.startswith(f'rooms/{room_id}/maps/') and '..' not in key and PurePosixPath(key).suffix=='.png' and len(PurePosixPath(key).parts)==4


def upload(db,room_id,data,min_area=400):
    from .models import Room, RoomLayout
    from . import layouts
    room=db.scalar(select(Room).where(Room.id==room_id).with_for_update())
    if room is None:raise Problem(404,'not_found','Không có địa điểm')
    layouts.guard(db,room_id)
    result,png=detect(data,min_area)
    key=f'rooms/{room_id}/maps/{uuid.uuid4()}.png'
    try:storage().put(key,png,content_type='image/png')
    except Exception:raise Problem(503,'storage_unavailable','Chưa lưu được ảnh sơ đồ') from None
    from app.infrastructure.storage.registry import track
    track(db,key)
    row=db.get(RoomLayout,room_id)
    return result|dict(image_key=key,image_url=f'/rooms/{room_id}/seat-map/image?key={quote(key)}',revision=row.revision if row else 0,min_area=min_area)


def save(db,room_id,data):
    from .models import Room, RoomLayout, Seat, SessionSeat, LabSession
    from . import layouts
    room=db.scalar(select(Room).where(Room.id==room_id).with_for_update())
    if room is None:raise Problem(404,'not_found','Không có địa điểm')
    layouts.guard(db,room_id)
    row=db.get(RoomLayout,room_id)
    if data.revision!=(row.revision if row else 0):raise Problem(409,'layout_conflict','Sơ đồ đã đổi, hãy tải lại')
    if not valid_key(room_id,data.image_key):raise Problem(422,'invalid_image','Ảnh không thuộc địa điểm này')
    from app.infrastructure.storage.registry import track
    track(db,data.image_key,True)
    try:blob=storage().get(data.image_key)
    except Exception:raise Problem(503,'storage_unavailable','Không đọc được ảnh sơ đồ') from None
    image=decode_image(blob);width,height=image.size
    configs={r.id:r for r in data.regions}
    if len(configs)!=len(data.regions):raise Problem(422,'invalid_layout','Mã phòng bị trùng')
    labels=[r.label for r in data.regions]
    if len(set(labels))!=len(labels):raise Problem(422,'invalid_layout','Tên phòng không được trùng')
    polygons=[validate_quad(r.points,width,height) for r in data.regions]
    for i,polygon in enumerate(polygons):
        for other in polygons[:i]:
            overlap,_=cv.intersectConvexConvex(polygon.astype(np.float32),other.astype(np.float32))
            if overlap>.5:raise Problem(422,'overlapping_rooms','Các phòng không được chồng lên nhau')
    regions=[];total_runs=0
    for r in data.regions:
        region=region_geometry(r.id,r.points,width,height);total_runs+=len(region['runs'])
        if total_runs>MAX_RUNS:raise Problem(422,'complex_image','Sơ đồ có quá nhiều vùng')
        regions.append(region)
    current={str(s.id):s for s in db.scalars(select(Seat).where(Seat.room_id==room_id))}
    old={r['id']:r for r in row.layout.get('elements',[])} if row and row.layout.get('image_key')==data.image_key else {}
    keep={old[r.id].get('seat_id') for r in data.regions if r.id in old}
    for sid,seat in current.items():
        if sid not in keep:
            for ss in db.scalars(select(SessionSeat).where(SessionSeat.seat_id==seat.id)):db.delete(ss)
            db.flush();db.delete(seat)
        else:seat.seat_code='~'+uuid.uuid4().hex[:29]
    db.flush()
    labs=list(db.scalars(select(LabSession).where(LabSession.room_id==room_id)))
    elements=[]
    for region in regions:
        config=configs[region['id']];item=region|dict(kind='zone',label=config.label)
        seat=current.get(old.get(config.id,{}).get('seat_id'))
        if seat is None:
            seat=Seat(room_id=room_id,seat_code=config.label);db.add(seat);db.flush()
            for lab in labs:db.add(SessionSeat(session_id=lab.id,seat_id=seat.id))
        seat.seat_code=config.label;seat.capacity=config.capacity
        item.update(seat_id=str(seat.id),capacity=seat.capacity)
        elements.append(item)
    if row is None:row=RoomLayout(room_id=room_id,revision=0,layout={});db.add(row)
    row.layout=dict(type='image',detector='quadrilateral-v1',columns=width,rows=height,image_key=data.image_key,min_area=data.min_area,elements=elements)
    row.revision+=1;db.flush()
    return layouts.read(db,room_id)
