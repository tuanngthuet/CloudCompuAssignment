# A1 — Inventory LABSEAT — Bản bàn giao cuối đợt khảo sát 17/11/2026

- Người phụ trách: TV1 — Người 1, nhóm việc A1–A4.
- Phạm vi: khảo sát hiện trạng architecture/security bằng thao tác chỉ đọc.
- Region khảo sát: ap-southeast-2 (Sydney).
- Source baseline dùng để lập checklist: `b29675d0e22bf76e2a4b3c91e04f1bb68193c891`.
  Đây không phải bằng chứng commit đang chạy trên AWS.
- **Trạng thái tài liệu: FINAL FOR HANDOFF — bản tổng hợp bàn giao có giới hạn xác minh.**
- **Trạng thái kiểm chứng: đã đối chiếu các cấu hình nêu dưới đây;
  không còn 8 blocker quyền đọc trước đó. Các mục Pending/Unknown ở mục 9 chưa được xác minh.**
- Không tự kết luận reviewer đã Accepted A1 hoặc hệ thống đã PASS nghiệm thu.
  Tài liệu này không chứa kết quả test tải, failover, restore hoặc kiểm thử nghiệp vụ.

## 1. Nguồn và thời điểm bằng chứng

| Ký hiệu | Nguồn | Thời điểm bắt đầu |
|---|---|---|
| R1 | `20261117T103450Z-A1-200da2` | 17/11/2026 10:34:50 UTC; 17:34:50 giờ Việt Nam |
| R2 | `20261117T122731Z-A1-a2a64a` | 17/11/2026 12:27:31 UTC; 19:27:31 giờ Việt Nam |
| S1 | Truy vấn ASG bổ sung do TV1 chạy và cung cấp | Sau R1; chưa có timestamp chính xác |

JSON và manifest gốc giữ tại `.local/assessment/<run_id>/`.
Các kết luận dựa trên JSON/log TV1 cung cấp. Không coi dữ liệu R1 là snapshot
được tái xác nhận toàn bộ tại R2. API được gọi lần lượt, không phải snapshot đồng thời.
Timestamp từng phép đọc và commit checkout xem trong manifest gốc.

Các nhãn được hiểu như sau:

- **Đã đối chiếu AWS:** có dữ liệu describe/list cụ thể cho thuộc tính được nêu.
- **Source/Reported:** thông tin từ baseline hoặc biên bản nhóm, chưa chứng minh runtime.
- **Pending/Unknown:** thiếu dữ liệu hoặc chưa review nội dung.
- **Blocked đã gỡ:** phép đọc từng bị từ chối, đã thành công tại R2.

`COLLECTED` nghĩa là thu thập được dữ liệu, không tự chứng minh cấu hình đúng,
dịch vụ đang được dùng hoặc bài test đã đạt. Danh sách rỗng cần kiểm tra scope/bộ lọc.

## 2. Tóm tắt hiện trạng đã đối chiếu

| Nhóm | Hiện trạng quan sát | Nguồn |
|---|---|---|
| Mạng | VPC 10.20.0.0/16; 6 subnet trên 2 AZ; 2 NAT; 1 IGW; 1 S3 gateway endpoint | R1 |
| ALB | Internet-facing, active, 2 AZ; HTTP 301 sang HTTPS; 2 target healthy | R1 |
| ECS | API 2, worker 1, publisher 1; revision 9; một image digest chung | R1 |
| EC2 | 4 t3.small; 1 ở AZ 2a, 3 ở AZ 2b; 4 đăng ký ECS ACTIVE | R1 |
| ASG | labseat-lab-app; min/desired/max = 2/4/6; 4 Healthy/InService | S1 |
| ECS service scaling | API 2–8 task; target CPU 65%, memory 65%, request 660 | R2 |
| RDS | PostgreSQL 16.13; db.t4g.micro; Multi-AZ; private/encrypted; backup 1 ngày | R1 |
| Redis | 7.1.0; 2 cache.t3.micro; primary/replica khác AZ; snapshot 7 ngày | R1 |
| S3 | 2 bucket; Sydney; SSE-S3; versioning và 4 public-block flags bật | R1 |
| SQS | Queue + DLQ; retention 4/14 ngày; redrive maxReceiveCount 5 | R1 |
| IAM | Trust policy của 4 ECS role đã đọc; policy cấp quyền chưa review đầy đủ | R2 |
| SSM | 12 parameter SecureString, version 1; chỉ metadata | R2 |
| Monitoring | Log retention 7 ngày; alarms/action đã đọc; SNS delivery chưa kiểm thử | R1/R2 |

