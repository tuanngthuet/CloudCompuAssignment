# Review source bổ sung

## Giao dịch HTTP
app/shared/http.py:db_session mở Session và db.begin, yield cùng db cho route. Thoát bình thường commit; ngoại lệ đi qua context manager rollback. Sau giao dịch nghiệp vụ, nếu active_user_id tồn tại thì cập nhật hoạt động bằng Session.begin riêng. Lỗi ở giao dịch hoạt động không hoàn tác giao dịch nghiệp vụ đã commit. Chưa test vòng đời response trên phiên bản FastAPI triển khai.

## Route và lỗi
app/main.py include các router trực tiếp, không thêm prefix. Problem giữ status/code; IntegrityError được ánh xạ 409 conflict; DBAPIError 503 db_unavailable. Request validation 422. /healthz chỉ trả trạng thái/version, /readyz thực hiện SELECT 1; không chứng minh Redis/email đều hoạt động.

## CLI
app/cli.py chỉ khai báo seed, create-user, queue-settings, queue-recover. Seed bị chặn ngoài local/test. File CLI này không chứa publisher/worker receive-consume-delete loop. Entrypoint thực tế là app/events.py, vốn đã có trong ZIP nguồn. Đã kiểm tra receive → consume → delete; không cần bổ sung file này.

## Kiểm tra gói
Đã sửa dòng trống trong bảng Markdown; đã xuất 7 ERD PNG/SVG bằng Graphviz từ sơ đồ có sẵn. Chưa thực thi app, migration hoặc thao tác AWS. ADR vẫn Draft chờ owner xác nhận.
