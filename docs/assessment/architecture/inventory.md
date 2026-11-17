# A1 — Inventory LABSEAT: source baseline và bằng chứng AWS

- Người phụ trách: Người 1 (TV1; cần nhóm xác nhận nhận task).
- Ngày chuẩn bị: 17/11/2026. Source baseline: `b29675d0e22bf76e2a4b3c91e04f1bb68193c891`.
- Phạm vi: architecture/security; chỉ đọc. Không sửa runtime, seed, email, scaling, state hoặc hạ tầng.
- **Trạng thái A1: đã thu thập và đối chiếu một phần AWS thực tế; chưa hoàn tất.** Nguồn chính: run `20261117T103450Z-A1-200da2` do TV1 chạy trên máy Windows và truy vấn ASG bổ sung do TV1 cung cấp. Còn 8 phép đọc BLOCKED và các kiểm tra bổ sung tại mục 5. Không đánh PASS tải/failover/restore.
- Chưa có Hava export, kết quả tải/fault/restore. Không đánh PASS hệ thống từ cấu hình source.

## 1. Phân loại bằng chứng

- `SOURCE_CONFIRMED`: cấu hình/quan hệ đọc được trong code tại commit nêu trên, không chứng minh đã apply.
- `REPORTED`: biên bản nhóm ghi nhận, chưa được Người 1 đọc AWS đối chiếu trong lần khảo sát này.
- `AWS_CONFIRMED`: chỉ dùng sau khi có describe/list thực, timestamp, target và evidence.
- `UNKNOWN/BLOCKED`: chưa thu thập, thiếu quyền hoặc dữ liệu chưa xác định. API thành công nhưng danh sách rỗng không tự chứng minh đúng target/không có dịch vụ.

Mỗi lần chạy collector có `run_id`, khoảng UTC riêng cho từng API và commit của checkout. Snapshot không atomic; nếu nhóm đang deploy/scale, ghi cửa sổ thay đổi và thu lại các mục bị ảnh hưởng.

## 2. Inventory theo nhóm tài nguyên

Bảng dưới là checklist từ source baseline trước khảo sát, không phải bảng trạng thái hiện tại. Kết quả AWS đã đối chiếu được ghi ở phần “Bổ sung bằng chứng AWS thực tế”. Thuộc tính chưa có bằng chứng giữ UNKNOWN/BLOCKED. Resource ID, ARN và endpoint chi tiết lưu private trong `.local/assessment/<run_id>/`.

