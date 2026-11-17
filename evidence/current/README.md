# LABSEAT — kiểm chứng bản hiện tại

Ứng dụng0.6.0, schema `0002_platform`; kiểm tra local ngày17/11/2026. Bản local tại http://localhost:8000 dùng HTTP và email mock. Các kết quả local bên dưới được chốt trước triển khai cloud. AWS đã được triển khai và kiểm chứng bước đầu: [biên bản AWS](aws-deployment.md); chưa kiểm chứng email đến inbox thật.

| Phạm vi | Kết quả |
|---|---|
| Backend PostgreSQL/Redis/ElasticMQ | 265 passed toàn suite;14 skipped,33 botocore deprecation warnings. Auth/policy rerun22 passed sau guard token bị purge đồng thời |
| Chrome source UI + mocked business API + camera synthetic |40 passed; thêm6 bài chụp màn hình tính năng platform |
| JavaScript controller |38 passed |
| Terraform |11 roots/modules validate;30 provider-mock tests pass; fmt pass |
| Migration/deployment driver |28 passed, gồm thiếu schema platform phải chặn release, additive schema cho rollback, duplicate preflight và data preservation |
| Email/chính sách |55 passed; soft bounce đến trước lỗi mạng không tạo lần gửi mới |
| Local runtime |API/worker/publisher0.6.0; health/ready pass; `/ui`404; release DB smoke pass |
| Invariants database phục vụ |7 truy vấn đều0 rows |
| SSE local |Kết nối Redis thật, nhận initial invalidation và đóng stream thành công |
| Maintenance |Dry-run trên DB/storage local thành công; không execute purge/GC/ẩn danh trên dữ liệu phục vụ |

Các bài skip là các live-browser suites cần server/fixture riêng và opt-in Redis process fault. Bộ40 Chrome ở đây dùng source assets và HTTP fixture, không lấy mật khẩu quản trị hoặc tạo vé trong DB phục vụ. Camera dùng fake media; không thay thế Android/iOS/phần cứng thật.

Migration đã chạy sau khi dừng API/publisher/worker, pg_dump private và hash trước/sau. Toàn bộ hàng và cột nguyên bản của16 bảng nghiệp vụ khớp:2 users,3 reservations. Không seed/reset hoặc phát lại checkpoint SENT. Thêm10 bảng platform; ca hiện có giữ mode manual, last_activity_at backfill thời điểm nâng cấp. Backup chứa dữ liệu riêng nên ở `.local/backups`, không đưa vào evidence công khai; đường dẫn cụ thể lưu riêng `.local/platform-backup-location`. Không đọc hoặc đổi mật khẩu admin để kiểm chứng.

Ảnh platform dùng dữ liệu synthetic: [admin desktop](platform-admin-1440.png), [admin mobile](platform-admin-390.png), [staff desktop](platform-staff-1440.png), [staff mobile](platform-staff-390.png), [xác minh mobile](platform-guest-390.png). Các ảnh check-in/email khác minh họa luồng tương ứng; không phải chứng minh giao thư thực.

## Kiểm tra thiết kế

`GATE: OPEN 14 (rounds used up)`. Functional Chrome tests pass; checker thiết kế landing page còn14 findings trên cấu trúc ứng dụng hiện có (full-screen hero/section, marketing visual, wrap/container và horizontal rails). Không tuyên bố design gate pass. Danh sách từng finding nằm trong [log](design-gate.log).

Năm waiver có lý do trong [design-waivers.json](design-waivers.json):

- moment-none: không thêm hiệu ứng marketing ngoài phạm vi chức năng ứng dụng.
- cta: không tạo nút đăng kí giả khi danh mục chưa có ca mở.
- text-only: empty state là trạng thái hợp lệ, không thêm ảnh marketing để che nó.
- section-tile: dialog đăng nhập cần vừa nội dung, không ép thành section full-screen.
- copy-fact: không bịa số liệu/địa điểm trong tiêu đề khi không có dữ liệu ca.

Đã giữ focus ring bàn phím và kiểm không tràn màn hình390/1440 cho các màn hình mới. Các rule marketing còn mở không được dùng để suy ra lỗi kiểm tra quyền hoặc nghiệp vụ; chúng vẫn được ghi đầy đủ để review.

## Nghiệm thu môi trường thật

AWS đã được kiểm chứng bước đầu theo [biên bản triển khai](aws-deployment.md): HTTPS, IAM/runtime secrets, placement API qua hai AZ, DB/Redis/S3, đăng nhập và webhook auth. Chưa nghiệm thu inbox/bounce thực; Android/iOS camera; scaling dưới tải, failover, tải100 VU slots/30RPS/15 phút, p95/SLO và restore RPO/RTO. Theo [load test](../../docs/testing/load-test.md), [recovery](../../docs/deployment/recovery.md), [Brevo](../../docs/deployment/brevo.md) và [maintenance](../../docs/deployment/maintenance.md).
