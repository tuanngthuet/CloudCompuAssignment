# C1 — Preflight và smoke quan sát; chuẩn bị C2

Chủ sở hữu: Người 3. Trạng thái C1: **BLOCKED**. Runbook này dùng cho một lượt smoke quan sát **chỉ đọc** trên AWS Sydney; không tạo tải lớn, thay cấu hình, gửi email hoặc gây failover. Nguồn hiện có: [báo cáo C1](observability.md), [kế hoạch](../../sprints/ke-hoach-nghiem-thu-4-ngay.md), [capacity](../../deployment/capacity.md), [B1/B2](../../../evidence/assessment/b1b2-20261117a/summary.md), [B3](../functional/report.md) và [smoke Người 2](../../../evidence/assessment/20261119T172832Z-b4-c1-preflight/summary.md). Các giá trị từ snapshot cũ phải kiểm lại tại thời điểm chạy.

## Checklist trước khi chạy

Điền trạng thái `PASS`, `FAIL`, `BLOCKED` hoặc `NOT_RUN`, mốc UTC, người kiểm và đường dẫn bằng chứng vào bản sao private của bảng này. `PASS` chỉ dành cho mục có kiểm chứng đúng cửa sổ; nếu thiếu quyền, ghi mã lỗi và `BLOCKED`. Không ghi secret, token, ARN/account thô hoặc địa chỉ người nhận vào gói công khai.

| Hạng mục | Điều kiện và bằng chứng cần thu | Hiện tại |
|---|---|---|
| Runner ngoài ASG | Chứng minh runner không thuộc ASG được đo; `k6 version`, `aws --version`, phiên bản Python; CPU/RAM/network trước và trong smoke bằng `runner.ps1` | k6 v2.4.0 xác minh trên runner 20/11; ngoài ASG theo Người 3; saturation lúc tải còn BLOCKED |
| Clock | UTC trên runner, nguồn đồng bộ NTP/Windows Time và độ lệch; đối chiếu với timestamp AWS | FAIL tại 20/11 14:32 UTC: `w32tm` báo Local CMOS Clock, chưa đồng bộ; phải sửa và đo lại |
| AWS identity/read | `sts get-caller-identity` khớp account dự kiến, region `ap-southeast-2`, profile explicit; quyền đọc ECS/EC2/ASG/ELB/CloudWatch/RDS/ElastiCache/SQS/CloudWatch alarms/SNS. Ghi lỗi AccessDenied theo API | PASS tại smoke Người 2, cần kiểm lại ở runner hiện tại |
| API/ECS | Desired/running/pending từng service, rollout, digest/schema, task AZ, container instance resources, capacity provider và scaling activity | PASS tại snapshot 19/11 cho 2 API cùng digest; placement/headroom vẫn BLOCKED |
| ASG/EC2 | Min/desired/max, in-service/healthy, instance AZ, CPU credits; RAM/CPU/ENI thực theo container instance, EC2 attached ENI, IP trống subnet và khả năng đặt task khi mất một AZ | BLOCKED: ECS ENI thiếu, cận trên vật lý không chứng minh placement |
| ALB | Target group đúng, tối thiểu 2 healthy, unhealthy và target mapping theo AZ; thời điểm/độ phân giải CloudWatch; request stream chứng minh nhiều API task nhận request khi có probe hợp lệ | 2 healthy trong smoke cũ; request stream NOT_RUN |
| RDS | DB status/Multi-AZ, `DatabaseConnections` cùng `SHOW max_connections` read-only, reserve, budget 66 và rolling ceiling, schema/digest tương ứng | PASS tại snapshot Người 2: max 79, budget còn 8; kiểm lại trước tải |
| Queue/alarms/SNS | Queue/DLQ policy/redrive/visibility/depth/oldest age, publisher/worker running, alarm state/action, SNS subscription confirmed | Snapshot Người 2 có queue/DLQ 0, 14 alarm OK, 1 subscription confirmed; delivery workload NOT_RUN |
| Restore quota/quyền | Quota DB instances/storage/snapshots, subnet/IP, class/KMS/secret/IAM cho DB/app tạm; phối hợp B4, không dùng simulation allowed làm restore PASS | Quota snapshot có; IAM/KMS/placement/restore thật BLOCKED |
| Session/email cho C2/C3 | B2 bàn giao session mới, 100 user riêng, TTL đủ cửa sổ, CSRF/cookie/seat mapping; C2 có backend worker trước/sau và job test SKIPPED | BLOCKED: 100 session của B2 đã hết hạn; C2 chưa thực hiện |