| Nhóm | SOURCE_CONFIRMED / REPORTED | AWS cần xác minh | Nguồn trong repo | Evidence collector |
|---|---|---|---|---|
| Account/region | Biên bản 17/11 dùng Sydney `ap-southeast-2`. Account người dùng từng xác minh `403030570855`, phải STS lại | Đúng account, IAM, vùng; ghi UTC | `evidence/current/aws-deployment.md` | identity.json |
| VPC/DNS | Source bật DNS support/hostnames; 6 subnet theo 2 AZ | VPC đúng dự án, CIDR/associations, DNS flags, AZ thực | `infra/modules/network/main.tf` | vpcs/subnets; DNS flags kiểm riêng |
| Public/app/DB subnet | Cả 6 subnet source không auto public IP. Tính public/private phụ thuộc route, không chỉ flag này | Route gắn từng subnet và main route; public->IGW, app->NAT, DB không default Internet | `infra/modules/network/main.tf` | subnets/routes/igws/nacls |
| NAT/EIP | Source tạo NAT A; NAT B chỉ khi `multi_az_nat=true` | Đếm NAT Available, subnet/AZ, route mỗi app subnet; không giả định 1 hay 2 NAT | network main.tf; production tfvars example | nats/routes/subnets |
| S3 endpoint | Gateway endpoint gắn app route tables | Service/region, loại endpoint, association; policy cần review riêng | network main.tf | endpoints.json |
| SG/ports | Source ALB 80/443; ALB->app8000; app->DB5432 và Redis6379; không có rule SSH public | Từng SG thực, IPv4/IPv6, source SG, egress và NACL; 80 listener có redirect không | `infra/modules/network/security.tf` | security-groups/nacls/listeners |
| ECS services | Source API/publisher/worker cùng image; biên bản ghi API2/publisher1/worker1 | Desired/running/pending, rollout, task ARN/AZ, image digest, mapping task->container instance->EC2 | `infra/modules/compute/ecs.tf`; biên bản | ecs-service/ecs-tasks/ecs-container files |
| EC2/ASG | Biên bản min2/max6, t3.small, EBS30GB; **không cố định số EC2=2** | Min/desired/max và số in-service thực; AZ, instance type, volume, IMDSv2, launch template | compute main.tf; biên bản | asg/instances; volume kiểm riêng |
| Hai tầng scaling | Source ECS service autoscaling + capacity provider/ASG | Targets/policies/cooldown và capacity provider thực; cấu hình không chứng minh đã autoscale | compute ecs.tf, capacity.md | describe-scalable-targets / describe-scaling-policies; capacity provider kiểm riêng |
| ALB/ACM/DNS | Biên bản HTTPS labseat.id.vn, ACM issued, DNS Tenten | Public/internal, 2 AZ, listener80 redirect443, cert status/domain, TG ip/port8000, targets healthy | compute main.tf; biên bản | albs/listeners/targets/health; ACM/DNS kiểm riêng |
| RDS | Source PostgreSQL16, db.t4g.micro, encrypted/private. Biên bản Multi-AZ, backup **1 ngày** | Engine version/class, primary/secondary AZ, public=false, retention, earliest/latest restorable time | data main.tf; biên bản | rds.json |
| Redis | Source managed Redis7.1/cache.t3.micro, TLS/at-rest, runtime/operator/events ACL; biên bản primary/replica | Actual version/type/AZ, replication membership, auto-failover, TLS, subnet/SG và ACL mapping | managed_cache/main.tf; integration/main.tf | redis/redis-nodes; ACL/subnet mapping kiểm riêng |
| S3 app/state | Source private/AES256/versioning/TLS-only; app lifecycle noncurrent30days. Biên bản state đã trên S3 | Bucket đúng purpose/region; versioning, encryption, public block, policy/lifecycle; lockfile cấu hình backend riêng | data main.tf; bootstrap/state/main.tf; biên bản | buckets/s3 files; policy/lifecycle/backend kiểm riêng |
| IAM/SSM | Source API/publisher/worker/maintenance/execution có role; secret injection qua SSM; worker nhận Brevo key | ARN role, trust/policy thực, scope S3/SQS/SSM; không đọc giá trị parameter/password | iam/tasks.tf; integration/main.tf; compute/ecs.tf | iam role/attached/inline; ssm-metadata; policy contents kiểm riêng |
| SQS/DLQ | Source queue120s visibility, retention4days; DLQ14days; maxReceiveCount5; SSE/TLS | Thuộc đúng workload, redrive, encryption, backlog; không receive/purge messages | messaging/main.tf | queues/queue files |
| Monitoring/SNS | Source logs7days, metrics/alarms, SNS email; biên bản subscription confirmed | Alarm state/actions/dimensions, retention, SNS confirmed thực; không gửi mail/publish thử | observability/main.tf/dashboard.tf/events.tf | alarms/logs; subscription/dashboard kiểm riêng |
| Deployment/maintenance | Source deploy driver ECS + scheduled maintenance; biên bản schema0002_platform/release0.6.0 | Image digest chạy thực vs commit/release; ECR tag/digest, schedule/role; schema do owner cung cấp bằng chứng | deploy/ecs.py; compute/maintenance.tf; handoff/current.json | task digest; ECR/schedule/schema kiểm riêng |
| Email/application security | Source Brevo/outbox/SQS/worker, session/CSRF, S3 private. Biên bản đã login/smoke | Cấu hình backend email hiện tại do Người3 xác nhận; nguồn login/session/schema không suy từ healthz | app/modules/auth; app/modules/notifications; docs/deployment/brevo.md | Code review + bằng chứng owner; không đăng nhập/seed/tắt mail trong A1 |

