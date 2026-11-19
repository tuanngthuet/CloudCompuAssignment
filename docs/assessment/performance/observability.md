# C1 — Công cụ quan sát và preflight

Ngày soạn: 19/11/2026. Chủ sở hữu: Người 3. **Trạng thái nghiệm thu C1: BLOCKED.**
Trong phiên soạn, AWS CLI chưa có profile `tv1` và truy cập mặc định gặp proxy sandbox. Quyền chạy STS ngoài sandbox bị từ chối. Theo chỉ đạo nhóm, không thử AWS thêm trong phiên này. Chưa có smoke collector AWS hoặc kết quả tải được xác nhận.

Nguồn: [kế hoạch C1](../../sprints/ke-hoach-nghiem-thu-4-ngay.md), [capacity](../../deployment/capacity.md), [load test](../../testing/load-test.md), [inventory A1](../architecture/inventory.md).

## Phạm vi đã hoàn thiện tại source

- Collector chỉ đọc tại `scripts/assessment/observability/collect.py`: kiểm đúng AWS account trước khi đọc tài nguyên, lấy preflight, snapshot ECS/ASG/ALB theo 15–30 giây, scaling activity và CloudWatch 60 giây. Lưu `preflight.json`, `metrics.csv`, `activities.csv`, truy vấn từng mẫu trong `metric-requests/`, `manifest.json`, `summary.md` tại `.local/assessment/<run_id>/` (Git ignored).
- `chart.py` tạo SVG **riêng từng metric** từ CSV và biểu đồ tổng quan ba panel task ECS, EC2, ALB targets với trục đếm riêng; mẫu thiếu để lại khoảng trống thay vì nối đường. `source_at` cho biết timestamp CloudWatch, có thể cũ hơn `sample_at` do độ trễ xuất metric.
- `runner.ps1` ghi CPU, RAM khả dụng và network bytes/s của máy k6 bên ngoài ASG. Cần chạy song song k6; chưa có runner thật trong phiên này.
- Test local dùng dữ liệu synthetic, kiểm account mismatch dừng trước khi đọc resource, phân biệt ECS/ASG/ALB, tổng ENI/RAM theo AZ, CloudWatch dimensions và missing metrics, và SVG. **Synthetic test không phải bằng chứng AWS.**

## Chuẩn bị runner và tham số

Máy k6 phải ở ngoài ECS/EC2 ASG đang đo, đồng hồ đồng bộ UTC, network đủ cho mức tải dự kiến. Kiểm phiên bản k6, CPU/RAM/network runner trước và trong smoke; nếu runner bão hòa, kết quả latency/throughput chưa thể quy cho ứng dụng. Cài k6 theo quy trình của nhóm trên máy runner, không thay đổi ASG để đặt runner.

Lấy tham số **thực tế** từ AWS Console hoặc inventory A1 mới nhất: account ID, ECS cluster/service, ASG, target group ARN, ALB ARN suffix, target group ARN suffix, capacity provider, DB identifier, Redis cache cluster ID của **cả hai node**, SQS queue/DLQ name và URL, SNS topic ARN. Inventory A1 ngày 17/11 ghi cluster `labseat-lab`, ASG `labseat-lab-app`, 4 EC2 (1 AZ 2a, 3 AZ 2b) và API 2 task; **không dùng các con số đó làm baseline ngày chạy**. Không lấy account ID hay tên tài nguyên bằng suy đoán khi deployment đã đổi.

Ví dụ lệnh sau trên runner/terminal đã đăng nhập AWS (PowerShell, thay toàn bộ giá trị trong dấu `<...>`):

