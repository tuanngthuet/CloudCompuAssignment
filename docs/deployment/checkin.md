# Check-in do quản trị điều khiển

## Mở hoặc đóng tiếp nhận vé

Vào **Quản trị → Quản lí ca**, chọn ca đã lưu. Phần **Check-in** hiển thị Đang đóng/Đang mở, với nút **Mở check-in** hoặc **Đóng check-in**. Thay đổi lưu ngay, không cần bấm Lưu ca và không sửa lịch. Có thể đổi sau khi đã có đăng kí; không bị schedule_locked.

Ca mặc định đóng. Quản trị chủ động quyết định thời điểm tiếp nhận; check-in không có gate giờ bắt đầu; giờ kết thúc chỉ là deadline khi chọn end_at. Booking/confirm/cancel áp thời hạn riêng. Thay đổi check-in được ghi trong `checkin_policy_events` cùng transaction, gồm ca, người quản trị, trạng thái và thời điểm.

## Quét / nhập → xem thông tin → xác nhận

- **Quét QR** mở popup; đọc được mã sẽ đóng camera và tự tra cứu. Quét không tự check-in.
- Nhập mã vé (nội dung QR) hoặc mã đăng kí UUID: tự tra cứu sau khi ngừng gõ, hoặc bấm **Tra cứu vé**.
- Kết quả có thông tin vé, ca/phòng/thời gian, trạng thái, thời điểm đã check-in nếu có; cùng hồ sơ người đăng kí: họ tên, tài khoản, CCCD, email, số điện thoại tùy chọn và avatar nếu có.
- Chỉ vé CONFIRMED và ca đang mở mới hiện **Xác nhận check-in**. Vé HELD/EXPIRED/CANCELLED/CHECKED_IN vẫn xem được nhưng không hiện nút.
- Bấm xác nhận mới POST check-in. Server kiểm tra lại trạng thái vé và cờ mở ca trong transaction có khóa. Nếu ca vừa bị đóng sau tra cứu, từ chối409/checkin_closed và UI tải lại thông tin.
- Xác nhận lặp lại cùng vé CHECKED_IN trả thời điểm cũ, không thêm check-in/audit thứ hai. Check-in không bị hoàn tác khi đóng ca.

Tra cứu cũ trả về muộn không được ghi đè hồ sơ của mã đang nhập. Khi đổi mã hoặc đăng xuất, thông tin người trước được xóa khỏi UI. Thông tin được chèn bằng textContent; không render HTML từ tên/hồ sơ. Tra cứu và ảnh đại diện dành cho admin hoặc staff trong scope được giao; không thêm hồ sơ vào catalogue/public QR/Outbox.

## API

| Method/path | Yêu cầu | Kết quả |
|---|---|---|
| POST /admin/check-ins/lookup |Admin + CSRF, `{ticket_code: string}` (20..100 ký tự; mã QR hoặc UUID) |ticket/session/profile, can_check_in, reason; không đổi trạng thái vé |
| PATCH /admin/lab-sessions/{id}/check-in |Admin + CSRF, `{enabled: boolean}` strict |session_id/checkin_enabled; idempotent khi trạng thái không đổi |
| POST /admin/check-ins |Admin + CSRF, mã vé hoặc UUID |Xác nhận dưới các khóa User → LabSession SHARE → SessionSeat; kiểm checkin_enabled từ DB |
| GET /admin/check-ins/{reservation_id}/avatar |Admin |Ảnh đại diện private, không dùng đường dẫn /me của người quản trị |

Không có quyền đọc/sửa hồ sơ chung cho student hoặc guest. Cache-Control:no-store áp dụng cho JSON/ảnh private. POST check-in dùng cùng điều kiện manual flag, không thể bypass bằng gọi trực tiếp.

Policy update khóa User(actor) → LabSession UPDATE, nhất quán với thứ tự booking; khóa exclusive này serialize với check-in SHARE. Lookup chỉ là snapshot; quyết định cuối nằm ở POST có khóa và trạng thái mới nhất. Cờ lưu PostgreSQL dùng chung mọi API instance, không phải config riêng process.

## Migration và rollout

Schema head là `0002_platform`; baseline đã có checkin_enabled mặc địnhfalse và bảng audit. Migrate database đang dùng không thay đổi trạng thái mở/đóng của ca, tài khoản hoặc vé. Local: build image → `docker compose run --rm migrate` → cập nhật app/worker/publisher. Xem [migration runbook](../../migrations/README.md).

Không downgrade schema để rollback image. Chỉ chọn image tương thích schema và manual check-in policy; kiểm tra trong staging trước rollout. Chưa có AWS rollout được thực thi/xác minh.

QR ảnh trong email có cơ chế hết hạn riêng sau giờ kết thúc; file QR đính kèm và QR trong tài khoản vẫn dùng được để tra cứu. Check-in cuối cùng luôn theo trạng thái vé và cờ quản trị, không theo việc ảnh email còn hiển thị.

[Evidence và kiểm thử](../../evidence/current/README.md).

## Hạn đóng và phân công staff

Head `0002_platform` thêm `checkin_close_mode`: end_at (ca mới), custom (mốc tương lai khi mở), manual. Lịch hiện có được giữ manual. PATCH check-in nhận thêm `close_mode`/`closes_at`; GET trả effective flag. Effective flag là enabled AND Event ACTIVE AND DB clock chưa tới deadline. Không có gate15 phút hoặc giờ bắt đầu; ca end_at/custom hết hạn bị từ chối ngay cả khi scheduler chưa chạy. Muốn mở sau hạn phải chọn custom tương lai hoặc manual. Scheduler ghi policy audit với actor null/source scheduled.

Quản trị người dùng tạo role staff, rồi Phân công staff chọn ca và tài khoản. Staff đăng nhập, xác minh email, mở Ca được giao, chọn ca và quét/nhập mã để xem hồ sơ trước khi xác nhận. Backend kiểm assignment/role/status lại trong transaction confirmation. Thu hồi phân công hoặc lock tài khoản dừng quyền check-in. Staff không có quyền CSV, cấu hình ca, người dùng hoặc mở/đóng check-in. CCCD mặc định che; nút đối chiếu đầy đủ có audit, email/điện thoại không trả cho staff. Avatar có endpoint scoped riêng.