## Smoke C1 chỉ đọc

1. Trên runner **ngoài ASG**, xác minh tool và đồng hồ. Dùng profile được cấp; không in credential: `k6 version`, `aws --version`, `(Get-Date).ToUniversalTime().ToString('o')`, `w32tm /query /status`. Nếu clock không đồng bộ, ghi `BLOCKED`. Lưu thông tin phiên bản và độ lệch ở file private. Profile `tv2-compute` hiện đăng nhập đúng account và đã chạy [preflight C4 chỉ đọc](../../../evidence/assessment/20261120-c4-cli-preflight/summary.md); Windows Time vẫn chưa đồng bộ và độ đầy đủ datapoint C1/C3 chưa đạt điều kiện nghiệm thu.
2. Xác nhận account/region bằng `aws sts get-caller-identity --profile <profile> --region ap-southeast-2 --query Account --output text` và đối chiếu account kỳ vọng qua kênh private. Lấy tên/ARN/suffix thực từ AWS Console hoặc inventory mới; **không** dùng tên trong tài liệu lịch sử như nguồn hiện tại.
3. Bắt đầu đo runner song song với collector. Chạy bốn mẫu cách 30 giây, không chạy k6 trong lượt quan sát này. Các tham số giữa `<...>` là chỗ điền từ nguồn private trước khi chạy:

```powershell
./scripts/assessment/observability/runner.ps1 -OutputCsv .local/assessment/c1-runner.csv -Samples 5 -IntervalSeconds 30

py -3 scripts/assessment/observability/collect.py `
  --profile '<profile>' --expected-account '<12-digit-account>' `
  --region ap-southeast-2 --cluster '<cluster>' `
  --api-service '<api-service>' --worker-service '<worker-service>' `
  --publisher-service '<publisher-service>' --asg '<asg>' `
  --target-group '<target-group-arn>' --alb-suffix '<app/name/id>' `
  --target-group-suffix '<targetgroup/name/id>' `
  --capacity-provider '<capacity-provider>' --db '<db-id>' `
  --cache-cluster '<redis-node-1>' --cache-cluster-replica '<redis-node-2>' `
  --queue '<queue-name>' --dlq '<dlq-name>' `
  --queue-url '<queue-url>' --dlq-url '<dlq-url>' `
  --sns-topic '<topic-arn>' --interval 30 --samples 4
