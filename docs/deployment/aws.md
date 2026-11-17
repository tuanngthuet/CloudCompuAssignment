# Local CLI deployment cho ECS

Email dùng [Brevo API](brevo.md). Cấu hình email_backend=brevo, brevo_from_email/email_public_base_url và SSM BREVO_API_KEY khi bật gửi thật.

Các lệnh dưới đây là runbook cho người vận hành sau khi tự phê duyệt AWS deployment/cost. Agent chỉ implement và test local, không chạy các lệnh AWS/apply này. Không hosted CI/CD. Yêu cầu Docker, Python3, AWS CLIv2, Terraform>=1.7 (mock test dùng1.12+ cho state isolation), AWS profile/Identity Center và ACM certificate cùng region. Backend state phải private/encrypted/locked; không commit backend credentials, tfvars, deployment state hoặc AWS secrets.

## Region và đăng nhập IAM qua trình duyệt

Các root state/network hỗ trợ `us-east-1` và `ap-southeast-2`. Khi chọn Sydney, đặt `region="ap-southeast-2"` ở state, network, integration và backend; đặt hai AZ Sydney trong network (kiểm tra AZ thực tế trong tài khoản trước plan). Không đổi region của state đang phục vụ để di chuyển tài nguyên; kiểm kê tài nguyên và state trước khi tạo mới. ECS AMI được lấy qua SSM theo region; ACM certificate phải cùng region với ALB.

AWS CLI v2.32+ hỗ trợ đăng nhập bằng phiên AWS Console:

```bash
aws login --profile labseat-production --region ap-southeast-2
aws sts get-caller-identity --profile labseat-production --region ap-southeast-2
```

IAM identity cần policy `SignInLocalDevelopmentAccess` cho bước đăng nhập; quyền tạo và triển khai hạ tầng vẫn được cấp riêng. Nhập mật khẩu/MFA trực tiếp trên trang AWS. Nếu Terraform/SDK chưa đọc được `login_session`, dùng một profile riêng với `credential_process` gọi đường dẫn tuyệt đối tới `aws configure export-credentials --profile labseat-production --format process`; không in hoặc chép credentials vào source. Xem [AWS CLI console login](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html).

## Kiểm tra giới hạn account trước apply

Kiểm tra account plan bằng `aws freetier get-account-plan-state` và loại EC2 được account cho phép. Free plan có thể từ chối `t3.medium` hoặc RDS backup 30 ngày; giảm retention chỉ sau khi người vận hành chọn chính sách đó. `db_backup_retention_days` mặc định 30, cho phép 1–35 ngày và không cho tắt backup. Giữ `production=true` để không mất RDS Multi-AZ/Redis failover khi đổi thời gian lưu backup. Với account bị giới hạn loại máy, chọn loại được AWS cho phép và kiểm tra lại ngân sách RAM/ENI/task; cấu hình 2 máy `t3.small` có ít RAM dự phòng hơn 2 máy `t3.medium`.

Launch template ECS dùng EBS root 30 GB để đáp ứng snapshot của ECS-optimized AL2023 AMI hiện tại. Khi AMI thay đổi, kiểm tra minimum root volume của AMI trước apply.

## Lần đầu

1. Đọc [audit](../implementation/ecs-audit.md), kiểm account/backend inventory. Repo không có state thật được xác minh. Bootstrap state bằng `infra/bootstrap/state` theo cấu hình main.tf và variables.tf của root đó khi chưa có backend; không dùng state chung giữa hai môi trường. Hai profile là cấu hình thay thế cho môi trường lab; muốn chạy song song phải dùng AWS accounts riêng vì resource names/metric namespaces hiện dùng chung trong account. Dùng profile/region explicit. Ví dụ us-east-1:

   ```bash
   export AWS_PROFILE=labseat-demo AWS_REGION=us-east-1
   export EXPECTED_AWS_ACCOUNT_ID=YOUR_12_DIGIT_ACCOUNT
   export RELEASE_ID=ecs-0.6.0-UNIQUE_SOURCE_REVISION
   aws sts get-caller-identity --profile "$AWS_PROFILE" --region "$AWS_REGION"
   ```

