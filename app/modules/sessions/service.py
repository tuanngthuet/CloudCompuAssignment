"""Shared sessions application operations."""

def lab_dict(r,db=None):
    from app.modules.checkin.policy import deadline,effective
    value={k:getattr(r,k) for k in ('id','room_id','open_at','close_at','start_at','end_at','event_id','checkin_enabled')}
    if db is not None:value['checkin_enabled']=effective(db,r)
    return value|{'checkin_close_mode':r.checkin_close_mode,'checkin_closes_at':deadline(r)}