```

Không truyền `--instance-ids` trừ khi cần theo dõi EC2 vừa rời ASG; collector tự lấy các máy trong ASG từng mẫu. `--profile` và `--expected-account` bắt buộc; collector dừng trước các resource calls nếu account không khớp. Nếu AWS CLI/API không truy cập được, giữ log lỗi đã làm sạch và dừng, không đổi profile để thử đại.

4. Ghi đường dẫn private run do collector in ra. Tạo chart từ CSV của run đó:

```powershell
py -3 scripts/assessment/observability/chart.py .local/assessment/<run_id>/metrics.csv --out .local/assessment/<run_id>/charts
```

5. Đối chiếu `preflight.json`, `metrics.csv`, `activities.csv`, `metric-requests/`, `manifest.json`, `summary.md`, runner CSV và SVG. Đo khoảng cách `sample_at` thực và `collector.duration_seconds`. Chu kỳ collector 15–30 giây là tần suất **describe/query**; CloudWatch trong script hỏi bucket `Period=60` giây, không sinh datapoint 15–30 giây. Datapoint lặp hoặc tới trễ phải giữ `source_at/status`; giá trị thiếu không thay bằng 0. `OVER_INTERVAL` cần ghi nguyên, thử tối ưu CLI sau khi đo breakdown; không sửa timestamp để đạt gate.
6. Kiểm các metric thiếu bằng đúng namespace/dimensions và xem chúng có phát sinh ở workload quan sát hay không. Xác minh `CapacityProviderReservation`, ALB response/4xx/5xx và hai metric ứng dụng. Bổ sung nguồn read-only có timestamp cho ENI, DB lock waits, Redis role/events nếu cần cho C3–C5. Smoke không tải có thể không có latency/request errors; `MISSING_OR_DELAYED` không tự thành FAIL ứng dụng.
7. Chỉ sao chép bản đã làm sạch vào `evidence/assessment/<run_id>/`. Lưu private account/ARN, request JSON, activity description, tokens và credential ngoài Git. Manifest công khai cần run ID, source commit và `collector_sha256` (vì mã có thể chưa commit), digest/schema kiểm thực, khoảng UTC, status, hash tệp và giới hạn. Gắn đường dẫn bằng chứng vào bảng checklist; C1 vẫn BLOCKED nếu chưa có runner k6/clock, placement, request streams và review của Người 3.

## Kết quả kiểm mã collector và hướng xử lý nhịp mẫu

`collect.py` giới hạn `--interval` từ 15 đến 30 giây, đo bằng `time.monotonic()`, chờ `max(0, interval - elapsed)` và ghi `OVER_INTERVAL` khi một vòng vượt thời gian. Vì thế vòng 30.78 giây trong smoke Người 2 được phản ánh trung thực; không có lỗi lịch chạy làm biến 30.78 thành 30. Trong vòng hiện tại, AWS CLI describe, GetMetricData và scaling activity chạy tuần tự. Mã mới ghi duration từng nhóm qua `collector.describe_seconds`, `collector.cloudwatch_seconds` và `collector.activities_seconds` để tìm nghẽn trước khi cân nhắc gộp/đọc song song các nhóm độc lập. Mã cũng để `source_at` trống khi CloudWatch không trả datapoint; CSV lịch sử được giữ nguyên. Không giảm CloudWatch `Period=60` để giả độ phân giải 15 giây; nếu vẫn vượt 30 giây, đánh dấu thiếu điều kiện sampling.

## Danh sách thay đổi C2 trước khi chạy tải

| Script/quy trình | Việc cần sửa hoặc xác minh | Trạng thái |
|---|---|---|
| `booking.js` | Đã thêm `SESSIONS_FILE` tùy chọn chứa `{session_token,csrf_token,seat_id}` cho mỗi VU; khi không có file, giữ `ACCOUNTS_FILE` và login hiện có. Kiểm token khác nhau, expiry có timezone phủ thời lượng cộng 5 phút; `setup()` kiểm `/me` và user distinct/ACTIVE/verified trước tải, mỗi VU dùng cookie/CSRF và seat được bàn giao. Credentials mode cũng chặn username trùng. | PASS 7 test mô phỏng [local](../../../evidence/assessment/20261120T130757Z-c2-local/summary.md); AWS smoke BLOCKED vì session B2 hết hạn |
| `platform.js` | Đã thêm kiểm 100 session/seat distinct, TTL, `/me` verified/ACTIVE, ca còn mở và queue off; giữ 24 read/s + 2 workflow/s, cancel bằng **reservation_id từ response confirm** và đếm workflow đủ bước. Đo actual requests/dropped iterations từ k6; không nhận 30 RPS chỉ từ cấu hình. | Kiểm thử local PASS; AWS C3 BLOCKED bởi session B2 hết hạn và gate clock/AWS/C2 |
| `ecs-scaling.js` | Đây là tải GET để quan sát hai tầng, không có session/CSRF. Kiểm URL, giới hạn VU theo kế hoạch, metric/target/EC2 activity và điều kiện dừng. Script không tự chứng minh scale. | NOT_RUN trên AWS |
| Email window | Ghi worker task definition/digest/backend hiện tại; drain job thật; đổi worker sang `EMAIL_BACKEND=disabled` trong cửa sổ chung, giữ `APP_ENV`, publisher/worker chạy; kiểm rollout và job synthetic `SKIPPED`, không có Brevo send. Sau bài test drain job thử, khôi phục backend/task definition và kiểm một mail trong quota nhóm; không replay job SKIPPED. | NOT_RUN dưới trách nhiệm C2; không thay worker khi chưa đủ điều kiện/cửa sổ |

Các bước thay worker và test gửi mail thuộc C2 có phối hợp vận hành, không nằm trong smoke C1 chỉ đọc. Không commit file session hoặc credential; không dùng 100 session B2 cũ vì đã hết hạn theo bằng chứng bàn giao.

## C2 — Chuẩn bị session và smoke script

B2 cấp lại session sát giờ chạy và chuyển qua kênh private: `synthetic-sessions.json`, `SESSION_ID`, expiry bảo thủ sớm nhất có timezone, mapping seat/user và bằng chứng 100 user khác nhau. B2 phải kiểm guard seed/helper sau khi các ca đổi tên. Không dùng manifest ngày 18/11 để xác nhận TTL hiện tại. Trên runner, kiểm file nằm ngoài Git và đối chiếu lịch còn mở, capacity, ca chưa bắt đầu, account ACTIVE/verified. `SESSION_EXPIRES_AT` lấy từ manifest mới, không tự kéo dài mốc hết hạn; script dừng trước request nếu thời hạn không phủ `DURATION` cộng 5 phút. Mỗi VU dùng một session theo index; lượt `/me` đầu xác nhận phiên còn hợp lệ. Không tắt auth hoặc rate limit.

Lệnh smoke có ghi trạng thái trên runner (chỉ trong cửa sổ email đã chuyển disabled và B2 đã xác nhận readiness):

```powershell
k6 run -e BASE_URL=https://labseat.id.vn `
  -e SESSION_ID='<session-id-from-new-private-manifest>' `
  -e SESSIONS_FILE='<private-path>/synthetic-sessions.json' `
  -e SESSION_EXPIRES_AT='<earliest-expiry-with-timezone>' `
  -e VUS=1 -e DURATION=30s `
  --summary-export=.local/assessment/c2-booking-smoke.json `
  scripts/load/booking.js
```

