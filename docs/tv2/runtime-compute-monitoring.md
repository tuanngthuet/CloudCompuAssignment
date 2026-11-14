# Runtime, compute và giám sát LabSeat

Gói `W1-TV2` theo contract v3. Mốc bàn giao là Thứ Bảy, trạng thái **Ready for integration** sau khi các kiểm tra local và tĩnh đạt. TV1 review tại buổi tích hợp. Trạng thái và bằng chứng kiểm tra nằm trong `handoff/tv2.json`.

## Kiểm tra gói độc lập

Chạy từ thư mục gốc bằng Python 3.12, Terraform và Packer. Hai lệnh `init` tải provider nếu máy chưa có cache. `terraform validate` kiểm tra cấu hình và schema provider mà không cần AWS credentials hay input thật. Chạy `init` và `validate` trong bản sao tạm để giữ các thư mục bàn giao sạch.

```bash
python fixtures/tv2/smoke.py
python scripts/ami/build.py --mode fixture --app-dir fixtures/tv2 --app-version fixture-v1 --check-bundle
bash -n scripts/ami/install-runtime.sh
bash -n fixtures/tv2/start.sh
terraform fmt -check -recursive infra/modules
terraform -chdir=infra/modules/compute init -backend=false
terraform -chdir=infra/modules/compute validate
terraform -chdir=infra/modules/observability init -backend=false
terraform -chdir=infra/modules/observability validate
packer fmt -check scripts/ami/labseat.pkr.hcl
packer validate -syntax-only scripts/ami/labseat.pkr.hcl
```

Fixture mặc định bind `0.0.0.0:8000`. `GET /healthz` kiểm tra process và `GET /version` hiển thị phiên bản fixture. Kết quả chỉ dùng cho smoke test. Với Amazon Linux 2023, script cài runtime chạy `systemd-analyze verify /etc/systemd/system/labseat.service` trước khi bật unit.

## Giao ước ghép module

| Module | Đầu vào v3 | Đầu ra v3 |
| --- | --- | --- |
| `compute` | `vpc_id`, `public_subnet_ids`, `app_subnet_ids`, `alb_sg_id`, `app_sg_id` từ TV1. `app_instance_profile_name` từ TV3. `ami_id` từ bản build TV2. | `alb_url`, `alb_arn_suffix`, `target_group_arn_suffix`, `asg_name`, `launch_template_id`. Có thêm `target_group_arn` và `launch_template_version` cho kiểm tra. |
| `observability` | `alb_arn_suffix`, `target_group_arn_suffix`, `asg_name` từ compute. `db_instance_identifier` từ TV3. `alarm_email` do nhóm cung cấp. | `dashboard_name`, `sns_topic_arn`. Có thêm tên/ARN log group, tên alarm và scaling policy. |

Ví dụ đầu vào dưới đây mang nhãn **MOCK_ONLY**, dùng để đọc tên trường khi chuẩn bị ghép. Các giá trị là nhãn mô tả và không thể dùng để plan/apply.

```hcl
# MOCK_ONLY
vpc_id                    = "MOCK_ONLY_NETWORK_VPC"
public_subnet_ids         = ["MOCK_ONLY_PUBLIC_A", "MOCK_ONLY_PUBLIC_B"]
app_subnet_ids            = ["MOCK_ONLY_APP_A", "MOCK_ONLY_APP_B"]
alb_sg_id                 = "MOCK_ONLY_ALB_SG"
app_sg_id                 = "MOCK_ONLY_APP_SG"
app_instance_profile_name = "MOCK_ONLY_RUNTIME_PROFILE"
ami_id                    = "MOCK_ONLY_RELEASE_AMI"

alb_arn_suffix            = "MOCK_ONLY_COMPUTE_ALB_SUFFIX"
target_group_arn_suffix   = "MOCK_ONLY_COMPUTE_TARGET_GROUP_SUFFIX"
asg_name                  = "MOCK_ONLY_COMPUTE_ASG"
db_instance_identifier    = "MOCK_ONLY_DATA_DB_IDENTIFIER"
alarm_email               = "MOCK_ONLY_NOTIFICATION_EMAIL"
```

