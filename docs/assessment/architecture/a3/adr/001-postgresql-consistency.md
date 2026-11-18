# ADR-001-postgresql-consistency: PostgreSQL bảo vệ nhất quán đặt chỗ

- Trạng thái: Draft — mô tả quyết định suy ra từ code, chờ owner/reviewer xác nhận.
- Ngày soạn: 18/11/2026.
- Không coi đây là biên bản quyết định lịch sử hoặc kết quả nghiệm thu.

## Bối cảnh
Nhiều API instance có thể nhận yêu cầu đồng thời. Một user không được có hai lượt ACTIVE trong một ca; cùng slot không được cấp hai vé.

## Quyết định thể hiện trong source
Mô tả quyết định thể hiện trong source: dùng khóa hàng User → LabSession SHARE → SessionSeat theo thứ tự ổn định, kết hợp partial unique indexes và FK ghép. Dùng clock_timestamp của DB cho điều kiện thời gian.

## Phương án thay thế
Khóa chỉ trong bộ nhớ của một API instance không phối hợp được các instance. Khóa Redis riêng đòi hỏi xử lý lease/partition; optimistic retry trên unique constraint đơn thuần có thể giảm khóa nhưng cần quy trình retry và xử lý race rõ ràng.

## Hệ quả và đánh đổi
Đổi lại là thời gian chờ khóa và phụ thuộc DB. Service chọn slot trong capacity; DB chỉ CHECK slot>=0. Source có kiểm tra đăng ký theo event nhưng DB không có unique index theo event. Không chứng minh không deadlock hoặc đạt throughput khi chưa có bài tải.

## Bằng chứng
app/modules/booking/repository.py:lock; service.py:hold,transition; app/models.py:Reservation,SessionSeat; migrations/versions/0001_labseat.py.

## Kiểm chứng còn cần
Chạy concurrent same-slot/same-user/different-slot; kiểm tra invariant DB, timeout, deadlock và p95 theo VU/RPS. Đã đọc shared/http.py xác nhận transaction context; vẫn cần test lỗi commit và rollback qua HTTP.
