# Outbox, durable jobs, SQS và Brevo

Confirm ghi vé và Outbox trong cùng transaction PostgreSQL. Envelope broker chỉ có identifiers. Publisher khóa SKIP LOCKED, batch giới hạn, backoff lỗi và checkpoint publication; gửi thành công rồi mất checkpoint có thể tạo message lặp.

Worker chuyển canonical confirmation event sang EmailJob UUID ổn định theo reservation; SENT/SKIPPED checkpoint có sẵn không bị phát lại khi thay backend/email. Verification/reset/cancellation/resend/retention tạo EmailJob+PlatformEvent cùng transaction tương ứng. Job lưu recipient và snapshot nội dung; auth link snapshot dùng placeholder, không persist bearer token; worker tái tạo token trong RAM từ challenge và signing key.

Worker commit SENDING trước provider I/O, giải phóng connection DB. Concurrent claim được retry; provider idempotencyKey UUID/job ID và payload/sender ổn định bảo vệ retry trong cửa sổ30 phút. Kết quả chưa rõ quá29 phút chuyển UNKNOWN, không tự gửi lại. Brevo lỗi không thay trạng thái vé; delivery intent PENDING vẫn được giữ để đối chiếu/retry. ACCEPTED chỉ là ACK API, DELIVERED cần webhook. Không cam kết exactly-once/inbox delivery.

SQS visibility120 giây, maxReceiveCount5, DLQ retention14 ngày. Provider call có timeout, không follow redirect hoặc tự retry HTTP. Địa chỉ không tồn tại có thể được tiếp nhận rồi bounce; hard bounce/spam/blocked tạo suppression. Soft bounce/deferred không tự tạo lần gửi mới. Người dùng/admin chủ động resend có quota60 giây/3 lần ngày. Webhook API xác thực Bearer, lưu inbox dedup và xử lí ngoài request; xem [Brevo](brevo.md).

Publisher cũng phát availability invalidation qua Redis events ACL riêng. Redis Pub/Sub không phải nơi giữ vé hoặc trạng thái email; client resync snapshot DB và polling khi stream lỗi. Email publication được ưu tiên trước invalidation để lỗi Redis không cản email mới.

Local: migrate trước, `docker compose --profile events up -d sqs publisher worker`. ElasticMQ + mock không dùng AWS credentials, không gửi thư thật. Production chỉ disabled/brevo. Scheduler maintenance chạy các batch hủy ca/webhook/GC/retention; [maintenance](maintenance.md). Pending không purge; published events90 ngày, checkpoint365 ngày, idempotency30 ngày. Không redrive/replay quá cửa sổ an toàn mà chưa kiểm tra checkpoint/provider.

Giám sát DLQ, oldest message age, Outbox backlog, worker failure, EmailUnknown và heartbeat maintenance qua CloudWatch/SNS. Restart/failover admission Redis cần recovery epoch/drain; events ACL chỉ được publish/subscribe channel labseat:events:*, không đọc queue keys. TLS/Lua/ACL/failover và email giao nhận thật còn cần nghiệm thu trên môi trường được phép.
