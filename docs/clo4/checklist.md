# CLO4 — checklist ECS, chưa verified AWS

Mọi AWS evidence còn **pending**. Repository/Terraform mock/local tests không thay bằng chứng AWS. Dùng AWS_PROFILE/AWS_REGION/EXPECTED_AWS_ACCOUNT_ID explicit và chỉ chạy commands khi đã được phép triển khai.

| # | Yêu cầu / Terraform resource | Verification command / công việc operator | Bằng chứng cần lưu | Actual |
|---|---|---|---|---|
|1|VPC2AZ, public/private: module.network aws_vpc/subnet/route/NAT |`aws ec2 describe-subnets --filters Name=vpc-id,Values=VPC`; `aws ec2 describe-route-tables --filters Name=vpc-id,Values=VPC` |2AZ, ALB public route, app NAT private, DB không default internet |Pending |
|2|Private ECS EC2: module.compute aws_launch_template/app ASG |`aws ec2 describe-instances --instance-ids IDS`; `aws ecs describe-container-instances --cluster CLUSTER --container-instances ARNS` |No public IP, ECS-optimized AMI, registered resources/ENI |Pending |
|3|Storage: module.data aws_s3_bucket + RDS/gp3 EBS |`aws s3api get-public-access-block --bucket BUCKET`; `aws ec2 describe-volumes --volume-ids IDS` |S3 private/encrypted, EBS encrypted, assets cross-task |Pending |
|4|DB: module.data aws_db_instance |`aws rds describe-db-instances --db-instance-identifier labseat-lab`; exact-release smoke |Private PostgreSQL16, backup, TLS,baseline0001_labseat, reservation invariants; test restore |Pending |
|5|IAM: module.iam roles/profile/task policies |`aws iam get-role --role-name ROLE`; `aws ecs describe-task-definition --task-definition API_TD` |Host/execution/API/worker/publisher tách quyền, SSM refs không secret values |Pending |
|6|ALB +2 tầng scaling: module.compute aws_lb/appautoscaling/capacity_provider/ASG |[k6 và commands](../testing/load-test.md) |Task desired tăng →thiếu placement →EC2 inservice tăng tự động →healthy IP targets +request distribution |Pending |
|7|Monitoring/triggered alarm: module.observability metric alarms/SNS |`aws cloudwatch describe-alarms --alarm-name-prefix labseat-lab`; `aws cloudwatch describe-alarm-history --alarm-name labseat-lab-requests-per-target-high` |Alarm thật ALARM và confirmed SNS email cùng window; DLQ/age/backlog alarms |Pending |
|8|Monthly cost |[Planning estimate](../cost/monthly-estimate.md), Pricing Calculator export, AWS Budgets/credit review |Dated Calculator export/region/usage/HA alternatives; actual spend sau deployment |Planning only |

Acceptance bổ sung: rollout đủ capacity và timeout diagnostics, migration fail/timeout stop deployment, wrong DB release không được old ALB task che khuất, manual rollback last-good, graceful SIGTERM, Redis restart/failover recovery, SQS redrive/DLQ, Brevo sender/domain và actual acceptance/delivery, RDS restore/RPO/RTO. Không mark complete khi chưa có evidence từng mục. Không tạo tải/scale/trigger alarm thật trong lần repository implementation.
