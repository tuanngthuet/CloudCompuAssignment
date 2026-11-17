"""Closed minimal quadrilateral faces, independent of background/fill color."""
from io import BytesIO
import pytest
from PIL import Image,ImageDraw
from app.image_maps import detect,RegionInput,region_geometry
from app.errors import Problem


def encoded(image):
    out=BytesIO();image.save(out,'PNG');return out.getvalue()


def floorplan():
    image=Image.new('RGB',(600,360),'#eef1f4');d=ImageDraw.Draw(image)
    d.rectangle((20,20,320,180),outline='black',width=4);d.line((170,20,170,180),fill='black',width=4)
    d.text((50,60),'ROOM A',fill='blue');d.text((200,60),'ROOM B',fill='black')
    d.polygon([(370,30),(510,60),(480,190),(340,160)],outline='#364f73',width=4)
    return image


def test_shared_wall_smallest_faces_and_parallelogram_with_text():
    result,png=detect(encoded(floorplan()))
    assert len(result['regions'])==3
    assert result['detector']=='quadrilateral-v1'
    assert all(len(r['points'])==4 for r in result['regions'])
    assert max(r['area'] for r in result['regions'])<25000
    assert detect(png)[0]==result
    assert Image.open(BytesIO(png)).getpixel((0,0))==(238,241,244)


def test_nested_frames_keep_only_smallest_room():
    image=Image.new('RGB',(500,300),'white');d=ImageDraw.Draw(image)
    for box in [(10,10,490,290),(30,30,450,250),(60,60,180,170)]:d.rectangle(box,outline='black',width=4)
    result,_=detect(encoded(image));assert len(result['regions'])==1
    assert result['regions'][0]['area']<15000


@pytest.mark.parametrize('background',['white','#e7f2f9','#808080'])
def test_background_colors_and_touching_filled_rooms(background):
    image=Image.new('RGB',(400,240),background);d=ImageDraw.Draw(image)
    d.rectangle((20,20,170,180),fill='red');d.rectangle((171,20,320,180),fill='blue')
    result,_=detect(encoded(image));assert len(result['regions'])==2


def test_open_shapes_circles_and_triangles_are_not_rooms():
    image=Image.new('RGB',(500,300),'white');d=ImageDraw.Draw(image)
    d.line([(20,20),(130,20),(130,150),(20,150)],fill='black',width=4)
    d.ellipse((180,20,300,150),outline='black',width=4)
    d.polygon([(350,20),(450,150),(320,150)],outline='black',width=4)
    result,_=detect(encoded(image));assert result['regions']==[]
    assert detect(encoded(Image.new('RGB',(100,100),'white')))[0]['regions']==[]


def test_noise_threshold_and_geometry():
    image=Image.new('RGB',(250,180),'white');d=ImageDraw.Draw(image)
    d.rectangle((20,20,40,40),outline='black',width=2);d.rectangle((80,20,210,150),outline='black',width=3)
    assert len(detect(encoded(image),min_area=500)[0]['regions'])==1
    assert len(detect(encoded(image),min_area=100)[0]['regions'])==2
    region=region_geometry('m1',[(10,10),(60,10),(70,60),(20,60)],100,100)
    assert region['runs'] and len(region['points'])==4


@pytest.mark.parametrize('blob',[b'bad',b'<svg/>',b'x'*(5*1024*1024+1),encoded(Image.new('RGB',(2049,20),'white'))])
def test_bad_image(blob):
    with pytest.raises(Problem):detect(blob)


@pytest.mark.parametrize('points',[[(-1,0),(30,0),(30,30),(0,30)],[(0,0),(30,30),(30,0),(0,30)],[(0,0),(30,0),(30,0),(0,30)]])
def test_bad_manual_quadrilateral(points):
    with pytest.raises(Problem):region_geometry('m1',points,100,100)


def test_only_rooms_capacity_explicit_and_four_points():
    from pydantic import ValidationError
    data={'id':'r1','label':'Phòng A','points':[(0,0),(50,0),(50,50),(0,50)]}
    with pytest.raises(ValidationError):RegionInput(**data)
    with pytest.raises(ValidationError):RegionInput(**data,kind='seat',capacity=1)
    assert RegionInput(**data,capacity=50).kind=='zone'


def test_s3_preserves_lossless_png_content_type():
    from app.infrastructure.storage.objects import S3Storage
    class Client:
        def put_object(self,**kw):self.object=kw
    client=Client();body=encoded(Image.new('RGB',(4,4),'white'))
    S3Storage(client,'test','prefix').put('rooms/room/maps/map.png',body,content_type='image/png')
    assert client.object['ContentType']=='image/png' and client.object['Body']==body
