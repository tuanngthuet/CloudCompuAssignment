# LABSEAT — triển khai AWS ngày 17/11/2026

Ứng dụng đang phục vụ tại **https://labseat.id.vn**, phiên bản `0.6.0`, schema `0002_platform`. Đây là kiểm chứng triển khai và kết nối thực; không thay thế nghiệm thu tải, diễn tập sự cố hoặc restore.

## Cấu hình thực tế

- Region Sydney (`ap-southeast-2`), ALB HTTPS với chứng chỉ ACM đã cấp; HTTP chuyển sang HTTPS. DNS Tenten dùng ALIAS ở tên miền gốc.
- Hai API tasks chạy trên hai AZ; publisher và worker mỗi service có một task. Cả ba rollout hoàn tất, sử dụng image digest bất biến. Đã ghi last-good release sau database smoke và maintenance dry-run.
- ASG tối thiểu 2, tối đa 6 máy `t3.small`, root EBS 30 GB. ECS có thể tăng số máy để đủ chỗ cho task triển khai/maintenance; số máy đang chạy không cố định ở mức tối thiểu.
- RDS PostgreSQL private, Multi-AZ; backup tự động lưu **1 ngày** theo lựa chọn của chủ hệ thống để phù hợp giới hạn Free plan. Terraform vẫn mặc định 30 ngày cho môi trường khác và không cho tắt automated backups qua biến retention.
- Managed Redis có primary/replica qua hai AZ, automatic failover bật; TLS và ACL riêng cho admission/runtime, operator và events. Hàng đợi admission đã bật bằng CLI operator sau kiểm tra runtime ACL.
- Ảnh lưu S3 private; Terraform state trên S3 riêng, có mã hóa, versioning và lockfile. API, publisher, worker, maintenance và execution có IAM roles riêng.
- Brevo key/sender được xác minh qua API; key lưu SSM, chỉ worker nhận key. Đã tạo webhook transactional với Bearer token. SNS nhận cảnh báo đã xác nhận.
- Database mới; tạo tài khoản quản trị riêng. Không chuyển dữ liệu local hoặc seed phòng/ca/vé mẫu.

## Kiểm chứng đạt

| Phạm vi | Kết quả |
|---|---|
| Public HTTPS | `/`, `/healthz`, `/readyz`, `/readyz/queue` trả 200; release/version đúng, queue ready |
| ECS release | API2/publisher1/worker1 RUNNING, rollout COMPLETED; đúng image digest; PostgreSQL schema smoke thành công |
| Đăng nhập | Admin login, role admin, Secure/HttpOnly session cookie, logout thu hồi truy cập |
| RDS | Kết nối TLS có xác minh hostname/CA; runtime role riêng, schema head đúng; ngân sách max_connections được kiểm tra |
| Redis | TLS admission/runtime readiness và PubSub qua events ACL thực tế thành công |
| S3 | Put/get/delete đối tượng synthetic bằng API task role thành công; dọn cả version/delete marker của đối tượng kiểm tra |
| Brevo webhook | Không token trả403; token hợp lệ với JSON hỏng trả422, không thêm dữ liệu webhook giả |
| Quyền tạm | Gỡ quyền đọc RDS master secret và các parameter/policy bootstrap admin/operator sau khởi tạo |
| Terraform | Final plan: `No changes. Your infrastructure matches the configuration.` |

Kiểm tra source: 11 roots/modules Terraform validate và toàn suite mock35 pass trước bản sửa dashboard cuối; module observability rerun3 pass, có thêm bài kiểm tra managed Redis không sinh metric dimension null. Kiểm tra deployment driver9 pass; format/diff checks đạt. Không dùng mock tests để suy ra kết quả cloud.

Các lỗi phát hiện khi apply thật đã được sửa: giới hạn region cũ, ECS AMI yêu cầu root volume30 GB, loại EC2 không được Free plan cho phép, RDS retention30 ngày bị Free plan từ chối, Redis ACL/auth representation gây cập nhật lặp và dashboard dùng EC2 Redis dimension khi managed Redis không có instance ID.

## Chưa nghiệm thu

Chưa đo tải100 VU/30 RPS/15 phút, p95/SLO; chưa diễn tập AZ/Redis/RDS failover hoặc restore/RPO/RTO. Chưa thử camera trên Android/iOS thật hoặc chứng minh thư Brevo đến inbox/bounce thực. Không tuyên bố các hạng mục này đã đạt.

Log triển khai, cấu hình, state metadata và thông tin truy cập được giữ riêng tại `.local/production/`; không đưa secret, mật khẩu quản trị, token hoặc tfvars vào evidence công khai.
