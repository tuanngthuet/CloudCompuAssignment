# Tài khoản và ngân sách TV1

## Tình trạng đến 12/11/2026

Người dùng đã gửi bằng chứng Console đăng nhập IAM user tv1-network và xem VPC mặc định tại Sydney. Điều này chỉ chứng minh quyền đọc đã quan sát, không chứng minh quyền tạo ở us-east-1 hoặc CLI login. Chưa đọc AWS thật từ môi trường tạo gói này.

| Hạng mục | Trạng thái / việc còn làm |
|---|---|
| Account nhóm | Đã có theo Console; xác minh lại bằng STS trước deploy |
| IAM TV1 | Console xem VPC đạt; CLI/create/delete/S3 Pending |
| Root MFA | Nhờ chủ tài khoản xác nhận; TV1 IAM không tự làm root |
| IAM user MFA | Cấu hình nếu được cấp quyền; không chia sẻ password/token |
| IAM TV2/TV3/TV4 | Quản trị kiểm đủ user và scope; không suy diễn từ tên user |
| Region | Contract us-east-1; chuyển Console/CLI cùng vùng |
| Plan / credit / expiry | Pending — xem Billing thực; không assume 100/200 USD |
| Quota | Pending — VPC, EIP, NAT, AZ; TV2/3 kiểm EC2/RDS riêng |
| Budget | Pending — tính theo credit thực còn hiệu lực |
| Repo và remote | Gói độc lập; repo chung/nhánh/PR chờ nhóm chốt |

Mật khẩu mặc định đã từng chia sẻ: từng thành viên đổi riêng; không lưu credential vào repo. Không tạo key root, không dùng chung mật khẩu root, không tự nâng Paid plan.

## Quyền cần review với quản trị

TV1 cần quyền đọc/tạo/tag/sửa/xóa các VPC, subnet, route table, associations, IGW, EIP, NAT, SG/rules và VPC endpoints trong scope được cấp. Cần đọc AZ, VPC/CIDR; tạo/cấu hình bucket state (versioning, SSE, public block, ownership, policy). Quyền quota/billing/budget có thể do chủ tài khoản thực hiện.

Backend S3: ListBucket trên bucket; GetObject/PutObject trên từng key state; GetObject/PutObject/DeleteObject trên key `.tflock`. Không cần quyền DeleteObject cho chính file state để hoạt động bình thường. Chỉ cấp prefix cần thiết; không cấp mọi thành viên quyền đọc mọi state vì state có thể chứa secret. SSE-S3 không cần tự tạo KMS CMK. Bucket policy Deny HTTP không tự cấp Allow; IAM của người dùng vẫn phải cho phép các thao tác.

Gói không tạo IAM policy cho người khác và không tự gắn AdministratorAccess. Nếu API báo AccessDenied, gửi action/resource/error đã che secret cho quản trị.

## Ngân sách theo contract

Gọi C là credit thực còn dùng được cho dịch vụ dự kiến. Ngân sách B = 0,75 × C; dự phòng 0,25 × C. Cảnh báo 50%, 80%, 100% của B. Ví dụ C=100 USD (chỉ ví dụ, chưa xác nhận) thì B=75 USD, ngưỡng 37,50 / 60 / 75 USD. Budget là cảnh báo, không tự ngắt tài nguyên hay bảo đảm hóa đơn bằng 0. Kiểm tùy chọn credits/refunds trong bộ lọc budget để không che usage thực; đồng thời theo dõi riêng balance và expiry.

## Bảng ước tính để hoàn thiện sau kiểm tra giá

Chưa điền đơn giá vì chưa xác minh giá hiện hành, thời gian chạy và plan tài khoản. Đây là mẫu tính, không phải báo giá cuối.

| Thành phần | Công thức dự kiến | Owner |
|---|---|---|
| NAT Gateway | 1 × giờ chạy × giá/giờ + GB xử lý × giá/GB | TV1 |
| Public IPv4 | số địa chỉ tính phí × giờ × giá/giờ | TV1/TV2 |
| S3 state | GB-tháng + PUT/GET + versions | TV1 |
| Truyền dữ liệu xuyên AZ/Internet | GB theo từng chiều/tuyến × đơn giá | TV1/nhóm |
| EC2/EBS/ALB | số máy và giờ thực + dung lượng + LCU | TV2 |
| RDS/S3 app | giờ DB + lưu trữ/backup + requests | TV3 |
| CloudWatch/SNS | logs/metrics/alarms/notifications | TV2 |

So sánh phiên demo theo giờ với chạy thật 730 giờ/tháng trong AWS Pricing Calculator; tính cả app_b dùng NAT AZ A. Ghi URL estimate, ngày, Region, đơn vị và giả định vào report trước M4. Không kết luận credit đủ khi chưa tính.

Nguồn: https://calculator.aws/ ; https://aws.amazon.com/vpc/pricing/ ; https://developer.hashicorp.com/terraform/language/backend/s3