```powershell
py -3 scripts/assessment/observability/collect.py `
  --profile <profile> --expected-account <12-digit-account> `
  --cluster <ecs-cluster> --api-service <api-service> `
  --worker-service <worker-service> --publisher-service <publisher-service> `
  --asg <asg-name> --target-group <target-group-arn> `
  --alb-suffix <app/name/id> --target-group-suffix <targetgroup/name/id> `
  --capacity-provider <capacity-provider> --db <db-id> `
  --cache-cluster <redis-node-1-id> --cache-cluster-replica <redis-node-2-id> `
  --queue <queue-name> --dlq <dlq-name> --queue-url <queue-url> --dlq-url <dlq-url> `
  --sns-topic <topic-arn> --instance-ids <ec2-instance-1> <ec2-instance-2> `
  --interval 30 --samples 4
```

`--samples 4` là smoke quan sát khoảng hai phút; bài tải/fault dùng số mẫu phù hợp cửa sổ. Collector tự lấy EC2 IDs từ ASG ở từng snapshot để đo CPU credits của máy mới. `--instance-ids` chỉ bổ sung ID khi cần đối chiếu máy vừa rời ASG. Công cụ không gọi API tạo/sửa/xóa AWS và không đọc giá trị secret. Không chạy trên profile không xác minh account. `--profile` là tham số bắt buộc để tránh dùng nhầm môi trường.

Chạy ghi nhận runner song song:

```powershell
./scripts/assessment/observability/runner.ps1 -OutputCsv .local/assessment/runner.csv -Samples 4 -IntervalSeconds 30
```

Sau collector, tạo biểu đồ từ CSV private:

```powershell
py -3 scripts/assessment/observability/chart.py .local/assessment/<run_id>/metrics.csv --out .local/assessment/<run_id>/charts
```

Biểu đồ `tasks-ec2-targets.svg` đối chiếu ba nhóm theo cùng timestamp; các series thiếu được ghi `(missing)`, không vẽ thành 0. Biểu đồ này cần CSV collector, không tạo dữ liệu đo từ ảnh Console.

`activities.csv` lưu sự kiện ASG và ECS service scaling theo `activity_id`, ghi bản cập nhật khi status chuyển. Một activity có thể có hai dòng (InProgress rồi Successful); không đếm chúng là hai lần scale. CSV/SVG có thể chứa tên tài nguyên hoặc mốc vận hành; review và làm sạch trước khi chuyển sang `evidence/assessment/<run_id>/`. Giữ private manifest và thông tin truy cập ngoài Git. Không xuất dữ liệu giả vào evidence công khai.

## Kiểm tra preflight trước C3/C4/C5

| Mục | Nguồn và điều kiện cần xác minh | Trạng thái phiên này |
|---|---|---|
| Account/region, thời gian runner | STS account khớp; Sydney; UTC đồng bộ | BLOCKED |
| API/service/ALB | API tối thiểu 2 running, rollout hoàn tất, ít nhất 2 targets healthy, API task cùng digest; worker/publisher ready | NOT_RUN |
| ASG/ECS placement | Min/desired/max, in-service, container instances ACTIVE; RAM/ENI còn lại từng AZ, rolling headroom và AZ còn lại đủ slot cho dịch vụ thiết yếu | Ảnh Console cho thấy ASG 4/4 Healthy InService và 4 ECS instances Active; có RAM khả dụng của một máy, ENI/headroom theo AZ chưa đo, collector NOT_RUN |
| DB connections | RDS `DatabaseConnections`; chạy read-only `SHOW max_connections` trong VPC và kiểm budget 66 cùng reserve/rolling trong `capacity.md` | Ảnh Console hiển thị khoảng 8 kết nối tại thời điểm xem; `max_connections` và headroom chưa kiểm, collector NOT_RUN |
| Restore | RDS Multi-AZ/retention/latest restorable; quota DB instance/storage/snapshot và IAM/KMS cho DB tạm, phối hợp B4 | Ảnh Console cho thấy Multi-AZ, backup tự động 1 ngày và các snapshot Available; Service Quotas báo Access denied, quota/IAM/KMS và restore drill chưa xác minh |
| Redis | Trạng thái replication group, cả hai node, Multi-AZ/failover và metric từng node; xác nhận cache chỉ giữ admission, DB giữ reservation | Ảnh Console cho thấy Redis 7.1.0, `cache.t3.micro`, hai node Available, Multi-AZ và automatic failover bật; hành vi failover, memory/network headroom chưa kiểm |
| Queue/email/alarm | Queue/DLQ policy, backlog, worker, SNS subscription confirmed, alarm actions; C2 xác nhận email disabled trước tải | NOT_RUN |
| Runner | k6 version; CPU, RAM, network và clock trong smoke; runner không nằm trong ASG | BLOCKED: k6 không có trong PATH ở máy soạn |