TV1 nối các đầu vào ở root module `infra/integration/`. Giữ `environment = "lab"` cho lần tích hợp đầu để log group khớp cấu hình AMI. Hai module nhận giá trị từ root. Module compute đọc metadata của đúng AMI được truyền vào để chọn thiết bị root cho EBS. Subnet của ALB và app thuộc cùng VPC, tách riêng và phủ hai AZ. ALB HTTP dùng dữ liệu giả, forward đến cổng 8000, kiểm `/healthz`. Kiểm `/readyz` riêng để xác nhận kết nối DB.

## Nhận release và build AMI

1. Nhận manifest của TV4 gồm commit/version, dependency lock, revision DB, lệnh build/start/migrate/seed/test và mapping biến. Dùng thư mục release đã rà soát, có `requirements.lock` dạng pip và `start.sh` ở gốc. Nếu release cung cấp lệnh khởi động trong manifest, chuẩn bị `start.sh` theo lệnh đó và dùng `exec` để giữ đúng một process phục vụ tại `0.0.0.0:8000`. Runtime cung cấp venv trên `PATH`. Rà soát để gói chỉ có mã, tài sản và config mẫu. TV3/TV4 kiểm migration và chạy một lần trước khi triển khai bản mới.
2. Chốt AMI nguồn Amazon Linux 2023 x86_64, HVM, EBS, có SSM Agent, thiết bị root `/dev/xvda` và snapshot root không lớn hơn 20 GiB. Chọn subnet private với đường ra cho SSM, kho AL2023 và nguồn dependency. Có thể dùng subnet và SG app đã cấp nếu đáp ứng các đường ra này. Packer kết nối qua Session Manager plugin trên máy chạy build. Tài khoản chạy Packer cần quyền build AMI, dùng SSM session và PassRole cho profile đã chọn. Có thể dùng profile runtime của TV3 nếu nhóm cho phép dùng trên máy build và profile có quyền SSM. Bước bake không khởi động app hay lấy config runtime. [Packer Amazon EBS builder](https://developer.hashicorp.com/packer/integrations/hashicorp/amazon/latest/components/builder/ebs)
3. Khởi tạo plugin Packer rồi build từ bundle thật. Các biến shell trong ví dụ do người tích hợp điền từ hệ thống đã kiểm tra. Manifest Packer lưu AMI ID và metadata bản build.

```bash
packer init scripts/ami/labseat.pkr.hcl
python scripts/ami/build.py \
  --mode release --app-dir "$RELEASE_DIR" --app-version "$APP_VERSION" \
  --region us-east-1 --source-ami "$BASE_AMI_ID" \
  --build-subnet-id "$BUILD_SUBNET_ID" --build-security-group-id "$BUILD_SG_ID" \
  --build-instance-profile "$BUILD_PROFILE_NAME" \
  --manifest evidence/W1-TV2/packer-manifest.json
```

Build trên EC2 tạo AMI private, với EBS gp3 mã hóa và IMDSv2. Tại boot, `labseat.service` khởi động dưới user `labseat`, đọc các khóa đã biết từ Parameter Store qua instance profile rồi truyền vào môi trường của process. Config và secrets runtime chỉ có trên máy đang chạy. Service thử khởi động lại sau lỗi. EC2 ghi log app cục bộ và CloudWatch Agent gửi về `/labseat/lab/app`, mỗi instance một stream. Quy tắc logrotate giữ giới hạn log cục bộ.

| Cấu hình app | Nguồn |
| --- | --- |
| `APP_ENV`, `PORT`, `STORAGE_BACKEND` | Runtime đặt `lab`, `8000`, `s3`. |
| `AWS_REGION`, `APP_VERSION` | Metadata của AMI. |
| `DATABASE_URL` | `/labseat/lab/DATABASE_URL` kiểu SecureString. |
| `S3_BUCKET`, `S3_PREFIX` | `/labseat/lab/S3_BUCKET` và `/labseat/lab/S3_PREFIX` tùy chọn. Prefix rỗng mặc định để app dùng các key `rooms/` theo contract. |

TV3 cấp `ssm:GetParameters` cho các tên trên, `kms:Decrypt` nếu SecureString dùng khóa do nhóm quản lý, quyền S3 theo prefix và `logs:CreateLogStream`/`logs:PutLogEvents` cho stream dưới `/labseat/lab/app`. Terraform quản lý log group và retention. Nhóm xác nhận mapping với release TV4 trước khi apply. Giữ kết quả Parameter Store và URL DB ngoài log, AMI, manifest và Terraform state dùng chung.

## Apply, refresh và kiểm G1

1. Review plan ở `infra/integration/` với AMI chế độ `release` rồi apply trong cửa sổ cuối tuần. Lần đầu ASG tạo hai máy. Ở lần phát hành tiếp theo, thay `ami_id` để Terraform cập nhật Launch Template lên version số mới và khởi động rolling refresh. Giữ khoảng trống capacity cho một máy thay thế khi refresh và chờ trạng thái `Successful` nếu có refresh. [AWS Instance Refresh](https://docs.aws.amazon.com/autoscaling/ec2/userguide/instance-refresh-overview.html)
2. Lấy output từ root tích hợp vào các biến dưới đây. Kiểm tất cả target đang phục vụ có trạng thái `healthy` và hai máy của G1 dùng cùng AMI/version. Xác nhận `/readyz` trên từng máy qua SSM và chạy E2E qua ALB với TV4. Ghi app commit, AMI ID, Launch Template version, schema revision, thời điểm và log/ảnh kiểm chứng đã che bí mật.

```bash
aws autoscaling describe-instance-refreshes --auto-scaling-group-name "$ASG_NAME"
aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names "$ASG_NAME" \
  --query 'AutoScalingGroups[0].Instances[*].[InstanceId,LifecycleState,LaunchTemplate.Version]'
aws elbv2 describe-target-health --target-group-arn "$TARGET_GROUP_ARN"
aws ec2 describe-instances --instance-ids "$INSTANCE_A" "$INSTANCE_B" \
  --query 'Reservations[].Instances[].[InstanceId,ImageId,PrivateIpAddress,PublicIpAddress]'
curl --fail --silent --show-error "$ALB_URL/healthz"
curl --fail --silent --show-error "$ALB_URL/readyz"
```

3. Kiểm dashboard và log stream của từng EC2, kiểm retention 7 ngày, xác nhận email subscription. Nếu log chưa đến, kiểm file `/var/log/labseat/app.log`, agent status, quyền ghi stream và egress; khởi động lại agent qua SSM nếu log group vừa được tạo. Kiểm ứng dụng che bí mật trước khi thu log làm evidence.

```bash
aws cloudwatch get-dashboard --dashboard-name "$DASHBOARD_NAME"
aws logs describe-log-groups --log-group-name-prefix /labseat/lab/app
aws logs describe-log-streams --log-group-name /labseat/lab/app
aws sns list-subscriptions-by-topic --topic-arn "$SNS_TOPIC_ARN"
aws cloudwatch describe-alarms --alarm-names "$WORKLOAD_ALARM_NAME"
aws autoscaling describe-policies --auto-scaling-group-name "$ASG_NAME"
```

Target tracking khởi điểm 300 request/target/phút, warmup và health grace 120 giây. Alarm SNS riêng kích hoạt khi vượt 300 trong cả hai kỳ 60 giây, dùng hai dimensions ALB và target group. `RequestCountPerTarget` dùng `Sum` theo cách ALB công bố metric. Kiểm scaling và alarm bằng tải thật trong G2. [AWS Application Load Balancer metrics](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-cloudwatch-metrics.html)

Nếu refresh lỗi, xem status reason, ASG activity, target health và log qua SSM. Khi cần rollback, dừng refresh đang chạy theo quy trình nhóm, xác nhận schema tương thích với app cũ rồi đặt lại AMI đã kiểm chứng qua Terraform và kiểm health, version, readiness và E2E sau refresh. Giữ AMI trước trong thời gian có thể cần rollback.
