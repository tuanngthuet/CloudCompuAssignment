# Kiểm tra gói A4

- Đọc hai archive và pin commit từ ZIP comment; không fetch nhánh mới hoặc gọi AWS.
- Đối chiếu 17 file được liệt kê trong 4 run manifests của gói functional: tất cả khớp SHA-256 theo quy tắc LF cho text/raw bytes cho PNG. Chi tiết tại [source-hash-audit.json](source-hash-audit.json). Hash khớp chứng minh tính toàn vẹn gói, không chứng minh độc lập thao tác AWS.
- B5: 3/3 PNG khớp hash stage, before=restored và before≠overwritten.
- Source manifests gốc giữ nguyên; summary.md gốc không sao chép để tránh link phụ thuộc repository. Vì vậy danh sách files trong manifest gốc có thể dẫn tới summary không nằm trong gói A4. Manifest A4 mới chỉ liệt kê các file thực sự đính kèm.
- C1: đối chiếu CSV 252 dòng/4 mẫu/status counts với JSON. Không sửa missing values/source_at, không suy load/failover từ baseline.
- 4 sơ đồ có source DOT + SVG + PNG. Sơ đồ baseline kết hợp quan sát và quan hệ kiến trúc, không phải packet trace; sơ đồ PITR/fault ghi rõ chưa chạy.
- Gói chỉ chứa docs/assessment/architecture/a4. Không sửa app, migrations, A1–A3 hoặc chạy lại test ứng dụng.
- Không chốt A4 nghiệm thu khi B4, B5 tích hợp, C4/C5 và đối chiếu sau fault còn thiếu.

Các kiểm tra đóng gói tự động (hash bản sao, link nội bộ Markdown, PNG/SVG và ZIP) được ghi trong [package-checks.json](package-checks.json).