2. Tạo private `.local/network.tfvars` gồm `expected_account_id`, `redis_enabled=true`, `multi_az_nat=false` (production=true), region và AZs nếu đổi. `infra/bootstrap/network-stack/backend.tf` đã khai báo S3 backend; tạo backend.hcl riêng theo example. Review saved plan rồi apply thủ công:

   ```bash
   terraform -chdir=infra/bootstrap/network-stack init -backend-config=/PRIVATE/network-backend.hcl
   terraform -chdir=infra/bootstrap/network-stack plan -var-file="$PWD/.local/network.tfvars" -out="$PWD/.local/network.tfplan"
   terraform -chdir=infra/bootstrap/network-stack apply "$PWD/.local/network.tfplan"
   terraform -chdir=infra/bootstrap/network-stack output -json > .local/network-outputs.json
   python3 - <<'PY'
   import json
   from pathlib import Path
   outputs=json.loads(Path('.local/network-outputs.json').read_text())
   keys=('vpc_id','public_subnet_ids','app_subnet_ids','db_subnet_ids','alb_sg_id','app_sg_id','db_sg_id','redis_sg_id')
   Path('.local/network-input.auto.tfvars.json').write_text(json.dumps({'network':{k:outputs[k]['value'] for k in keys}}))
   PY
   ```

3. Tạo `.local/runtime.tfvars`: `expected_account_id`, `alarm_email`, `acm_certificate_arn`, `email_backend`, `brevo_from_email`, `email_public_base_url`, `redis_enabled=true`, profile values từ `infra/environments/.../terraform.tfvars.example`. Chọn demo EC2 Redis: build cache AMI bằng `scripts/cache/redis.pkr.hcl`, chuẩn bị TLS/ACL/SSM theo cache runbook rồi đặt `redis_ami_id`, `cache_compatibility_verified=true`. Hoặc demo managed single node: `managed_redis=true`, `production=false` và cấp auth token qua `TF_VAR_redis_auth_token` và `TF_VAR_redis_operator_password` từ secret store của người vận hành. Production: managed=true, production=true; network root multi_az_nat=true riêng. Token managed Redis sẽ có trong encrypted Terraform state: giới hạn quyền đọc state. Không truyền token trong command line/history/source.

4. Chọn `image="ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/labseat-lab@sha256:0000000000000000000000000000000000000000000000000000000000000000"` và `bootstrap=true` **chỉ cho lần đầu**. Digest placeholder không chạy: cả ba services desired0 và API scaling min0. Như vậy có ECR/capacity/task templates trước khi push, nhưng chưa phục vụ code trước migration. Copy integration backend example sang backend.tf, cấu hình backend riêng; review plan giữ nguyên RDS/S3/network theo inventory:

   ```bash
   cp infra/integration/backend.tf.example infra/integration/backend.tf
   terraform -chdir=infra/integration init -backend-config=/PRIVATE/runtime-backend.hcl
   terraform -chdir=infra/integration plan -var-file="$PWD/.local/network-input.auto.tfvars.json" -var-file="$PWD/.local/runtime.tfvars" -out="$PWD/.local/runtime.tfplan"
   terraform -chdir=infra/integration apply "$PWD/.local/runtime.tfplan"
   terraform -chdir=infra/integration output -json deployment > .local/ecs-deployment.json
   chmod 600 .local/ecs-deployment.json
   ```

