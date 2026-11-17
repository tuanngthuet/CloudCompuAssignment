# Bản đồ source LABSEAT

| Phần | Nguồn triển khai | Trách nhiệm |
|---|---|---|
| HTTP/UI | app/main.py, app/templates, app/static | Routes, middleware, giao diện tại / |
| Auth/profile | app/modules/auth, app/modules/profiles | Session, CSRF, hồ sơ private, avatar |
| Ca/phòng | app/modules/admin, sessions, rooms; app/image_maps.py, layouts.py | Lịch, ảnh, sơ đồ, sức chứa và revision |
| Booking | app/modules/booking | Holds, confirm/cancel, locks, slots, idempotency |
| Vé/check-in | app/modules/tickets, app/modules/checkin | QR, export, tra cứu admin, manual policy và audit |
| Admission | app/modules/queue, app/infrastructure/redis, app/queue_admin.py | FIFO, quota, policy/epoch, recovery |
| Email/events | app/modules/notifications, app/events.py | Outbox, SQS, delivery lock, Brevo, mock |
| Database | app/infrastructure/database, app/models.py, migrations | PostgreSQL, transaction hooks và Alembic |
| Storage | app/infrastructure/storage | Local shared volume/S3, validation, normalization |
| Observability | app/infrastructure/observability | JSON logs, metrics và DB telemetry |
| Deployment | deploy, infra | ECS image, one-off migrate/smoke, rollout, rollback, AWS resources |
| Verification | tests/app, scripts/tests, scripts/load | PostgreSQL/Redis/HTTP/browser, provider mock và load scenarios |

Một image phục vụ API/worker/publisher theo command. Không có bản ứng dụng thứ hai trong repository. Schema head `0002_platform`; một baseline DDL đóng băng là thành phần runtime; app.migrate có kiểm tra schema trước khi đổi marker database đang dùng. [Kiến trúc](../architecture/current.md), [kết quả kiểm tra](../../evidence/current/README.md).
