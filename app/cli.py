import argparse
import getpass
import os
from datetime import timedelta
from sqlalchemy import select
from app.infrastructure.database.session import Session
from .models import User, Room, Seat, LabSession, SessionSeat, Event
from app.modules.auth.service import hasher
from app.modules.booking.service import now
from .layouts import initialize

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['seed','create-user','queue-settings','queue-recover'])
    parser.add_argument('--username')
    parser.add_argument('--role',choices=['student','admin'],default='student')
    parser.add_argument('--students',type=int,default=100)
    flags=parser.add_mutually_exclusive_group()
    for flag in ['enable','disable','begin','finish']:
        flags.add_argument('--'+flag,action='store_true')
    parser.add_argument('--actor')
    parser.add_argument('--reason')
    for field in ['capacity','selection-seconds','heartbeat-seconds','waiting-grace-seconds']:
        parser.add_argument('--'+field,type=int)
    args=parser.parse_args()
    if args.command.startswith('queue-'):
        if (args.command=='queue-settings' and (args.begin or args.finish)) or (args.command=='queue-recover' and (args.enable or args.disable)):
            parser.error('Operation flag does not match command')
        from .queue_admin import run
        run(args,parser)
        return
    if args.command=='seed' and os.getenv('APP_ENV','local') not in ('local','test'):
        parser.error('Seed is restricted to local/test')
    password=os.getenv('SEED_PASSWORD') or getpass.getpass('Password (not recorded): ')
    if not password.strip():
        parser.error('Password must not be empty')
    with Session.begin() as db:
        if args.command=='create-user':
            if not args.username:
                parser.error('--username required')
            db.add(User(username=args.username,role=args.role,password_hash=hasher.hash(password)))
            return
        encoded=hasher.hash(password)
        for name,role in [('admin','admin')]+[(f'student{i:03}','student') for i in range(1,args.students+1)]:
            if db.scalar(select(User.id).where(User.username==name)) is None:
                db.add(User(username=name,role=role,password_hash=encoded))
        room=db.scalar(select(Room).where(Room.name=='Phòng máy demo'))
        if room is None:
            room=Room(name='Phòng máy demo'); db.add(room); db.flush()
            initialize(db,room)
            seats=list(db.scalars(select(Seat).where(Seat.room_id==room.id)))
            clock=now(db)
            # Registration and check-in windows overlap for the first demonstration session.
            for days in (0,1):
                start=clock+timedelta(days=days,minutes=10)
                event=Event(name=f'Ca thực hành mẫu {days+1}',venue='Phòng máy',session_type='practice')
                db.add(event);db.flush()
                lab=LabSession(event_id=event.id,room_id=room.id,open_at=start-timedelta(hours=1),close_at=start-timedelta(minutes=1),start_at=start,end_at=start+timedelta(hours=2))
                db.add(lab); db.flush()
                for seat in seats:
                    db.add(SessionSeat(session_id=lab.id,seat_id=seat.id))
    print('Completed. Existing accounts and sessions preserved.')

if __name__=='__main__':
    main()
