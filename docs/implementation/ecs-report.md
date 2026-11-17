# Báo cáo triển khai LABSEAT

Source hiện tại là FastAPI modular monolith, container hóa bằng một image. ECS vận hành ba services API, Outbox publisher và worker trên cùng cluster/EC2 ASG private qua hai AZ. Capacity Provider quản lí EC2 capacity; API Service autoscaling quản lí số tasks. [Sơ đồ kiến trúc](../architecture/current.md), [capacity/DB budget](../deployment/capacity.md).

PostgreSQL quản lí tài khoản/session/CSRF, hồ sơ, lịch, phòng, holds/vé, queue policy, idempotency và audit. Khóa hàng và unique constraints bảo đảm không vượt sức chứa, một đăng kí hiệu lực/người/ca và confirm trong hạn. Redis cung cấp admission với recovery epoch; S3 lưu ảnh private. Các API tasks dùng chung dữ liệu và không cần sticky session.

Xác nhận vé tạo Outbox trong cùng transaction. Publisher gửi identifiers-only event vào SQS/DLQ; worker kiểm dữ liệu chuẩn và delivery lock rồi gửi email LABSEAT qua Brevo API. Retry transport có giới hạn; duplicate vẫn có thể xảy ra sau provider acceptance trước DB commit. Vé không bị mất vì email lỗi. API key chỉ cấp cho worker.

Hồ sơ yêu cầu email khi lưu, số điện thoại tùy chọn; ca thi yêu cầu họ tên/CCCD/email. Quản trị mở/đóng check-in từng ca. Quét/nhập mã hiển thị vé và hồ sơ trước, xác nhận riêng; server kiểm lại policy/status trong transaction. Camera có popup, vùng quét, animation và jsQR fallback; HTTP ngoài localhost dùng ảnh/nhập mã.

Deployment CLI kiểm account, digest, one-off migration exit/timeout, rollout và smoke đúng image/database. Rollback dùng release đã smoke thành công, không downgrade schema. Execution role inject SSM; task roles tách S3/SQS, host chỉ phục vụ ECS/SSM. Network/DB/S3 private, monitoring và SNS do Terraform quản lí.

[Kết quả kiểm tra local](../../evidence/current/README.md) là phạm vi đã xác minh. AWS chưa triển khai/nghiệm thu: placement/ENI, autoscale hai tầng, quyền IAM thật, TLS/ACL/failover, Brevo delivery, DLQ/SNS và RDS restore còn cần kiểm theo [checklist](../clo4/checklist.md). [Dự toán](../cost/monthly-estimate.md) phải dựa trên cấu hình và giá của tài khoản tại thời điểm triển khai.