## 3. Quan hệ để bàn giao Hava và test

1. Public DNS -> HTTPS ALB -> target group IP -> private API tasks -> PostgreSQL.
2. API -> Redis admission (correctness vẫn do PostgreSQL) và Redis Pub/Sub events ACL riêng.
3. API -> private S3; nguồn S3 gateway endpoint chỉ ở app route tables theo source.
4. Transactional outbox PostgreSQL -> publisher -> SQS -> worker -> Brevo; lỗi chuyển DLQ theo redrive.
5. ECS task placement trên EC2 do một capacity provider/ASG; task scaling và EC2 scaling là hai phép đo riêng.
6. Task execution role pull image/log/secret injection; task roles cho quyền runtime riêng; maintenance có role riêng.
7. API ra Internet qua NAT; RDS không có đường Internet default theo module mạng. Phải đối chiếu route thực trước kết luận.

## 4. Mâu thuẫn/câu hỏi phải chốt

| ID | Phát hiện tại source baseline | Xử lý A1 |
|---|---|---|
| A1-F01 | `handoff/current.json` aws_deployed/aws_verified=false; `docs/architecture/current.md` ghi chưa triển khai; biên bản17/11 ghi đã triển khai | Ghi mâu thuẫn, xin owner xác nhận timestamp/release và đối chiếu describe. Không sửa biên bản cũ thành PASS |
| A1-F02 | Hướng dẫn tuần1 cũ us-east-1; biên bản hiện tại ap-southeast-2 | Dùng Sydney cho khảo sát mới; không apply plan bootstrap cũ |
| A1-F03 | production tfvars example t3.medium; biên bản t3.small | Ghi instance type quan sát được, không lấy example làm runtime |
| A1-F04 | RDS retention default30; biên bản1 | Xác minh BackupRetentionPeriod, Earliest/LatestRestorableTime. Gửi B4; chưa kết luận restore được |
| A1-F05 | Network tùy chọn NAT B; example production yêu cầu bật nhưng biên bản không nêu số NAT | Đếm NAT/routes thực để vẽ phụ thuộc AZ chính xác |
| A1-F06 | Commit b29675d có thay đổi auth verification/image caching sau release0.6.0 | Không suy latest source đã chạy. Lấy image digest đang chạy và manifest release từ owner |
| A1-F07 | Số task/EC2 thực có thể thay đổi do rollout/capacity | Chụp UTC và đếm tại thời điểm; không coi desired/min là running |
| A1-F08 | Biên bản deployment không phải acceptance load/failover/restore | Giữ các bài C3–C5/B4–B5 NOT_RUN cho đến evidence mới |

## 5. Phần còn thiếu và cách đóng A1

