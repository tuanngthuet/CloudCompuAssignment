"""Shared tickets application operations."""

def ticket(r):
    return {k:getattr(r,k) for k in ('session_id','seat_id','status','ticket_code','hold_expires_at','checked_in_at')} | {'reservation_id':r.id}


