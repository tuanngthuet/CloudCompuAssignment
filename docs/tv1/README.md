# TV1 tuần 1 — LabSeat

Bộ chuẩn bị Terraform theo contract 3.0: mạng và S3 lưu state. Chưa triển khai AWS. Không tạo EC2, ALB, RDS hoặc IAM role của các thành viên khác. Root network nằm dưới `infra/bootstrap/network-stack/` để giữ phạm vi TV1; cuối tuần có thể nối module vào root tích hợp chung.

## Bước bạn làm ngay trên Windows

1. Giải nén thư mục `tv1-week1` vào `E:\dtđm\` hoặc thư mục bạn chọn.
2. VS Code → File → Open Folder → chọn thư mục `tv1-week1` (có README.md).
3. Terminal → New Terminal; chạy từ thư mục này:

```powershell
terraform version
aws --version
powershell -NoProfile -ExecutionPolicy Bypass -File .\docs\tv1\check.ps1
```

Lệnh kiểm tra tải provider qua Internet; có thể mất vài phút ở lần đầu. Nó chỉ chạy fmt, init không backend, validate và mock tests; không gọi AWS API và không dùng credential. `ExecutionPolicy Bypass` chỉ áp dụng cho tiến trình con này. File khóa provider được đóng gói; không tự `init -upgrade`. Nếu lỗi, dừng và gửi nguyên thông báo (không gửi secret).

Nếu không muốn chạy script, thực hiện thủ công:

```powershell
terraform fmt -check -recursive
terraform -chdir=infra/modules/network init -backend=false -lockfile=readonly
terraform -chdir=infra/modules/network validate
terraform -chdir=infra/modules/network test
terraform -chdir=infra/bootstrap/state init -backend=false -lockfile=readonly
terraform -chdir=infra/bootstrap/state validate
terraform -chdir=infra/bootstrap/state test
terraform -chdir=infra/bootstrap/network-stack init -backend=false -lockfile=readonly
terraform -chdir=infra/bootstrap/network-stack validate
```

Thủ công chỉ dùng ở bản giải nén chưa init backend thật. Script dùng thư mục metadata tạm độc lập để không ghi đè backend đã cấu hình.

## Git sau khi kiểm tra

Chỉ dùng `git init` nếu đây là thư mục độc lập chưa có repo. Nếu đã có repo nhóm, chép file theo namespace; hợp nhất `.gitignore` và mẫu PR, không ghi đè mù.

```powershell
git init
git switch -c tv1/w1-package
git status --short
```

Review nội dung trước khi add/commit. Chỉ commit code, tài liệu và `.terraform.lock.hcl`. Không commit `.terraform`, state, tfvars thật, backend.hcl, plan, log có secret hoặc AWS credentials.

## Bộ bàn giao

- `infra/modules/network/`: module độc lập, 5 inputs và 8 outputs contract.
- `infra/bootstrap/state/`: bucket state riêng, private, mã hóa AES256, versioning, TLS-only, chống xóa nhầm.
- `infra/bootstrap/network-stack/`: root chỉ nối module network; backend S3 có lockfile.
- `docs/tv1/network.md`: thiết kế/CIDR/SG/giới hạn.
- `docs/tv1/deploy-weekend.md`: trình tự cuối tuần, output và dọn tài nguyên.
- `docs/tv1/account-budget.md`: quyền, credit/quota và chi phí còn phải xác minh.
- `docs/tv1/evidence/validation.txt`: kết quả thực chạy trong môi trường tạo gói.
- `handoff/tv1.json`, `report/parts/tv1.md`: trạng thái trung thực và checklist.

## Điểm dừng trước AWS

Không chạy apply chỉ vì validate/test thành công. Chưa xác minh CLI auth, quyền IAM/S3/EC2, AZ khả dụng, quota NAT/EIP/VPC, CIDR trùng, plan/credit/budget. Người dùng đã đăng nhập Console `tv1-network`; việc đó không tự đăng nhập AWS CLI.

Region contract là `us-east-1`; không dùng VPC mặc định đã thấy ở Sydney. Không tự nâng Paid plan hoặc mua domain. Hạn cập nhật: M4 23/11/2026, M5 30/11/2026.
