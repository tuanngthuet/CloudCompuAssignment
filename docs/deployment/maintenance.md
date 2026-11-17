# Maintenance và vòng đời dữ liệu

Lệnh mặc định chỉ báo cáo, không xóa hoặc ẩn danh:

```bash
docker compose run --rm maintenance
# Chỉ chạy khi đã xem dry-run và có backup phù hợp:
docker compose run --rm maintenance python -m app.maintenance --execute --limit 100
```

Mỗi lượt giới hạn1–1000 bản ghi cho từng pha; mặc định100. Lease PostgreSQL15 phút ngăn các lượt execute chồng nhau. Scheduler ECS chạy mỗi5 phút với pool1, role riêng chỉ có S3 ListBucket theo prefix rooms/events/users và DeleteObject dưới ba prefix đó. Mỗi lượt phát MaintenanceSuccess/Failure; cảnh báo khi mất heartbeat15 phút, GC lỗi hoặc email UNKNOWN. API không giữ connection trong lúc người dùng mở SSE.

| Đối tượng | Điều kiện dọn |
|---|---|
| Phiên/challenge | Hết hạn ít nhất7 ngày |
| Rate counter | Window cũ hơn1 ngày |
| Idempotency | Cũ hơn30 ngày; hợp đồng replay trong30 ngày |
| Outbox/PlatformEvent | Đã published và cũ hơn90 ngày |
| Webhook inbox | Đã processed và cũ hơn90 ngày |
| Audit/check-in audit/delivery checkpoint | Cũ hơn365 ngày; delivery phải SENT/SKIPPED |
| Email context/recipient | Job hoàn tất và cũ hơn90 ngày; giữ ID/trạng thái để đối chiếu |
| Storage registry DELETED | Xóa object thành công ít nhất90 ngày |

Không purge pending Outbox/webhook/job. UNKNOWN cần đối chiếu provider; không tự gửi lại. Không redrive message đã hết cửa sổ idempotency30 ngày mà chưa kiểm tra lịch sử. SQS giữ message tối đa14 ngày, ngắn hơn thời gian giữ checkpoint365 ngày.

GC inventory có cursor để đi hết prefix. Object tối thiểu24 giờ tuổi mới được cách ly; sau đó chờ thêm24 giờ. Trước khi xóa, khóa registry và kiểm lại mọi tham chiếu avatar/poster/ảnh phòng/layout. Upload hoặc publish cũng khóa registry, từ chối object đang DELETING/DELETED. Upload thành công nhưng transaction rollback được tìm lại qua inventory. Object tham chiếu không bị xóa chỉ vì registry cũ. Thay/xóa avatar gỡ tham chiếu trước, GC xử lí sau. Sau10 lần xóa lỗi, dừng retry object và phát cảnh báo; người vận hành sửa nguyên nhân, kiểm object không tham chiếu rồi reset failures để thử lại.

Student không hoạt động335 ngày được gửi thông báo; sau365 ngày chỉ tự ẩn danh nếu có webhook DELIVERED của đúng thông báo ít nhất30 ngày và không còn đăng kí đang/sắp diễn ra. Login, sửa hồ sơ và hoạt động phiên reset hạn lưu; cập nhật hoạt động sau khi transaction nghiệp vụ kết thúc để giữ thứ tự khóa. Admin/staff không tự ẩn danh. Migration backfill last_activity_at bằng thời điểm nâng cấp.

Không có bằng chứng giao thư thì chuyển danh sách duyệt ở Quản trị người dùng. Admin phải rà soát, nhập lý do và xác nhận ẩn danh; API vẫn từ chối tài khoản chưa đủ365 ngày hoặc còn đăng kí tương lai. Ẩn danh xóa tên/email/CCCD/điện thoại/avatar, thay username/password, thu hồi mọi phiên/challenge; giữ UUID, vé và audit lịch sử. Không có chức năng khôi phục PII sau ẩn danh.

Trước release, deployment CLI tắt schedule; sau migration, service rollout, exact-image smoke và maintenance dry-run, CLI chuyển schedule sang cùng image digest rồi bật. Nếu release lỗi, schedule giữ tắt để người vận hành xem xét; rollback chuyển về maintenance definition của last-good tương thích schema. Không downgrade database.
