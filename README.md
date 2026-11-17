# LABSEAT

LABSEAT quản lí đăng kí ca thi/thực hành, chọn phòng theo sức chứa, giữ suất, vé QR, check-in và hồ sơ người đăng kí. Phiên bản hiện tại: **0.6.0**; schema: **0002_platform**.

FastAPI modular monolith chạy bằng một image trên ECS/EC2: một cluster, một ASG private qua hai AZ và ba services API, Outbox publisher, worker. PostgreSQL lưu dữ liệu nghiệp vụ; Redis điều phối admission; S3 lưu ảnh private. Email xác nhận đi qua transactional Outbox → SQS/DLQ → Brevo API.

## Chạy local

```bash
docker compose build app
docker compose up -d db
docker compose run --rm migrate
docker compose up -d app
docker compose --profile events up -d sqs publisher worker
```

Mở http://localhost:8000. Email local dùng mock. Redis tùy chọn: `docker compose --profile queue up -d redis`; bật admission bằng công cụ quản trị queue sau khi kiểm tra readiness. Migrate giữ nguyên tài khoản, ảnh và vé; không chạy reset/seed trên database đang sử dụng. Xem [hướng dẫn local và API](docs/labseat.md).

Check-in: vào **Quản lí ca → Mở check-in**. Quét QR hoặc nhập mã để xem thông tin vé và hồ sơ, rồi bấm **Xác nhận check-in**. [Chi tiết](docs/deployment/checkin.md).

## Tài liệu

- [Kế hoạch nghiệm thu 4 ngày cho 3 người](docs/sprints/ke-hoach-nghiem-thu-4-ngay.md): chia task, prompt AI, đầu ra/Git, tiêu chí hoàn thành và diễn tập tải/failover/restore.
- [Đặc tả hệ thống chi tiết](docs/dac-ta-he-thong.md): nghiệp vụ, phân quyền, dữ liệu, API, kiến trúc và nghiệm thu.
- [Kiến trúc](docs/architecture/current.md), [quyết định](docs/architecture/decisions.md), [bản đồ source](docs/implementation/ecs-audit.md), [hướng dẫn cho AI](docs/tu-duy-he-thong-hien-tai-cho-ai.md).
- [AWS deployment](docs/deployment/aws.md), [capacity](docs/deployment/capacity.md), [rollback](docs/deployment/rollback.md), [event pipeline](docs/deployment/events.md).
- [Brevo và cấu hình sender/API key](docs/deployment/brevo.md), [camera QR](docs/deployment/camera.md), [sơ đồ phòng](docs/image-seat-maps.md).
- [Kiểm thử](docs/testing/concurrency.md), [load test](docs/testing/load-test.md), [kết quả local](evidence/current/README.md).
- [Nghiệm thu AWS](docs/clo4/checklist.md), [dự toán chi phí](docs/cost/monthly-estimate.md), [báo cáo triển khai](docs/implementation/ecs-report.md).

## Kiểm tra

```bash
docker compose --profile test run --rm test
node tests/app/ui.test.mjs
python3 scripts/tests/check-infra.py --terraform /PATH/terraform
```

Tests dùng PostgreSQL/Redis riêng. Terraform mock tests cần Terraform 1.12+. AWS đã triển khai và kiểm chứng bước đầu: [biên bản AWS](evidence/current/aws-deployment.md). Autoscaling dưới tải, inbox email thật và khôi phục RDS chưa được nghiệm thu; kết quả local không thay thế các bước này.

Nền tảng tài khoản/staff/email/realtime: [đặc tả chi tiết](docs/dac-ta-he-thong.md). [Maintenance và retention](docs/deployment/maintenance.md), [diễn tập restore](docs/deployment/recovery.md), [nghiệm thu tải](docs/testing/load-test.md). Local mặc định mock email; Brevo thật cần sender, API key, signing key và webhook token cấu hình riêng.
