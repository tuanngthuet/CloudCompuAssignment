# LABSEAT — hướng dẫn làm việc với source

Phiên bản 0.6.0, Alembic head `0002_platform`. [README](../README.md) là điểm vào; [đặc tả đầy đủ](dac-ta-he-thong.md); [kiến trúc](architecture/current.md), [source map](implementation/ecs-audit.md), [API/sản phẩm](labseat.md), [kết quả kiểm tra](../evidence/current/README.md).

## Nguồn chuẩn

- `app/modules`: auth, profiles, sessions, rooms, booking, tickets, checkin, admin, queue, notifications. `app/infrastructure`: database, storage, Redis và observability. Import trực tiếp module triển khai.
- `app/main.py`: router, error handlers, middleware và giao diện tại `/`. `app/static` + `app/templates`: frontend; jsQR đóng gói tại static/vendor.
- `migrations/versions/0001_labseat.py`: một baseline DDL đóng băng. Chạy `python -m app.migrate` dưới advisory lock; database đủ schema được kiểm trước khi đổi marker, không tự stamp/reset. Revision0002_platform thêm auth/staff/lifecycle/email/realtime/maintenance, không sửa baseline.
- `infra`: bootstrap state/network, integration và các module ECS, data, IAM, cache, messaging, monitoring. `deploy`: build/push, migrate, rollout, smoke, rollback bằng CLI.
- `handoff/current.json`: metadata hiện tại. `evidence/current`: kết quả kiểm tra và ảnh minh họa dữ liệu giả.

## Invariants

PostgreSQL là nguồn chuẩn. Booking khóa User UPDATE → LabSession SHARE → SessionSeat UPDATE theo UUID; unique active user/session và slot chống vượt sức chứa. Thời gian lấy từ DB. Confirm chỉ hold còn hạn và commit vé cùng Outbox. Idempotency response lưu DB.

Redis có ACL riêng cho admission và Pub/Sub; lỗi khi policy bật phải fail-closed. Policy/epoch/marker và generation-aware consume sau commit bảo vệ recovery. Không tự FLUSHALL hoặc đặt marker để vượt readiness. TLS/hostname verification và runtime/operator ACL được kiểm ở production.

Email chỉ Brevo API; local/test có mock và có thể disabled. Worker dùng durable job snapshot và provider idempotency UUID; kết quả chưa rõ quá29 phút chuyển UNKNOWN để đối chiếu. Webhook Bearer inbox cập nhật delivery và suppression; resend có quota. Không log API key/recipient/profile/ticket. Key chỉ inject vào worker qua SSM hoặc file secret local.

Email bắt buộc khi lưu hồ sơ, điện thoại tùy chọn. Ca thi cần họ tên/CCCD/email. Check-in do `lab_sessions.checkin_enabled` điều khiển; admin mở/đóng riêng từng ca. Tra cứu admin+CSRF hiển thị vé/hồ sơ; POST xác nhận mới thay trạng thái và kiểm lại policy dưới lock. Lặp CHECKED_IN idempotent. Không thêm PII vào catalogue/Outbox.

## Runtime và kiểm tra

Một ECS cluster, một EC2 ASG private 2/2/6 qua hai AZ; API 2..8 tasks, worker/publisher mỗi service 1 task; một image. API dùng một Uvicorn process, budget3 (nghiệp vụ2+counter1)/overflow0, background pool1. Capacity Provider quản lí host scaling. Healthz shallow; readyz kiểm DB; release smoke chạy image candidate đúng DB/schema.

Local dùng Docker Compose, PostgreSQL và shared images volume. Khi thay namespace Compose phải giữ nguyên volume dữ liệu thực tế. Không đọc credential từ `.local` để kiểm thử. Tests chỉ trỏ DB `*_test` và fixture/browser server riêng; không reset DB đang phục vụ. Không gửi email thật, apply Terraform hoặc triển khai AWS chỉ để chạy kiểm tra source.

Xem [AWS runbook](deployment/aws.md) và [checklist nghiệm thu](clo4/checklist.md). AWS chưa được triển khai/nghiệm thu. Báo cáo chỉ khẳng định các kiểm tra có log thực tế.

Baseline đóng băng cộng revision0002_platform tạo schema hiện tại. Chuyển marker giữ dữ liệu theo migrations/README.md; không import ORM để sinh DDL runtime và không chạy CREATE lại trên database đang có bảng.
