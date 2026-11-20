# C4 — Diễn tập mất compute ứng dụng một AZ

Chủ sở hữu: Người 3. **Trạng thái: BLOCKED / inject NOT_RUN / rollback NOT_RUN.** Phạm vi là các EC2 thuộc ASG ứng dụng ở **một AZ được chốt**, không can thiệp subnet, NAT, RDS, Redis hay toàn AZ. [Kế hoạch C4](../../sprints/ke-hoach-nghiem-thu-4-ngay.md#c4-diễn-tập-mất-compute-một-az) yêu cầu C3 đã kết thúc, baseline ổn định, B3 probe và email disabled. [C3 hiện tại](load-report.md) có năm bài AWS NOT_RUN; không coi đây là baseline sau tải. Không chạy đồng thời C3/C5/PITR/S3 restore.

## Quyết định kỹ thuật và giới hạn

- ASG `labseat-lab-app` trong [Terraform](../../../infra/modules/compute/main.tf) có hai app subnets, min/desired/max từ config và `protect_from_scale_in=true`. ECS Capacity Provider bật managed scaling, termination protection và draining; các service dùng `awsvpc`, `spread` AZ và `binpack` memory theo [Terraform ECS](../../../infra/modules/compute/ecs.tf). Đây là cấu hình nguồn, phải đối chiếu AWS thực tại giờ chạy.
- Snapshot [C1/B4](../../../evidence/assessment/20261119T172832Z-b4-c1-preflight/summary.md) ngày 19/11 có ASG 4 EC2 (2a:1, 2b:3), API 2, worker 1, publisher 1; cận trên slot trống 2a:1, 2b:3. ENI `remainingResources` từ ECS thiếu. Cận trên không chứng minh AZ còn lại chứa được mọi task thiết yếu; **không chọn/stop EC2 từ snapshot này**.
- [Ảnh Console mới ngày 20/11](../../../evidence/assessment/20261120T1455Z-c4-preparation/console-observations.md) cho thấy ASG 4 EC2 InService/Healthy chia 2–2 giữa 2a/2b, ECS 4 task running/0 pending, một API task trên 2a. Một EC2 2b còn khoảng 0,493 GiB (~505 MiB) available, dưới memory task API 512 MiB; các ảnh chưa có ENI slots hoặc ALB target healthy ở cả hai AZ. Đây là snapshot mới hơn, vẫn **không** chứng minh capacity AZ còn lại hay xác định target list cho inject.
- [Preflight AWS CLI chỉ đọc ban đầu](../../../evidence/assessment/20261120-c4-cli-preflight/summary.md) thấy 5 EC2. [Kiểm lại capacity](../../../evidence/assessment/20261120-c4-capacity-recheck/summary.md) thấy ASG trở về 4 EC2, chia 2–2; target API khỏe cả hai AZ. ECS vẫn không trả `remainingResources.ENI`, nhưng preflight dùng EC2 interface limit trừ số đang gắn trên máy không có trunk ENI. Các task mất xếp được ở AZ còn lại tại snapshot; **không còn thêm một slot API overlap ở cả hai hướng**, nên prepare/inject BLOCKED. Snapshot không dùng cho prepare khi clock runner chưa đồng bộ hoặc đã quá 10 phút.
- AWS xác nhận cập nhật `placementConstraints` của ECS service không khởi động deployment mới, còn cập nhật `networkConfiguration` thì có. Vì thế phương án *ứng viên* là constraint `memberOf` AZ còn lại cho ba service, không đổi network config. Vẫn phải kiểm thực tế task IDs/target health trước và sau cập nhật; nếu task bị chuyển/drain trước fault thì rollback và đánh BLOCKED. [AWS UpdateService](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_UpdateService.html).
- Tạm hạn chế ASG app subnet còn AZ sống sót để replacement không quay về AZ mục tiêu; lưu đúng danh sách subnet và suspended processes gốc. Suspend `AZRebalance` trước khi cập nhật; việc suspend **không chặn mọi cân bằng khi scale in/out**, nên phải giám sát scaling activity/task IDs giữa các bước. Nếu subnet update gây drain/terminate trước inject, rollback và không ghi là mất AZ. [AWS suspended processes](https://docs.aws.amazon.com/autoscaling/ec2/userguide/understand-how-suspending-processes-affects-other-processes.html).
- `ec2 stop-instances` trên instance trong ASG sẽ khiến ASG đánh unhealthy và thay thế; đây là cơ chế inject dự kiến, **không phải** manual desired count hay `terminate-instance-in-auto-scaling-group`. Chỉ dùng danh sách EC2 đã khóa từ dry-run, xác minh lại membership/AZ ngay trước lệnh. [AWS health checks](https://docs.aws.amazon.com/autoscaling/ec2/userguide/health-check-grace-period.html).

## Gate trước khi chuẩn bị

| Gate | Cần có | Hiện tại |
|---|---|---|
| Window/C3/B3/C2 | C3 dừng và hệ thống ổn định; B3 probe trước/sau cùng run ID; worker disabled và job synthetic không gửi; C5/restore không chạy | BLOCKED: [C3](load-report.md) chưa có tải AWS; [B3](../functional/report.md) X02 NOT_RUN; [C2](runbook.md#c2--cửa-sổ-worker-disabled--restore) chưa chốt |
| Runner và AWS | Clock đồng bộ UTC, AWS CLI đúng account/region, quyền read/ASG update/ECS update/EC2 stop/rollback, collector chạy liên tục | Một phần PASS: profile `tv2-compute` đúng account/region và các API preflight đọc được. BLOCKED: Windows Time chưa đồng bộ; quyền mutate/rollback và collector liên tục chưa xác minh. [CLI preflight](../../../evidence/assessment/20261120-c4-cli-preflight/summary.md) |
| Capacity AZ sống sót | API tối thiểu, worker, publisher và thêm một API overlap; CPU, RAM, ENI/branch ENI, subnet IP, DB budget, ASG max6, alarm/SNS; đủ slot thực hoặc chuẩn bị capacity có ghi riêng | BLOCKED: phép xếp task cần thay PASS ở cả hai hướng, nhưng `survivor_api_overlap=BLOCKED` ở cả hai. Cần capacity bổ sung rồi kiểm lại live; DB budget chưa chốt |
| Baseline | ASG subnet/desired/min/max/processes/activity, EC2 InService/Healthy, ECS agent ACTIVE/connected; ECS service constraints/network/task ARN/digest/AZ/instance; API target healthy ở cả hai AZ theo task IP; queue/DLQ, RDS, Redis; 7 invariants và UI probe | NOT_RUN tại cửa sổ C4 |
| Isolation dry-run | Target AZ có API task; mọi target EC2 đúng ASG và đúng AZ; survivor đã đủ slot; sau constraint/subnet đổi, task/EC2/target cũ không dịch chuyển trước inject | NOT_RUN |

## 1. Preflight và dry-run chỉ đọc

Chạy từ root repo trên runner ngoài ASG, với profile/account và Target Group ARN đã xác minh qua kênh private. Script dừng nếu account sai, chỉ ghi JSON private dưới `.local/assessment/`, in **số lượng**, không in ID. Không commit file private. Chọn AZ có API đang chạy; ưu tiên phương án tác động ít EC2 hơn **chỉ khi** AZ còn lại đủ capacity thực. Không tự suy từ số EC2.

```powershell
./scripts/assessment/faults/preflight.ps1 `
  -Profile '<profile>' -ExpectedAccount '<12-digit-account>' `
  -TargetAz 'ap-southeast-2a' -TargetGroupArn '<actual-target-group-arn>' `
  -OutputDir '.local/assessment/<c4-run-id>/preflight'
```

Review `baseline.private.json`: `dry_run.target_instance_ids`, target task ARN/AZ/service, survivor EC2, `survivor_slots` với `eni_source`, `placement_dry_run` theo từng EC2, `healthy_api_by_az`, subnet IPs, ASG processes, ECS service network/constraints, ALB target mapping. Script chỉ báo `exact_survivor_slots=PASS` khi xếp được từng target task vào CPU/RAM/ENI còn lại trên từng EC2. Nếu ECS không báo ENI và máy **không có trunk ENI**, script lấy giới hạn native network interfaces từ EC2 API trừ số interface đang gắn; thiếu dữ liệu hoặc có trunk không xác định thì BLOCKED. Gate riêng `survivor_api_overlap` yêu cầu còn một slot API (CPU/RAM/ENI) sau khi xếp task mất. Gate `alb_api_az_coverage` đối chiếu private IP API task với target healthy ở cả hai AZ. Phép xếp mô phỏng vẫn cần xác minh task placement, subnet IP và activity thật ngay trước prepare. Giữ SHA-256 baseline và source commit/script hash; chốt target list một lần. Không dùng ID trong ảnh cũ.

Tạo bản private từ [mẫu attestation](../../../scripts/assessment/faults/attestation.example.json) trong `.local/assessment/<c4-run-id>/attestation.private.json`. Chỉ đổi mỗi gate thành `true` khi có đường dẫn evidence thật; mặc định tất cả `false`. Bộ script `prepare/inject` từ chối nếu thiếu một gate. Không commit bản private. Chạy probe nhẹ trong terminal riêng trước prepare và tiếp tục qua rollback:

```powershell
./scripts/assessment/faults/observe.ps1 `
  -OutputCsv '.local/assessment/<c4-run-id>/http-probe.private.csv' `
  -IntervalSeconds 15 -Samples 240
```

## 2. Prepare isolation — chỉ trong cửa sổ C4 đã chốt

Lưu baseline private trước mọi mutate. Mọi thay đổi dưới đây chỉ ở **ASG ứng dụng** và **ba ECS service**; không sửa NAT/subnet route, ALB AZ, RDS/Redis hoặc task definition. Thực hiện tuần tự, kiểm task ARN, EC2 ID/AZ, desired/running/pending, target health, scaling activity sau **mỗi** bước:

1. Nếu AZ sống sót thiếu slot cho task cần thay **hoặc API overlap**, chuẩn bị capacity theo kế hoạch riêng trong giới hạn ASG max6; ghi rõ desired thủ công và mốc UTC, không dùng làm bằng chứng autoscaling C3. Chỉ tiếp tục khi instance mới ACTIVE/agent connected, ENI/RAM/CPU và subnet IP thật đủ; nếu không, BLOCKED. Không drain target EC2 để tạo chỗ.
2. Ghi suspended processes gốc; chỉ suspend thêm `AZRebalance` và, nếu policy có thể scale in giữa window, `AlarmNotification` theo quyết định điều phối. Giữ `Launch`, `Terminate`, `HealthCheck`, `ReplaceUnhealthy` hoạt động để instance đã stop được thay thế. Không resume một process vốn đã suspended trước C4.
3. Cập nhật `placementConstraints` `memberOf attribute:ecs.availability-zone == <survivor-AZ>` cho API, worker, publisher; bảo toàn constraints gốc trong manifest để restore chính xác. Không đổi `networkConfiguration`, task definition hoặc desired count. Đọc lại cả ba service và task/target; nếu deployment mới hoặc task cũ dịch chuyển, rollback ngay.
4. Chỉ khi trên còn ổn, giới hạn ASG `VPCZoneIdentifier` vào app subnet của AZ sống sót, giữ min/desired/max. Đọc lại ASG Activity, EC2, ECS tasks và ALB. Nếu target EC2/task thay đổi **trước** lệnh inject, dừng và rollback; ghi `isolation=FAIL`, không gọi đó là AZ loss. AWS không có dry-run chung cho chuỗi thay đổi này; phép kiểm từng bước là gate bắt buộc.
5. Rerun preflight vào thư mục `prepared` và diff với baseline: target list và task ARN mục tiêu phải giữ nguyên, ASG chỉ còn subnet sống sót, three service constraints đúng, healthy target còn ≥2, không có rollout bất ngờ. Chụp Console/video UTC ngay trước inject. Chỉ khi người điều phối ký xác nhận C3/B3/C2/clock/capacity/rollback và không có fault khác mới được chuyển bước 3.

[prepare.ps1](../../../scripts/assessment/faults/prepare.ps1) thực hiện các thay đổi ở bước 2–4 theo thứ tự và kiểm lại target/task/health sau từng bước; mặc định chỉ dry-run, `-Execute` mới mutate. Nếu prepare lỗi, script yêu cầu rollback baseline; operator phải xác nhận rollback thật và không tiếp tục inject. Script không tự tăng desired hoặc chuẩn bị capacity.

```powershell
./scripts/assessment/faults/prepare.ps1 `
  -Profile '<profile>' -ExpectedAccount '<12-digit-account>' `
  -BaselinePath '.local/assessment/<c4-run-id>/preflight/baseline.private.json' `
  -AttestationPath '.local/assessment/<c4-run-id>/attestation.private.json'
# Sau review dry-run và tất cả gate PASS, lặp lại lệnh với -Execute.
```

Không dùng `terraform apply` cho prepare/rollback; module Terraform yêu cầu hai AZ, một apply ở giữa window có thể hoàn tác khác biệt ngoài phạm vi. Không lưu JSON task definition có secret values trong evidence public.

## 3. Inject đúng EC2 đã chốt

Trước lệnh, dùng `describe-auto-scaling-groups`, `describe-instances`, ECS `describe-tasks` để đối chiếu lại **toàn bộ** target IDs với baseline/prepared; nếu có ID mới, AZ sai hoặc target list rỗng, BLOCKED. Ghi `incident_at_utc` ngay trước `stop-instances`; truyền ID bằng array PowerShell lấy từ manifest private đã khóa, không dùng wildcard, tag filter mới hoặc tất cả instance trong ASG. Không dùng `ecs update-container-instances-state DRAINING`, `stop-task`, `terminate-instances`, thay route/subnet hay manual scale desired để mô phỏng fault. Lệnh EC2 stop là tác động có thật và chỉ chạy khi các gate trên PASS.

```powershell
# Minh họa thao tác có kiểm soát; $targetIds lấy từ manifest private đã khóa,
# đối chiếu live và in danh sách cho operator duyệt trước khi thực thi.
$targetIds = @('<reviewed-instance-id>')
aws ec2 stop-instances --instance-ids $targetIds `
  --profile '<profile>' --region ap-southeast-2 --no-cli-pager
```

Thao tác chuẩn là [inject.ps1](../../../scripts/assessment/faults/inject.ps1), mặc định dry-run; nó rerun preflight live, đòi target IDs nhập lại chính xác, age snapshot ≤10 phút, ECS constraints và ASG subnet sống sót, capacity/health PASS. `-Execute` mới gọi `stop-instances`. Lưu output private ở thư mục live; không copy ARN/ID thô vào Git.

```powershell
./scripts/assessment/faults/inject.ps1 `
  -Profile '<profile>' -ExpectedAccount '<12-digit-account>' `
  -BaselinePath '.local/assessment/<c4-run-id>/preflight/baseline.private.json' `
  -PreparedPath '.local/assessment/<c4-run-id>/preflight/prepared.private.json' `
  -AttestationPath '.local/assessment/<c4-run-id>/attestation.private.json' `
  -ConfirmInstanceIds '<exact-comma-separated-locked-IDs>'
# Sau review dry-run và live snapshot, lặp lại với -Execute.
```

Ghi response private, sau đó đối chiếu EC2 state/ASG replacement chỉ ở AZ sống sót, ECS task PENDING/RUNNING, target health và API request stream. Một instance restart hoặc một task restart không chứng minh mất nhóm compute ở một AZ; tất cả target EC2 của AZ mục tiêu phải được xác minh stop/ASG replacement theo timeline.

## 4. Observe và gate dừng

Bắt đầu collector C1, runner CPU/RAM/network và probe GET nhẹ **trước** prepare, giữ qua inject và rollback. [Lệnh collector, chart và phân biệt sampling 15–30 s với CloudWatch period 60 s](runbook.md#smoke-c1-chỉ-đọc). Chạy B3 probe + bảy invariant SQL read-only trước/sau và khi app ổn định, không dùng health 200 thay correctness. Không bật email thật, không tạo booking lớn. Ghi UTC từng mốc: prepare, incident, first 5xx, loss target/task, ASG activity, EC2 register, replacement task healthy, UI/probe/SQL đạt, rollback và baseline hai AZ đạt. Giữ source_at/status cho metric thiếu hoặc chậm, k6/HTTP response mã lỗi, video Console có clock UTC và danh sách target đã che.

Dừng fault/đi rollback nếu invariant sai, mất toàn bộ healthy targets, 5xx >5% liên tục 2 phút, DB connections chạm budget, phụ thuộc ngoài compute lỗi, capacity vượt max6/API max8, hoặc 60 phút chưa phục hồi. Nếu rollback không khôi phục ngay, ghi trạng thái lỗi và escalation; không xóa bằng chứng lần lỗi. Thời gian hồi phục đo từ `incident_at_utc` tới **ready_and_verified_at** có UI + B3 + invariant, không lấy first health 200 làm RTO.

## 5. Rollback và nghiệm thu

Sau khi app ổn định ở AZ còn lại, khôi phục nguyên danh sách ASG app subnets, từng ECS service placement constraint gốc và chỉ resume process mà C4 vừa suspend. So sánh field-by-field với baseline; không tự giảm desired/capacity tạm cho đến khi hai AZ đã có ECS instance ACTIVE, API target healthy và worker/publisher ổn định. Capacity tạm phải được cleanup theo change record, tránh làm mất task đang chạy. Không start lại EC2 cũ nếu ASG đã terminate/thay thế chúng. Chờ AZRebalance và placement tự phân bố, kiểm hai AZ, healthy targets, queue/DLQ, RDS/Redis, alarm/SNS, UI, B3 và bảy invariant. Nếu chưa trở lại baseline hai AZ, C4 **FAIL/BLOCKED**, không ghi PASS dù app hiện trả 200.

[rollback.ps1](../../../scripts/assessment/faults/rollback.ps1) mặc định dry-run, so sánh current ASG subnets/service constraints với baseline và từ chối cấu hình lạ; `-Execute` gửi yêu cầu hoàn tác trong thứ tự subnet → constraints → processes. Script **không** tự kết luận PASS hoặc ép ASG desired về giá trị cũ.

```powershell
./scripts/assessment/faults/rollback.ps1 `
  -Profile '<profile>' -ExpectedAccount '<12-digit-account>' `
  -BaselinePath '.local/assessment/<c4-run-id>/preflight/baseline.private.json'
# Sau review, lặp lại với -Execute; tiếp tục quan sát/đối chiếu baseline hai AZ.
```

Gói evidence private `.local/assessment/<c4-run-id>/`: baseline/prepared/final JSON, manifest/hash, target list, AWS activity/events, C1 metrics CSV/charts, runner CSV, HTTP probe, B3/SQL kết quả, video link và timeline UTC. Chỉ chuyển bản đã che sang `evidence/assessment/<c4-run-id>/` và dẫn từ [failover report](failover-report.md). **Hiện chưa có run ID fault, incident, CSV/video C4 hoặc kết quả rollback.**

## C5 — RDS rồi Redis failover (chưa kích hoạt)

**Gate bắt buộc:** C4 đã kết thúc và baseline hai AZ ổn định; C3 không chạy; không có PITR/S3 restore hay fault khác; runner UTC đồng bộ; cửa sổ và người trực rollback đã chốt; B3 probe nghiệp vụ cùng bảy truy vấn trong `scripts/tests/db-invariants.sql` có kết quả trước fault; worker email disabled được xác minh ở task đang chạy và không có mail thật; account/region/quyền đọc cùng quyền `rds:RebootDBInstance`, `elasticache:TestFailover` được kiểm chứng. Một service `running=desired` chỉ xác nhận một phần của gate. Không chạy bước Redis khi RDS/app chưa phục hồi đầy đủ. Nếu gate thiếu, chỉ thực hiện preflight đọc và ghi `BLOCKED`.

Tài liệu AWS hiện hành: [RDS RebootDBInstance](https://docs.aws.amazon.com/AmazonRDS/latest/APIReference/API_RebootDBInstance.html) yêu cầu `ForceFailover` cho **Multi-AZ DB instance**; Multi-AZ DB cluster dùng API khác. [ElastiCache TestFailover](https://docs.aws.amazon.com/AmazonElastiCache/latest/APIReference/API_TestFailover.html) nhận replication group và node group; giới hạn **15 node groups trong 24 giờ trượt**, có thể bị AWS chặn trong sự kiện vận hành. Kiểm Events/account quota thực ngay trước lệnh; sự kiện rỗng của một replication group không chứng minh quota toàn account còn 15. `TestFailover` là bài kiểm thử, không dùng làm công cụ sửa sự cố production.

### Preflight và baseline riêng cho từng bài

Chạy từ runner ngoài ASG với `--profile`/`--region` explicit; đối chiếu STS account private trước mọi resource call. Lưu raw JSON và log chứa ID, endpoint, địa chỉ vào `.local/assessment/<c5-run-id>/` (Git ignored), chỉ công bố bản tổng hợp đã che. Dùng `(Get-Date).ToUniversalTime().ToString('o')` và nguồn NTP/Windows Time đã đồng bộ để gắn mốc; AWS Event Date dùng đối chiếu. Không dùng timestamp từ runner mất đồng bộ để tính downtime. Chụp CLI version, source commit, config worker/task digest, ECS/ASG/ALB targets, RDS/Redis/SQS/alarms và DB connection budget. Ghi endpoint **dưới dạng hash**, DNS resolution theo thời gian private; không đổi endpoint production.

```powershell
$profileName = '<verified-profile>'
$region = 'ap-southeast-2'
aws sts get-caller-identity --profile $profileName --region $region --query Account --output text
aws rds describe-db-instances --db-instance-identifier '<verified-db-id>' --profile $profileName --region $region --output json
aws rds describe-events --source-type db-instance --source-identifier '<verified-db-id>' --duration 1440 --profile $profileName --region $region --output json
aws elasticache describe-replication-groups --replication-group-id '<verified-rg-id>' --profile $profileName --region $region --output json
aws elasticache describe-events --duration 1440 --profile $profileName --region $region --output json
```

RDS phải là DB instance `available`, `MultiAZ=true`, **không có `DBClusterIdentifier`**, không có pending modification/backup/maintenance chồng lên; lưu primary AZ, standby topology theo nguồn AWS, endpoint/DNS và Events. Redis phải `available`, `MultiAZ=enabled`, `AutomaticFailover=enabled`, xác minh đúng `NodeGroupId`, primary/replica AZ, TLS/ACL, endpoint và events. Xác nhận account-wide test failover 24 giờ và quyền bằng nguồn audit/CloudTrail/owner; IAM simulation hoặc thiếu AccessDenied không thay cho xác nhận thao tác. B3 marker và giao dịch/vé đã commit phải được đọc lại bằng SQL trước fault. Giữ probe HTTP nhẹ và collector C1 xuyên suốt, ghi `sample_at/source_at/status` và khoảng thiếu metric; CloudWatch period 60 giây không phải sampling 15 giây.

### RDS: inject, observe, phục hồi

Chỉ sau khi gate RDS PASS, chạy đúng **một lần** lệnh dưới đây với DB ID đã đối chiếu ngay trước lệnh. Ghi `incident_at_utc` và response private. Không chạy `failover-db-cluster`, không thay `DATABASE_URL`, DNS hoặc secret để che lỗi.

```powershell
aws rds reboot-db-instance --db-instance-identifier '<verified-db-id>' --force-failover --profile $profileName --region $region --output json
```

Lấy `describe-db-instances`, RDS Events và DNS resolution theo chu kỳ 15–30 giây, đồng thời probe GET và một workflow synthetic nhẹ đã duyệt. Ghi HTTP lỗi/timeout, thời gian reconnect DB, DB connections, AZ trước/sau, task/target health, ứng dụng/UI, marker/vé commit và bảy invariant SQL. `available` hoặc `/healthz` 200 chưa đủ: chỉ kết thúc khi B3 workflow và SQL xác nhận đúng. Giới hạn quan sát 60 phút; nếu mất phục vụ ngoài dự kiến, dừng synthetic traffic, chuyển sang recovery/incident với người trực, giữ toàn bộ dữ liệu lỗi. Không force failback để lấy topology mong muốn; ghi AZ cuối thật.

### Redis: inject sau khi RDS/app ổn định

Chụp baseline mới, xác minh node group/quota/events lại. Sau khi probe B3 và SQL hậu RDS PASS, chạy đúng **một lần**:

```powershell
aws elasticache test-failover --replication-group-id '<verified-rg-id>' --node-group-id '<verified-node-group-id>' --profile $profileName --region $region --output json
```

Theo dõi `describe-replication-groups`, `describe-events` replication group **và cache cluster**, DNS, kết nối TLS/ACL, admission join/wait/grant/heartbeat/expiry, lease/queue epoch và PubSub/realtime bằng client synthetic đã duyệt. Phân biệt state Redis tạm thời có thể mất hoặc đổi thứ tự với reservation/vé bền trong DB; không tuyên bố queue nguyên vẹn. Đối chiếu ticket/hold invariants và không cấp vượt sức chứa. Nếu cần operator recovery, ghi lệnh, người làm, thời gian và ảnh hưởng thứ tự chờ; không tự chạy failover lần hai. Giới hạn 60 phút và cùng quy tắc dừng/incident như RDS.

### Evidence và kết luận

Mỗi bài có run ID/UTC riêng, baseline/final config, AWS Events, CLI response, HTTP/SQL/B3 probes, CSV metrics/charts, lỗi/timeout, DNS/reconnect, video hoặc link Console đã che, `incident_at_utc`, `ready_and_verified_at`, thời gian thực và mọi operator action. Công bố tại `evidence/assessment/<c5-run-id>/`, dẫn từ [failover-report.md](failover-report.md); giữ raw private trong `.local`. Trạng thái `PASS` chỉ khi role/AZ chuyển được xác nhận **và** nghiệp vụ/invariants phục hồi; nếu chưa inject là `NOT_RUN/BLOCKED`, nếu đã chạy nhưng vi phạm ngưỡng là `FAIL`. Không gộp RDS và Redis thành một kết quả.