`preflight.json` chỉ tự thu được phần AWS API phù hợp, **không tự xác nhận** `max_connections`, schema, tốc độ runner hay khả năng restore IAM/KMS. Người chạy điền kết quả kiểm tra bổ sung trong manifest/báo cáo cùng timestamp và nguồn. C1 chỉ đạt khi các mục này có bằng chứng và smoke thật; kết quả collector `COLLECTED_REVIEW_REQUIRED` không phải `PASS`.

## Metrics và cách đọc

`metrics.csv` có `sample_at,metric,value,unit,source_at,status`. ECS service `desired/running/pending`, ASG `desired/in_service`, ALB healthy lấy từ describe tại thời điểm lấy mẫu. ECS container `runningTasksCount` và `remainingResources` được cộng theo AZ; giá trị thiếu được ghi `MISSING`, không tính thành 0. Không suy có thể đặt task chỉ từ RAM nếu ENI hết. `preflight.json` ghi capacity provider và liên kết ASG để đối chiếu topology. CloudWatch dùng `GetMetricData` period 60 giây, vì vậy lặp lại giá trị giữa các lần lấy mẫu 30 giây là bình thường. Metric không có datapoint được ghi `MISSING_OR_DELAYED`, không ghi 0.
`alb.request_count` là tổng request trong 60 giây CloudWatch; `alb.rps` chia tổng đó cho 60, không biểu thị RPS tức thời. Target 4xx/5xx và ALB 4xx/5xx được lưu riêng. `ReadLatency`/`WriteLatency` RDS lưu theo giây, dù Console có thể hiển thị mili giây. DB lock wait, thời điểm Redis failover và request stream chứng minh nhiều API task nhận tải chưa có metric xác minh trong phiên này; cần bổ sung nguồn SQL/events/app logs ở các bài C3–C5 và ghi rõ khi thiếu.
`collector.duration_seconds` cho biết một vòng thu thập mất bao lâu. Nếu vượt `--interval`, status là `OVER_INTERVAL`; CSV giữ timestamp thực, không giả rằng đã đạt chu kỳ 15–30 giây. Khi đó giảm số truy vấn hoặc tăng interval trong giới hạn 30 giây và ghi hạn chế nếu vẫn chậm.

CloudWatch dimensions được căn theo Terraform: `ClusterName/ServiceName` cho ECS, `ClusterName/CapacityProviderName` cho reservation, `AutoScalingGroupName` cho ASG và EC2 CPU, `LoadBalancer/TargetGroup` cho ALB target, `DBInstanceIdentifier` cho RDS, `CacheClusterId` cho Redis, `QueueName` cho SQS. CPU credits dùng `InstanceId` từng EC2, không dùng dimension ASG. Các metric ứng dụng không có dimensions. Nếu metric vẫn thiếu sau vài phút, dùng CloudWatch Metrics Console kiểm namespace/dimensions và ghi thiếu thật; không tự nội suy.