- Collector đã chạy; NAT đã được sửa tham số và thu thập thành công. ASG đã được đối chiếu bằng truy vấn bổ sung do tên ASG khác tên cluster. Giữ kết quả gốc, không sửa asg.json rỗng thành bằng chứng mới. Khi quản trị bổ sung quyền, chạy lại để kiểm tra các mục BLOCKED.
- Collector chỉ thu baseline metadata; còn DNS flags, EBS volume, capacity-provider detail, ACM/DNS, IAM policy contents, maintenance, SNS confirmation, S3 lifecycle/policy, Redis ACL/subnet mapping cần kiểm riêng theo checklist.
- Chỉ đọc metadata; không xuất secret/env values/cookie, không get-secret-value/get-parameter, không tải state hoặc user data.
- Dữ liệu từ CLI có thể gồm tài nguyên khác trong cùng account (Redis/scaling) hoặc bucket labseat ở vùng khác. Phải lọc theo VPC/service/region và liên kết resource trước đưa vào inventory, không tự gộp tất cả thành LabSeat.
- Chuyển kết luận đã kiểm chứng sang AWS_CONFIRMED với tên file và UTC. Giữ UNKNOWN cho phần không xác minh được.
- Bàn giao cho C1: VPC/subnet/AZ, ECS/ASG/capacity mapping, ALB target health, RDS/Redis thông số. Bàn giao cho B4: RDS ID private, retention, restore window và SG/subnet.
- IDs/endpoints nằm trong manifest private cho nhóm; bản public chỉ chứa tên vai trò, cấu hình cần thiết và nhãn ẩn danh nhất quán.
- A1 chỉ hoàn tất sau khi mọi nhóm có nguồn xác minh hoặc blocker cụ thể. A2 Hava cần quyền read-only role do quản trị cấp; chưa thao tác Hava trong gói này.

## Bổ sung bằng chứng AWS thực tế — 17/11/2026

Nguồn: lần thu thập `20261117T103450Z-A1-200da2`.
Region: ap-southeast-2 (Sydney).

### ALB và ECS

- Listener HTTP cổng 80 chuyển hướng 301 sang HTTPS cổng 443.
- Listener HTTPS có chứng chỉ ACM và forward tới target group API.
- Hai target API ở cổng 8000 đều healthy, mỗi AZ một target.
- API: desired 2, running 2, pending 0.
- Worker: desired 1, running 1, pending 0.
- Publisher: desired 1, running 1, pending 0.
- Cả ba service dùng subnet private, SG App và tắt cấp public IP.
- Các deployment đều COMPLETED; task definition revision 9.
- Worker và publisher mỗi service chỉ có một task chạy, chưa có
  bản sao đồng thời trên hai AZ.

### Giới hạn xác minh

Đây là bằng chứng cấu hình và trạng thái tại thời điểm thu thập.
Chưa xác nhận kiểm thử tải, failover hoặc nghiệp vụ đầu cuối.
Các mục bị BLOCKED vẫn chờ bổ sung quyền đọc và kiểm tra lại.

### EC2 và Redis — bằng chứng AWS thực tế

Nguồn: lần thu thập `20261117T103450Z-A1-200da2`.

- Có 4 EC2 loại t3.small đang running: 1 tại AZ 2a, 3 tại AZ 2b.
- Các EC2 nằm trong subnet private và gắn SG App.
- Đã đối chiếu cả 4 EC2 với container instance ECS; chi tiết tại mục ASG bên dưới.
- Redis phiên bản 7.1.0, gồm 2 node cache.t3.micro.
- Redis primary ở AZ 2a, replica ở AZ 2b; cả hai available.
- Redis bật Multi-AZ, automatic failover, TLS và mã hóa lưu trữ.
- Thời gian giữ snapshot Redis: 7 ngày.
- Chưa kiểm thử failover Redis thực tế.

#### ASG và ECS — đã đối chiếu

- ASG thực tế: labseat-lab-app.
- MinSize = 2, DesiredCapacity = 4, MaxSize = 6.
- Cả 4 EC2 đều Healthy/InService và đã đăng ký ECS ở trạng thái ACTIVE.
- Phân bố EC2: 1 máy tại AZ 2a, 3 máy tại AZ 2b.
- Snapshot ECS ghi nhận 4 task trên 3 máy; 1 máy không có task.
- Collector ban đầu lọc nhầm ASG theo tên cluster labseat-lab,
  nên trả về danh sách rỗng. Truy vấn bổ sung đã xác nhận ASG.
- Chưa xác minh chính sách scaling, nguyên nhân desired = 4
  hoặc kết quả kiểm thử scale-out/scale-in.
