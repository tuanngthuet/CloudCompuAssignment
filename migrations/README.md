# Schema LABSEAT

Một baseline duy nhất: `versions/0001_labseat.py`, revision `0001_labseat`; head hiện tại `0002_platform`. File chứa DDL cố định của 16 bảng, khóa, CHECK constraints, indexes, defaults và policy queue ban đầu; không import ORM models hoặc dùng Base.metadata.create_all để tạo schema.

```bash
python -m app.migrate
# Docker Compose:
docker compose run --rm migrate
```

- Database trống: áp baseline và0002_platform để tạo toàn bộ schema hiện tại và một policy queue mặc định tắt. Không tạo user, ca, vé hoặc gửi email.
- Database đang ở `0009_current_event_fields`: lệnh app.migrate kiểm schema khớp baseline đóng băng, gồm bảng/cột/types/nullability/defaults, FK, PK, unique/CHECK constraints và partial-index predicates; yêu cầu queue policy tồn tại. Chỉ khi khớp mới đổi marker sang `0001_labseat` trong cùng transaction. Không chạy lại CREATE TABLE, backfill hoặc sửa dữ liệu nghiệp vụ; giữ policy/epoch/check-in đã cấu hình.
- Database ở0001_labseat: preflight duplicate email chuẩn hóa/CCCD, thêm unique indexes và26 bảng/cột platform; giữ email chưa xác minh, backfill last_activity_at=now và checkin_close_mode=manual cho lịch hiện có. Không gửi email hoặc seed dữ liệu.
- Database ở head mới: chạy lại không thay đổi dữ liệu.
- Revision không được nhận diện, schema không khớp, hoặc bảng tồn tại nhưng không có revision: dừng; không tự stamp/reset hoặc đoán cấu trúc.

PostgreSQL advisory lock serialize các process migrate, kể cả fresh install và chuyển marker đồng thời. Toàn bộ kiểm tra và đổi marker nằm cùng transaction; lỗi phải rollback.

Khi chuyển marker dùng **python -m app.migrate**, không dùng trực tiếp alembic upgrade/stamp: Alembic không còn file của revision đã gộp để tìm đường đi. Database trống có thể dùng `python -m alembic -c migrations/alembic.ini upgrade head`. Revision `0002_platform` là thay đổi additive tiếp theo, không sửa baseline đã áp dụng.

`downgrade base` xóa toàn bộ schema ứng dụng, chỉ dùng database test disposable khi chủ động xóa dữ liệu. Không downgrade schema để rollback image. Thay đổi tiếp theo thêm revision mới có down_revision=0001_labseat; không sửa định nghĩa baseline đã áp dụng.

Tests chỉ chạy APP_ENV=test với TEST_DATABASE_URL kết thúc `_test`. Bộ test kiểm fresh roundtrip, chuyển marker giữ mọi bảng nghiệp vụ, drift guards, unknown revision, database chưa có marker và nhiều process đồng thời. [Deployment](../docs/deployment/aws.md), [rollback](../docs/deployment/rollback.md).

Nếu có duplicate, migration dừng atomically; operator rà soát và sửa theo tài khoản thực, không tự merge/xóa. Fresh ca mặc định checkin_close_mode=end_at. Không downgrade0002 trên dữ liệu staff/scheduler thực để rollback image; downgrade test có thể không biểu diễn role/audit mới.
