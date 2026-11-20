# Đánh giá RPO/RTO

**Chưa có RPO/RTO end-to-end.** Mục tiêu RPO ≤900s, RTO ≤3600s; availability 99,5%/30 ngày là mục tiêu, không phải kết quả.

| Đại lượng | Giá trị | Có được dùng để nghiệm thu? |
|---|---|---|
| Thời gian toàn lượt S3 | 25.793484s | Chỉ thời lượng lượt độc lập, gồm chuẩn bị/cleanup |
| Từ stage overwritten đến restored | 3.207088s | Chỉ khoảng cách hai mốc ghi nhận; không phải downtime/RTO app |
| RPO phục hồi DB | null | Chưa có commit marker trong DB restored |
| RTO dịch vụ | null | Chưa có incident_at và ready_and_verified_at hợp lệ |
| images_verified | false | Chưa kiểm DB reference/app/cache |

RPO = incident_at − latest_recovered_commit_at. RTO = ready_and_verified_at − incident_at. Cần timestamp timezone, thứ tự latest ≤ incident ≤ ready, invariant DB restored và ảnh qua app đạt, cùng evidence_paths. Source measure.py của gói kiểm các điều kiện này; không chạy với dữ liệu giả để tạo kết quả.

Retention 1 ngày, LatestRestorableTime, hash object S3 hoặc invariant DB nguồn không thay marker commit đã phục hồi. Failover RDS sang standby cũng không phải PITR tạo DB mới. Không lấy thời gian CopyObject làm RTO toàn ứng dụng.

Ảnh published qua app có thể cache 24 giờ theo tên file; query v không phải S3 VersionId. Metadata no-store ở S3 của lượt độc lập không chứng minh app/browser hết stale cache. Lượt tích hợp cần ghi URL/header, DB key, version/hash và hình hiển thị bình thường, đối chiếu request không cache có giải thích.

## Xác nhận đối chiếu 20/11/2026

Theo phần bàn giao Người 2, hai khoảng thời gian **25.793484s** và **3.207088s** khớp JSON gốc. JSON giữ timestamp chính xác tới microsecond; timeline A4 hiển thị tới millisecond. Không đổi hai khoảng này thành downtime hoặc RTO phục vụ.

B4 vẫn BLOCKED và chưa có DB/app restored. Việc đối chiếu sơ đồ planned không chứng minh đã chạy PITR. Người 2 kiểm DB, nghiệp vụ và B5 trước khi ghi ready; không chuyển production sang DB restored. Không có số đo AWS mới trong lượt cập nhật tài liệu này.
