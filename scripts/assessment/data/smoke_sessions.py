"""Verify an assessment handoff against the normal LABSEAT HTTP API."""

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from pathlib import Path

import httpx
from PIL import Image


def aware(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise SystemExit("Handoff timestamps must include a timezone")
    return result


def verify(directory, base_url, minimum_valid_seconds=3600):
    manifest = json.loads((directory / "manifest.json").read_text())
    sessions = json.loads((directory / "synthetic-sessions.json").read_text())
    if (len(sessions) < 100 or len({s["session_token"] for s in sessions}) != len(sessions)
            or len({s["csrf_token"] for s in sessions}) != len(sessions)):
        raise SystemExit("Expected at least 100 distinct sessions")
    if minimum_valid_seconds < 3600:
        raise SystemExit("Handoff window must be at least one hour")
    if aware(manifest["sessions_expire_at"]) < datetime.now(timezone.utc)+timedelta(seconds=minimum_valid_seconds):
        raise SystemExit("Session TTL does not cover the requested window")
    lab = manifest["load_session"]
    expected_rooms = {}
    for schedule in manifest["schedule_rooms"]:
        mapping = {s["seat_id"]: (s["code"], s["capacity"]) for s in schedule["seats"]}
        if schedule["room_id"] in expected_rooms and expected_rooms[schedule["room_id"]] != mapping:
            raise SystemExit("Manifest contains inconsistent room mapping")
        expected_rooms[schedule["room_id"]] = mapping
    if not expected_rooms or not set(expected_rooms).issubset(manifest["rooms"]):
        raise SystemExit("Manifest room mapping is incomplete")
    users = set()
    with httpx.Client(base_url=base_url, timeout=15) as client:
        catalogue = client.get('/lab-sessions').raise_for_status().json()
        current = next((s for s in catalogue['items'] if s['id']==lab), None)
        clock = aware(catalogue['server_time'])
        window = clock+timedelta(seconds=minimum_valid_seconds)
        if (not current or aware(current['open_at'])>clock or aware(current['close_at'])<window
                or aware(current['start_at'])<=window or aware(manifest['sessions_expire_at'])<window):
            raise SystemExit("Load schedule/session TTL is not ready for the requested window")
        for room, expected in expected_rooms.items():
            layout = client.get(f"/rooms/{room}/seat-map").raise_for_status().json()
            zones = [item for item in layout["elements"] if item["kind"] == "zone"]
            actual = {item['seat_id']: (item['label'], item['capacity']) for item in zones}
            if layout.get("type") != "image" or len(zones)!=len(expected) or actual!=expected:
                raise SystemExit("Image zone UUID/label/capacity does not match the manifest")
            image = client.get(layout["image_url"]).raise_for_status()
            if not image.headers["content-type"].startswith("image/"):
                raise SystemExit("Map image endpoint did not return an image")
            with Image.open(BytesIO(image.content)) as decoded:
                if decoded.format not in ('PNG','JPEG','WEBP') or max(decoded.size)>2048 or len(image.content)>5*1024*1024:
                    raise SystemExit("Map image exceeds B2 format/dimension/size limits")
        rooms = client.get(f"/lab-sessions/{lab}/seats").raise_for_status().json()["items"]
        available = {item["id"]:item["remaining"] for item in rooms if item["remaining"] > 0}
        if any(n>available.get(seat,0) for seat,n in Counter(s['seat_id'] for s in sessions).items()):
            raise SystemExit("Fixture assignments exceed remaining seat capacity")
        verified = {user["id"] for user in manifest["users"] if user["role"] == "student"}
        for row in sessions:
            client.cookies.set("labseat_session", row["session_token"])
            identity = client.get("/me").raise_for_status().json()
            if (identity["id"] not in verified or row["seat_id"] not in available
                    or identity.get('account_status')!='ACTIVE' or not identity.get('email_verified')):
                raise SystemExit("Unexpected identity or unavailable seat in platform fixture")
            users.add(identity["id"])
        if len(users) != len(sessions):
            raise SystemExit("Multiple sessions belong to the same account")
        row = sessions[0]
        client.cookies.set("labseat_session", row["session_token"])
        headers = {"X-CSRF-Token": row["csrf_token"]}
        held = None
        try:
            access=client.post(f"/lab-sessions/{lab}/queue/join", json={}, headers=headers).raise_for_status().json()
            if access['status'] not in ('ADMITTED','DISABLED'):
                raise SystemExit("Smoke user is waiting; no hold was attempted")
            held = client.post("/holds", json={"session_id": lab, "seat_id": row["seat_id"]},
                               headers=headers).raise_for_status().json()
        finally:
            try:
                if held:
                    client.post(f"/reservations/{held['hold_id']}/cancel", json={}, headers=headers).raise_for_status()
            finally:
                client.post(f"/lab-sessions/{lab}/queue/leave",json={},headers=headers).raise_for_status()
    return {'image_maps':len(expected_rooms),'unique_users':len(users),'hold_cancel':'PASS'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--minimum-valid-seconds",type=int,default=3600)
    args = parser.parse_args()
    print(json.dumps(verify(args.directory,args.base_url,args.minimum_valid_seconds)))


if __name__ == "__main__":
    main()
