# ADR-004-outbox-email: Outbox và email job có chống trùng

- Trạng thái: Draft — mô tả quyết định suy ra từ code, chờ owner/reviewer xác nhận.
- Ngày soạn: 18/11/2026.
- Không coi đây là biên bản quyết định lịch sử hoặc kết quả nghiệm thu.

## Bối cảnh
Xác nhận vé và gọi dịch vụ email không có một transaction chung. Lỗi mạng có thể khiến kết quả gửi không rõ.

## Quyết định thể hiện trong source
Confirm thêm OutboxEvent cùng session với reservation. Publisher lấy pending bằng SKIP LOCKED, gửi SQS và ghi published_at. Consumer kiểm tra event, dùng NotificationDelivery và job UUID5; dispatch commit SENDING trước I/O, giữ nội dung để retry và ghi UNKNOWN khi kết quả không chắc chắn.

## Phương án thay thế
Gửi email đồng bộ trong request làm tăng latency và không giải quyết atomicity DB/provider. Gửi message rồi mới lưu vé có thể báo vé chưa tồn tại. Exactly-once xuyên DB, queue và provider không được source này bảo đảm.

## Hệ quả và đánh đổi
Có thể publish trùng giữa SQS send và DB commit. Có độ trễ email và cần vận hành retry/DLQ/webhook. ACCEPTED/SENT khác DELIVERED; UNKNOWN không tự coi là gửi thành công. Không xác nhận provider runtime chỉ từ việc có file Brevo.

## Bằng chứng
booking/service.py:transition; notifications/service.py:publish_batch,consume; notifications/jobs.py:dispatch; notifications/adapters.py.

## Kiểm chứng còn cần
Fault sau SQS send trước commit; redelivery; lỗi provider; crash sau SENDING; webhook trùng; vé bị hủy trước gửi. Chưa đọc loop worker/ack và chưa chạy end-to-end.