Redis có hai node nên collector ghi `redis.node_1.*` và `redis.node_2.*` theo **ID node cố định** (connections, engine CPU và freeable memory), ánh xạ ID nằm trong `preflight.json`. Tên `node_1/node_2` không đồng nghĩa primary/replica sau failover; đối chiếu role thực tế bằng Console/API tại thời điểm phân tích. Ảnh dashboard Redis có 165 metric nhưng không cung cấp datapoint gốc, statistic hay baseline tải; chưa thể kết luận hiệu năng cache từ đường biểu đồ.

CSV chưa đủ chứng minh autoscaling: ở C3 cần đối chiếu scaling activity, task placement, healthy target và request stream từ nhiều API task, SNS nhận alarm workload thật. C4/C5 cần events, probe nghiệp vụ và timeline riêng. Không diễn giải task tăng là EC2 đã tăng.

## Kết quả kiểm tra trong phiên soạn

- `python -m unittest discover -s scripts/assessment/observability -p test_local.py -v`: **6/6 đạt**, gồm account guard, scaling activity, capacity provider, task theo AZ, missing metric, dimensions Redis/EC2, phép tính ALB RPS và khoảng trống trên chart. Fixture dùng thư mục Git ignored vì ACL sandbox Windows chặn `TemporaryDirectory` mode 0700.
- Python `py_compile` cho collector/chart/test: đạt. Chạy CLI `chart.py` từ CSV synthetic và parse XML: **4/4 SVG hợp lệ**. `runner.ps1` ghi một mẫu local CPU/RAM/network trạng thái `OBSERVED`. Đây là kiểm thử chức năng trên máy soạn, chưa phải runner k6 bên ngoài ASG.
- Danh mục 20 ảnh Console đã che định danh và SHA-256: **20/20 khớp**. Bản gốc chỉ giữ trong `.local/assessment/c1-originals/` (Git ignored); chưa commit/push.
- Smoke AWS, collector runtime AWS, chart từ AWS, kiểm `max_connections`, quota và runner k6: **BLOCKED/NOT_RUN**, không có số liệu thật.

### Ảnh AWS Console do người dùng cung cấp ngày 19/11/2026

Nguồn là 20 ảnh AWS Console người dùng đính kèm trong cuộc trao đổi; bản đã che và SHA-256 được lưu tại [evidence-c1](./evidence-c1/README.md), bản gốc giữ riêng trong `.local/assessment/c1-originals/`. Đây là **minh chứng giao diện do người dùng cung cấp**, không phải kết quả collector hay chuỗi thời gian AWS được agent xác minh độc lập. Các màn hình được chụp/refresh ở thời điểm khác nhau; chỉ kết luận thuộc tính hiển thị rõ trên bản gốc và nêu rõ khi vùng che làm mất chi tiết.

