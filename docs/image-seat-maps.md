# Sơ đồ phòng từ ảnh

Trong **Quản trị → Sơ đồ phòng**, chọn ca và tải ảnh PNG/JPEG/WebP tối đa 5 MB, tối đa 2048 px mỗi chiều. Bấm **Nhận diện phòng**. Ảnh không cần nền xám hoặc các phòng tô màu khác nhau; cần có đường biên tứ giác khép kín nhìn thấy được.

Hệ thống nhận diện hình chữ nhật, vuông, bình hành và các tứ giác lồi kín. Giữ các hình nhỏ bên trong, bỏ khung lớn bao ngoài. Hai phòng chung cạnh vẫn được tách; nếu không có đường biên phân chia thì hệ thống không tự suy đoán ra hai phòng. Tùy chọn diện tích phòng tối thiểu (mặc định 400 px²) giúp bỏ chữ/chi tiết nhỏ. Nền ảnh và màu tô không quyết định sức chứa hoặc loại phòng.

## Chỉnh sửa

- **Chọn phòng**: bấm một vùng để mở Cài đặt phòng. Nhập tên (tối đa 30 ký tự, không trùng) và **Số người được đăng kí** (1–100.000). Bấm Áp dụng hoặc Lưu sơ đồ phòng. Mỗi phòng bắt buộc nhập sức chứa; không có lựa chọn ghế đơn.
- **Xóa phòng**: nút trong phần cài đặt xóa vùng đang chọn khỏi bản nháp; không sửa pixel ảnh gốc.
- **Thêm phòng**: kéo chuột hoặc chạm kéo trên ảnh để tạo hình chữ nhật, rồi nhập tên và số người. Tọa độ được quy đổi về ảnh gốc ở mọi kích thước màn hình. Escape hủy thao tác kéo. Phòng mới không được chồng phòng khác; chung cạnh được phép.
- **Lưu sơ đồ phòng** lưu toàn bộ phòng còn lại và phòng kéo thêm. Chỉnh tên/sức chứa được giữ trong bản nháp khi chuyển chọn phòng; chưa lưu sẽ có cảnh báo khi rời trang/đổi ca/nhận diện lại.

Nếu không tìm được tứ giác, ảnh vẫn tải thành công để admin kéo thêm phòng bằng tay. Cần ít nhất một phòng để lưu. Sơ đồ đã có lịch sử đăng kí vẫn khóa sửa để bảo toàn đăng kí và QR.

## Người đăng kí

Chọn đúng vùng phòng trên ảnh hoặc chọn tên phòng trong danh sách bên dưới. Hiển thị số suất còn lại/tổng sức chứa. Nhiều tài khoản cùng đăng kí phòng đến sức chứa, mỗi tài khoản tối đa một suất trong ca. Giữ suất 3 phút, xác nhận, hủy, QR và Checkin giữ nguyên. Hồ sơ đủ họ tên/CCCD/email vẫn bắt buộc cho ca thi.

## API và lưu trữ

- `POST /admin/rooms/{room_id}/seat-map/image`: multipart `file`, `min_area` tùy chọn (16–10000, mặc định 400). Trả ảnh PNG lossless, kích thước ảnh, detector `quadrilateral-v1`, image_key/revision và các tứ giác points/runs. Không còn nhận diện theo tolerance nền.
- `PUT /admin/rooms/{room_id}/seat-map/image`: revision, image_key, min_area và regions. Mỗi vùng gồm id, kind=`zone`, label, capacity và points gồm đúng bốn cặp tọa độ nguyên theo thứ tự quanh hình. Có thể bỏ vùng tự nhận diện và thêm vùng mới; không gửi runs từ client.
- Backend xác thực admin/CSRF, ảnh thuộc ca, revision, tứ giác lồi, không tự cắt, nằm trong ảnh, không chồng lấn, tên/id không trùng và sức chứa. Runs/mask được dựng lại ở server. Giới hạn 500 phòng và 100.000 runs. Không tin x/y/width/runs do client gửi.
- JSON layout có detector `quadrilateral-v1`; không cần migration schema. Seat/slot nội bộ được tái sử dụng cho từng phòng/suất, giữ cơ chế khóa và chống vượt sức chứa hiện có.
- Ảnh vẫn dùng đường dẫn `[S3_PREFIX/]rooms/<id>/maps/<uuid>.png` với storage adapter hiện có. API task role giới hạn quyền vào prefix ảnh tương ứng.

Nhận diện dùng OpenCV headless và NumPy, pin trong requirements. Phân tích cạnh/contour, xấp xỉ tứ giác, kiểm tra bằng chứng cạnh, loại hình bao ngoài và bản sao của nét viền. Giới hạn một luồng OpenCV/worker. Tài liệu kỹ thuật: [OpenCV contours](https://docs.opencv.org/4.12.0/d9/d8b/tutorial_py_contours_hierarchy.html), [polygon/shape descriptors](https://docs.opencv.org/4.10.0/d3/dc0/group__imgproc__shape.html).

Ảnh và kiểm thử mới: [kết quả kiểm tra](../evidence/current/README.md).

## Cập nhật số suất khi đang chọn

Ảnh sơ đồ đã công bố và ảnh đại diện ca dùng cache trình duyệt 24 giờ (`Cache-Control: public, max-age=86400`) khi tham số `v` khớp tên file của ảnh hiện tại. URL do ứng dụng tạo đã có phiên bản; thay ảnh sẽ đổi URL. URL không có/sai phiên bản, ảnh preview qua tham số `key`, response lỗi và dữ liệu nghiệp vụ vẫn `no-store`. Cache chỉ áp dụng nội dung ảnh, không áp dụng số suất còn lại hoặc JSON sơ đồ; lần tải đầu vẫn đọc S3 qua API, không dùng Redis cache ảnh.

Số suất vẫn được cập nhật nền. Ảnh, SVG và các nút danh sách giữ nguyên khi chỉ thay số suất/trạng thái/lựa chọn; không tải lại cả sơ đồ mỗi 5 giây. API `/lab-sessions/{id}/seats` trả thêm `layout_revision`; geometry chỉ tải lại khi đổi ca hoặc revision thay đổi. Nếu một phòng thật sự hết suất, lựa chọn phòng đó sẽ bị bỏ để tránh thao tác dựa trên dữ liệu cũ. Xem [kiểm thử](testing/concurrency.md).