Đây là smoke nhỏ, không phải C3. Giữ raw k6 output, thời điểm UTC, status từng API, số hold/confirm/cancel, queue wait/admission và kết quả `/me`; làm sạch token/cookie/PII trước khi đưa vào evidence. `setup()` gọi `/me` tuần tự cho các session để chặn hai token thuộc cùng user; các request preflight này nằm ngoài cửa sổ tải k6. Nếu thiếu k6 hoặc session mới, ghi `BLOCKED` thay vì dùng credentials cũ ngoài mục đích kiểm tương thích. Chế độ credentials cũ vẫn dùng `ACCOUNTS_FILE` khi không truyền `SESSIONS_FILE`; login thật vẫn chịu rate limit. [Kiểm thử local](../../../evidence/assessment/20261120T130757Z-c2-local/summary.md) chỉ mô phỏng HTTP, chưa chứng minh AWS.

## C2 — Cửa sổ worker disabled → restore

Chỉ bắt đầu khi Người 3 đã chốt cửa sổ với nhóm, tài khoản/region/cluster/service/target đúng, B2 có phiên mới và đã thống nhất không có đăng ký, verify/reset hoặc mail thật khác trong cửa sổ. Disabled áp dụng **mọi email mới**, không riêng batch. Không dùng backend `mock` trên production, không đổi `APP_ENV`, không tắt publisher/worker và không replay job đã `SKIPPED`. [B3](../functional/report.md) ghi worker về revision 10/backend disabled sau lượt mail lịch sử; đây không phải xác nhận trạng thái hiện tại. Nếu baseline hiện là disabled, cần phân biệt “đã disabled sẵn” với thao tác chuyển backend trong C2.

