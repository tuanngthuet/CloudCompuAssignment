# Tài khoản và ngân sách TV1

## Tình trạng đến 14/11/2026

Đã xác minh AWS CLI bằng profile tv1, tài khoản 403030570855,
IAM user tv1-network. Đã đọc danh sách AZ và VPC tại us-east-1.
Đã tạo plan bootstrap S3 thành công: 6 add, 0 change, 0 destroy.
Chưa chạy apply; chưa xác nhận quyền tạo/xóa hoặc triển khai thành công.

| Hạng mục | Trạng thái / việc còn làm |
|---|---|
| Account nhóm | STS xác nhận 403030570855 |
| IAM TV1 | Console và CLI đọc VPC/AZ đạt; quyền tạo/xóa và thao tác S3 chưa kiểm chứng bằng apply |
| Root MFA | Pending — nhờ chủ tài khoản xác nhận |
| IAM user MFA | Pending — chưa có bằng chứng xác nhận |
| IAM TV2/TV3/TV4 | Quản trị kiểm đủ user và scope; chưa xác nhận đầy đủ |
| Region | us-east-1 theo contract; CLI đã đọc được tài nguyên trong vùng này |
| Plan / credit | Console hiển thị Free plan, còn 120 USD |
| Expiry | Console hiển thị 161 ngày còn lại, đến 22/04/2027 |
| Billing | Xem được credit; Current month và Forecasted month end vẫn Access denied |
| Quota | Pending — đã đọc được AZ; chưa xác minh hạn mức và mức sử dụng VPC/EIP/NAT |
| Budget | Dự kiến 90 USD, dự phòng 30 USD; chưa xác nhận đã cấu hình cảnh báo |
| Repo và remote | origin trỏ https://github.com/tuanngthuet/CloudCompuAssignment.git; nhánh tv1/w1-package đã đồng bộ, working tree clean theo log trước lần sửa tài liệu này |
| Triển khai AWS | Chưa chạy apply; chưa có bucket state hoặc outputs mạng được xác nhận từ triển khai này |

Các trạng thái trên dựa trên log và nội dung Console người dùng cung cấp;
không phải kết quả truy cập AWS trực tiếp từ môi trường tạo tài liệu.

Mật khẩu mặc định đã từng chia sẻ: từng thành viên đổi riêng; không lưu credential vào repo. Không tạo key root, không dùng chung mật khẩu root, không tự nâng Paid plan.

## Quyền cần review với quản trị

TV1 cần quyền đọc/tạo/tag/sửa/xóa các VPC, subnet, route table, associations, IGW, EIP, NAT, SG/rules và VPC endpoints trong scope được cấp. Cần đọc AZ, VPC/CIDR; tạo/cấu hình bucket state (versioning, SSE, public block, ownership, policy). Quyền quota/billing/budget có thể do chủ tài khoản thực hiện.

Backend S3: ListBucket trên bucket; GetObject/PutObject trên từng key state; GetObject/PutObject/DeleteObject trên key `.tflock`. Không cần quyền DeleteObject cho chính file state để hoạt động bình thường. Chỉ cấp prefix cần thiết; không cấp mọi thành viên quyền đọc mọi state vì state có thể chứa secret. SSE-S3 không cần tự tạo KMS CMK. Bucket policy Deny HTTP không tự cấp Allow; IAM của người dùng vẫn phải cho phép các thao tác.

Gói không tạo IAM policy cho người khác và không tự gắn AdministratorAccess. Nếu API báo AccessDenied, gửi action/resource/error đã che secret cho quản trị.

## Ngân sách theo contract

Credit hiển thị tại thời điểm kiểm tra: C = 120 USD.
Cần đối chiếu điều kiện áp dụng của credit với các dịch vụ dự kiến sử dụng.

- Ngân sách dự kiến B = 0,75 × 120 = 90 USD.
- Dự phòng = 0,25 × 120 = 30 USD.
- Ngưỡng cảnh báo dự kiến: 45 USD / 72 USD / 90 USD
  tương ứng 50% / 80% / 100% của B.

Chưa xác nhận đã tạo AWS Budget hoặc kiểm tra nhận thông báo.
Budget là cảnh báo, không tự ngắt tài nguyên hoặc bảo đảm hóa đơn bằng 0.
Kiểm tùy chọn credits/refunds để cảnh báo phản ánh usage phù hợp;
theo dõi riêng số dư credit và ngày hết hạn.

Chưa kết luận 120 USD đủ cho toàn hệ thống vì chưa hoàn thiện
ước tính thời gian chạy, lưu lượng và chi phí của các thành viên.
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

## Kiểm tra local và AWS mới nhất

- Windows Terraform 1.17.2: fmt, validate và mocked contract tests PASS
  theo kết quả Terminal người dùng cung cấp.
- AWS CLI 2.40.1: đã đăng nhập profile tv1 và xác minh danh tính bằng STS.
- Đã đọc VPC tại us-east-1:
  vpc-0c7b260a1f39fa5b3, default=true, CIDR 172.31.0.0/16.
- Plan bootstrap S3 đã lưu thành bootstrap.tfplan:
  6 add, 0 change, 0 destroy.
- Bucket dự kiến: labseat-lab-tfstate-403030570855-tv1.
- Chưa chạy apply; plan và mock tests không chứng minh tài nguyên
  đã được tạo hoặc hạ tầng tích hợp đã hoạt động.