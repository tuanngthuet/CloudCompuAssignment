# W1-TV3 Dữ liệu quyền truy cập và phục hồi

Thiết kế dùng RDS PostgreSQL 16 private, Single-AZ, lưu trữ mã hóa và backup 7 ngày. S3 private chứa ảnh trong `rooms/` và gói phát hành trong `releases/`. Runtime dùng instance profile, ghi được trong `rooms/` và có quyền đọc gói phát hành. Cấu hình nhạy cảm của app được lấy từ SecureString dưới `/labseat/lab/`.

SQL tham chiếu kiểm hai ràng buộc đăng ký theo người/ca và chỗ/ca, cùng thao tác giải phóng hold quá hạn trong transaction. TV4 sở hữu migration chính thức. Hướng dẫn thao tác và phạm vi kiểm chứng nằm tại [runbook TV3](../../docs/tv3/data-iam-recovery.md).

**Pending weekend**. Ghép subnet/SG và log group thật, áp dụng module, cấp SecureString, review migration với TV4, kiểm query DB, quyền runtime và ảnh A → B trên AWS. Bài restore có đo thời gian thuộc cửa sổ kiểm chứng tuần 2.
