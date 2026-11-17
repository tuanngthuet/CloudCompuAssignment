from types import SimpleNamespace
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.map_geometry import default_seats, fallback, validate
from app.schemas import MapInput
from app.errors import Problem

def element(**kwargs):
    return dict(id=str(uuid4()),kind='seat',seat_code='A01',x=0,y=0,width=1,height=1)|kwargs

def model(elements,**kwargs):
    return MapInput(**(dict(revision=0,columns=8,rows=12,elements=elements)|kwargs))

def test_default_60_positions():
    seats=[SimpleNamespace(id=uuid4(),seat_code=code) for code in default_seats()]
    layout=fallback(seats);validate(model(layout['elements']))
    items=[e for e in layout['elements'] if e['kind']=='seat']
    assert len(items)==60 and len({e['seat_code'] for e in items})==60
    assert {e['y'] for e in items}==set(range(2,12))
    assert {e['x'] for e in items}=={0,1,3,4,6,7}
    assert {e['seat_id'] for e in items}=={str(s.id) for s in seats}

@pytest.mark.parametrize('items',[
    [element(),element(seat_code='A02')],
    [element(x=8)],
    [element(width=2)],
    [element(seat_code='')],
    [element(),element(x=1)],
    [element(kind='label',seat_id=str(uuid4()))],
])
def test_invalid_layout(items):
    with pytest.raises(Problem):validate(model(items))

def test_duplicate_element_or_seat_identity():
    e=element()
    with pytest.raises(Problem):validate(model([e,e|{'x':2,'seat_code':'A02'}]))
    sid=str(uuid4())
    with pytest.raises(Problem):validate(model([element(seat_id=sid),element(x=2,seat_code='A02',seat_id=sid)]))

def test_valid_room_objects_and_seats():
    validate(model([element(),element(kind='board',seat_code='',x=1,width=5,label='Bảng'),element(kind='door',seat_code='',y=2),element(kind='label',seat_code='',y=3,label='Lối đi')]))

@pytest.mark.parametrize('kwargs',[{'columns':41},{'rows':0},{'revision':-1},{'elements':[element(x=-1)]},{'elements':[element(kind='unknown')]}])
def test_schema_limits(kwargs):
    with pytest.raises(ValidationError):MapInput(**(dict(revision=0,columns=8,rows=12,elements=[])|kwargs))

def test_extra_seats_are_not_lost():
    seats=[SimpleNamespace(id=uuid4(),seat_code='room-'+str(i)) for i in range(20)]
    layout=fallback(seats);validate(MapInput(revision=0,**layout))
    assert len([e for e in layout['elements'] if e['kind']=='seat'])==20
