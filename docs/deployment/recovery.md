# Nghiệm thu backup và khôi phục

Mục tiêu vận hành: SLO availability99,5% theo cửa sổ30 ngày; RPO≤15 phút; RTO≤60 phút. Đây là mục tiêu cần đo, không phải SLA hay kết quả đã đạt. Terraform đặt RDS backup retention30 ngày và S3 versioning; noncurrent object versions hết hạn sau30 ngày. Không có thao tác AWS thật được thực hiện trong lượt implement này.

Chạy diễn tập trên môi trường synthetic được phép, tách khỏi thời gian load test. Lưu thời điểm UTC, account/region, release digest, DB snapshot/PITR latest-restorable-time, schema revision, counts và hash của dữ liệu kiểm chứng, S3 key/version ID/hash. Không đưa PII, token, connection string hoặc key vào evidence.

1. Ghi `incident_at` ngay khi bắt đầu mô phỏng mất dịch vụ. Ghi commit marker có timestamp DB mỗi phút từ trước sự cố, để đo dữ liệu cuối thực sự khôi phục được.
2. Dùng RDS restore-to-point-in-time vào **DB identifier mới**, private subnet group/SG, encryption và cùng parameter group; không ghi đè DB đang phục vụ. Kiểm latest-restorable-time thay vì suy từ retention30 ngày.
3. Chờ DB available, lấy endpoint mới. Kiểm migration revision, `scripts/tests/db-invariants.sql`, active registrations/slot uniqueness, user/session ownership và không gửi lại email SENT. Không chạy seed/reset.
4. Khôi phục object bị mất bằng version ID dưới prefix tương ứng trong môi trường diễn tập; kiểm SHA-256 và mọi DB reference. Noncurrent lifecycle30 ngày có nghĩa quá hạn này có thể không phục hồi được bản cũ.
5. Cập nhật DATABASE_URL secret của **môi trường diễn tập**, rollout image digest đã smoke, kiểm health/ready, đăng nhập synthetic, đọc vé/QR, hold-confirm-cancel và staff check-in. SQS/publisher/worker cần kiểm checkpoint trước khi redrive; không phát lại email đã hoàn tất.
6. Chỉ ghi `ready_and_verified_at` khi toàn bộ kiểm tra đúng dữ liệu và ảnh đã qua. `latest_recovered_commit_at` lấy từ marker commit thực tế trong DB restored, không lấy thời gian snapshot nếu không đối chiếu dữ liệu.
7. Ghi JSON riêng trong `.local/recovery-record.json`, gồm ba timestamp ISO8601 có timezone, `database_invariants_passed`, `images_verified`, `evidence_paths`. Chạy `python scripts/recovery/measure.py .local/recovery-record.json`. Script từ chối thiếu kiểm chứng và trả exit1 khi vượt mục tiêu.
8. Ghi nguyên nhân nếu vượt RPO/RTO, thời gian từng bước và điều chỉnh capacity/backup/quy trình; đo lại. Chỉ dọn tài nguyên diễn tập sau khi người vận hành xác định đúng identifier và đã giữ evidence cần thiết.

S3 versioning không thay thế backup database; RDS retention không chứng minh RPO. Chuyển ALB sang release cũ không phục hồi transaction đã mất. Dữ liệu secret và dịch vụ ngoài AWS có quy trình khôi phục riêng. Mọi thao tác restore/deploy thật cần tài khoản và phạm vi môi trường được người vận hành cho phép.
