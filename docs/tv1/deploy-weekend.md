# Triển khai và bàn giao cuối tuần

Chỉ thực hiện khi nhóm chốt dùng tài khoản thật, quyền và ngân sách. Không có thao tác apply tự động trong gói.

## 1. Xác thực đúng tài khoản

Console login không thay thế CLI credentials. Nhờ quản trị cung cấp phương án CLI được phép (SSO/role hoặc credential phù hợp); không nhập mật khẩu Console vào `aws configure`, không dùng root key và không đưa secret vào Terraform. Nếu dùng profile, đặt `$env:AWS_PROFILE = "ten-profile-da-cau-hinh"`. Không đưa profile vào module.

```powershell
aws sts get-caller-identity
aws ec2 describe-availability-zones --region us-east-1 --query "AvailabilityZones[?State=='available'].ZoneName" --output table
aws ec2 describe-vpcs --region us-east-1 --query "Vpcs[].{VpcId:VpcId,Cidr:CidrBlock}" --output table
```

Đối chiếu Account với tài khoản nhóm, ARN với user/role được cấp. Nếu AccessDenied, nhờ quản trị bổ sung đúng hành động cho TV1; không tự kết luận tài khoản đã đủ quyền. Kiểm tất cả CIDR associations/peering/VPN nếu có, không chỉ CIDR chính. Kiểm quota VPC/EIP/NAT, quyền S3 tạo bucket, credit và budget bằng Console. Chọn hai AZ được trả về; không tự assume tên a/b đều được cấp.

## 2. Tạo bucket state riêng

Từ thư mục gốc gói:

```powershell
Copy-Item .\infra\bootstrap\state\terraform.tfvars.example .\infra\bootstrap\state\terraform.tfvars
```

Sửa `expected_account_id` là ID nhóm; `state_bucket_name` là tên toàn cục duy nhất (chữ thường, số, dấu gạch ngang), ví dụ ghép project/account/suffix tự chọn. Không dùng bucket chứa ảnh app. Không để placeholder. Sau đó:

```powershell
terraform -chdir=infra/bootstrap/state init
terraform -chdir=infra/bootstrap/state plan -out=bootstrap.tfplan
terraform -chdir=infra/bootstrap/state show bootstrap.tfplan
```

Review bucket, versioning, AES256, public access block, ownership, TLS-only. Nếu đúng tài khoản và đúng scope mới chạy:

```powershell
terraform -chdir=infra/bootstrap/state apply bootstrap.tfplan
terraform -chdir=infra/bootstrap/state output
```

Bootstrap lần đầu dùng local state. Giữ file state riêng tư; không xóa hoặc commit. Bucket có prevent_destroy và force_destroy=false.

## 3. Chuyển bootstrap state lên S3

Sau khi bucket đã tạo:

```powershell
Copy-Item .\infra\bootstrap\state\backend.tf.example .\infra\bootstrap\state\backend.tf
Copy-Item .\infra\bootstrap\state\backend.hcl.example .\infra\bootstrap\state\backend.hcl
```

Điền bucket thật trong backend.hcl, giữ key `labseat/lab/bootstrap.tfstate`, region và lockfile. Không ghi secret vào backend.hcl. Chạy:

```powershell
terraform -chdir=infra/bootstrap/state init -migrate-state -backend-config=backend.hcl
```

Đọc yêu cầu migrate và xác nhận chỉ khi đúng bucket/key. Kiểm object bootstrap.tfstate tồn tại, versioning Enabled, encryption và public block đúng. Giữ bản local backup riêng tư đến khi xác minh chuyển thành công.

## 4. Triển khai mạng

```powershell
Copy-Item .\infra\bootstrap\network-stack\terraform.tfvars.example .\infra\bootstrap\network-stack\terraform.tfvars
Copy-Item .\infra\bootstrap\network-stack\backend.hcl.example .\infra\bootstrap\network-stack\backend.hcl
```

Điền account ID, AZ thực và CIDR không trùng; điền cùng bucket nhưng key `labseat/lab/network.tfstate` khác bootstrap. Không dùng fixture mock để deploy.

```powershell
terraform -chdir=infra/bootstrap/network-stack init -reconfigure -backend-config=backend.hcl
terraform -chdir=infra/bootstrap/network-stack plan -out=network.tfplan
terraform -chdir=infra/bootstrap/network-stack show network.tfplan
```

Plan phải là mạng mới của labseat, 6 subnet/2 AZ, 1 NAT, không đổi VPC mặc định, không có EC2/RDS/IAM. NAT và EIP có thể bắt đầu tính chi phí khi tạo; review ngân sách trước lệnh sau:

```powershell
terraform -chdir=infra/bootstrap/network-stack apply network.tfplan
terraform -chdir=infra/bootstrap/network-stack output
```

Nếu apply lỗi giữa chừng, có thể đã tạo tài nguyên tính phí. Giữ nguyên state, xem lỗi và plan lại; không xóa state hoặc chạy lại bằng root mới để né lỗi.

## 5. Bàn giao outputs và evidence

```powershell
New-Item -ItemType Directory -Force .\local-evidence | Out-Null
terraform -chdir=infra/bootstrap/network-stack output -json | Out-File -Encoding utf8 .\local-evidence\network-outputs.json
```

File output JSON có wrapper type/value/sensitive; TV2/TV3 lấy phần `value` tương ứng. Review trước chia sẻ, không gửi state hoặc plan. Cập nhật handoff bằng IDs thật sau kiểm chứng; hiện handoff chỉ liệt kê output names. Evidence: account/region (che thông tin riêng), Resource map, subnet/routing, NAT/endpoint, SG, budget đã cấu hình. Chỉ claim kiểm tra thật đã chạy.

Cuối tuần nếu nhóm chuyển sang `infra/integration/`, không apply module network lần thứ hai từ state khác. Phải lập phương án di chuyển/import state với khóa và backup; hoặc giữ state mạng riêng, truyền outputs rõ ràng. Không đọc state người khác trong module.

## 6. Dọn tài nguyên

Trước khi xóa: sao lưu dữ liệu và evidence cần giữ; thống nhất ngừng demo. TV2 tháo ALB/ASG/EC2 và TV3 tháo RDS/ENI liên quan trước, nếu không VPC/SG/subnet sẽ DependencyViolation.

```powershell
terraform -chdir=infra/bootstrap/network-stack plan -destroy -out=destroy.tfplan
terraform -chdir=infra/bootstrap/network-stack show destroy.tfplan
# Chỉ chạy sau khi cả nhóm đã chốt dọn và review plan:
terraform -chdir=infra/bootstrap/network-stack apply destroy.tfplan
```

Kiểm NAT, EIP và tài nguyên phụ thực sự biến mất. S3 state được bảo vệ khỏi destroy; giữ đến khi mọi stack đã dọn và evidence lưu an toàn. Nếu muốn xóa bucket: quản trị phải quyết định lưu state/version/lock, chuyển state ra backend khác trước, gỡ bảo vệ một cách chủ động rồi xóa toàn bộ versions sau khi hết phụ thuộc. Không cung cấp script xóa bucket hàng loạt.

## Tài liệu tham khảo

- https://developer.hashicorp.com/terraform/language/backend/s3
- https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/vpc_security_group_ingress_rule
- https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/vpc_endpoint