- Nguồn: truy vấn ASG bổ sung và ecs-container-0.json của lần
  thu thập 20261117T103450Z-A1-200da2; hai nguồn không lấy đồng thời.

### S3, SQS và CloudWatch Logs — bằng chứng AWS thực tế

Nguồn: lần thu thập `20261117T103450Z-A1-200da2`.

#### S3

Hai bucket được thu thập:
- labseat-403030570855-ap-southeast-2-tfstate
- labseat-lab-app-2f0ec9f354f548a825f4255b13

Cả hai bucket:
- Nằm tại ap-southeast-2.
- Bật versioning.
- Mã hóa mặc định AES256 (SSE-S3).
- Bật cả bốn tùy chọn Block Public Access.
- Bucket policy status trả về IsPublic = false.

Chưa kiểm thử khôi phục phiên bản object.
Chưa xác minh cơ chế lockfile của Terraform backend từ dữ liệu này.

#### SQS

| Thuộc tính | Queue notifications | Queue notifications-dlq |
|---|---|---|
| Visibility timeout | 120 giây | 30 giây |
| Thời gian giữ message | 4 ngày | 14 ngày |
| SQS-managed encryption | Bật | Bật |
| Số message hiển thị xấp xỉ | 0 | 0 |

Queue notifications có redrive policy trỏ tới notifications-dlq,
với maxReceiveCount = 5.

Số message hiển thị bằng 0 tại thời điểm khảo sát chưa chứng minh
luồng gửi email thành công; chưa thu thập message đang xử lý
hoặc message bị trì hoãn. Chưa kiểm thử retry/DLQ thực tế.

#### CloudWatch Logs

- /labseat/lab/app: giữ log 7 ngày.
- /labseat/lab/redis: giữ log 7 ngày.
- Cả hai trả về storedBytes = 0 tại thời điểm thu thập.
- Chưa đọc log stream hoặc log event để xác nhận ứng dụng ghi log.
- Quyền đọc CloudWatch alarms vẫn đang BLOCKED.

### Mạng và RDS — bằng chứng AWS thực tế

Nguồn: các file vpcs.json, subnets.json, routes.json, nats.json,
igws.json, endpoints.json, security-groups.json và rds.json
của run `20261117T103450Z-A1-200da2`.

| Nhóm subnet | AZ 2a | AZ 2b | Định tuyến thực tế |
|---|---|---|---|
| Public | 10.20.0.0/24 | 10.20.1.0/24 | Default route tới IGW |
| App private | 10.20.10.0/24 | 10.20.11.0/24 | NAT cùng AZ; route S3 gateway endpoint |
| DB | 10.20.20.0/24 | 10.20.21.0/24 | Chỉ route nội bộ VPC |

- VPC: 10.20.0.0/16, không phải VPC mặc định.
- Có 6 subnet trên ap-southeast-2a và ap-southeast-2b.
- Cả 6 subnet tắt tự gán public IPv4; phân loại public/private dựa trên route.
- Có 5 route table: 4 bảng gắn rõ với subnet, 1 bảng main.
- Các route gửi trong bằng chứng đều active.
- Có 2 NAT Gateway public/available, mỗi AZ một NAT.
- IGW gắn đúng VPC; S3 Gateway Endpoint available, gắn hai app route table.
- SG ALB nhận TCP 80/443 từ Internet, gửi TCP 8000 tới SG App.
- SG App nhận TCP 8000 chỉ từ SG ALB; gửi TCP 5432 tới SG DB,
  TCP 6379 tới SG Redis và TCP 80/443 ra ngoài.
- SG DB chỉ nhận TCP 5432 từ SG App; SG Redis chỉ nhận TCP 6379 từ SG App.
- Không thấy ingress SSH 22 trong các SG đã gửi.
- Default SG tồn tại; chưa xác định có tài nguyên nào dùng nó.
- Chưa kết luận NACL hoặc kết nối đầu cuối đã đạt từ SG/route.

