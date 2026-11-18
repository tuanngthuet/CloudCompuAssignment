# Kiểm tra A3

- Phân tích AST ba file Python nguồn; không import app, không kết nối DB/AWS.
- 26 bảng: tập tên khớp model và chuỗi migration 0001 → 0002.
- Tập tên cột khớp ở từng bảng.
- 28 ánh xạ FK, gồm khóa ghép: khớp model và migration.
- Sơ đồ ERD chỉ dùng FK khai báo; không đoán FK từ tên cột.
- Các sequence được đọc thủ công từ route/service/repository đã nhận.
- Chưa chạy migration, HTTP integration, concurrent booking, SQS/email hay failover.
- Chưa so sánh tất cả type/default/CHECK/index bằng database diff.
- Chưa có commit SHA của bộ source. SHA-256 file được ghi trong source-manifest.json.
- Mermaid cung cấp dạng .mmd và Markdown; chưa xác minh bằng renderer Mermaid trong môi trường này.