## 3. Mạng, định tuyến và Security Group

Nguồn R1: `vpcs.json`, `subnets.json`, `routes.json`, `nats.json`,
`igws.json`, `endpoints.json`, `security-groups.json`.

| Nhóm subnet | AZ 2a | AZ 2b | Định tuyến thực tế |
|---|---|---|---|
| Public | 10.20.0.0/24 | 10.20.1.0/24 | Default route tới IGW |
| App private | 10.20.10.0/24 | 10.20.11.0/24 | NAT cùng AZ; route S3 endpoint |
| DB | 10.20.20.0/24 | 10.20.21.0/24 | Chỉ route nội bộ VPC |

- VPC không phải mặc định. Cả 6 subnet tắt tự gán public IPv4;
  phân loại public/private dựa trên route, không chỉ flag này.
- Có 5 route table: 4 bảng gắn rõ với subnet, 1 bảng main.
- Các route đã gửi đều active.
- Hai public NAT đều available, mỗi AZ một NAT. IGW gắn đúng VPC.
- S3 Gateway Endpoint available, service Sydney S3, gắn hai app route table.

| Security Group | Ingress | Egress quan sát |
|---|---|---|
| ALB | TCP 80/443 từ 0.0.0.0/0 | TCP 8000 tới SG App |
| App | TCP 8000 từ SG ALB | TCP 5432 tới SG DB; 6379 tới SG Redis; 80/443 tới 0.0.0.0/0 |
| DB | TCP 5432 từ SG App | Danh sách rỗng |
| Redis | TCP 6379 từ SG App | TCP 443 tới 0.0.0.0/0 |

Không thấy ingress SSH 22 trong các SG được gửi. Default SG tồn tại;
chưa xác định có tài nguyên nào dùng nó. NACL được collector thu thập nhưng
chưa review nội dung trong đợt này. Chưa kiểm thử kết nối đầu cuối.

## 4. ALB, ECS, image và EC2/ASG

### 4.1. ALB và service

Nguồn R1: `albs.json`, `listeners-0.json`, `health-0-0.json`,
`ecs-service-0/1/2.json`.

- ALB internet-facing/active trên hai public subnet, gắn SG ALB.
- HTTP 80 redirect 301 tới HTTPS 443.
- HTTPS listener gắn chứng chỉ ACM, forward tới target group API.
- SSL policy: `ELBSecurityPolicy-TLS13-1-2-2021-06`.
- Hai target API cổng 8000 đều healthy, mỗi AZ một target.
- Chưa xác minh DNS tên miền hoặc status/domain/expiry của chứng chỉ ACM.

| Service | Desired | Running | Pending | Rollout |
|---|---:|---:|---:|---|
| API | 2 | 2 | 0 | COMPLETED |
| Worker | 1 | 1 | 0 | COMPLETED |
| Publisher | 1 | 1 | 0 | COMPLETED |

Cả ba service dùng subnet private .10/.11, SG App, assignPublicIp DISABLED.
Chỉ API gắn ALB. Cấu hình cho phép hai AZ không đồng nghĩa mỗi service có
bản sao đồng thời tại cả hai AZ.

### 4.2. Image và vị trí task

Nguồn R1: `ecs-definition-0/1/2.json`, `ecs-tasks-0.json`,
`ecs-container-0.json`.

Cả ba task definition revision 9 ghim cùng image digest; cả 4 task
đang chạy có digest khớp:

```text
sha256:fe6118739b4c12b2c2f170c26601db59080144ecdbb415b70c53655041073d08
```

| Task | AZ | Status / Health | Máy chạy (nhãn nội bộ tài liệu) |
|---|---|---|---|
| API A | 2a | RUNNING / HEALTHY | EC2-A |
| API B | 2b | RUNNING / HEALTHY | EC2-B1 |
| Worker | 2b | RUNNING / UNKNOWN | EC2-B1 |
| Publisher | 2b | RUNNING / UNKNOWN | EC2-B2 |

