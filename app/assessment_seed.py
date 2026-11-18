"""LABSEAT B1/B2 synthetic acceptance data. Commands plan by default."""

import argparse
from datetime import timedelta
from hashlib import sha256
import hmac
from io import BytesIO
import json
import os
from pathlib import Path
from random import Random
import re
import secrets
from unicodedata import normalize
from uuid import NAMESPACE_URL, uuid5

from fastapi import Response
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from sqlalchemy import delete, or_, select, text, update

from app import image_maps
from app.infrastructure.database.session import Session
from app.infrastructure.redis import admission
from app.infrastructure.storage.objects import normalize_poster, storage
from app.infrastructure.storage.registry import track
from app.models import (
    AdminAudit, AuditEvent, CheckinPolicyEvent, EmailJob, Event, LabSession,
    LoginSession, NotificationDelivery, OutboxEvent, PlatformEvent, Reservation,
    Room, RoomLayout, Seat, SessionSeat, StaffAssignment, User, WebhookInbox,
)
from app.modules.auth import service as auth
from app.modules.booking import service as booking


class Batch:
    def __init__(self, name):
        self.name = name
        self.prefix = f"b1-{name}"
        self.users = [(f"student{i:03}", "student") for i in range(1, 501)]
        self.users += [(f"admin{i:02}", "admin") for i in range(1, 3)]
        self.users += [(f"staff{i:02}", "staff") for i in range(1, 7)]
        family_names = ("Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Phan", "Vũ", "Đặng",
                        "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý", "Mai", "Trương")
        given_names = ("Anh Thư", "Bảo Ngọc", "Bích Trâm", "Diệu Linh", "Gia Hân",
                       "Hà My", "Hải Yến", "Hoài An", "Khánh Linh", "Kim Ngân",
                       "Mai Phương", "Minh Anh", "Ngọc Hân", "Ngọc Mai", "Phương Nhi",
                       "Quỳnh Chi", "Thanh Hà", "Thảo Vy", "Thu Trang", "Tú Anh",
                       "Anh Khoa", "Bảo Long", "Chí Kiên", "Đức Anh", "Đức Huy",
                       "Gia Bảo", "Hải Đăng", "Hoàng Nam", "Hữu Phúc", "Khánh Duy",
                       "Minh Đức", "Minh Quân", "Nhật Minh", "Quang Huy", "Quốc Bảo",
                       "Thành Đạt", "Thiên Ân", "Trung Kiên", "Tuấn Anh", "Việt Hoàng")
        names = [f"{family} {given}" for family in family_names for given in given_names]
        Random(self.id("vietnamese-names-v1").int).shuffle(names)
        people = [key for key, role in self.users if role in ("student", "staff")]
        self.display_names = dict(zip(people, names[:len(people)], strict=True))
        self.user_ids = [self.id(key) for key, _ in self.users]
        self.event_ids = [self.id(f"event-{i}") for i in range(12)]
        self.room_ids = [self.id(f"room-{i}") for i in range(6)]
        self.hsa_room_id = self.id("exam-01-hsa-room")
        self.tsa_room_id = self.id("exam-03-tsa-room")
        self.hsa05_room_id = self.id("exam-05-hsa-room")
        self.bio_room_id = self.id("practice-07-bio-room")
        self.elec_room_id = self.id("practice-09-elec-room")
        self.physics_room_id = self.id("practice-11-physics-room")
        self.lab_ids = [self.id(f"lab-{i}") for i in range(24)]

    def id(self, key):
        return uuid5(NAMESPACE_URL, f"labseat/assessment/v1/{self.name}/{key}")

    def username(self, key):
        return f"{self.prefix}-{key}"

    def manifest(self):
        return {
            "batch": self.name, "manifest_id": str(self.id("manifest")),
            "users": [{"username": self.username(key), "role": role, "id": str(uid)}
                      for (key, role), uid in zip(self.users, self.user_ids, strict=True)],
            "events": [str(uid) for uid in self.event_ids],
            "rooms": [str(uid) for uid in self.room_ids],
            "sessions": [str(uid) for uid in self.lab_ids],
            "load_session": str(self.lab_ids[22]),
            "ui_session": str(self.lab_ids[20]),
        }


PLAN_ROOMS = (
    ("416-C", 50, 213, 116, 301), ("417-C", 50, 303, 116, 391),
    ("213-C", 242, 213, 310, 301),
    ("412-C", 400, 164, 546, 215), ("411-C", 548, 164, 690, 215),
    ("310-C", 400, 235, 546, 286), ("309-C", 548, 235, 690, 286),
    ("111B-C", 400, 347, 471, 400), ("111A-C", 473, 347, 545, 400),
    ("109B-C", 547, 347, 617, 400), ("109A-C", 619, 347, 690, 400),
    ("113A-C", 400, 603, 480, 666), ("113B-C", 482, 603, 562, 666),
    ("115A-C", 564, 603, 644, 666), ("115B-C", 646, 603, 726, 666),
    ("307-C", 886, 228, 951, 298), ("306-C", 886, 300, 951, 380),
    ("305B-C", 886, 382, 951, 466), ("305A-C", 886, 468, 951, 564),
    ("304-C", 886, 566, 951, 628),
    ("409-C", 967, 164, 1045, 227), ("408-C", 967, 229, 1045, 299),
    ("406-C", 967, 337, 1045, 416), ("405-C", 967, 418, 1045, 564),
    ("404-C", 967, 566, 1045, 628),
)
PLAN_SELECTIONS = (
    (10, 9, 8, 7), (11, 12, 13, 14, 2, 19),
    (0, 1, 3, 4, 5, 6, 15, 16), (20, 21, 22, 23),
    (7, 8, 9, 10, 17, 18), (11, 12, 13, 14, 15, 16, 19, 24),
)


