# ADR-002-idempotency: Lưu response idempotency trong PostgreSQL

- Trạng thái: Draft — mô tả quyết định suy ra từ code, chờ owner/reviewer xác nhận.
- Ngày soạn: 18/11/2026.
- Không coi đây là biên bản quyết định lịch sử hoặc kết quả nghiệm thu.

## Bối cảnh
Client có thể gửi lại sau timeout; tạo hold lại không được kéo dài thời gian giữ.

## Quyết định thể hiện trong source
Khi client gửi Idempotency-Key hợp lệ, scope theo user_id và SHA-256 của key. Fingerprint gồm operation và payload canonical JSON. Replay response nếu giống; trả 409 nếu key dùng cho payload khác. Record và mutation dùng cùng DB session.

## Phương án thay thế
Cache trong RAM mất khi process restart; Redis cache có lifecycle khác DB. Chỉ làm idempotent theo trạng thái không phát hiện key dùng nhầm payload và không luôn trả response cũ.

## Hệ quả và đánh đổi
Header là tùy chọn. Không tuyên bố mọi request tự được deduplicate. Khóa User có thể serialize nhiều mutation; lưu response tăng dữ liệu. Chưa thấy chính sách retention idempotency trong phần source nhận được.

## Bằng chứng
app/modules/booking/idempotency.py:execute; router.py; app/models.py:IdempotencyRecord.

## Kiểm chứng còn cần
Retry cùng key; cùng key khác payload/operation; khác user cùng key; timeout sau commit; replay không đổi expires_at. Cần kiểm tra transaction owner.