IP hai API task khớp hai target ALB healthy. EC2-B3 đăng ký ECS nhưng
không có task trong snapshot. Worker và publisher cùng ở AZ 2b; chưa
kiểm thử phục hồi khi mất AZ này. Health UNKNOWN chưa chứng minh lỗi hoặc
xử lý nghiệp vụ thành công.

Cả ba definition dùng awsvpc, CPU 256 units và memory 512 MiB;
API khai báo port 8000, worker/publisher không khai báo port mapping.
API, worker, publisher có task role riêng và dùng chung execution role.
BREVO_API_KEY chỉ xuất hiện trong danh sách secret injection của worker
trong ba definition đã kiểm tra; không đọc giá trị secret.
Revision 9 không phải phiên bản release. Đối chiếu digest với commit/release
để Pending theo phạm vi bàn giao hiện tại.

### 4.3. EC2 và ASG

Nguồn R1: `instances.json`, `ecs-container-0.json`; ASG dùng S1.

- Có 4 EC2 t3.small đang running, subnet private, SG App.
- 1 máy AZ 2a, 3 máy AZ 2b; cả 4 đã đăng ký ECS ACTIVE.
- Tổng 4 task chạy trên 3 máy, một máy không có task.
- MetadataOptions của cả 4 máy: HttpTokens required, HttpEndpoint enabled,
  HttpPutResponseHopLimit 1.
- ASG đúng tên là labseat-lab-app; min 2, desired 4, max 6.
- S1 ghi nhận cả 4 instance Healthy/InService, khớp ID EC2 trong R1.
- Chưa xác minh lý do desired = 4 hoặc kết luận máy không có task là thừa.

Collector cũ lọc ASG bằng tên cluster labseat-lab nên trả [].
Truy vấn S1 bỏ bộ lọc sai và xác nhận labseat-lab-app.
Giữ nguyên bằng chứng gốc; không sửa asg.json cũ để che lỗi collector.
Khi chạy lại phải phân biệt tên ASG với tên cluster.

## 5. Scaling và monitoring
Nguồn: describe-scalable-targets.json,
describe-scaling-policies.json và alarms.json của lần thu thập mới.
Run ID: `20261117T122731Z-A1-a2a64a` (R2).

- API service có giới hạn scaling 2–8 task.
- Có 3 target tracking policy:
  CPU 65%, memory 65%, ALBRequestCountPerTarget 660.
- Các policy có scale-out cooldown 60 giây,
  scale-in cooldown 180 giây và DisableScaleIn = false.
- Các cờ tạm dừng scaling của scalable target đều false.
- Ba target tracking AlarmHigh của API đang OK;
  ba AlarmLow đang ALARM tại thời điểm khảo sát.
- Hai alarm CapacityProviderReservation đang OK,
  action trỏ tới policy của ASG labseat-lab-app.
- Các alarm nghiệp vụ/hạ tầng được thu thập đều OK,
  actions enabled và trỏ tới SNS labseat-lab-workload.
- Chưa xác minh ngưỡng/period/treat-missing-data của alarms,
  xác nhận SNS subscription hoặc lịch sử scale-out/scale-in.
- Đây là xác minh cấu hình, chưa phải kết quả kiểm thử autoscaling.

Giá trị 660 được ghi theo cấu hình metric ALBRequestCountPerTarget,
không diễn giải thành 660 request/giây. Không suy giá trị ngưỡng AlarmLow
hoặc nguyên nhân chính xác từ tên alarm.

Có bằng chứng alarm CapacityProviderReservation gắn capacity provider
labseat-lab và action tới ASG labseat-lab-app, nhưng chưa đọc đầy đủ
managed scaling target/cooldown của capacity provider hoặc policy EC2.
ECS scaling 2–8 task khác ASG scaling 2–6 máy.

Nguồn R1, logs.json: /labseat/lab/app và /labseat/lab/redis đều retention
7 ngày, storedBytes = 0 trong phản hồi. Chưa đọc log stream/event;
không kết luận ứng dụng không ghi log từ giá trị này.

## 6. RDS, Redis, S3 và SQS

### 6.1. RDS

Nguồn R1: rds.json.

| Thuộc tính RDS |Giá trị quan sát |
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
### 6.2. Redis

Nguồn R1: redis.json và redis-nodes.json.

- Replication group labseat-lab available, gồm 2 node cache.t3.micro,
  engine Redis 7.1.0.