| Màn hình | Quan sát được | Chưa chứng minh |
|---|---|---|
| ECS cluster Services | `labseat-lab` Active tại Sydney; 3 services Active, 4 tasks đang chạy, 0 pending, 4 registered container instances. Ảnh đầu hiển thị 19/11/2026 22:42 UTC+7. | Số ASG InService, vị trí AZ, khả năng tăng thêm task. |
| ECS Tasks | 2 API, 1 worker, 1 publisher Running; API Health Healthy, worker/publisher Health Unknown trên ảnh. | Digest, request distribution, correctness, trạng thái health của background service theo probe nghiệp vụ. |
| ECS Infrastructure | Ảnh trước hiển thị 4 container instances `t3.small` Active khi phần provider đang loading. Ảnh sau hiển thị provider `labseat-lab` với kiểu Autoscaling EC2, 4 instances Active, task count theo máy 2/1/1/0; 3 máy ở AZ 2b, 1 máy ở AZ 2a. | ENI còn lại từng AZ, CPU credits, khả năng đặt task mới. |
| ECS container instance | Một máy `t3.small` ở AZ 2b, thuộc provider `labseat-lab`/ASG `labseat-lab-app`, có 2 tasks running; CPU khả dụng 1,536 units, RAM khả dụng 505 MiB tại thời điểm ảnh. | ENI còn lại, CPU credits, khả năng nhận thêm task và trạng thái các máy khác. |
| API service | 2/2 tasks running, deployment Success; 2 load balancer targets Healthy và 0 Unhealthy. | Latency/SLO và autoscaling dưới tải. |
| API service metrics | UI hiển thị đồ thị CPU, memory, network và service tasks trong khoảng xem 3 giờ. | Datapoint gốc, exact dimensions, CSV có thể tái tạo hoặc ngưỡng nghiệm thu. |
| ASG Details/Instance Management | `labseat-lab-app` desired 4, min 2, max 6, trạng thái At the desired capacity; 4 `t3.small` InService và Healthy. Bảng instance cho thấy 3 ở AZ 2b, 1 ở AZ 2a. | RAM/ENI và CPU credits từng máy; lý do desired 4; capacity AZ còn lại khi fault. |
| ASG Activity | Lịch sử có các lần launch/terminate Successful và các scale-in Cancelled với lý do instance còn được bảo vệ khỏi scale-in. | Scaling do bài tải C3 gây ra, thời điểm task ECS thay đổi, target healthy và request traffic sau scale. |
| RDS Configuration | `labseat-lab` Available, PostgreSQL 16.13 trên `db.t4g.micro` (1 GiB RAM), storage gp3 20 GiB, mã hóa bật; Multi-AZ Yes, primary ở AZ 2b và secondary ở AZ 2a. | `max_connections`, reserve kết nối, IOPS/throughput thực dưới tải và tình trạng restore. |
| RDS Maintenance and backups | Backup tự động bật, retention 1 ngày; ba snapshot tự động ngày 17–19/11 hiển thị Available; màn hình hiển thị mốc thời gian khôi phục 19/11/2026 23:13 UTC+7. | Quota và quyền tạo DB tạm, KMS, thời gian restore/RTO; snapshot Available chưa chứng minh restore thành công. |
| RDS Monitoring | Dashboard một giờ hiển thị `DatabaseConnections` khoảng 8, CPU khoảng 4%; có đồ thị CPU credits, FreeableMemory, FreeStorageSpace, ReadLatency và WriteLatency. Ảnh latency hiển thị cả đơn vị seconds và milliseconds do Console quy đổi. | Datapoint gốc, statistic/period chính xác, baseline dưới tải, ngưỡng DB budget. Không lấy giá trị chính xác từ pixel đồ thị. |
| RDS Service Quotas | Console trả `Access denied` cho `servicequotas:ListAWSDefaultServiceQuotas`. | Quota áp dụng và headroom cho restore; cần quyền đọc quota phù hợp hoặc người có quyền cung cấp giá trị. |
| Redis replication group/nodes | `labseat-lab` Redis 7.1.0, `cache.t3.micro`, hai node Available (`labseat-lab-001` primary, `labseat-lab-002` replica), Multi-AZ, automatic failover và mã hóa at-rest/in-transit bật trên ảnh. | Failover thực tế, role sau chuyển đổi, cache headroom và độ trễ ứng dụng. |
| Redis metrics | Console hiển thị CPU/engine CPU, memory, network và active connections theo hai node trong cửa sổ xem. | Datapoint gốc, statistic/period, tải tương ứng, ngưỡng bão hòa; không suy số chính xác từ pixel. |

Các ảnh này hỗ trợ baseline trực quan nhưng **không thay thế** smoke collector, preflight DB/quota/runner, CSV/chart thực hoặc C3 load test. Chỉ bản đã che nằm trong thư mục evidence của repo; bản gốc chứa định danh vận hành phải ở ngoài Git.

## Thao tác AWS Console để bổ sung evidence

