# Báo cáo TV1 tuần 1

Package W1-TV1 phiên bản 1.0.1, contract 3.0. TV1 đã chuẩn bị cấu hình mạng và S3 lưu Terraform state độc lập. Theo kết quả Terminal người dùng cung cấp, kiểm tra fmt, validate và mocked contract tests trên Windows đều PASS. Chưa triển khai AWS.

## Mã nguồn và kết quả

| Hạng mục | Kết quả | Bằng chứng |
|---|---|---|
| Repo cá nhân | https://github.com/nguyendang44/labseat-tv1 | Log push người dùng cung cấp |
| Nhánh | tv1/w1-package | Log Git |
| Commit nền | 9043e85 | Log Git sau khi kiểm tra |
| Terraform | 1.17.2 windows_amd64 | Terminal người dùng |
| AWS CLI | 2.40.1 | Terminal người dùng; không phải Python runtime của app |
| fmt / validate / mock tests | PASS theo thông báo cuối script trên Windows | docs/tv1/evidence/windows-check-summary.txt |
| AWS plan / apply | Chưa chạy | Không có evidence AWS deployment |

File windows-check-summary.txt là bản tóm tắt trích log người dùng, không phải log đầy đủ hoặc CI. Commit 9043e85 được ghi sau khi chạy kiểm tra; chưa có log CI gắn trực tiếp commit đó. File validation.txt giữ lịch sử kiểm tra tại môi trường tạo gói, nơi provider bị chặn socket. Kết quả Windows bổ sung bằng chứng sau đó; không sửa lịch sử thành một lần chạy thành công giả.

## Cấu hình đã chuẩn bị

Module network gồm 2 AZ/6 subnet, IGW, một NAT, S3 Gateway Endpoint cho tầng app và ba Security Groups. ALB nhận HTTP 80, app nhận 8000 chỉ từ ALB, DB nhận 5432 chỉ từ app; không mở SSH public. Hai subnet DB dùng route table không có default route ra Internet. Region us-east-1 và VPC CIDR mặc định 10.20.0.0/16 theo contract, vẫn phải kiểm tra AZ/CIDR thật trước apply.

S3 state riêng có AES256, versioning, Block Public Access, TLS-only và chống xóa nhầm. Backend dùng lockfile; deployment root kiểm account ID. Chưa tạo compute/data/IAM của thành viên khác.

## Trạng thái bàn giao

Phần code đã vượt kiểm tra local theo log người dùng. Chưa khẳng định toàn bộ W1-TV1 Ready for integration vì hồ sơ credit/quota/ngân sách và quyền thực tế chưa đầy đủ. Chưa Accepted; G1 chưa kiểm chứng. Chưa có IDs thật của mạng đồ án để bàn giao.

TV2 review module network và hồ sơ cuối tuần. Handoff xuất tên output ngay; chỉ bổ sung IDs thật sau apply và kiểm tra thực tế. Mock tests không chứng minh kết nối, IAM hoặc khả năng chịu tải trên AWS.

## Việc còn lại

1. Đính kèm log Windows đầy đủ nếu cần reviewer kiểm từng test. Không cần chạy lại chỉ để thay đổi báo cáo; có thể dùng log đã lưu ở local-evidence/check-windows.txt.
2. TV1 và quản trị xác minh root MFA, CLI auth, quyền tạo/xóa tài nguyên, quota, credit/hạn dùng và budget.
3. Kiểm AZ, CIDR trùng và plan; review chi phí NAT/EIP trước apply.
4. Triển khai cuối tuần, xuất outputs thật, kiểm private/routes/SG và phối hợp TV2/TV3/TV4 kiểm tích hợp.
5. Hoàn thiện bảng chi phí bằng giá/usage thực. Một NAT là điểm phụ thuộc AZ; chưa đạt dự phòng toàn AZ.

## Mốc nộp và trách nhiệm

M4: 23/11/2026. M5: 30/11/2026. TV1 tự giải thích được subnet, route, SG, state locking và chi phí. AI hỗ trợ tạo code/tài liệu và cập nhật báo cáo theo evidence; kết quả chạy Windows do người dùng cung cấp.