Năm ảnh Console do Người 3 cung cấp cho thấy:

| Ảnh | Quan sát trực tiếp | Giới hạn |
|---|---|---|
| `C2-01-worker-task-definition.png` | Task definition family `labseat-lab-worker`, revision **11**, container `app`, `APP_ENV=production`, `EMAIL_BACKEND=brevo`, `AWS_REGION=ap-southeast-2`. | Chỉ chứng minh cấu hình revision 11; chưa chứng minh service dùng revision này. Không có mốc UTC gắn với ảnh. |
| `C2-02-worker-service-baseline.png` | ECS worker service `Active`, deployment status `Success`, task definition hiển thị **revision 10**, desired **1**. Console hiển thị “Last updated” **20/11/2026 20:25 UTC+7** (tương ứng **13:25 UTC**). | Không có ảnh tab Tasks/Deployments để đối chiếu revision của task đang chạy, trạng thái running/pending rõ ràng hay image digest. “Last updated” không tự chứng minh thời điểm chụp hoặc trạng thái sau đó. |
| Ảnh task definition revision 10 (Người 3 vừa cung cấp, chưa đặt tên evidence) | Family `labseat-lab-worker`, revision **10**, container `app`, `APP_ENV=production`, `EMAIL_BACKEND=disabled`, `AWS_REGION=ap-southeast-2`. | Chứng minh cấu hình revision 10 trong Console; chưa chứng minh task đang chạy dùng revision này. Không có mốc UTC gắn với ảnh. |
| Ảnh chi tiết ECS task (chưa đặt tên evidence) | Breadcrumb task definition **`labseat-lab-worker:10`**, task `Running`, container `app` `Running`; dòng started hiển thị **19/11/2026 10:14 UTC+7** (tương ứng **03:14 UTC**). | Xác nhận một task revision 10 đã chạy; không thay thế snapshot service deployment, desired/running/pending, digest hoặc kiểm tra task khác tại thời điểm smoke. |
| Ảnh CloudWatch log filter (chưa đặt tên evidence) | Tìm chuỗi `SKIPPED`, khung **1 hour**, múi giờ UTC; Console báo **“No events found”**. | Chưa có job test/run ID, log stream và mốc chạy để đối chiếu; kết quả rỗng không chứng minh worker không xử lý job, job đã `SKIPPED` hay không gửi Brevo. |

**Revision 11 là ứng viên Brevo, không phải baseline của service theo ảnh C2-02.** Revision 10 được cấu hình disabled và ảnh task xác nhận một container revision 10 đang chạy. Nếu service vẫn ổn định trên revision 10 tại cửa sổ C2, không cần tạo thêm revision hoặc rollout disabled: chỉ kiểm trạng thái và smoke. Baseline bước 1 vẫn `BLOCKED` cho đến khi có snapshot task/deployment cùng cửa sổ, digest và queue/job. Năm ảnh gốc chứa định danh tài khoản, ARN, endpoint hoặc địa chỉ email nên giữ private, không đưa nguyên ảnh vào Git.

