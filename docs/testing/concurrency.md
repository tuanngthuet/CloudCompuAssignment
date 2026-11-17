# Kiểm tra booking, migration và nhiều instance

Tests chỉ dùng APP_ENV=test và PostgreSQL database kết thúc `_test`. Suite tạo/xóa schema và truncate dữ liệu test; không trỏ vào database đang phục vụ.

```bash
docker compose --profile test run --rm test python -m pytest tests/app -q -rs -p no:cacheprovider
node tests/app/ui.test.mjs
```

`test_booking_concurrency.py` kiểm phòng độc lập tiến triển trong khi transaction phòng khác chưa kết thúc, admin exclusive edit chờ booking, đối chuyển phòng với hold hết hạn không deadlock và 1.000 attempts tạo đúng số registration. Idempotency tests kiểm replay, payload mismatch, concurrent keys và rollback. Đây là kiểm tra tính đúng dưới tải có kiểm soát, không phải production RPS/p95 benchmark.

`test_db.py` kiểm last-place race, một người/nhiều phòng, expiry, confirm/cancel/check-in lặp, ownership/CSRF, FIFO/quota/heartbeat, generation mismatch và recovery. Hai Uvicorn processes kiểm login/auth, hold/confirm, avatar và queue readiness dùng chung DB/Redis/ảnh. Hai Redis process-fault cases cần fixture disposable được bật riêng.

`test_migrate.py` kiểm schema từ đầu, đổi baseline marker giữ dữ liệu tồn tại và từ chối schema drift, repeated upgrade, unknown revision và migration processes đồng thời. `test_checkin_control.py` kiểm manual policy, PII/admin/CSRF, idempotence, audit và đóng ca sau lookup. `test_notifications.py`, `test_brevo_email.py`, `test_brevo_booking.py`, `test_sqs_local.py` kiểm Outbox/delivery, HTTP provider mock và ElasticMQ transport.

Camera/browser mock tests: RUN_CAMERA_BROWSER_TESTS=1 với Playwright/Chrome; UI fixtures khác cần LABSEAT_BROWSER_UI_TEST=1 và BROWSER_EXECUTABLE. Các browser tests gọi HTTP thật phải dùng server demo disposable và BROWSER_TEST_ALLOWED=local-demo-only. Không chạy fixture tạo dữ liệu song song suite truncate cùng DB. [Kết quả](../../evidence/current/README.md).

`scripts/tests/db-invariants.sql` kiểm sức chứa theo phòng/ca, slot, một đăng kí hiệu lực và ticket/check-in consistency trong transaction read-only. Mỗi query phải trả zero rows.
