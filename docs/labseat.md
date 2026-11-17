# Sử dụng LABSEAT

[Đặc tả hệ thống chi tiết](dac-ta-he-thong.md) mô tả đầy đủ nghiệp vụ, dữ liệu, API và vận hành.

Giao diện tại `/`, OpenAPI tại `/docs` và `/openapi.json`. Source nằm trong `app/`; [kiến trúc ECS](architecture/current.md), [migration](../migrations/README.md).

## Local

Chạy các lệnh trong [README](../README.md). Docker Compose cung cấp app, PostgreSQL và shared images volume. Profile `events` cung cấp ElasticMQ, publisher và worker dùng mock email; `queue` cung cấp Redis; `multi` thêm app-peer tại localhost:8001 dùng chung DB/Redis/ảnh. Queue mặc định tắt trong PostgreSQL. Seed chỉ dành cho database demo mới, yêu cầu SEED_PASSWORD riêng. Không reset hoặc seed database đang sử dụng.

## Tài khoản và hồ sơ

Đăng kí tài khoản, đăng nhập, mở Tài khoản để chỉnh hồ sơ. Email bắt buộc khi lưu; điện thoại tùy chọn, có nhập phải hợp lệ. Ca thi yêu cầu họ tên, CCCD 12 chữ số và email trước khi vào hàng chờ, giữ suất hoặc xác nhận. Ca thực hành không áp điều kiện hồ sơ ca thi. Email/CCCD/điện thoại chỉ hiển thị cho chủ tài khoản và quản trị khi tra cứu vé.

Ảnh đại diện nhận JPEG/PNG/WebP tối đa 5 MB, chuẩn hóa thành JPEG vuông 256×256. Menu tài khoản hiển thị ảnh/họ tên hoặc tên tài khoản, hỗ trợ bàn phím và đóng bằng Escape. API hồ sơ: GET/PUT `/me/profile`; ảnh: GET/POST/DELETE `/me/avatar`. Mọi thao tác ghi cần phiên đăng nhập và CSRF.

## Ca và phòng

Quản trị tạo ca thi/thực hành với ảnh, địa điểm, mô tả và lịch mở/đóng đăng kí, bắt đầu/kết thúc. Ảnh ca chuẩn hóa 1280×720. Trang danh sách nhóm ca theo trạng thái đăng kí; chọn ca để xem thông tin và phòng còn suất.

POST/PATCH `/admin/events` nhận multipart `data` JSON và `poster`; tạo mới cần ảnh và schedule. API kiểm admin/CSRF, thời gian, phòng và trùng lịch. Lịch có đăng kí bị khóa chỉnh sửa; nút mở/đóng check-in lưu riêng và vẫn sử dụng được. [Sơ đồ phòng từ ảnh](image-seat-maps.md) quản lí vùng phòng và sức chứa.

## Đăng kí và vé

Chọn phòng → giữ suất tối đa 3 phút và không quá giờ đóng đăng kí → xác nhận. PostgreSQL kiểm thời gian, suất trống và một đăng kí hiệu lực mỗi người/ca. Hết hạn giữ suất thì không xác nhận được; hủy áp thời hạn nghiệp vụ. Vé nằm trong Tài khoản, gồm mã QR và thông tin đăng kí. Xác nhận vé tạo Outbox cùng transaction; lỗi email không hủy vé.

POST `/holds`, `/holds/{id}/confirm`, `/reservations/{id}/cancel` nhận Idempotency-Key 8–128 ký tự ASCII chữ/số/._:-. Cùng người/key/operation/payload trả lại response đã commit; đổi nội dung trả 409. Replay không kéo dài hold. GET `/me/tickets` trả trạng thái hiện tại; GET `/me/tickets/{id}/qr` trả QR chủ tài khoản.

## Check-in

Quản trị chọn ca trong Quản lí ca và bấm Mở check-in. Quét QR hoặc nhập mã vé/mã đăng kí ở Checkin để xem vé, ca/phòng và hồ sơ người đăng kí. Chỉ vé CONFIRMED trong ca đang mở mới có nút Xác nhận check-in. Quét/tra cứu không đổi trạng thái vé. Quản trị quyết định thời điểm mở/đóng, không có cửa sổ giờ cố định. [Hướng dẫn check-in](deployment/checkin.md), [camera và HTTP](deployment/camera.md).

## Bảo mật và lưu trữ

Session, CSRF, role và queue policy lưu PostgreSQL, dùng chung các API tasks. Ảnh private qua local shared volume hoặc S3; object key được kiểm phạm vi. Ảnh thay/xóa được dọn sau commit, lỗi cleanup cần bảo trì. Logger ghi route template, không ghi hồ sơ, mã QR hoặc URL capability. Storage không có transaction chung với DB nên cần giám sát object mồ côi.