| Thuộc tính RDS | Giá trị quan sát |
|---|---|
| Engine | PostgreSQL 16.13 |
| Class | db.t4g.micro |
| Storage | 20 GiB |
| Status | available |
| Publicly accessible | false |
| Storage encrypted | true |
| Multi-AZ | true |
| Primary / Secondary AZ | 2b / 2a |
| Backup retention | 1 ngày |
| LatestRestorableTime | 2026-11-17T10:33:10Z |
| EarliestRestorableTime | null trong kết quả collector; chưa xác định |

RDS gắn SG DB và subnet group gồm hai subnet .20/.21.
Chưa kiểm thử failover, restore hoặc RPO/RTO; không suy backup lỗi từ
trường EarliestRestorableTime null.

## Trạng thái tồn đọng sau khảo sát

| Phép đọc | Trạng thái ở run hiện tại | Việc cần làm |
|---|---|---|
| iam-role-0 đến iam-role-3 | BLOCKED (4 lần) | Kiểm tra quyền iam:GetRole trên role dự án |
| describe-scalable-targets | BLOCKED | Kiểm tra application-autoscaling:DescribeScalableTargets |
| describe-scaling-policies | BLOCKED | Kiểm tra application-autoscaling:DescribeScalingPolicies |
| alarms | BLOCKED | Kiểm tra cloudwatch:DescribeAlarms |
| ssm-metadata | BLOCKED | Kiểm tra ssm:DescribeParameters; không đọc giá trị secret |

Lần trước đã ghi AccessDenied/AccessDeniedException ở các phép đọc này.
Log console của run hiện tại chỉ hiển thị BLOCKED; đọc summary.md/manifest.json
của chính run để xác nhận mã lỗi trước khi kết luận nguyên nhân vẫn giống nhau.
IAM attached/inline đã thu thập là danh sách policy, chưa chứng minh đã review
nội dung quyền. Quyền metadata không bao gồm yêu cầu đọc giá trị parameter.

### Các điểm đã làm rõ so với source baseline

- A1-F02: khảo sát hiện tại dùng Sydney, không dùng plan tuần 1 ở us-east-1.
- A1-F03: 4 EC2 quan sát được đều t3.small.
- A1-F04: RDS backup retention thực tế là 1 ngày.
- A1-F05: thực tế có 2 NAT, app subnet dùng NAT cùng AZ.
- A1-F07: ECS API/worker/publisher chạy 2/1/1 task; ASG desired 4,
  4 EC2 Healthy/InService. Đây là snapshot, chưa xác minh nguyên nhân scaling.
- A1-F01 và A1-F06: vẫn cần owner xác nhận release/commit/image digest và
  thống nhất tài liệu deployment; không tự sửa lịch sử biên bản.
- A1-F08: kiểm thử tải/fault/restore vẫn cần bằng chứng từ owner phụ trách.

### Bằng chứng cần giữ và bàn giao

- Run ID chứa thời điểm bắt đầu 2026-11-17 10:34:50 UTC
  (17:34:50 giờ Việt Nam). Timestamp từng API lấy từ manifest.json;
  các API không được gọi đồng thời.
- Truy vấn ASG bổ sung được thực hiện sau run; chưa nhận timestamp chính xác.
  Không gán timestamp của run cho truy vấn bổ sung.
- Các kết luận ở tài liệu này dựa trên JSON/log TV1 cung cấp;
  không có kiểm tra AWS độc lập từ môi trường soạn tài liệu.
- Giữ JSON/manifest gốc trong .local, không commit toàn bộ thư mục private.
- Bàn giao bản inventory cho nhóm, kèm blocker cụ thể; chưa đánh A1 hoàn tất.
- A2 Hava, A3 sơ đồ/ADR và A4 bằng chứng sự cố/restore chưa được xác minh
  trong lần cập nhật này.
