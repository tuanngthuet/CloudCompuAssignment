"""Coordinate publication and garbage collection with an object-row lock."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.models import StorageObject, User, Room, Event, RoomLayout
from app.modules.booking.service import require


def track(db, key, referenced=False):
    db.execute(
        insert(StorageObject).values(key=key, state="STAGED").on_conflict_do_nothing()
    )
    row = db.scalar(
        select(StorageObject)
        .where(StorageObject.key == key)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    require(
        row.state not in ("DELETING", "DELETED"),
        409,
        "image_expired",
        "Ảnh đã hết thời hạn. Tải ảnh lại.",
    )
    if referenced:
        row.state = "REFERENCED"
        row.quarantine_at = None
    return row


def referenced_keys(db):
    values = set()
    for model, column in [
        (User, User.avatar_key),
        (Room, Room.image_key),
        (Event, Event.poster_key),
    ]:
        values.update(
            key for key in db.scalars(select(column).where(column.is_not(None))) if key
        )
    values.update(
        row.layout["image_key"]
        for row in db.scalars(select(RoomLayout))
        if row.layout.get("image_key")
    )
    return values


def is_referenced(db, key):
    from sqlalchemy import or_

    checks = [
        select(User.id).where(User.avatar_key == key).exists(),
        select(Room.id).where(Room.image_key == key).exists(),
        select(Event.id).where(Event.poster_key == key).exists(),
        select(RoomLayout.room_id)
        .where(RoomLayout.layout["image_key"].astext == key)
        .exists(),
    ]
    return bool(db.scalar(select(or_(*checks))))
