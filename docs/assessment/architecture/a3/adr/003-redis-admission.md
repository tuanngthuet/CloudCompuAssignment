# ADR-003-redis-admission: Redis quản lý admission, PostgreSQL lưu vé

- Trạng thái: Draft — mô tả quyết định suy ra từ code, chờ owner/reviewer xác nhận.
- Ngày soạn: 18/11/2026.
- Không coi đây là biên bản quyết định lịch sử hoặc kết quả nghiệm thu.

## Bối cảnh
Cần giới hạn lượt được chọn chỗ, nhưng việc cấp vé phải dựa trên ràng buộc bền vững.

## Quyết định thể hiện trong source
Queue policy lưu ở PostgreSQL, lượt admission xử lý qua Redis/Lua. Khi tạo hold mới, guard chỉ gọi Redis nếu queue enabled. Lượt được consume bằng after_commit; rollback loại danh sách release.

## Phương án thay thế
Dùng Redis làm nguồn chuẩn cho vé cần cơ chế đồng bộ/khôi phục phức tạp. Admission chỉ ở RAM không thống nhất giữa các API. Tắt admission là một chế độ code hỗ trợ nhưng không tương đương kiểm soát tải.

## Hệ quả và đánh đổi
Queue enabled và Redis lỗi thì hold mới bị từ chối 503; không khẳng định toàn bộ app ngừng. Confirm/cancel không gọi guard. Lỗi consume sau commit được log; vé đã commit không bị rollback. Cần quản lý recovery/epoch và TTL của Redis.

## Bằng chứng
app/infrastructure/redis/admission.py:policy,guard,release_after_commit,discard_after_rollback; app/queue_scripts/admission.lua; app/queue_admin.py; booking/service.py.

## Kiểm chứng còn cần
Kiểm tra enabled/disabled, WAITING/EXPIRED, Redis outage, recovery generation và lỗi consume sau commit. Chưa chạy fault test.