def floor_plan(index):
    """An original booking plan based on the topology of the SPT reference."""
    image = Image.new("RGB", (1096, 752), "#ffffff")
    draw = ImageDraw.Draw(image)
    ink, muted, red = "#122744", "#4e5760", "#9c271d"

    def label(position, value, size, fill=ink, anchor="lt"):
        font = ImageFont.load_default(size=size)
        # The Pillow font in the task image lacks Vietnamese glyphs. Render
        # uppercase Latin letters with the marks from their decomposed spelling.
        glyphs = []
        for char in value:
            base, *marks = normalize("NFD", char)
            glyphs.append(("D" if base == "Đ" else base, marks, base == "Đ"))
        plain = "".join(base for base, _, _ in glyphs)
        draw.text(position, plain, font=font, fill=fill, anchor=anchor)
        x, y = position
        if anchor == "mt":
            x -= font.getlength(plain) / 2
        thickness = max(1, round(size / 19))
        for i, (base, marks, crossed) in enumerate(glyphs):
            start = x + font.getlength(plain[:i])
            center = start + font.getlength(base) / 2
            distance = max(2, size / 9)
            top = y - distance
            if crossed:
                draw.line((start - 1, y + size * .37, start + distance * 2, y + size * .37),
                          fill=fill, width=thickness)
            for mark in marks:
                if mark == "\u031b":  # Horn on Ơ or Ư.
                    edge = start + font.getlength(base) - 2
                    draw.arc((edge - distance, y - distance, edge + distance, y + distance),
                             0, 95, fill=fill, width=thickness)
                elif mark == "\u0323":
                    bottom = y + font.getbbox(base, anchor="lt")[3] + thickness
                    draw.ellipse((center - thickness, bottom, center + thickness, bottom + thickness * 2),
                                 fill=fill)
                else:
                    paths = {
                        "\u0302": [(-1, 0), (0, -1), (1, 0)],
                        "\u0306": [(-1, -1), (-.5, -.35), (0, 0), (.5, -.35), (1, -1)],
                        "\u0301": [(-.5, 0), (.7, -1)],
                        "\u0300": [(-.7, -1), (.5, 0)],
                        "\u0303": [(-1, 0), (-.5, -.65), (.5, 0), (1, -.65)],
                        "\u0309": [(-.5, -.8), (.5, -.8), (.5, -.4), (0, 0)],
                    }
                    draw.line([(center + dx * distance, top + dy * distance)
                               for dx, dy in paths[mark]], fill=fill, width=thickness)
                    top -= distance

    label((48, 37), "LABSEAT", 34)
    label((49, 80), f"DEMO  /  {index + 1:02}", 18, red)
    label((600, 43), "SƠ ĐỒ PHÒNG", 40, anchor="mt")
    label((600, 94), f"NHÀ {chr(65 + index)}  /  CA KIỂM THỬ", 22, muted, "mt")
    draw.line((48, 131, 1047, 131), fill="#687787", width=2)
    columns = [
        (50, 116, 4), (128, 171, 3), (182, 225, 3), (242, 310, 2), (326, 369, 1),
        (760, 822, 1), (837, 870, 2), (886, 951, 3), (967, 1045, 4),
    ]
    for left, right, level in columns:
        draw.rectangle((left, 164, right, 628), fill="#e0e2e4", outline="#344353", width=2)
        for top in (212, 302, 392, 478, 565):
            draw.line((left, top, right, top), fill="#9fa7af", width=2)
        label(((left + right) // 2, 640), f"T{level}", 16, muted, "mt")
    draw.rectangle((400, 164, 727, 426), outline="#344353", width=2)
    draw.rectangle((400, 304, 690, 325), fill="#e0e2e4", outline="#344353", width=2)
    for top, level in ((179, 4), (248, 3), (307, 2), (365, 1)):
        label((708, top), f"T{level}", 15, muted, "mt")
    draw.rectangle((760, 252, 822, 408), fill="#ffffff", outline="#344353", width=2)
    label((791, 278), "107-C", 15, anchor="mt")
    label((791, 325), "BAN", 13, red, "mt")
    label((791, 344), "CHỈ ĐẠO", 13, red, "mt")

    selected = PLAN_SELECTIONS[index]
    for slot, (room, left, top, right, bottom) in enumerate(PLAN_ROOMS):
        active = slot in selected
        draw.rectangle((left, top, right, bottom), fill="#fff1ea" if active else "#e0e2e4",
                       outline=red if active else "#8d969f", width=2)
        if active:
            code = f"R{index + 1:02}-{selected.index(slot) + 1:02}"
            label((left + 5, top + 6), room, 13)
            label(((left + right) // 2, top + 25), code, 17, red, "mt")

    label((548, 462), f"{len(selected)} PHÒNG MỞ ĐĂNG KÝ", 19, red, "mt")
    label((548, 500), "45 SUẤT / PHÒNG", 15, muted, "mt")
    draw.line((50, 696, 680, 696), fill=ink, width=2)
    draw.line((799, 696, 1045, 696), fill=ink, width=2)
    draw.line((742, 675, 742, 626), fill=ink, width=3)
    draw.polygon([(735, 633), (742, 624), (749, 633)], fill=ink)
    label((742, 698), "CỔNG VÀO", 19, anchor="mt")

    regions = []
    for number, slot in enumerate(selected, 1):
        room, left, top, right, bottom = PLAN_ROOMS[slot]
        code = f"R{index + 1:02}-{number:02}"
        regions.append({
            "id": code, "label": f"{code} ({room})", "capacity": 45,
            "points": [[left, top], [right, top], [right, bottom], [left, bottom]],
        })
    result = BytesIO()
    image.save(result, "PNG")
    return result.getvalue(), regions


def password(master, username):
    return hmac.new(master.encode(), username.encode(), sha256).hexdigest()


def assert_owned(db, batch, *, cleanup=False):
    users = {row.id: row for row in db.scalars(select(User).where(User.id.in_(batch.user_ids)))}
    for (key, role), uid in zip(batch.users, batch.user_ids, strict=True):
        user = users.get(uid)
        if user and (user.username != batch.username(key) or (not cleanup and user.role != role)):
            raise RuntimeError("Seed user identity or role changed")
    for event in db.scalars(select(Event).where(Event.id.in_(batch.event_ids))):
        if not event.name.startswith(f"[{batch.prefix}] "):
            raise RuntimeError("Seed event identity changed")
    dedicated_rooms = [batch.hsa_room_id, batch.tsa_room_id, batch.hsa05_room_id, batch.bio_room_id, batch.elec_room_id, batch.physics_room_id]
    for room in db.scalars(select(Room).where(Room.id.in_(batch.room_ids + dedicated_rooms))):
        if not room.name.startswith(f"[{batch.prefix}] "):
            raise RuntimeError("Seed room identity changed")
    labs = {row.id: row for row in db.scalars(select(LabSession).where(LabSession.id.in_(batch.lab_ids)))}
    for index, uid in enumerate(batch.lab_ids):
        lab = labs.get(uid)
        expected_rooms = {batch.room_ids[index // 4]}
        if index // 2 in (0, 2, 4, 6, 8, 10):
            expected_rooms.add(dedicated_rooms[index // 4])
        if lab and (lab.event_id != batch.event_ids[index // 2] or lab.room_id not in expected_rooms):
            raise RuntimeError("Seed schedule identity changed")


def event_name(batch, index):
    return f"[{batch.prefix}] {'Exam' if index < 6 else 'Practice'} {index + 1:02}"


def room_name(batch, index):
    return f"[{batch.prefix}] Test building {index + 1:02}"


def add_users(db, batch, master, clock):
    existing = set(db.scalars(select(User.id).where(User.id.in_(batch.user_ids))))
    for (key, role), uid in zip(batch.users, batch.user_ids, strict=True):
        if uid in existing:
            continue
        username = batch.username(key)
        # Deterministic 12-digit synthetic identifier; database uniqueness checks collisions.
        cccd = f"99{uid.int % 10**10:010}"
        db.add(User(id=uid, username=username, role=role,
                    full_name=batch.display_names.get(key, f"Test {key}"),
                    password_hash=auth.hasher.hash(password(master, username)),
                    email=f"{username}@example.invalid", email_verified_at=clock, cccd=cccd))
    db.flush()


def add_catalogue(db, batch, clock):
    for index, uid in enumerate(batch.room_ids):
        if not db.get(Room, uid):
            db.add(Room(id=uid, name=room_name(batch, index)))
    db.flush()
    for index, uid in enumerate(batch.event_ids):
        if db.get(Event, uid):
            continue
        poster = f"events/{uid}/poster/{batch.id(f'poster-{index}')}.jpg"
        plan, _ = floor_plan(index // 2)
        storage().put(poster, normalize_poster(plan), content_type="image/jpeg")
        track(db, poster, True)
        cancelled = index == 9
        db.add(Event(id=uid, name=event_name(batch, index), venue=room_name(batch, index // 2),
                     description="Synthetic LABSEAT assessment fixture.",
                     session_type="exam" if index < 6 else "practice", poster_key=poster,
                     status="CANCELLED" if cancelled else "ACTIVE",
                     lifecycle_at=clock if cancelled else None,
                     lifecycle_actor=batch.user_ids[500] if cancelled else None,
                     cancelled_at=clock if cancelled else None,
                     cancelled_by=batch.user_ids[500] if cancelled else None,
                     cancellation_reason="Synthetic cancelled event" if cancelled else ""))
    db.flush()
    for index, uid in enumerate(batch.lab_ids):
        if db.get(LabSession, uid):
            continue
        # Registration windows overlap, but physical schedules sharing a room do not.
        start = clock + timedelta(days=5, hours=index * 3)
        opening, closing = clock - timedelta(hours=1), clock + timedelta(days=4)
        if index in (14, 15):
            opening = clock + timedelta(days=1)
        elif index in (16, 17):
            closing = clock - timedelta(minutes=10)
        elif index in (12, 13):
            start = clock - timedelta(days=2) + timedelta(hours=index * 3)
            opening, closing = start - timedelta(days=2), start - timedelta(hours=1)
        db.add(LabSession(id=uid, event_id=batch.event_ids[index // 2],
                          room_id=batch.room_ids[index // 4], open_at=opening, close_at=closing,
                          start_at=start, end_at=start + timedelta(hours=2),
                          checkin_enabled=index == 10))
    db.flush()
    for index, uid in enumerate(batch.room_ids):
        if db.get(RoomLayout, uid):
            continue
        image, regions = floor_plan(index)
        uploaded = image_maps.upload(db, uid, image)
        image_maps.save(db, uid, image_maps.ImageMapInput(
            revision=uploaded["revision"], image_key=uploaded["image_key"],
            min_area=uploaded["min_area"], regions=regions,
        ))
    for index, uid in enumerate(batch.user_ids[502:]):
        sid = batch.lab_ids[index * 2]
        if not db.get(StaffAssignment, (sid, uid)):
            db.add(StaffAssignment(session_id=sid, user_id=uid, assigned_by=batch.user_ids[500]))


def rename_people(db, batch):
    ids = [uid for (key, _), uid in zip(batch.users, batch.user_ids, strict=True)
           if key in batch.display_names]
    users = {row.id: row for row in db.scalars(
        select(User).where(User.id.in_(ids)).order_by(User.id).with_for_update())}
    if len(users) != len(ids):
        raise RuntimeError("Batch is missing student or staff accounts")
    for (key, role), uid in zip(batch.users, batch.user_ids, strict=True):
        if uid not in users:
            continue
        user = users[uid]
        if user.username != batch.username(key) or user.role != role or user.status == "ANONYMIZED":
            raise RuntimeError("Unexpected account identity, role or status in batch")
        user.full_name = batch.display_names[key]


def exam_map(map_bytes, *, boxes, labels, reference, prefix, accent):
    plan = image_maps.decode_image(map_bytes).convert("RGB")
    width, height = plan.size
    draw = ImageDraw.Draw(plan)
    elements = []
    for index, (box, label) in enumerate(zip(boxes, labels, strict=True), 1):
        left, top, right, bottom = [round(value * scale) for value, scale in
                                    zip(box, (width / reference[0], height / reference[1]) * 2, strict=True)]
        draw.rectangle((left, top, right, bottom), outline=accent, width=3)
        points = [[left, top], [right, top], [right, bottom], [left, bottom]]
        image_maps.validate_quad(points, width, height)
        elements.append(image_maps.region_geometry(f"{prefix}-{index}", points, width, height) |
                        {"kind": "zone", "label": label, "capacity": 45})
    map_output = BytesIO()
    plan.save(map_output, "PNG")
    return (width, height), elements, map_output.getvalue()


def exam_artwork(map_bytes, logo_bytes, *, boxes, labels, reference, prefix, accent,
                 poster_blue, poster_fill=False):
    size, elements, image = exam_map(
        map_bytes, boxes=boxes, labels=labels, reference=reference, prefix=prefix, accent=accent,
    )
    artwork = image_maps.decode_image(logo_bytes).convert("RGB")
    logo = ImageOps.contain(artwork, (690, 690) if poster_blue else (1080, 620))
    poster = Image.new("RGB", (1280, 720), "#0b1d4a" if poster_blue else "white")
    if poster_blue:
        backdrop = ImageOps.fit(artwork, (1280, 720)).filter(ImageFilter.GaussianBlur(48))
        poster = Image.blend(backdrop, poster, .65)
    poster.paste(logo, ((1280 - logo.width) // 2, (720 - logo.height) // 2))
    if poster_fill:
        poster = ImageOps.fit(artwork, (1280, 720), method=Image.Resampling.LANCZOS)
    poster_output = BytesIO()
    poster.save(poster_output, "JPEG", quality=92)
    return size, elements, image, poster_output.getvalue()


def hsa_artwork(map_bytes, logo_bytes):
    return exam_artwork(
        map_bytes, logo_bytes, reference=(2048, 1137), prefix="hsa", accent="#07854b",
        poster_blue=True,
        boxes=((1414, 165, 1488, 225), (1335, 165, 1410, 225),
               (1255, 165, 1330, 225), (1176, 165, 1250, 225)),
        labels=("P.002 (C.A301)", "P.003 (C.A302)", "P.004 (C.A303)", "P.005 (C.A304)"),
    )


def ielts_artwork(map_bytes, logo_bytes):
    return exam_artwork(
        map_bytes, logo_bytes, reference=(1080, 834), prefix="ielts", accent="#bf153b",
        poster_blue=False,
        boxes=((410, 445, 473, 484), (275, 445, 338, 484), (207, 445, 270, 484),
               (139, 445, 203, 484), (478, 185, 542, 224)),
        labels=("P.1 (A4.01)", "P.2 (A4.02)", "P.3 (A4.03)", "P.4 (A4.04)", "P.5 (B4.01)"),
    )


def tsa_artwork(map_bytes, logo_bytes):
    return exam_artwork(
        map_bytes, logo_bytes, reference=(1500, 947), prefix="tsa", accent="#9c192b",
        poster_blue=False,
        boxes=((1242, 349, 1357, 421), (1242, 271, 1357, 343), (1242, 193, 1357, 265),
               (1002, 37, 1116, 110), (882, 37, 996, 110), (761, 37, 876, 110),
               (761, 116, 876, 187), (882, 116, 996, 187), (1002, 116, 1116, 187),
               (1122, 193, 1236, 265), (1122, 271, 1236, 343), (1122, 349, 1236, 421)),
        labels=tuple(f"P.{index}" for index in range(36, 48)),
    )


def sat_artwork(map_bytes, logo_bytes, *, poster_fill=True):
    return exam_artwork(
        map_bytes, logo_bytes, reference=(1200, 760), prefix="sat", accent="#007caa",
        poster_blue=False, poster_fill=poster_fill,
        boxes=((211, 630, 421, 712), (428, 630, 637, 712), (644, 630, 745, 712),
               (752, 630, 853, 712), (988, 506, 1090, 583), (988, 153, 1090, 231),
               (859, 25, 937, 106), (752, 25, 853, 106), (644, 25, 745, 106),
               (428, 25, 637, 106), (211, 25, 421, 106)),
        labels=("71A+71B (A2-412)", "72A+72B (A2-411)", "73 (A2-410)", "74 (A2-409)",
                "75 (A2-407)", "76 (A2-406)", "77 (A2-405)", "78 (A2-404)",
                "79 (A2-403)", "80A+80B (A2-402)", "81A+81B (A2-401)"),
    )


def hsa05_artwork(map_bytes, logo_bytes):
    return exam_artwork(
        map_bytes, logo_bytes, reference=(2048, 1041), prefix="hsa05", accent="#087c47",
        poster_blue=False,
        boxes=((1640, 230, 1712, 286), (1477, 230, 1548, 286), (1395, 230, 1466, 286),
               (1313, 230, 1384, 286), (1231, 230, 1302, 286),
               (1722, 160, 1794, 217), (1640, 160, 1712, 217), (1558, 160, 1630, 217),
               (1477, 160, 1548, 217), (1395, 160, 1466, 217), (1313, 160, 1384, 217),
               (1231, 160, 1302, 217), (1149, 160, 1220, 217),
               (648, 578, 716, 629), (648, 640, 716, 691), (673, 781, 733, 830),
               (464, 781, 525, 830), (309, 640, 376, 691), (309, 578, 376, 629),
               (648, 718, 732, 769), (552, 718, 637, 769), (457, 718, 541, 769),
               (272, 718, 349, 769), (231, 640, 298, 691), (231, 578, 298, 629),
               (387, 578, 454, 629)),
        labels=tuple(f"P.{index:03} ({code})" for index, code in enumerate(
            ("A-202", "A-204", "A-205", "A-206", "A-207", "A-301", "A-302",
             "A-303", "A-304", "A-305", "A-306", "A-307", "A-308", "B-101",
             "B-102", "B-103", "B-106", "B-110", "B-111", "B-202", "B-203",
             "B-204", "B-206", "B-207", "B-208", "B-011"), 1)),
    )


def apply_isolated_exam(db, batch, artwork, *, exam_number, prefix, room_id, room_label):
    (width, height), elements, image, poster = artwork
    event_id = batch.event_ids[exam_number - 1]
    lab_start = (exam_number - 1) * 2
    original_index = (exam_number - 1) // 2
    original_room = batch.room_ids[original_index]
    exam = f"Exam {exam_number:02}"
    event = db.get(Event, event_id, with_for_update=True)
    expected_type = "exam" if exam_number <= 6 else "practice"
    if not event or event.session_type != expected_type:
        raise RuntimeError(f"Batch {exam} is missing or has an unexpected type")
    room = db.get(Room, room_id, with_for_update=True)
    labs = list(db.scalars(select(LabSession).where(
        LabSession.id.in_(batch.lab_ids[lab_start:lab_start + 2])).order_by(LabSession.id).with_for_update()))
    if len(labs) != 2 or any(lab.event_id != event_id for lab in labs):
        raise RuntimeError(f"{exam} schedules are incomplete")
    seat_prefix = f"exam-{exam_number:02}-{prefix}-seat"
    if room is None:
        if any(lab.room_id != original_room for lab in labs):
            raise RuntimeError(f"{exam} no longer uses its original shared room")
        old_seats = list(db.scalars(select(Seat).where(
            Seat.room_id == original_room).order_by(Seat.seat_code)))
        expected_seats = 4 + 2 * (original_index % 3)
        if (len(old_seats) != expected_seats or len(old_seats) > len(elements)
                or any(seat.capacity != 45 for seat in old_seats)):
            raise RuntimeError(f"{exam} room capacity changed")
        db.add(Room(id=room_id, name=f"[{batch.prefix}] {room_label}"))
        db.flush()
        for index, element in enumerate(elements, 1):
            seat_id = batch.id(f"{seat_prefix}-{index}")
            db.add(Seat(id=seat_id, room_id=room_id, seat_code=element["label"], capacity=45))
            db.flush()
            for lab in labs:
                db.add(SessionSeat(session_id=lab.id, seat_id=seat_id))
            db.flush()
            if index > len(old_seats):
                continue
            old = old_seats[index - 1]
            for lab in labs:
                db.execute(update(Reservation).where(Reservation.session_id == lab.id,
                           Reservation.seat_id == old.id).values(seat_id=seat_id))
                removed = db.execute(delete(SessionSeat).where(
                    SessionSeat.session_id == lab.id, SessionSeat.seat_id == old.id))
                if removed.rowcount != 1:
                    raise RuntimeError(f"{exam} has unexpected room links")
        for lab in labs:
            lab.room_id = room_id
    elif any(lab.room_id != room_id for lab in labs):
        raise RuntimeError(f"Dedicated room exists but {exam} is not assigned to it")

    for index, element in enumerate(elements, 1):
        seat = db.get(Seat, batch.id(f"{seat_prefix}-{index}"))
        if not seat or (seat.room_id, seat.capacity, seat.seat_code) != (room_id, 45, element["label"]):
            raise RuntimeError(f"Existing {exam} seat mapping changed")
        element["seat_id"] = str(seat.id)
    key = f"rooms/{room_id}/maps/{batch.id(prefix + '-map-' + sha256(image).hexdigest())}.png"
    poster_key = f"events/{event_id}/poster/{batch.id(prefix + '-poster-' + sha256(poster).hexdigest())}.jpg"
    row = db.get(RoomLayout, room_id, with_for_update=True)
    if not row or row.layout.get("image_key") != key:
        storage().put(key, image, content_type="image/png")
        track(db, key, True)
        layout = {"type": "image", "detector": "quadrilateral-v1", "columns": width,
                  "rows": height, "image_key": key, "min_area": 400, "elements": elements,
                  "assessment_artwork": prefix}
        if row:
            row.layout, row.revision = layout, row.revision + 1
        else:
            db.add(RoomLayout(room_id=room_id, revision=1, layout=layout))
    if event.poster_key != poster_key:
        storage().put(poster_key, poster, content_type="image/jpeg")
        track(db, poster_key, True)
        event.poster_key = poster_key


def apply_hsa(db, batch, map_bytes, logo_bytes):
    apply_isolated_exam(db, batch, hsa_artwork(map_bytes, logo_bytes), exam_number=1,
                        prefix="hsa", room_id=batch.hsa_room_id, room_label="HSA - Khu A")


def apply_tsa(db, batch, map_bytes, logo_bytes):
    apply_isolated_exam(db, batch, tsa_artwork(map_bytes, logo_bytes), exam_number=3,
                        prefix="tsa", room_id=batch.tsa_room_id, room_label="TSA - Sơ đồ phòng thi")


def apply_hsa05(db, batch, map_bytes, logo_bytes):
    apply_isolated_exam(db, batch, hsa05_artwork(map_bytes, logo_bytes), exam_number=5,
                        prefix="hsa05", room_id=batch.hsa05_room_id, room_label="HSA - Khu A và B")


def dong_da_exam_map(map_bytes):
    return exam_map(
        map_bytes, reference=(454, 305), prefix="hsa05", accent="#1767a4",
        boxes=((392, 208, 415, 229), (392, 184, 415, 204), (392, 160, 415, 180),
               (392, 112, 415, 132), (392, 88, 415, 108),
               (366, 88, 388, 108), (366, 112, 388, 132), (366, 160, 388, 180),
               (366, 184, 388, 204), (366, 208, 388, 229),
               (340, 208, 362, 229), (340, 184, 362, 204), (340, 160, 362, 180),
               (340, 112, 362, 132), (340, 88, 362, 108),
               (7, 184, 30, 204), (7, 160, 30, 180), (7, 136, 30, 155), (7, 112, 30, 131),
               (34, 112, 55, 131), (34, 136, 55, 155), (34, 160, 55, 180),
               (34, 184, 55, 204), (59, 184, 87, 204), (59, 160, 87, 180)),
        labels=tuple(f"P.{index:03}" for index in range(1, 26)),
    )


def house_a_exam_map(map_bytes):
    if len(map_bytes) > image_maps.MAX_BYTES:
        raise RuntimeError("The House A source image exceeds the upload limit")
    with Image.open(BytesIO(map_bytes)) as source:
        if source.width * source.height > 16_000_000:
            raise RuntimeError("The House A source image exceeds the pixel limit")
        resized = ImageOps.exif_transpose(source).convert("RGB")
    resized.thumbnail((image_maps.MAX_SIDE, image_maps.MAX_SIDE), Image.Resampling.LANCZOS)
    normalized = BytesIO()
    resized.save(normalized, "JPEG", quality=94)
    boxes = [(745, 2272, 812, 2368), (820, 2017, 888, 2114), (901, 2017, 970, 2114)]
    floor_two = ((745, 886), (902, 1120), (1132, 1350))
    boxes.extend((left, 1827, right, 1922) for left, right in floor_two)
    boxes.extend((left, 1574, right, 1669) for left, right in reversed(floor_two))
    columns = ((745, 886), (902, 1043), (1052, 1196), (1206, 1350))
    for upper, lower in ((1128, 1382), (689, 943), (254, 509)):
        boxes.extend((left, lower, right, lower + 95) for left, right in columns)
        boxes.extend((left, upper, right, upper + 95) for left, right in reversed(columns))
    room_codes = ("A101", "A106", "A105", "A201", "A202", "A203", "A204", "A205", "A206")
    room_codes += tuple(f"A{floor}{number:02}" for floor in (3, 4, 5) for number in range(1, 9))
    return exam_map(
        normalized.getvalue(), reference=(1813, 2560), prefix="hsa05", accent="#087c47",
        boxes=boxes, labels=tuple(f"P.{i:03} ({code})" for i, code in enumerate(room_codes, 1)),
    )


def apply_hsa05_map(db, batch, map_bytes, *, house_a=False):
    room_id, event_id = batch.hsa05_room_id, batch.event_ids[4]
    db.execute(select(Room.id).where(Room.id == room_id).with_for_update()).scalar_one()
    labs = list(db.scalars(select(LabSession).where(
        LabSession.room_id == room_id).order_by(LabSession.id).with_for_update()))
    if {lab.id for lab in labs} != set(batch.lab_ids[8:10]) or any(lab.event_id != event_id for lab in labs):
        raise RuntimeError("The dedicated room must serve exactly the two Exam 05 schedules")
    row = db.get(RoomLayout, room_id, with_for_update=True)
    if not row or row.layout.get("assessment_artwork") not in ("hsa05", "hsa05-dongda", "hsa05-house-a"):
        raise RuntimeError("Exam 05 has no supported image layout")
    variant = "hsa05-house-a" if house_a else "hsa05-dongda"
    make_map = house_a_exam_map if house_a else dong_da_exam_map
    (width, height), elements, image = make_map(map_bytes)
    key = f"rooms/{room_id}/maps/{batch.id(variant + '-map-' + sha256(image).hexdigest())}.png"
    if row.layout["image_key"] == key:
        return
    seats = {seat.id: seat for seat in db.scalars(select(Seat).where(
        Seat.room_id == room_id).with_for_update())}
    seat_ids = [batch.id(f"exam-05-hsa05-seat-{i}") for i in range(1, 34)]
    if (len(seats) not in (25, 26, 33) or set(seats) != set(seat_ids[:len(seats)])
            or any(seat.capacity != 45 for seat in seats.values())):
        raise RuntimeError("Exam 05 has unexpected registered seat identities or capacities")
    removed_ids = set(seats) - set(seat_ids[:len(elements)])
    if removed_ids:
        if db.scalar(select(Reservation.id).where(Reservation.seat_id.in_(removed_ids)).limit(1)):
            raise RuntimeError("A removed room has booking history and requires explicit reassignment")
        db.execute(delete(SessionSeat).where(SessionSeat.seat_id.in_(removed_ids)))
        for seat_id in removed_ids:
            db.delete(seats[seat_id])
    for seat_id, element in zip(seat_ids[:len(elements)], elements, strict=True):
        seat = seats.get(seat_id)
        if seat is None:
            seat = Seat(id=seat_id, room_id=room_id, seat_code=element["label"], capacity=45)
            db.add(seat)
            db.flush()
            db.add_all(SessionSeat(session_id=lab.id, seat_id=seat_id) for lab in labs)
        else:
            seat.seat_code = element["label"]
        element["seat_id"] = str(seat.id)
    storage().put(key, image, content_type="image/png")
    track(db, key, True)
    row.layout = row.layout | {"columns": width, "rows": height, "image_key": key,
                               "elements": elements, "assessment_artwork": variant}
    row.revision += 1


def apply_in_place_exam(db, batch, artwork, *, exam_number, prefix):
    index = exam_number - 1
    room_index = index // 2
    event_id, room_id = batch.event_ids[index], batch.room_ids[room_index]
    exam = f"Exam {exam_number:02}"
    event = db.get(Event, event_id, with_for_update=True)
    expected_type = "exam" if exam_number <= 6 else "practice"
    if not event or event.session_type != expected_type:
        raise RuntimeError(f"Batch {exam} is missing or has an unexpected type")
    db.execute(select(Room.id).where(Room.id == room_id).with_for_update()).scalar_one()
    labs = list(db.scalars(select(LabSession).where(
        LabSession.room_id == room_id).order_by(LabSession.id).with_for_update()))
    if {lab.id for lab in labs} != set(batch.lab_ids[index * 2:index * 2 + 2]) or any(lab.event_id != event_id for lab in labs):
        raise RuntimeError(f"{exam} must be the only event using its room")
    row = db.get(RoomLayout, room_id, with_for_update=True)
    if not row or row.layout.get("type") != "image":
        raise RuntimeError(f"{exam} has no image layout")
    (width, height), elements, image, poster = artwork
    seats = {str(seat.id): seat for seat in db.scalars(select(Seat).where(
        Seat.room_id == room_id).with_for_update())}
    current_artwork = row.layout.get("assessment_artwork")
    previous = list(row.layout["elements"])
    if {zone["seat_id"] for zone in previous} != set(seats) or any(seat.capacity != 45 for seat in seats.values()):
        raise RuntimeError(f"{exam} has unexpected seat identities or capacities")
    if current_artwork is None and len(previous) == 4 + 2 * (room_index % 3):
        previous.sort(key=lambda zone: zone["id"])
        for offset in range(len(previous), len(elements)):
            seat_id = batch.id(f"exam-{exam_number:02}-{prefix}-seat-{offset + 1}")
            added = Seat(id=seat_id, room_id=room_id, seat_code=elements[offset]["label"], capacity=45)
            db.add(added)
            db.flush()
            db.add_all(SessionSeat(session_id=lab.id, seat_id=seat_id) for lab in labs)
            seats[str(seat_id)] = added
            previous.append({"seat_id": str(seat_id)})
    elif current_artwork != prefix or [zone["id"] for zone in previous] != [zone["id"] for zone in elements]:
        raise RuntimeError(f"{exam} does not match the expected fixture layout")
    for old, zone in zip(previous, elements, strict=True):
        seat = seats[old["seat_id"]]
        seat.seat_code = zone["label"]
        zone["seat_id"] = str(seat.id)
    key = f"rooms/{room_id}/maps/{batch.id(prefix + '-map-' + sha256(image).hexdigest())}.png"
    poster_key = f"events/{event_id}/poster/{batch.id(prefix + '-poster-' + sha256(poster).hexdigest())}.jpg"
    if row.layout["image_key"] != key:
        storage().put(key, image, content_type="image/png")
        track(db, key, True)
        row.layout = row.layout | {"columns": width, "rows": height, "image_key": key,
                                   "elements": elements, "assessment_artwork": prefix}
        row.revision += 1
    if event.poster_key != poster_key:
        storage().put(poster_key, poster, content_type="image/jpeg")
        track(db, poster_key, True)
        event.poster_key = poster_key


def apply_ielts(db, batch, map_bytes, logo_bytes):
    apply_in_place_exam(db, batch, ielts_artwork(map_bytes, logo_bytes), exam_number=2, prefix="ielts")


def apply_sat(db, batch, map_bytes, logo_bytes):
    apply_in_place_exam(db, batch, sat_artwork(map_bytes, logo_bytes), exam_number=4, prefix="sat")


def apply_toeic(db, batch, map_bytes, logo_bytes):
    apply_in_place_exam(db, batch, sat_artwork(map_bytes, logo_bytes, poster_fill=False),
                        exam_number=6, prefix="toeic")


def bio_artwork(map_bytes, logo_bytes):
    return exam_artwork(
        map_bytes, logo_bytes, reference=(659, 405), prefix="bio", accent="#117d46",
        poster_blue=False,
        boxes=((272, 172, 616, 226), (41, 212, 105, 249),
               (109, 212, 180, 228), (109, 233, 180, 249)),
        labels=("Dãy K - Phòng thí nghiệm", "H204 - Phòng Hóa", "H104", "H104a"),
    )


def apply_bio(db, batch, map_bytes, logo_bytes):
    apply_isolated_exam(db, batch, bio_artwork(map_bytes, logo_bytes), exam_number=7,
                        prefix="bio", room_id=batch.bio_room_id, room_label="Thực hành Sinh hóa")


def elec_artwork(map_bytes, logo_bytes):
    return exam_artwork(
        map_bytes, logo_bytes, reference=(725, 466), prefix="elec", accent="#c77900",
        poster_blue=False,
        boxes=((114, 51, 198, 74), (204, 51, 273, 74), (278, 51, 358, 74),
               (455, 51, 527, 74), (532, 51, 613, 74),
               (114, 79, 198, 103), (204, 79, 273, 103), (278, 79, 358, 103),
               (455, 79, 527, 103),
               (616, 187, 690, 214), (616, 219, 690, 248), (616, 253, 690, 280),
               (616, 320, 690, 346), (616, 352, 690, 380),
               (525, 187, 610, 214), (525, 219, 610, 248), (525, 253, 610, 280),
               (525, 320, 610, 346)),
        labels=tuple(f"P.{i:02}" for i in range(1, 19)),
    )


def apply_elec(db, batch, map_bytes, logo_bytes):
    apply_isolated_exam(db, batch, elec_artwork(map_bytes, logo_bytes), exam_number=9,
                        prefix="elec", room_id=batch.elec_room_id, room_label="Thực hành Điện")


def chemistry_artwork(map_bytes, logo_bytes):
    rooms = {}
    # D4: three rooms on each of floors 2 through 5.
    for start, floor, top, bottom in ((60,2,604,671), (69,3,678,748),
                                       (78,4,755,824), (90,5,832,900)):
        for offset, (left, right) in enumerate(((223,420), (427,627), (633,842))):
            rooms[start + offset] = (f"{floor}0{3-offset}-D4", (left,top,right,bottom))
    # D1: floors 2 through 5 appear as vertical columns, bottom to top.
    rows = ((754,844), (657,746), (560,649), (464,552), (334,424), (237,326))
    for start, floor, left, right in ((63,2,1040,1134), (72,3,1142,1237),
                                      (81,4,1245,1339), (93,5,1347,1442)):
        for offset, (top, bottom) in enumerate(rows, 1):
            rooms[start + offset - 1] = (f"{floor}0{offset}-D1", (left,top,right,bottom))
    for start, floor, top, bottom in ((87,4,272,331), (99,5,201,264)):
        for offset, (left, right) in enumerate(((637,844), (437,630), (220,430))):
            rooms[start + offset] = (f"{floor}0{offset+1}-D2", (left,top,right,bottom))
    assert set(rooms) == set(range(60, 102))
    return exam_artwork(
        map_bytes, logo_bytes, reference=(1491,1055), prefix="chemistry", accent="#164b88",
        poster_blue=False, boxes=tuple(rooms[number][1] for number in range(60,102)),
        labels=tuple(f"HN{number:03} ({rooms[number][0]})" for number in range(60,102)),
    )


def apply_chemistry(db, batch, map_bytes, logo_bytes):
    apply_in_place_exam(db, batch, chemistry_artwork(map_bytes, logo_bytes),
                        exam_number=12, prefix="chemistry")


def physics_artwork(map_bytes, logo_bytes):
    codes = ("701", "702", "703", "704A", "704B", "705", "707", "803", "804", "805",
             "809", "810", "811", "901", "902", "904", "905", "906", "907", "908",
             "909", "910", "911", "1001", "1002", "1003", "1004", "1005", "1006",
             "1007A", "1007B", "1101", "1102", "1103")
    return exam_artwork(
        map_bytes, logo_bytes, reference=(1491, 1055), prefix="physics", accent="#174783",
        poster_blue=False,
        boxes=((802,875,973,918), (978,875,1142,918), (1149,875,1310,918),
               (1059,801,1310,844), (802,801,1053,844), (300,801,632,844), (97,875,632,918),
               (1129,707,1310,750), (1129,634,1310,677), (978,634,1122,677),
               (97,707,272,750), (278,707,443,750), (450,707,632,750),
               (802,541,973,584), (978,541,1122,584), (1129,467,1310,510),
               (978,467,1122,510), (802,467,973,510), (333,467,632,510), (97,467,326,510),
               (97,541,272,584), (278,541,443,584), (450,541,632,584),
               (807,374,1127,417), (1134,374,1310,417), (1028,301,1310,344),
               (802,301,1021,344), (333,301,632,344), (97,301,326,344),
               (97,374,255,417), (262,374,443,417), (802,208,1122,250),
               (1129,208,1310,250), (1129,134,1310,177)),
        labels=tuple(f"HN{number} ({code}-K1)" for number, code in zip(range(582, 616), codes, strict=True)),
    )


def apply_physics(db, batch, map_bytes, logo_bytes):
    apply_isolated_exam(db, batch, physics_artwork(map_bytes, logo_bytes), exam_number=11,
                        prefix="physics", room_id=batch.physics_room_id, room_label="Thực hành Vật lý")


def mechanic_artwork(map_bytes, logo_bytes):
    size, _, image, poster = exam_artwork(
        map_bytes, logo_bytes, reference=(1183, 1083), prefix="mechanic", accent="#008fc6",
        poster_blue=False, boxes=(), labels=(),
    )
    width, height = size
    plan = image_maps.decode_image(image).convert("RGB")
    draw, elements = ImageDraw.Draw(plan), []
    quads = (((290, 230), (409, 231), (380, 371), (267, 365)),
             ((267, 371), (377, 377), (351, 493), (244, 488)),
             ((244, 496), (350, 501), (322, 644), (214, 639)),
             ((214, 647), (321, 652), (292, 797), (184, 797)))
    for i, quad in enumerate(quads, 1):
        points = [[round(x * width / 1183), round(y * height / 1083)] for x, y in quad]
        image_maps.validate_quad(points, width, height)
        draw.line([tuple(point) for point in points] + [tuple(points[0])], fill="#008fc6", width=3)
        elements.append(image_maps.region_geometry(f"mechanic-{i}", points, width, height) |
                        {"kind": "zone", "label": f"P.{6224 + i} (F1.{6 + 2 * i:02})", "capacity": 17})
    output = BytesIO()
    plan.save(output, "PNG")
    return size, elements, output.getvalue(), poster


def apply_mechanic(db, batch, map_bytes, logo_bytes):
    room_id, event_id = batch.room_ids[4], batch.event_ids[9]
    event = db.get(Event, event_id, with_for_update=True)
    if not event or event.session_type != "practice":
        raise RuntimeError("Practice 10 is missing or has an unexpected type")
    db.execute(select(Room.id).where(Room.id == room_id).with_for_update()).scalar_one()
    labs = list(db.scalars(select(LabSession).where(
        LabSession.room_id == room_id).order_by(LabSession.id).with_for_update()))
    if {lab.id for lab in labs} != set(batch.lab_ids[18:20]) or any(lab.event_id != event_id for lab in labs):
        raise RuntimeError("Practice 10 must be the only event using its room")
    row = db.get(RoomLayout, room_id, with_for_update=True)
    if not row or row.layout.get("assessment_artwork") not in (None, "mechanic"):
        raise RuntimeError("Practice 10 has an unsupported map")
    seats = {str(seat.id): seat for seat in db.scalars(select(Seat).where(
        Seat.room_id == room_id).with_for_update())}
    previous = sorted(row.layout["elements"], key=lambda region: region["id"])
    old_capacity = 17 if row.layout.get("assessment_artwork") == "mechanic" else 45
    if (len(previous) != (4 if old_capacity == 17 else 6)
            or {zone["seat_id"] for zone in previous} != set(seats)
            or any(seat.capacity != old_capacity for seat in seats.values())):
        raise RuntimeError("Practice 10 seat identities or capacities changed")
    removed = [seats[zone["seat_id"]].id for zone in previous[4:]]
    if removed and db.scalar(select(Reservation.id).where(Reservation.seat_id.in_(removed)).limit(1)):
        raise RuntimeError("Removed regions have booking history and require explicit reassignment")
    retained = [seats[zone["seat_id"]].id for zone in previous[:4]]
    if db.scalar(select(Reservation.id).where(
            Reservation.seat_id.in_(retained), Reservation.status.in_(("HELD", "CONFIRMED", "CHECKED_IN")),
            Reservation.slot >= 17).limit(1)):
        raise RuntimeError("Existing bookings exceed the 17 places shown on the map")
    (width, height), elements, image, poster = mechanic_artwork(map_bytes, logo_bytes)
    for old, element in zip(previous[:4], elements, strict=True):
        seat = seats[old["seat_id"]]
        seat.seat_code, seat.capacity = element["label"], 17
        element["seat_id"] = str(seat.id)
    if removed:
        db.execute(delete(SessionSeat).where(SessionSeat.seat_id.in_(removed)))
        for seat in seats.values():
            if seat.id in removed:
                db.delete(seat)
    key = f"rooms/{room_id}/maps/{batch.id('mechanic-map-' + sha256(image).hexdigest())}.png"
    poster_key = f"events/{event_id}/poster/{batch.id('mechanic-poster-' + sha256(poster).hexdigest())}.jpg"
    if row.layout["image_key"] != key:
        storage().put(key, image, content_type="image/png")
        track(db, key, True)
        row.layout = row.layout | {"columns": width, "rows": height, "image_key": key,
                                   "elements": elements, "detector": "quadrilateral-v1", "assessment_artwork": "mechanic"}
        row.revision += 1
    if event.poster_key != poster_key:
        storage().put(poster_key, poster, content_type="image/jpeg")
        track(db, poster_key, True)
        event.poster_key = poster_key


def bio_tower_map(map_bytes):
    return exam_map(
        map_bytes, reference=(1084, 1451), prefix="bio", accent="#117d46",
        boxes=((101, 745, 485, 858), (700, 458, 900, 571),
               (492, 458, 695, 571), (302, 458, 486, 571),
               (101, 458, 297, 571), (101, 170, 486, 283)),
        labels=tuple(f"Phòng thi {i} (Tầng {floor:02})" for i, floor in
                     enumerate((9, 10, 10, 10, 10, 11), 1)),
    )


def apply_bio_map(db, batch, map_bytes):
    """Replace only Practice 07's map, preserving its poster and booking identities."""
    room_id, event_id = batch.bio_room_id, batch.event_ids[6]
    event = db.get(Event, event_id, with_for_update=True)
    if not event or event.session_type != "practice":
        raise RuntimeError("Practice 07 is missing or has an unexpected type")
    db.execute(select(Room.id).where(Room.id == room_id).with_for_update()).scalar_one()
    labs = list(db.scalars(select(LabSession).where(
        LabSession.room_id == room_id).order_by(LabSession.id).with_for_update()))
    if {lab.id for lab in labs} != set(batch.lab_ids[12:14]) or any(lab.event_id != event_id for lab in labs):
        raise RuntimeError("The dedicated room must serve exactly the two Practice 07 schedules")
    row = db.get(RoomLayout, room_id, with_for_update=True)
    if not row or row.layout.get("assessment_artwork") not in ("bio", "bio-tower-a"):
        raise RuntimeError("Practice 07 has no supported image layout")
    seats = {seat.id: seat for seat in db.scalars(select(Seat).where(
        Seat.room_id == room_id).with_for_update())}
    seat_ids = [batch.id(f"exam-07-bio-seat-{i}") for i in range(1, 7)]
    if (len(seats) not in (4, 6) or set(seats) != set(seat_ids[:len(seats)])
            or {str(seat_id) for seat_id in seats} != {zone["seat_id"] for zone in row.layout["elements"]}
            or any(seat.capacity != 45 for seat in seats.values())):
        raise RuntimeError("Practice 07 has unexpected seat identities or capacities")
    (width, height), elements, image = bio_tower_map(map_bytes)
    key = f"rooms/{room_id}/maps/{batch.id('bio-tower-map-' + sha256(image).hexdigest())}.png"
    if row.layout["image_key"] == key:
        return
    for seat_id, element in zip(seat_ids, elements, strict=True):
        seat = seats.get(seat_id)
        if seat is None:
            seat = Seat(id=seat_id, room_id=room_id, seat_code=element["label"], capacity=45)
            db.add(seat)
            db.flush()
            db.add_all(SessionSeat(session_id=lab.id, seat_id=seat_id) for lab in labs)
        else:
            seat.seat_code = element["label"]
        element["seat_id"] = str(seat.id)
    storage().put(key, image, content_type="image/png")
    track(db, key, True)
    row.layout = row.layout | {"columns": width, "rows": height, "image_key": key,
                               "elements": elements, "assessment_artwork": "bio-tower-a"}
    row.revision += 1


def com_artwork(map_bytes, logo_bytes):
    if len(map_bytes) > image_maps.MAX_BYTES:
        raise RuntimeError("Computer lab image exceeds the upload limit")
    with Image.open(BytesIO(map_bytes)) as source:
        if source.width * source.height > 16_000_000:
            raise RuntimeError("Computer lab image exceeds the pixel limit")
        plan = ImageOps.exif_transpose(source).convert("RGB")
    plan.thumbnail((image_maps.MAX_SIDE, image_maps.MAX_SIDE), Image.Resampling.LANCZOS)
    image = BytesIO()
    plan.save(image, "PNG")
    upper_rows = ((325, 438), (456, 567), (584, 699), (714, 827))
    lower_rows = ((907, 1007), (1027, 1127), (1147, 1245))
    boxes = []
    for left, right in ((1887, 2023), (1731, 1866), (1563, 1703)):
        boxes.extend((left, top, right, bottom) for top, bottom in upper_rows)
        rows = lower_rows[:2] if left == 1563 else lower_rows
        boxes.extend((left, top, right, bottom) for top, bottom in rows)
    return exam_artwork(
        image.getvalue(), logo_bytes, reference=(2324, 1582), prefix="com", accent="#175b95",
        poster_blue=False, boxes=boxes,
        labels=tuple(f"P.{index:03}" for index in range(1, 21)),
    )


def apply_com(db, batch, map_bytes, logo_bytes):
    apply_in_place_exam(db, batch, com_artwork(map_bytes, logo_bytes), exam_number=8, prefix="com")


def restyle_catalogue(db, batch):
    """Refresh appearance while retaining the booking region identities."""
    for index, room_id in enumerate(batch.room_ids):
        db.execute(select(Room.id).where(Room.id == room_id).with_for_update()).scalar_one()
        row = db.get(RoomLayout, room_id, with_for_update=True)
        if not row or row.layout.get("type") != "image":
            raise RuntimeError("Batch must already have its image layouts")
        if row.layout.get("assessment_artwork") in ("ielts", "sat", "toeic", "com", "mechanic", "chemistry"):
            continue
        image, regions = floor_plan(index)
        key = f"rooms/{room_id}/maps/{batch.id('spt-style-map-v1')}.png"
        if row.layout["image_key"] == key:
            continue
        previous = {element["id"]: element for element in row.layout["elements"]}
        if set(previous) != {region["id"] for region in regions}:
            raise RuntimeError("Existing booking regions differ from the seed plan")
        width, height = image_maps.decode_image(image).size
        seats = {str(seat.id): seat for seat in db.scalars(
            select(Seat).where(Seat.room_id == room_id).with_for_update())}
        if set(seats) != {old["seat_id"] for old in previous.values()}:
            raise RuntimeError("Existing booking region identities differ from the seed plan")
        elements = []
        for region in regions:
            seat = seats[previous[region["id"]]["seat_id"]]
            if seat.capacity != region["capacity"]:
                raise RuntimeError("Existing room capacity differs from the seed plan")
            image_maps.validate_quad(region["points"], width, height)
            seat.seat_code = region["label"]
            element = image_maps.region_geometry(region["id"], region["points"], width, height)
            elements.append(element | {"kind": "zone", "label": region["label"],
                                       "capacity": seat.capacity, "seat_id": str(seat.id)})
        storage().put(key, image, content_type="image/png")
        track(db, key, True)
        row.layout = row.layout | {"columns": width, "rows": height, "image_key": key,
                                   "elements": elements}
        row.revision += 1
    for index, event_id in enumerate(batch.event_ids):
        if index == 0 and db.get(Room, batch.hsa_room_id):
            continue
        if index == 2 and db.get(Room, batch.tsa_room_id):
            continue
        if index == 4 and db.get(Room, batch.hsa05_room_id):
            continue
        if index == 6 and db.get(Room, batch.bio_room_id):
            continue
        if index == 8 and db.get(Room, batch.elec_room_id):
            continue
        if index == 10 and db.get(Room, batch.physics_room_id):
            continue
        if index == 1 and db.get(RoomLayout, batch.room_ids[0]).layout.get("assessment_artwork") == "ielts":
            continue
        if index == 3 and db.get(RoomLayout, batch.room_ids[1]).layout.get("assessment_artwork") == "sat":
            continue
        if index == 5 and db.get(RoomLayout, batch.room_ids[2]).layout.get("assessment_artwork") == "toeic":
            continue
        if index == 7 and db.get(RoomLayout, batch.room_ids[3]).layout.get("assessment_artwork") == "com":
            continue
        if index == 9 and db.get(RoomLayout, batch.room_ids[4]).layout.get("assessment_artwork") == "mechanic":
            continue
        if index == 11 and db.get(RoomLayout, batch.room_ids[5]).layout.get("assessment_artwork") == "chemistry":
            continue
        event = db.get(Event, event_id, with_for_update=True)
        if not event:
            raise RuntimeError("Missing batch event")
        key = f"events/{event_id}/poster/{batch.id('spt-style-poster-v1')}.jpg"
        if event.poster_key != key:
            image, _ = floor_plan(index // 2)
            storage().put(key, normalize_poster(image), content_type="image/jpeg")
            track(db, key, True)
            event.poster_key = key


def book(batch):
    # One transaction per booking so the normal Redis after-commit consume runs.
    for index in range(300):
        with Session.begin() as db:
            lock_batch(db, batch)
            user = batch.user_ids[index]
            # The final group uses the second check-in event schedule. Schedule
            # 12 is deliberately historical, and the UI/load fixtures stay empty.
            lab_index = min(index // 45 * 2, 11)
            lab = db.get(LabSession, batch.lab_ids[lab_index])
            if not lab or not db.get(User, user):
                raise RuntimeError("Run prepare first")
            current = db.scalar(select(Reservation).where(
                Reservation.session_id == lab.id, Reservation.user_id == user))
            if current:
                continue
            seat = db.scalar(select(Seat.id).where(Seat.room_id == lab.room_id).order_by(Seat.seat_code))
            access = admission.action(db, user, lab, "join", booking.now(db))
            if access["status"] not in ("ADMITTED", "DISABLED"):
                raise RuntimeError(f"Synthetic admission returned {access['status']}; retry this stage")
            hold, _ = booking.hold(db, user, lab.id, seat)
            booking.transition(db, user, hold.id)
            if index == 299:
                booking.transition(db, user, hold.id, "cancel")
            elif index == 269:
                booking.transition(db, batch.user_ids[507], hold.id, "check-in")


def lock_batch(db, batch):
    key = int.from_bytes(batch.id("manifest").bytes[:8], "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def save_private(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}")
    try:
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as handle:
            json.dump(data, handle, indent=2)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def create_sessions(db, batch, output):
    lab = db.get(LabSession, batch.lab_ids[22])
    clock = booking.now(db)
    if not lab or not lab.open_at <= clock or lab.close_at < clock + timedelta(hours=1):
        raise RuntimeError("Load schedule must remain open for at least one hour")
    seats = list(db.scalars(select(Seat).where(Seat.room_id == lab.room_id).order_by(Seat.seat_code)))
    if not seats or sum(seat.capacity for seat in seats) < 100:
        raise RuntimeError("Insufficient load seat capacity")
    result = []
    load_users = batch.user_ids[300:400]
    users = {row.id: row for row in db.scalars(select(User).where(User.id.in_(load_users)))}
    for index, uid in enumerate(load_users):
        user = users.get(uid)
        if not user or user.status != "ACTIVE" or not user.email_verified_at:
            raise RuntimeError("Load account is missing or ineligible")
        session_id = batch.id(f"load-session-{index}")
        db.execute(delete(LoginSession).where(LoginSession.id == session_id))
        response = Response()
        identity = auth.create_session(db, user, response)
        session = next(item for item in db.new if isinstance(item, LoginSession))
        session.id = session_id
        cookie = next(value for name, value in response.raw_headers
                      if name == b"set-cookie" and value.startswith(b"labseat_session="))
        token = cookie.decode().split(";", 1)[0].split("=", 1)[1]
        result.append({"session_token": token, "csrf_token": identity["csrf_token"],
                       "seat_id": str(seats[index % len(seats)].id)})
        db.flush()
    # Write after commit so a failed transaction never publishes unusable tokens.
    manifest = batch.manifest()
    manifest["rooms"].extend(
        str(room_id) for room_id in (batch.hsa_room_id, batch.tsa_room_id, batch.hsa05_room_id, batch.bio_room_id, batch.elec_room_id, batch.physics_room_id)
        if db.get(Room, room_id)
    )
    manifest["schedule_rooms"] = []
    for sid in batch.lab_ids:
        schedule = db.get(LabSession, sid)
        room_seats = db.scalars(select(Seat).where(Seat.room_id == schedule.room_id)
                                .order_by(Seat.seat_code))
        manifest["schedule_rooms"].append({
            "session_id": str(sid), "room_id": str(schedule.room_id),
            "event_id": str(schedule.event_id), "open_at": schedule.open_at.isoformat(),
            "close_at": schedule.close_at.isoformat(), "start_at": schedule.start_at.isoformat(),
            "end_at": schedule.end_at.isoformat(),
            "seats": [{"seat_id": str(seat.id), "code": seat.seat_code,
                       "capacity": seat.capacity} for seat in room_seats],
        })
    manifest["sessions_expire_at"] = (clock + timedelta(hours=8)).isoformat()
    return output / "synthetic-sessions.json", result, manifest


def cleanup(db, batch):
    room_ids = batch.room_ids + [batch.hsa_room_id, batch.tsa_room_id, batch.hsa05_room_id, batch.bio_room_id, batch.elec_room_id, batch.physics_room_id]
    foreign = db.scalar(select(Reservation.id).where(
        Reservation.session_id.in_(batch.lab_ids) != Reservation.user_id.in_(batch.user_ids)
    ).limit(1))
    if foreign:
        raise RuntimeError("Non-batch reservations exist; cleanup was refused")
    if db.scalar(select(LabSession.id).where(
        LabSession.room_id.in_(room_ids), LabSession.id.not_in(batch.lab_ids)).limit(1)):
        raise RuntimeError("Non-batch schedule uses a batch room")
    if db.scalar(select(LabSession.id).where(
        LabSession.event_id.in_(batch.event_ids), LabSession.id.not_in(batch.lab_ids)).limit(1)):
        raise RuntimeError("Non-batch schedule uses a batch event")
    if db.scalar(select(StaffAssignment.user_id).where(
        StaffAssignment.session_id.in_(batch.lab_ids) != StaffAssignment.user_id.in_(batch.user_ids)
    ).limit(1)):
        raise RuntimeError("Staff assignment crosses the batch boundary")
    if db.scalar(select(CheckinPolicyEvent.id).where(
        CheckinPolicyEvent.session_id.in_(batch.lab_ids),
        CheckinPolicyEvent.actor_id.not_in(batch.user_ids)).limit(1)):
        raise RuntimeError("A non-batch operator changed the check-in policy")
    reservations = select(Reservation.id).where(
        Reservation.session_id.in_(batch.lab_ids), Reservation.user_id.in_(batch.user_ids))
    jobs = select(EmailJob.id).where(
        EmailJob.user_id.in_(batch.user_ids),
        or_(EmailJob.reservation_id.is_(None), EmailJob.reservation_id.in_(reservations)),
    )
    queries = [
        delete(PlatformEvent).where(PlatformEvent.subject_id.in_(batch.lab_ids)),
        delete(WebhookInbox).where(WebhookInbox.job_id.in_(jobs)),
        delete(PlatformEvent).where(PlatformEvent.subject_id.in_(jobs)),
        delete(EmailJob).where(EmailJob.id.in_(jobs)),
        delete(NotificationDelivery).where(NotificationDelivery.reservation_id.in_(reservations)),
        delete(OutboxEvent).where(OutboxEvent.reservation_id.in_(reservations)),
        delete(AuditEvent).where(AuditEvent.reservation_id.in_(reservations), AuditEvent.actor_id.in_(batch.user_ids)),
        delete(Reservation).where(Reservation.id.in_(reservations)),
        delete(CheckinPolicyEvent).where(CheckinPolicyEvent.session_id.in_(batch.lab_ids),
                                        CheckinPolicyEvent.actor_id.in_(batch.user_ids)),
        delete(StaffAssignment).where(StaffAssignment.session_id.in_(batch.lab_ids),
                                     StaffAssignment.user_id.in_(batch.user_ids)),
        delete(SessionSeat).where(SessionSeat.session_id.in_(batch.lab_ids)),
        delete(LabSession).where(LabSession.id.in_(batch.lab_ids)),
        delete(RoomLayout).where(RoomLayout.room_id.in_(room_ids)),
        delete(Seat).where(Seat.room_id.in_(room_ids)),
        delete(Room).where(Room.id.in_(room_ids)),
        delete(Event).where(Event.id.in_(batch.event_ids)),
        delete(LoginSession).where(LoginSession.user_id.in_(batch.user_ids)),
        delete(AdminAudit).where(AdminAudit.actor_id.in_(batch.user_ids),
                                 AdminAudit.subject_id.in_(batch.user_ids + batch.event_ids + batch.lab_ids)),
        delete(User).where(User.id.in_(batch.user_ids)),
    ]
    for query in queries:
        db.execute(query)
    # The shared storage registry garbage collector reclaims unreferenced assets.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    artwork_stages = {"hsa": apply_hsa, "ielts": apply_ielts, "tsa": apply_tsa,
                      "sat": apply_sat, "hsa05": apply_hsa05, "toeic": apply_toeic, "bio": apply_bio,
                      "com": apply_com, "elec": apply_elec, "mechanic": apply_mechanic,
                      "physics": apply_physics, "chemistry": apply_chemistry}
    parser.add_argument("stage", choices=("prepare", "book", "sessions", "restyle", "rename",
                                          *artwork_stages, "hsa05-map", "hsa05-house-a", "bio-map", "cleanup"))
    parser.add_argument("--batch", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--manifest-id")
    parser.add_argument("--email-window-confirmed", action="store_true")
    parser.add_argument("--hsa-map", type=Path)
    parser.add_argument("--hsa-logo", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,23}", args.batch):
        parser.error("Use a 3–24 character lowercase batch ID")
    batch = Batch(args.batch)
    print(json.dumps({"batch": batch.name, "manifest_id": str(batch.id("manifest")),
                      "stage": args.stage, "execute": args.execute, "users": 508,
                      "events": 12, "schedules": 24, "reservations": 300, "maps": 6,
                      "load_session": str(batch.lab_ids[22]), "ui_session": str(batch.lab_ids[20])}))
    if not args.execute:
        return
    if args.stage == "cleanup" and args.manifest_id != str(batch.id("manifest")):
        parser.error("Cleanup requires the matching --manifest-id from the batch plan")
    if args.stage == "book" and not args.email_window_confirmed:
        parser.error("Confirm the isolated email window with --email-window-confirmed")
    output = Path(".local/assessment") / args.batch
    if args.stage == "book":
        with Session.begin() as db:
            assert_owned(db, batch)
        book(batch)
    else:
        with Session.begin() as db:
            lock_batch(db, batch)
            if args.stage not in artwork_stages and args.stage not in ("hsa05-map", "hsa05-house-a", "bio-map"):
                assert_owned(db, batch, cleanup=args.stage == "cleanup")
            if args.stage == "prepare":
                master = os.environ.get("ASSESSMENT_SEED_MASTER", "")
                if len(master) < 24:
                    parser.error("Inject ASSESSMENT_SEED_MASTER (minimum 24 characters) via protected runtime config")
                clock = booking.now(db)
                add_users(db, batch, master, clock)
                add_catalogue(db, batch, clock)
            elif args.stage == "sessions":
                session_path, sessions, manifest = create_sessions(db, batch, output)
            elif args.stage == "restyle":
                restyle_catalogue(db, batch)
            elif args.stage == "rename":
                rename_people(db, batch)
            elif args.stage in ("hsa05-map", "hsa05-house-a", "bio-map"):
                map_bytes = args.hsa_map.read_bytes() if args.hsa_map else globals().get("HSA_MAP")
                if not map_bytes:
                    parser.error("Provide the room map")
                if args.stage == "bio-map":
                    apply_bio_map(db, batch, map_bytes)
                else:
                    apply_hsa05_map(db, batch, map_bytes, house_a=args.stage == "hsa05-house-a")
            elif args.stage in artwork_stages:
                map_bytes = args.hsa_map.read_bytes() if args.hsa_map else globals().get("HSA_MAP")
                logo_bytes = args.hsa_logo.read_bytes() if args.hsa_logo else globals().get("HSA_LOGO")
                if not map_bytes or not logo_bytes:
                    parser.error("Provide both the room map and the logo")
                artwork_stages[args.stage](db, batch, map_bytes, logo_bytes)
            else:
                cleanup(db, batch)
    if args.stage == "sessions":
        save_private(session_path, sessions)
        save_private(output / "manifest.json", manifest)


if __name__ == "__main__":
    main()
