# Đăng kí, mật khẩu và xác minh email — 17/11/2026

Release production: `ecs-0.6.0-account-flow-20261117T062419Z`. API/publisher/worker rollout COMPLETED; exact-release DB smoke và maintenance dry-run đạt, last-good release đã được ghi. Không đổi schema hoặc reset dữ liệu production.

- Đăng kí yêu cầu email hợp lệ, chuẩn hóa trim+lower và không trùng email chính đã lưu; tài khoản tạo mới chưa xác minh email. Không tự gửi thư khi tạo tài khoản.
- Bỏ mức tối thiểu 12 ký tự cho đăng kí/đổi/đặt lại mật khẩu và công cụ local tạo/reset tài khoản. Mật khẩu vẫn phải không rỗng/không chỉ chứa khoảng trắng; API giữ giới hạn tối đa 1024 ký tự và xác nhận trùng nhau.
- CCCD là trường tùy chọn, rỗng vẫn được đăng kí ca thi; nếu cung cấp vẫn kiểm định dạng 12 chữ số và uniqueness như trước. Ca thi vẫn yêu cầu họ tên và email đã xác minh.
- Banner đầu trang xuất hiện với tài khoản chưa xác minh (kể cả đang đổi email), dẫn tới `#email-verification` để gửi liên kết. Banner ẩn với khách, sau đăng xuất và khi trạng thái email đã xác minh được cập nhật.

## Kiểm chứng

- [Backend](account-flow-tests.log): 90 passed trên PostgreSQL/Redis disposable; gồm email trùng/cạnh tranh, mật khẩu ngắn, xác minh từ email đăng kí và exam queue/hold/confirm khi CCCD rỗng. Không dùng database production cho suite destructive.
- [JavaScript](account-flow-ui-tests.log): 39 passed, gồm payload email/mật khẩu ngắn và vòng đời banner.
- [Chrome HTTP thật local](account-flow-browser-tests.log): 5 passed ở 320/390/768/1024/1440 px; đăng kí, link banner, profile email tự có, CCCD optional, reload/logout/login và không lỗi JavaScript.
- [Production](account-flow-verification.json): schema email required/minimum password 1; Chrome mobile đăng nhập admin hiện có, mở link banner tới xác minh, CCCD không required, banner ẩn sau logout, không overflow/console errors. Không tạo tài khoản hay gửi email thật để chạy smoke test.

Ảnh local synthetic: [form mobile](account-register-390.png), [form desktop](account-register-1440.png), [banner mobile](account-unverified-390.png), [banner desktop](account-unverified-1440.png).

Đây là kiểm chứng luồng tài khoản và giao diện; không thay kết quả nghiệm thu Brevo tới inbox thật hoặc kiểm thử tải AWS.
