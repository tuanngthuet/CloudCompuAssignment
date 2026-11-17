import uuid
from .errors import Problem

def fail(message,status=422):
    raise Problem(status,"invalid_layout",message)

def default_seats():
    return [f'{row}{col:02}' for row in 'ABCDEFGHIJ' for col in range(1,7)]

def fallback(seats):
    elements=[{'id':str(uuid.uuid5(uuid.NAMESPACE_URL,'board')), 'kind':'board','x':1,'y':0,'width':6,'height':1,'label':'BẢNG / MÀN HÌNH'}]
    codes=default_seats()
    extras=0
    for seat in seats:
        if seat.seat_code in codes:
            i=codes.index(seat.seat_code);x=[0,1,3,4,6,7][i%6];y=i//6+2
        else:
            x=extras%8;y=12+extras//8;extras+=1
        elements.append({'id':str(seat.id),'kind':'seat','seat_id':str(seat.id),'seat_code':seat.seat_code,'x':x,'y':y,'width':1,'height':1,'label':''})
    return {'columns':8,'rows':max(12,12+(extras+7)//8),'elements':elements}

def validate(data):
    cols,rows=data.columns,data.rows
    occupied=set();ids=set();codes=set();seats=set()
    for e in data.elements:
        if e.id in ids:fail('ID phần tử trùng')
        ids.add(e.id)
        if e.kind=='seat':
            if not e.seat_code or e.seat_code in codes:fail('Mã ghế trống hoặc trùng')
            codes.add(e.seat_code)
            if e.width!=1 or e.height!=1:fail('Ghế phải chiếm một ô')
            if e.seat_id:
                if e.seat_id in seats:fail('Ghế xuất hiện nhiều lần')
                seats.add(e.seat_id)
        elif e.seat_id is not None:fail('Vật thể không được tham chiếu ghế')
        if e.x+e.width>cols or e.y+e.height>rows:fail('Phần tử ngoài biên')
        cells={(x,y) for x in range(e.x,e.x+e.width) for y in range(e.y,e.y+e.height)}
        if occupied & cells:fail('Các phần tử chồng lấn')
        occupied |= cells