1. Đăng nhập đúng account/region Sydney; chụp thời điểm UTC và trạng thái ECS Cluster → Services/Tasks: desired/running/pending, digest, placement/AZ.
2. EC2 → Auto Scaling Groups: min/desired/max, InService, instance IDs/AZ, scaling activities; ECS container instances xem registered/remaining memory/ENI. Ghi cấu hình và capacity của AZ còn lại.
3. EC2 → Target Groups: healthy/unhealthy; CloudWatch Metrics: các dimensions ở trên, datapoint và độ phân giải. Kiểm alarms/action và SNS subscription `Confirmed` mà không lộ email.
4. RDS → DB: đối chiếu status, Multi-AZ, retention, LatestRestorableTime bằng API/Console tại giờ chạy; chạy `SHOW max_connections` qua kết nối read-only trong VPC, đo `DatabaseConnections` và tính headroom so với budget 66. Kiểm quyền/quota DB instances, snapshots, storage và KMS cho DB restore tạm với B4. Ảnh Service Quotas hiện báo Access denied; nhờ người có quyền đọc quota hoặc cấp quyền đọc phù hợp, ghi giá trị quota áp dụng cùng timestamp. Xác minh restore bằng drill của B4 trước khi đánh dấu đạt.
5. SQS → Queue/DLQ: redrive, visibility, backlog/age. Xác nhận worker/publisher và email window với C2.
   Với Redis, ElastiCache → replication group/nodes: xác nhận role và trạng thái hai node tại giờ chạy, lấy đúng cache cluster IDs, đối chiếu metrics `node_1/node_2` và ghi thời điểm failover nếu có.
6. Trên runner ngoài ASG: chạy collector một smoke, ghi CPU/RAM/network đồng thời, tạo SVG từ CSV, lưu manifest/evidence đã làm sạch. Chỉ sau đó cập nhật trạng thái C1 và bàn giao baseline cho C3–C5.

## Chốt C1 và điều kiện trước C3

**Source đã sẵn sàng để chạy thử:** collector chỉ đọc, preflight, CSV/activity, chart SVG và đo runner trên Windows; sáu unit test, CLI chart và một mẫu runner local đã đạt. **Nghiệm thu AWS: BLOCKED.** Chưa có collector smoke trên AWS, runner k6 độc lập, preflight đầy đủ, baseline metrics/CSV/chart từ AWS hoặc request stream. Ảnh Console ở trên không chuyển trạng thái C1 thành PASS. Dừng phát triển C1 tại đây; chỉ cập nhật kết luận khi có evidence chạy thật và review của nhóm.

Các điều kiện bắt buộc trước khi khởi động C3:

1. B1/B2 bàn giao manifest dữ liệu và session còn hạn; B3 smoke chức năng đạt.
2. C2 xác nhận `EMAIL_BACKEND=disabled`, worker/publisher vẫn hoạt động và job synthetic không gửi Brevo; thống nhất cửa sổ email với cả nhóm.
3. C1 smoke collector trên đúng account/region, CSV và chart tái tạo được, task/EC2/ALB target tách riêng; lỗi API và metric thiếu được ghi, không có khoảng trống không giải thích.
4. Xác nhận DB `max_connections` và budget 66, RAM/ENI/placement theo AZ, ALB healthy, quota/headroom restore và các alarm/SNS liên quan; Service Quotas hiện Access denied cần người có quyền xác minh.
5. Runner k6 nằm ngoài ASG, thời gian UTC đồng bộ, CPU/RAM/network không bão hòa trong smoke; có baseline nhẹ và khả năng ghi request stream nhiều API task.

**Bàn giao sang C2:** theo [kế hoạch bốn ngày](../../sprints/ke-hoach-nghiem-thu-4-ngay.md), bước tiếp theo là rà soát email runbook và `booking.js`/`platform.js`, chuẩn bị chế độ `SESSIONS_FILE` từ B2 và quy trình ghi nhận backend/task definition trước–sau. Việc đổi backend worker, phát job synthetic và khôi phục Brevo cần cửa sổ vận hành được nhóm phối hợp; chưa thực hiện trong C1.
