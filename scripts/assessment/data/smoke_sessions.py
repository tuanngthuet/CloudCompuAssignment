"""Verify an assessment handoff against the normal LABSEAT HTTP API."""

import argparse
import json
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    manifest = json.loads((args.directory / "manifest.json").read_text())
    sessions = json.loads((args.directory / "synthetic-sessions.json").read_text())
    if len(sessions) < 100 or len({s["session_token"] for s in sessions}) != len(sessions):
        raise SystemExit("Expected at least 100 distinct sessions")
    lab = manifest["load_session"]
    users = set()
    with httpx.Client(base_url=args.base_url, timeout=15) as client:
        for room in manifest["rooms"]:
            layout = client.get(f"/rooms/{room}/seat-map").raise_for_status().json()
            zones = [item for item in layout["elements"] if item["kind"] == "zone"]
            expected = {"tsa": (12,), "sat": (11,), "toeic": (11,), "hsa05": (26,), "hsa05-dongda": (25,),
                        "hsa05-house-a": (33,), "com": (20,)}.get(
                layout.get("assessment_artwork"), range(4, 9))
            if layout.get("type") != "image" or len(zones) not in expected:
                raise SystemExit("Unexpected number of selectable image zones")
            image = client.get(layout["image_url"]).raise_for_status()
            if not image.headers["content-type"].startswith("image/"):
                raise SystemExit("Map image endpoint did not return an image")
        rooms = client.get(f"/lab-sessions/{lab}/seats").raise_for_status().json()["items"]
        available = {item["id"] for item in rooms if item["remaining"] > 0}
        verified = {user["id"] for user in manifest["users"] if user["role"] == "student"}
        for row in sessions:
            client.cookies.set("labseat_session", row["session_token"])
            identity = client.get("/me").raise_for_status().json()
            if identity["id"] not in verified or row["seat_id"] not in available:
                raise SystemExit("Unexpected identity or unavailable seat in platform fixture")
            users.add(identity["id"])
        if len(users) != len(sessions):
            raise SystemExit("Multiple sessions belong to the same account")
        row = sessions[0]
        client.cookies.set("labseat_session", row["session_token"])
        headers = {"X-CSRF-Token": row["csrf_token"]}
        client.post(f"/lab-sessions/{lab}/queue/join", json={}, headers=headers).raise_for_status()
        held = client.post("/holds", json={"session_id": lab, "seat_id": row["seat_id"]},
                           headers=headers).raise_for_status().json()
        client.post(f"/reservations/{held['hold_id']}/cancel", json={}, headers=headers).raise_for_status()
    print(f"PASS: {len(manifest['rooms'])} image maps; {len(users)} unique users; hold and cancel succeeded")


if __name__ == "__main__":
    main()