5. Chuẩn bị SSM `/labseat/lab/DATABASE_URL` dạng SecureString bằng công cụ secret riêng, không print ra terminal/repo. RDS cấp master secret do AWS quản lý; tạo DATABASE_URL và role DB đủ chạy additive migrations **trong VPC** qua SSM/operator session; không mở public DB. DB URL dùng `sslmode=verify-full&sslrootcert=/srv/labseat/app/infrastructure/database/rds-global-bundle.crt`; image chứa CA bundle công khai từ https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem. Làm mới bundle từ AWS và build release mới khi CA thay đổi. Khi Redis enabled, cần `REDIS_URL` (rediss://host:6379/0, không embedded credentials/query), `REDIS_USERNAME`, `REDIS_PASSWORD` SecureString, `REDIS_CA_CERT` PEM. Không cấp cache SERVER_KEY/ACL/operator password cho API. Execution role inject SSM khi task start; không tự refresh secret đang chạy. Custom KMS key đặt kms_key_arn và key policy tương ứng. S3 bucket/prefix lấy trực tiếp Terraform task environment.

6. Chạy local tests, build, push, deploy:

   ```bash
   docker compose --profile test run --rm test
   deploy/build.sh
   deploy/push.sh
   deploy/deploy.sh
   deploy/verify.sh
   ```

   build tạo linux/amd64 image; push tag unique vào immutable ECR rồi lưu digest trong `.local/ecs-image-$RELEASE_ID.json`. Deploy register candidate API/worker/publisher definitions từ templates; chạy `python -m app.migrate` bằng one-off ECS task awsvpc private; đợi exit0; mới cập nhật services/desired count và bật API scaling min2/max8. Mọi task dùng image digest. Không migrate trên startup. Migration/smoke cần một slot/ENI thật; timeout mặc định300s, rollout900s; có thể chỉnh TASK_TIMEOUT_SECONDS/DEPLOY_TIMEOUT_SECONDS.

7. Deploy xác minh rollout đúng task definitions, chạy one-off `python -m app.smoke` từ đúng API release image/config, kiểm DB và các bảng/cột release cần (schema head0002_platform), chỉ cho phép rollback image tương thích các cột đang dùng. Maintenance schedule tắt trước migration và chỉ chuyển cùng release/bật sau smoke; rollback cập nhật cả maintenance definition. Sau success mới ghi `.local/ecs-last-good.json`. Bảo quản file này theo môi trường và sao lưu an toàn; script dùng local file lock để chặn hai command đồng thời trong cùng state directory. Dùng DEPLOY_STATE_DIR riêng (ví dụ .local/demo và .local/production) và DEPLOY_CONFIG tương ứng cho từng môi trường; file lock không phối hợp hai máy operator, nên vẫn chỉ một deployer/môi trường. `migrate.sh` có thể chạy riêng sau push: register candidate đúng image và chạy migration; deploy.sh vẫn tự chạy migration idempotent trước rollout. `smoke-test.sh` dùng candidate hiện tại. `verify.sh` hiển thị service counts/events, kiểm rollout và chạy smoke đúng last-good release. Kiểm HTTP `/healthz`, DB `/readyz`, queue `/readyz/queue` riêng. Queue mặc địnhOFF trong DB; enable/recovery bằng `python -m app.queue_admin` theo CLI help qua one-off task/operator trong VPC, không tự tạo marker để bypass recovery.

8. Cập nhật runtime.tfvars `image` thành digest thật, `bootstrap=false` và review/apply plan để source khớp thực tế. Terraform ignore task_definition/desired_count của service vì CLI và autoscaling quản lý, nhưng quản lý task templates/runtime configuration. Sau mọi thay đổi runtime config/secret cần một release deploy mới để dùng template mới. Xác nhận SNS subscription và Brevo sender/domain/API key trước bật email_backend=brevo. Bật email sau template update và rollout; notification đã SKIPPED không tự gửi lại.

## Release tiếp theo và lỗi triển khai

Giữ AWS_PROFILE/AWS_REGION/EXPECTED_AWS_ACCOUNT_ID, DEPLOY_CONFIG và RELEASE_ID explicit. Build → push → deploy; không reuse tag. Runtime config lấy từ Terraform templates, giữ cùng migration history. Không tự retry mutation khi không rõ kết quả; AWS_MAX_ATTEMPTS=1, run-task có client token. Nếu CLI timeout khi register/update/run-task, đối chiếu ECS trước khi thử lại; task có thể đã được tạo dù CLI chưa nhận kết quả.

100/200 rolling, circuit breaker+rollback, ALB drain30s; Uvicorn graceful30s, ECS stopTimeout60s, worker/publisher ngừng nhận việc rồi hoàn tất I/O đang xử lý. Timeout one-off sẽ stop task và báo events; rollout timeout không tự đảo migration hoặc blind retry. Khi script bị Ctrl-C/network timeout, dùng ECS inventory kiểm task còn chạy và stop nếu cần, đặc biệt migration advisory lock.

Smoke sai DB sau ECS rollout success sẽ dừng deploy, không đánh dấu candidate last-good; circuit breaker dùng healthz nên có thể không rollback lỗi credential đó. Chạy `deploy/rollback.sh` để quay cả ba service về `.local/ecs-last-good.json` của lần deploy thành công trước, đợi và smoke lại. Không downgrade DB. Nếu đây là release đầu thì chưa có last-good: giữ/bật maintenance, sửa config, deploy release mới; không giả lập rollback thành công. [Chi tiết rollback](rollback.md).

Task events/capacity và logs cần đọc bằng quyền operator thích hợp; script cố ý không in DB URL/SDK exception/secret-bearing task definition. Cần IAM deployer cho ECR push, ECS register/run/stop/update/describe, iam:PassRole đúng task/execution roles, application-autoscaling register target và sts identity; Terraform operator tách riêng. Không có profile credentials trong image/scripts. ALB dependency smoke không thay thế nghiệp vụ/restore/load test AWS.

Check-in dùng manual policy trong PostgreSQL. Chỉ rollout/rollback image tương thích schema baseline0001_labseat và kiểm tra thao tác mở/đóng/tra cứu/xác nhận trong staging. Xem [check-in runbook](checkin.md).

Baseline hiện tại là `0001_labseat`. Migrate database mới tạo trực tiếp schema; với database đã đủ schema, app.migrate kiểm tra trước khi đổi marker, không tạo lại bảng. Xem [migration runbook](../../migrations/README.md). Các contract migration trong tương lai cần maintenance/backup và image tương thích.
