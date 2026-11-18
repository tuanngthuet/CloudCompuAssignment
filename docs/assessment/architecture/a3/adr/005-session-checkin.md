# ADR-005-session-checkin: Phiên đăng nhập DB và quyền check-in theo ca

- Trạng thái: Draft — mô tả quyết định suy ra từ code, chờ owner/reviewer xác nhận.
- Ngày soạn: 18/11/2026.
- Không coi đây là biên bản quyết định lịch sử hoặc kết quả nghiệm thu.

## Bối cảnh
API chạy nhiều instance; người check-in cần đúng vai trò và phạm vi ca.

## Quyết định thể hiện trong source
LoginSession lưu token_hash và csrf_hash ở DB, expiry 8 giờ lúc tạo. Authenticate đọc phiên và kiểm tra CSRF với request ghi. Admin dùng endpoint riêng; staff phải ACTIVE, email verified và có StaffAssignment. Transition kiểm tra scope lại dưới khóa.

## Phương án thay thế
Session cục bộ cần sticky routing và mất khi thay instance. JWT stateless cần cách revoke/đồng bộ thay đổi quyền. Chỉ kiểm tra vai trò staff mà bỏ assignment làm rộng phạm vi quyền.

## Hệ quả và đánh đổi
DB tham gia mỗi lần xác thực. Secure cookie phụ thuộc COOKIE_SECURE, không mặc định bật trong source; cần kiểm tra cấu hình triển khai. Hồ sơ được che bớt ở staff lookup nhưng endpoint reveal có audit. Không tuyên bố đạt least privilege toàn hệ thống chỉ từ module này.

## Bằng chứng
auth/service.py:authenticate,create_session,cookie; checkin/staff.py; checkin/policy.py:scope,effective; booking/service.py:transition.

## Kiểm chứng còn cần
Test CSRF thiếu/sai, phiên hết hạn, staff chưa xác minh/chưa phân công, đổi assignment đồng thời, đóng check-in và replay check-in. Cần runtime config để xác minh cookie Secure.