1. **Baseline private trước chuyển (`BLOCKED`, có ảnh một phần).** Trên AWS Console hoặc CLI với profile explicit, lưu UTC, account/region, worker service ARN, task definition ARN/revision, image digest, `EMAIL_BACKEND`, `APP_ENV`, secret *names* (không lưu values), desired/running/pending, deployment/health/events; ghi publisher tương tự. Ảnh mới đã xác nhận một task revision 10 `Running`; tại cửa sổ C2, mở lại **Tasks** và **Deployments** để xác nhận tất cả task của service dùng revision 10 và rollout ổn định, đối chiếu digest. Lưu JSON `describe-services` và `describe-task-definition` private, hash và đường dẫn manifest. Kiểm khác biệt runtime so với runbook Terraform/deploy; chặn nếu đang rollout hoặc có thay đổi cùng lúc. Ghi riêng **baseline ARN/backend** và **đích Brevo được nhóm duyệt sau window**; chúng có thể khác nhau.
2. **Drain job thật (`NOT_RUN`).** Đối chiếu Admin Email/DB read-only và SQS/DLQ: job thật chưa hoàn tất, in-flight, oldest age, unknown/retry. Hoàn tất hoặc điều tra chúng trước đổi backend. Ghi count theo trạng thái và timestamp, không ghi recipient/QR. Nếu còn job có thể gửi thật khi worker trở lại, dừng cửa sổ.
3. **Chuyển đúng worker (`NOT_RUN`).** Nếu baseline là Brevo, tạo candidate task definition từ baseline, chỉ sửa `EMAIL_BACKEND` của container worker thành `disabled`; giữ image digest, `APP_ENV`, command, roles, secrets, networking, CPU/memory và mọi trường khác. Review diff field-by-field, lưu candidate ARN và source hash; cập nhật **worker service** trong cửa sổ được giao, chờ rollout COMPLETED, running=desired, pending=0 và task mới đúng candidate. Nếu baseline đã disabled, ghi nhận và xác minh task đang chạy đúng revision/config, không tạo rollout giả để lấy bằng chứng. Không đổi API/publisher, không chạy full release deploy để vô ý thay nhiều service. Nếu rollout lỗi, quay worker service về baseline ARN và chờ ổn định trước khi tiếp tục.
4. **Smoke và chứng minh không gửi (`NOT_RUN`).** Chạy smoke 1 VU ở trên. Đối chiếu reservation/outbox/job/delivery của đúng batch/run: job và delivery chuyển `SKIPPED`, không tăng provider attempts/message ID. Tìm log theo đúng log group/stream, job/run ID và khoảng UTC bao phủ lúc xử lý; ảnh tìm `SKIPPED` rỗng trong một giờ trước smoke không phải bằng chứng PASS. Queue test drain, publisher/worker vẫn running. Đối chiếu Brevo transactional activity/quota trước và sau cùng cửa sổ, không có gửi từ job synthetic; nếu thiếu quyền xem Brevo, ghi `BLOCKED` cho kết luận không gửi. Giữ audit/log đã che và timestamp; không coi chỉ một ảnh worker disabled là đủ.
5. **Kết thúc và restore (`NOT_RUN`).** Dừng tạo booking test, chờ job test hoàn tất `SKIPPED`, queue/DLQ không còn backlog synthetic có thể gửi sau restore. So sánh worker baseline với hiện tại; nếu có rollout khác xen vào thì dừng và điều phối, không ghi đè. Nếu baseline là Brevo, cập nhật worker service về **baseline task definition ARN đã lưu**, chờ rollout hoàn tất và xác nhận digest/APP_ENV/publisher/API đúng baseline. Nếu baseline vốn disabled, chỉ chuyển sang Brevo khi nhóm đã xác minh và duyệt riêng task definition Brevo, sender/domain/API key/quota và đích cuối; nếu chưa có đích hợp lệ thì giữ baseline disabled và C2 còn BLOCKED. Không gửi lại các job `SKIPPED`.
6. **Kiểm mail sau restore (`NOT_RUN`).** Quota nhóm là **300 mail/ngày**; đối chiếu số đã dùng trong ngày, quota Brevo còn lại và số mail nhóm cho phép trong cửa sổ trước khi gửi. Dùng **một** giao dịch synthetic mới qua API bình thường; xác minh job/attempt, callback/Brevo và Inbox/Spam theo tiêu chí B3. Không gửi nếu window/mail quota chưa được nhóm cho phép. Ghi worker baseline cuối, queue/DLQ, alarm/SNS và số mail đã dùng. Nếu kiểm này chưa thực hiện, restore cấu hình có thể PASS riêng nhưng C2 tổng thể vẫn BLOCKED.

