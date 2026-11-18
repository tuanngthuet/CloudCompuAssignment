# Bằng chứng B1/B2 — b1b2-20261117a

Theo cấu trúc evidence trong kế hoạch sprint. Báo cáo chỉ chứa số liệu và UUID kỹ thuật; không có mật khẩu, token hoặc DATABASE_URL.

## 1. Nguồn và thời điểm

- Website: https://labseat.id.vn; AWS `ap-southeast-2`.
- Snapshot RDS: **21:57:08 ngày 18/11/2026, UTC+7**, giao dịch `REPEATABLE READ READ ONLY`.
- ECS audit task: `98c3ead9a9114155b31c3ff4d72a60c3`; log `/labseat/lab/app`, stream `api/app/98c3ead9a9114155b31c3ff4d72a60c3`.
- Đếm theo UUID của batch, vì tên event đã được người dùng đổi trên web.
- HTTP chỉ đọc cùng đợt: `/events`, sơ đồ/ảnh phòng, ảnh poster và seats của lịch.
- Đợt ghi tài liệu không seed, sửa lịch, cấp phiên hoặc chạy tải.

## 2. Kết quả B1 tại snapshot

| Kiểm tra | Kết quả |
| --- | --- |
| Student/admin/staff | 500 / 2 / 6; tất cả đã xác minh email |
| Event/lịch | 12 event: 6 exam, 6 practice; 24 lịch |
| Trạng thái event | 11 ACTIVE, 1 CANCELLED (Practice 10) |
| Reservation | 303: 300 CONFIRMED, 1 CHECKED_IN, 2 CANCELLED |
| Email job gắn đăng ký của tài khoản batch | 303 SKIPPED |
| Staff assignment | 6 phân công, 6 staff, 6 lịch được phủ |
| Invariants | 7 truy vấn trong `scripts/tests/db-invariants.sql` đều 0 dòng vi phạm |

Lượt seed ban đầu tạo 300 đăng ký (298 CONFIRMED, 1 CHECKED_IN, 1 CANCELLED). Lượt smoke đầu bổ sung một đăng ký hủy; tổng hiện tại đã thay đổi do thao tác demo. Không dùng tổng 300/301 của lịch sử làm tổng hiện hành.

## 3. Kết quả B2 tại snapshot

- Cả **12 ảnh sơ đồ và 12 poster trả HTTP 200**.
- Lịch đại diện mỗi ca khớp manifest về nhãn, `seat_id`, capacity và số vùng. Snapshot DB xác nhận hai lịch mỗi ca cùng số vùng/sức chứa.
- Số vùng Exam 01–Practice 12: `4, 5, 12, 11, 33, 11, 6, 20, 18, 4, 34, 42`.
- Chỗ/lịch tương ứng: `180, 225, 540, 495, 1485, 495, 270, 900, 810, 68, 1530, 1890`.
- Practice 10 bị loại khỏi `/events` công khai vì CANCELLED; không phải mất dữ liệu hoặc thiếu ảnh.
- 100 fixture session thuộc 100 user riêng; **0 còn hiệu lực**. Hạn từ 04:26:46 đến 04:28:24 ngày 18/11/2026, UTC+7. Không chạy smoke đọc/ghi mới với gói đã hết hạn.

## 4. Bằng chứng kiểm thử và triển khai trước snapshot

- PostgreSQL 17 disposable với schema `0002_platform`: đã kiểm seed, tạo 100 phiên, booking qua service, chạy lại không nhân đôi, 7 invariants và cleanup bộ nền.
- Các stage tùy chỉnh ảnh đã kiểm riêng giữ ID/mã QR/trạng thái vé và chạy lại không tăng revision; các lần giảm/gỡ vùng có guard bảo vệ lịch sử đặt chỗ.
- Các stage áp dụng cấu hình cuối của Practice 07–12:

| Ca | Stage | ECS task |
| --- | --- | --- |
| Practice 07 | bio-map | `b9fdcdb7182f44e7af0541df6385d2d2` |
| Practice 08 | com | `b9fe42323e514a8bafe0078947a06d07` |
| Practice 09 | elec | `039216f8d8884c15904165e0d43a17e0` |
| Practice 10 | mechanic | `adfce21b85e3407daf498df2e4677018` |
| Practice 11 | physics | `70ed03933f3849cba735f564c5c99c60` |
| Practice 12 | chemistry | `3b9b5f1f2950470dbbf888824c9a752a` |

Ảnh poster/sơ đồ của từng stage được đối chiếu SHA-256 với preview sau khi áp dụng. Đây là kiểm tra artifact/DB/API, không thay thế bằng chứng luồng admin upload/nhận diện cho B2.

## 5. Giới hạn kết luận

Chưa có bằng chứng kiểm lại toàn bộ seed/cleanup sau tất cả tùy chỉnh cuối; guard/SQL còn phụ thuộc tên cũ. Nguồn/quyền dùng ảnh và tiêu chí 6 ảnh/4–8 vùng chưa được chốt; helper smoke chưa hỗ trợ đủ ảnh mới và session đã hết hạn. Vì vậy chưa đóng B1/B2.

Nội dung từng bước và việc còn lại được ghi tại [B1 dataset](../../../docs/assessment/functional/dataset.md) và [B2 hướng dẫn bàn giao](../../../scripts/assessment/data/README.md).
