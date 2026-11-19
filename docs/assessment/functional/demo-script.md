# B3 — Kịch bản demo trên ca SAT có sẵn

Theo đúng [B3 trong sprint](../../sprints/ke-hoach-nghiem-thu-4-ngay.md#b3-kiểm-thử-chức-năng-regression-và-demo). Website: https://labseat.id.vn. Chỉ dùng ca và tài khoản B1/B2 có sẵn; không tạo ca demo mới.

## 1. Dữ liệu và chuẩn bị

- Ca: **Kì thi SAT - Ca demo**, lịch `1a7402d1-a9df-5053-8282-a4ab4d33e813`, 14:14–16:14 ngày 23/11/2026, giờ Việt Nam. Đọc lại trạng thái/giờ thực tế khi quay; hạn đăng ký đã ghi nhận là 20:14 ngày 21/11/2026.
- Student475 đã có vé CONFIRMED, phòng **72A+72B (A2-411)**; dùng mật khẩu riêng bạn đã chọn sau reset, không dùng mật khẩu fixture cũ. Không hủy vé này chỉ để dựng lại cảnh.
- Nếu chưa có clip đặt vé từ đầu, dùng student có sẵn chưa đăng ký SAT (ví dụ student477 sau khi kiểm tra trạng thái thực tế). Ghi đúng tài khoản trong video; dùng QR của chính vé vừa đặt cho đoạn check-in, không ghép thành một người từ hai vé khác nhau.
- Student476 dùng bài giữ rồi hủy **giữ chỗ**, không phải hủy ca. Browser quan sát dùng tài khoản khác, hai context độc lập.
- Staff04 **Dương Tú Anh** đã được phân công lịch SAT đầu tiên. Admin01 dùng quản trị, mở/đóng check-in và CSV. Credentials riêng ở bộ tài khoản private B1/B2 mà người dùng đã có; không quay mật khẩu/file này.
- Điện thoại iPhone XR/Safari: ghi phiên bản OS/browser thực tế. Quét bằng nút **Quét QR trong LABSEAT**, không dùng ứng dụng Camera ngoài website để thay bài kiểm.
- Email hiện disabled sau cửa sổ kiểm thật. Khi quay có thể lấy QR trên website; không bật email hoặc gửi thêm thư chỉ để lấy lại ảnh.

## 2. Video B3 do người dùng cung cấp: student → admin/staff check-in

| Bước | Thao tác | Kết quả cần thấy |
| --- | --- | --- |
| 1 | Student đăng nhập, mở SAT, đối chiếu lịch/poster/sơ đồ và chọn phòng còn chỗ. | Đúng ca/phòng, hiển thị khả dụng. Nếu xuất hiện admission/hàng chờ thì quay cả bước được cấp lượt. |
| 2 | Giữ suất; browser độc lập quan sát cùng ca. | Có thời hạn giữ; số chỗ trên browser kia cập nhật không reload. Có thể dùng student476 để quay hủy giữ và trả chỗ ở clip riêng. |
| 3 | Xác nhận đăng ký, mở vé của đúng student đó. | Vé CONFIRMED, ca/lịch/phòng khớp; có QR trên website. Nếu chỉ quay vé student475 đang có thì không nhận cảnh đó là đã quay đặt vé từ đầu. |
| 4 | Admin ghi cấu hình check-in ban đầu, chọn đúng SAT. Chủ động mở check-in để demo trước giờ thi. | Trạng thái mở đúng lịch; không sửa ngày ca hoặc sơ đồ/sức chứa. |
| 5 | Staff04 trên điện thoại chọn SAT → Quét QR → cấp quyền camera → quét vé trên laptop. | Camera thật mở; tra đúng thông tin vé, chưa tự check-in. |
| 6 | Đối chiếu rồi bấm Xác nhận check-in một lần. | Thành công; vé chuyển CHECKED_IN. |
| 7 | Quét lại cùng QR trong LABSEAT. | Báo đã check-in, không tạo lượt mới. |
| 8 | Student tải lại vé; admin mở đúng lịch trong Danh sách đăng kí và Xuất CSV. | Vé/dòng CSV đúng trạng thái/phòng/tài khoản. Che thông tin người khác khi quay. |
| 9 | Admin trả lại cấu hình check-in như trước khi quay. | Đối chiếu đã phục hồi. Baseline cũ là đang đóng, tự đóng theo giờ kết thúc; ưu tiên baseline thực tế vừa ghi. |

Giữ lỗi và kết quả thực tế nếu xảy ra; không cắt dựng thành thành công. Bản nộp che mật khẩu, CCCD, link auth và QR còn hiệu lực. Không có thời lượng video hoặc số ảnh bắt buộc được mục B3 quy định.

## 3. Ảnh người dùng đã cung cấp

1. **Thư xác nhận SAT có QR và nhãn Inbox**: chứng minh thư vé hiển thị đúng ca/lịch/phòng/QR. Bản gốc có QR còn hiệu lực giữ private; bản dẫn xuất đã che QR/mã đăng ký được thêm vào report theo yêu cầu người dùng. Không thay đổi bản gốc.
2. [Reset thành công](../../../evidence/assessment/20261119T034356Z-b3-functional/screenshots/password-reset-success.png): trang ghi “Đã đặt lại mật khẩu. Đăng nhập để tiếp tục.” Không có mật khẩu hoặc URL auth trong khung ảnh.

Nguồn và hash hai ảnh ở [manifest.json](../../../evidence/assessment/20261119T034356Z-b3-functional/manifest.json). Người dùng đã xác nhận đăng nhập bằng mật khẩu tự chọn; server challenge consumed/session cũ revoked là bằng chứng bổ sung, không nhận ảnh reset đơn lẻ là bằng chứng login thành công.

## 4. Còn cần ảnh nào?

Sprint không yêu cầu ảnh riêng cho từng case nếu đã có bằng chứng kiểm thử hoặc video rõ ràng. Ưu tiên bổ sung **video bước 1–9**, gồm camera thật và check-in/lặp.

- Nếu video chưa rõ kết quả trên điện thoại: chụp màn hình **check-in thành công** và **quét lại báo đã check-in**.
- Nếu chưa có đoạn đăng nhập sau reset: có thể chụp trang đã đăng nhập đúng student475, che thông tin nhạy cảm. Đây là bổ sung cho xác nhận người dùng/server đã có, không phát sinh bài reset mới.
- Realtime hai browser và danh sách/CSV có thể xuất hiện trong video; không bắt buộc chụp thêm ảnh trùng nội dung.
- Không dựng ảnh cho các cửa sổ tải/fault/restore chưa chạy. Khi nhóm có lịch, B3 lấy probe nghiệp vụ và bảy invariants đúng trước/sau cửa sổ đó.

## 5. Đối chiếu các bài còn lại

Ma trận [test-cases.csv](test-cases.csv) và [report.md](report.md) lưu quyền UI/API ba vai, CRUD, admission/heartbeat/expiry, replay/race, hết hạn/hết chỗ/trùng lịch, QR sai/đóng/lặp và CSV. Video thao tác tay không thay test race hoặc truy vấn invariants.

UI ba vai và sai lịch đã bổ sung bằng hai lịch SAT có sẵn, không tạo ca; payload QR được nhập qua ô lookup nên không gọi đó là lần quét camera mới. Cửa sổ email thật bổ sung có hai thư DELIVERED, Inbox do người nhận xác nhận; email đã tắt lại. X01–X03 chờ C3/C4/C5/B4/B5 có lịch; không đánh PASS các mục này trước khi thực hiện.

Video do người dùng cung cấp sau. Báo cáo sẽ ghi link kho nhóm, thời lượng và quyền truy cập khi nhận được; hiện chưa có link/video để nghiệm thu V01. Không tạo thêm video trong lần dọn output này.