- Primary tại AZ 2a, replica tại AZ 2b, cả hai available.
- Multi-AZ và automatic failover enabled; TLS và at-rest encryption bật.
- Snapshot retention 7 ngày.
- Hai node gắn SG Redis; user group được ghi nhận là labseat-lab.
- Chưa kiểm tra nội dung ACL/user mapping, chi tiết subnet group,
  hoặc kiểm thử failover/restore.

### 6.3. S3

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

### 6.4. SQS

Nguồn R1: queue-0.json và queue-1.json.

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

## 7. IAM và SSM metadata

Nguồn: iam-role-0..3.json và ssm-metadata.json.
Run ID: 20261117T122731Z-A1-a2a64a.
Thời điểm bắt đầu run: 2026-11-17T12:27:31Z
(19:27:31 giờ Việt Nam); timestamp từng API nằm trong manifest.

- Đã đọc trust policy của 4 role: API, execution, publisher, worker.
- Cả 4 cho phép ecs-tasks.amazonaws.com thực hiện sts:AssumeRole.
- Trust policy có điều kiện SourceAccount đúng account nhóm và
  SourceArn giới hạn ECS tại ap-southeast-2 trong account đó.
- Không ghi nhận permissions boundary trong kết quả.
- Chưa kiểm tra đầy đủ nội dung policy cấp quyền; chưa kết luận
  các role đã đáp ứng nguyên tắc quyền tối thiểu.
- Thu thập được 12 parameter dưới /labseat/lab/,
  tất cả Type = SecureString, Version = 1.
- Chỉ đọc metadata; không thu thập giá trị secret.
- Tên parameter Brevo/SES không chứng minh backend email hiện hành.


Trust policy chỉ xác định ai có thể assume role; chưa chứng minh quyền
runtime tối thiểu. Boundary null không có nghĩa role có AdministratorAccess.
Các API list-attached-role-policies/list-role-policies trả danh sách policy,
không thay thế việc đọc và review nội dung policy.

## 8. Kết quả xử lý blocker và sai lệch baseline

| Mục | Trạng thái bàn giao |
|---|---|
| NAT CLI_ERROR_252 | Đã sửa --filter cho describe-nat-gateways; R1 thu thập thành công |
| ASG [] | Do lọc nhầm tên; S1 xác nhận ASG labseat-lab-app |
| 4 iam:GetRole | Từng BLOCKED; R2 COLLECTED, trust đã review |
| 2 Application Auto Scaling calls | Từng BLOCKED; R2 COLLECTED, cấu hình đã review |
| cloudwatch:DescribeAlarms | Từng BLOCKED; R2 COLLECTED, state/action đã review |
| ssm:DescribeParameters | Từng BLOCKED; R2 COLLECTED, metadata đã review |
| Region tuần 1 us-east-1 | Baseline khảo sát thực tế dùng Sydney |
| Example t3.medium / báo cáo t3.small | R1 xác nhận 4 máy t3.small |
| RDS default backup 30 ngày / báo cáo 1 ngày | R1 xác nhận retention 1 ngày |
| NAT B tùy chọn | R1 xác nhận 2 NAT, app route qua NAT cùng AZ |
| Handoff/source ghi chưa triển khai | Là sai lệch tài liệu tại source baseline; AWS runtime đã quan sát, nhưng release/commit chưa đối chiếu |

**Không còn blocker quyền đọc trong 8 phép gọi đã xin bổ sung.**
Điều này không chứng minh mọi phép kiểm tra ngoài collector đều có quyền
hoặc đã hoàn tất. Không đánh lại dữ liệu R1 thành dữ liệu R2.

## 9. Pending/Unknown và phạm vi chưa xác minh

