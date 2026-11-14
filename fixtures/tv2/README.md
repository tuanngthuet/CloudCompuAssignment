# W1-TV2 health fixture

The fixture uses the Python 3.12 standard library and serves two HTTP endpoints for compute and runtime smoke checks.

| Endpoint | Response |
| --- | --- |
| `GET /healthz` | `200` with `{"status":"ok"}` while the process is serving requests |
| `GET /version` | `200` with `fixture: true`, `version`, and the local `instance` hostname |

Other GET routes return `404`. The fixture has no database, readiness checks, AWS resources, or reservation behavior. Fixture results cover startup, HTTP routing, and version reporting only.

Run from the workspace root with Python 3.12 available as `python`.

```text
python fixtures/tv2/smoke.py
python fixtures/tv2/app.py
```

The manual command listens on `0.0.0.0:8000` by default. Override `HOST`, `PORT`, or `APP_VERSION` in the environment. The default version is `fixture-v1`. The smoke command binds to a loopback port assigned by the OS and stops the child process after checking the responses.