Manifest C2 cần run ID, phase `baseline/disabled/smoke/drain/restored/mail-check`, owner, commit script, digest/schema, account/region đã làm sạch, mốc UTC, trước/sau task definition, queue/job counts, Brevo attempts/quota, kết quả và cleanup/rollback. Lưu các bản gốc private; gói công khai chỉ có dữ liệu đã làm sạch và hash. **Trạng thái hiện tại: BLOCKED** — k6 v2.4.0 đã được xác minh bằng đường dẫn tuyệt đối và profile AWS CLI `tv2-compute` dùng được cho preflight đọc; chưa có session B2 mới hoặc bằng chứng job synthetic `SKIPPED`/Brevo/restore. Windows Time vẫn chưa đồng bộ.

# C3 — Thực thi AWS và cleanup

Chỉ target `https://labseat.id.vn` và batch `demo-load-mechanic21`. Trước khi tải, kiểm backup/TTL/mapping trong [tài liệu dữ liệu](../functional/dataset.md), worker email disabled ổn định, B3 smoke, clock, targets, DB và limits. Không chạy đồng thời fault/restore; giữ credentials và raw logs private.

## Thứ tự

1. Chạy baseline 5 VU bằng `scripts/assessment/observability/cloud-runner.ps1 -Phase baseline`.
2. Queue operator `begin`, chờ `recovery_not_before`, rồi `disable`; kiểm OFF và chạy `-Phase platform` 15 phút. Sau đó `enable` và kiểm ready/baseline policy.
3. Khi queue ON, chạy `-Phase admission20`, rồi `-Phase admission50`, mỗi mức 5 phút.
4. Chạy `-Phase scaling60`; chỉ tăng 100/150/200 khi chưa thấy EC2 scale-out, TTL/gates/headroom vẫn đạt. Giữ 15 phút mỗi mức và không chỉnh desired thủ công.
5. Chạy `-Phase recovery` 30 phút; có thể quan sát đến 45 phút và đối chiếu activities, task, instance thực.

`cloud-runner.ps1` trả receipt riêng ở bước Start. Chờ task `STOPPED`, sau đó dùng `-Stage Collect -Receipt <private-receipt> -Aws <aws.exe>`. Không Start lại khi chưa rõ task cũ. Bundle phải hash-verified; runner Fargate dùng 2048 CPU/4096 MiB ngoài ASG; ClockDrift phải `SYNCHRONIZED` với bound không quá 100 ms; TTL tối thiểu 2 giờ. Dùng Linux k6 binary đã kiểm chứng và không cài vào EC2 ứng dụng.

## Cấp lại session và thu evidence

Chạy `run-isolated-load.ps1 -Stage sessions -Batch demo-load-mechanic21 -MinimumValidSeconds 14400 -Execute`, rồi cùng batch chạy stage smoke. Yêu cầu SSM tunnel, TLS verify full và backup đã xác minh. Không kéo dài TTL trực tiếp trong file; gói bốn file private phải đúng manifest và không chứa backup key/master.

Collector C1 dùng `collect.py`/`runner.ps1` với inventory thực, interval 30 giây và DB budget 51. Lệnh `node scripts/load/summarize-c3.mjs <private-metrics.ndjson> <public-phase-dir>` tạo CSV/SVG đã loại URL, token và PII; `chart.py` vẽ metrics tài nguyên và giữ nguyên các khoảng trống dữ liệu.

## Kết thúc

Sau khi toàn bộ load task dừng, chạy probe/invariants; cleanup dry-run rồi execute đúng batch và manifest `0a59f708-244e-5d0d-80d1-c3907727db17`; kiểm 10 bảng demo và 7 invariants, đồng thời giữ backup. Chuyển gói phiên sang `RETIRED`; gỡ Redis user tạm khỏi group, xóa hai SSM parameters và inline policy tạm; dọn task-definition revisions/S3 versions theo receipt sau khi tải artifact về; dừng monitor, collector và tunnel của lượt chạy. Ghi riêng mọi bước chưa làm và kết quả `FAIL`.