| Mục | Bằng chứng còn thiếu / lý do | Bàn giao tiếp |
|---|---|---|
| Image ↔ commit/release | Có digest runtime, chưa có mapping build/release; chủ động để Pending | Owner deployment |
| VPC DNS flags, EIP, NACL | Collector chưa lấy DNS flags/EIP; NACL chưa review nội dung | TV1 kiểm tra chỉ đọc khi cần |
| Domain/ACM | Listener có cert ARN; chưa đối chiếu DNS, cert status/domain/expiry | TV1 / owner domain |
| EBS và launch template | Chưa có describe volume/template; không coi EBS30GB từ biên bản là runtime đã xác minh | Owner compute |
| Capacity provider/ASG policy | Có ASG và managed-scaling alarms; chưa có toàn bộ provider config/policy/activity | Owner compute / Người 3 |
| IAM permission policies | Trust đã đọc; chưa review nội dung managed/inline policies, maintenance role | Quản trị / TV1 |
| S3 lifecycle/policy/backend locking | Đã biết encryption/versioning/public block; thiếu lifecycle, TLS-only policy và cấu hình lockfile backend | Owner state/data |
| Redis ACL/subnet group | Có SG, user-group name, AZ; chưa có ACL và subnet-group mapping chi tiết | Owner data |
| SNS/alarms/dashboard/log events | Có alarm actions; chưa xác nhận subscription, delivery, threshold/period/missing-data hoặc dashboard/log stream | Người 3 |
| Maintenance/schema/email backend | Chưa đọc schedule, schema runtime, hoặc giá trị cấu hình email; không suy backend từ tên secret | Owner app/data |
| Tải/scaling thực nghiệm/fault/restore | Không thực hiện trong khảo sát chỉ đọc này | Các task C/B và A4 theo phân công |
| Hava exports, sơ đồ/ADR | Không nằm trong bằng chứng A1 lần này | A2/A3 |

Các mục trên là giới hạn minh bạch của bản bàn giao, không được đổi thành
PASS hoặc “không tồn tại”. Nếu rubric yêu cầu xác minh đầy đủ một mục,
cần bổ sung bằng chứng trước khi reviewer Accepted.

## 10. Bàn giao và bảo quản bằng chứng

- Cho A2: dùng các subnet/AZ, route, placement và quan hệ SG đã xác minh
  để đối chiếu Hava. DNS, ACL và các policy chi tiết giữ nhãn chưa xác minh.
- Cho Người 2/B4: RDS retention 1 ngày, Multi-AZ, subnet/SG, restore window
  đã quan sát; LatestRestorableTime không phải bằng chứng restore thành công.
- Cho Người 3: API 2–8 task, ASG 2–6 máy; snapshot 2/1/1 task,
  hai NAT cùng AZ, worker/publisher cùng AZ 2b, cấu hình alarms/SQS.
- Luồng outbox → publisher → SQS → worker → email và semantics Redis
  vẫn là mô tả từ source; khảo sát metadata chưa chứng minh end-to-end.
- Giữ JSON và manifest gốc tại .local, không commit secret, state,
  hoặc toàn bộ thư mục private. Cung cấp bằng chứng gốc cho reviewer
  qua kênh nội bộ thích hợp.
- ID/ARN/endpoint chi tiết được giữ trong bằng chứng gốc;
  bảng báo cáo chủ yếu dùng tên vai trò, cấu hình và nhãn máy.
- S1 cần lưu riêng kèm thời điểm nếu truy vấn lại; không ghi đè snapshot cũ.
- Người review ghi nhận Accepted riêng sau khi đánh giá phạm vi và các
  mục còn Pending. “Final” ở đây là phiên bản tài liệu bàn giao,
  không phải xác nhận nghiệm thu toàn hệ thống.

## Phụ lục — Nguồn source baseline

Các đường dẫn sau là nguồn checklist đã ghi nhận ở baseline, không có
tuyên bố rằng source mới nhất đã được đọc lại hoặc deployed trong đợt này.

| Nhóm | Nguồn |
|---|---|
| Network/SG | infra/modules/network/main.tf; security.tf |
| Compute/ECS/scaling | infra/modules/compute/main.tf; ecs.tf |
| RDS/S3 | infra/modules/data/main.tf |
| Redis | infra/modules/managed_cache/main.tf |
| IAM/integration | infra/modules/iam/tasks.tf; infra/integration/main.tf |
| Messaging | infra/modules/messaging/main.tf |
| Monitoring | infra/modules/observability/main.tf; dashboard.tf; events.tf |
| Maintenance/deployment | infra/modules/compute/maintenance.tf; deploy/ecs.py |
| Biên bản/handoff | evidence/current/aws-deployment.md; handoff/current.json |
| App/email | app/modules/auth; app/modules/notifications; docs/deployment/brevo.md |

Đường dẫn là tham chiếu trong bản checklist nguồn; nội dung source không
thay thế bằng chứng runtime. Sai lệch tài liệu deployment cũ được giữ như
phát hiện lịch sử, không sửa thành một kết quả test đã đạt.
