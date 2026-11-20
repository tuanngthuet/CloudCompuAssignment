# C3 — tải chuẩn, admission, autoscaling và recovery

Chủ sở hữu: Người 3. Nhánh: `assessment/load-resilience`. **Trạng thái tổng thể: BLOCKED / chưa nghiệm thu AWS.** Báo cáo này không có số liệu tải AWS mới. Kết quả C1/B2/B3 lịch sử là đầu vào preflight, không được tính làm PASS C3. Tiêu chí nguồn: [kế hoạch](../../sprints/ke-hoach-nghiem-thu-4-ngay.md#c3-tải-chuẩn-admission-autoscaling-và-biểu-đồ), [runbook C1/C2](runbook.md), [B1/B2](../../../evidence/assessment/b1b2-20261117a/summary.md), [B3](../functional/report.md).

## Readiness ngày 20/11/2026; cập nhật AWS CLI và collector chỉ đọc

`PASS` chỉ xác nhận phần đã đo tại mốc ghi rõ; snapshot cũ không xác nhận trạng thái AWS hiện tại. `BLOCKED` nghĩa là thiếu phép đo hoặc tiền điều kiện nên chưa chạy tải. Không có bài C3 nào đã khởi chạy.

| # | Điều kiện | Trạng thái | Bằng chứng và khoảng trống |
|---|---|---|---|
| 1 | k6/version | PASS | `C:\Program Files\k6\k6.exe version` trả `v2.4.0`, exit 0. PATH của shell agent chưa nhận `k6`; gọi bằng đường dẫn tuyệt đối hoặc bổ sung PATH trên runner. `k6 inspect` đọc được `catalogue.js` và `ecs-scaling.js` khi truyền `BASE_URL`; chưa phải chạy tải. |
| 2 | Runner CPU/RAM/network | BLOCKED | Runner ngoài ASG theo xác nhận Người 3. WMI: 20 logical processors, RAM tổng 15,73 GiB. Mẫu sau đó: CPU 23,81%, RAM còn 2547 MiB, network 3557,29 bytes/s. GET health thành công; chưa đo liên tục dưới k6 hoặc chứng minh headroom đến 200 VU. [Smoke Người 2](../../../evidence/assessment/20261119T172832Z-b4-c1-preflight/summary.md) từng có RAM chỉ 452–1023 MiB. Mốc giờ runner chưa đáng tin cậy. |
| 3 | Clock UTC/GET health | FAIL | GET `/healthz` trả HTTP 200 `status=ok`. `w32tm /query /status` vẫn báo `Leap Indicator: 3`, `Stratum: 0`, `Source: Local CMOS Clock`, chưa có lần đồng bộ thành công. Thử `w32tm /resync` bị từ chối `0x80070005`. Cần đồng bộ Windows Time với quyền phù hợp, kiểm lại độ lệch trước khi lấy timeline C3. |
| 4 | Contract script/API | PASS (kiểm mã) | Đối chiếu router hiện hành: GET `/lab-sessions` có `server_time`, `queue_policy`; GET seats có `items/available`; `/me`; queue join/heartbeat/leave; hold trả `hold_id`, confirm trả `reservation_id`, cancel dùng reservation ID. `platform.js` dùng constant arrival 24 read/s + 2 workflow/s, 3 write/workflow; `booking.js` phân loại 409 theo `code`, 429 là unexpected và ghi riêng. Chưa có smoke AWS xác nhận image đang chạy cùng contract. |
| 5 | B2 synthetic data | BLOCKED | [B2](../../../evidence/assessment/b1b2-20261117a/summary.md): 100 fixture thuộc 100 user nhưng **0 còn hiệu lực** từ 18/11. Chưa nhận/kiểm chứng file session mới; cần B2 cấp private manifest/session sát giờ chạy. |
| 6 | Session TTL/cookie/CSRF/user/seat | BLOCKED | Script kiểm token riêng, TTL, cookie `labseat_session`, CSRF `labseat_csrf`, `/me` distinct ACTIVE/verified và seat mapping. Chưa có fixture hợp lệ để chạy kiểm thật; không giả định 100 seat sẵn từ manifest cũ. |
| 7 | B3 smoke/invariants | BLOCKED | [B3](../functional/report.md) và [summary](../../../evidence/assessment/20261119T034356Z-b3-functional/summary.md) ghi API AWS 33 PASS, bảy invariant zero rows ở lượt lịch sử, nhưng B3 chưa chốt, có 3 FAIL/2 BLOCKED/3 NOT_RUN; X01 sau tải vẫn NOT_RUN. Cần smoke/invariants đúng cửa sổ C3, cùng digest/run ID. |
| 8 | C2 disabled/SKIPPED/queue/Brevo | BLOCKED | Ảnh/đợt [C2 local](../../../evidence/assessment/20261120T130757Z-c2-local/summary.md) và [runbook](runbook.md#c2--cửa-sổ-worker-disabled--restore) cho thấy worker revision 10 disabled; chưa có job synthetic `SKIPPED`, đối chiếu Brevo hay restore. GET `/lab-sessions` 14:32:24 UTC trả `queue_policy.enabled=true` (25 ca, 21 ca mở thêm 16 phút). Queue phải OFF có audit cho Platform, ON có audit cho Admission. Không thay policy trong lượt này. |
| 9 | Collector C1 đủ metrics | BLOCKED | [Một vòng và ba mẫu liên tiếp AWS chỉ đọc](../../../evidence/assessment/20261120-c3-live-readonly/summary.md): lượt ba mẫu 187 dòng, 151 OBSERVED, 6 MISSING, 30 MISSING_OR_DELAYED, 0 OVER_INTERVAL; hai khoảng 30,000344/30,000781 s, vòng 17,99/13,28/14,52 s. Nhịp 30 s đã quan sát ngắn hạn, nhưng ENI, capacity reservation, ALB, queue wait và Redis latency còn thiếu/chậm. CloudWatch `Period=60` s; clock UTC chưa đồng bộ. |
| 10 | AWS CLI identity/region/read | PASS (quyền đọc đã thử) | Profile `tv2-compute`, STS đúng account/region `ap-southeast-2`; collector đọc thành công ECS/EC2/ASG/ALB, CloudWatch, RDS, ElastiCache, SQS, SNS và alarms. Xem [evidence](../../../evidence/assessment/20261120-c3-live-readonly/summary.md). Quyền sửa queue/worker và restore chưa được kiểm; quyền đọc không mở gate chạy tải. |
| 11 | ECS/EC2/ALB/dependencies ổn định | BLOCKED | Snapshot mới: ASG desired/in-service 5, API 2/2, worker/publisher 1/1, 2 API target healthy; RDS available, hai Redis node available, SQS/DLQ 0 visible, 14 alarms OK một thời điểm. [Evidence](../../../evidence/assessment/20261120-c3-live-readonly/summary.md). Đây là một snapshot; chưa có baseline ổn định trong cửa sổ C3, task digest/schema và traffic streams. |
| 12 | DB budget, RAM/ENI, quota/restore | BLOCKED | CloudWatch `DatabaseConnections=8` ở một datapoint; `max_connections`/budget mới chưa kiểm bằng SQL. Năm máy `t3.small` có tối đa 3 network interfaces/máy theo EC2 API; interfaces đang gắn theo AZ 2a: 1,2; 2b: 1,2,3. Không máy nào có thuộc tính `ecs.awsvpc-trunk-id`; ECS không trả ENI remaining. Cần kiểm task placement, subnet IP, quota và đủ capacity cho API max8/ASG max6 trước scaling. [Số B4/C1 lịch sử](../../../evidence/assessment/20261119T172832Z-b4-c1-preflight/summary.md) không thay thế gate hiện tại. |

**Quyết định gate:** không phát request k6 tới AWS; session B2 hết hạn, C2 chưa chứng minh email, clock chưa đồng bộ và queue đang ON ở lần GET mới. AWS CLI/collector chỉ đọc đã kiểm được nhưng chưa đủ các gate C3. Các GET health/danh sách ca là phép kiểm nhẹ, không tạo tải nghiệp vụ.

**Biến động sau snapshot C3:** [preflight C4 chỉ đọc về sau](../../../evidence/assessment/20261120-c4-capacity-recheck/summary.md) thấy ASG desired/in-service **4** thay vì 5; AWS Activity ghi ECS managed scaling 5→4 rồi cân bằng AZ. Số 5 ở bảng trên là snapshot C3 trước đó, không phải baseline hiện tại hoặc bằng chứng autoscaling C3 dưới tải. Cần đọc lại toàn bộ placement/metrics khi bắt đầu C3.

[Bản ghi readiness đầu](../../../evidence/assessment/20261120T1432Z-c3-readiness/summary.md) và [bản ghi collector mới](../../../evidence/assessment/20261120-c3-live-readonly/summary.md) lưu command, số đo rút gọn và giới hạn. Trước tải: đồng bộ Windows Time bằng quyền quản trị rồi xác minh lại; nhận B2 session private còn TTL; xác nhận C2 job SKIPPED/Brevo và cửa sổ; kiểm B3 smoke/invariants. Trên AWS Console: kiểm ECS deployment/task digest/placement, ASG min–desired–max/activity, EC2 registration/ENI/RAM theo AZ, Target Group healthy, RDS connections/budget SQL, Redis/SQS/DLQ, alarms/SNS và quota/restore; lưu snapshot UTC cùng run ID. Điều phối queue OFF cho Platform rồi ON cho Admission trong cửa sổ được duyệt; ghi audit trước/sau và khôi phục baseline. Kiểm C4/C5/PITR/S3 restore không chạy đồng thời. Sau từng mức, đối chiếu invariant SQL read-only và UI; chỉ tăng tải nếu mọi gate dừng an toàn.

## Kết quả theo bài

| Bài | Gate và quan sát cần có | Trạng thái | Bằng chứng C3 |
|---|---|---|---|
| Baseline | Tải nhẹ 5 phút; task, EC2, target, latency, DB connections, queue và runner cùng mốc UTC | BLOCKED / NOT_RUN | Chưa có k6/collector run C3 |
| Platform | 100 VU slots, arrival rate 24 read/s + 2 workflow/s × 3 write = **30 request/s mục tiêu** trong 15 phút, queue off; p95 read <500 ms, write <1 s, unexpected error <1%, dropped iterations 0, invariant 0, UI/nghiệp vụ còn đúng | BLOCKED / NOT_RUN | Chưa có session mới hoặc k6 summary/CSV |
| Admission | Queue on; 20 rồi 50 VU, mỗi mức 5 phút; wait/grant/expiry/heartbeat, expected 409/429 và unexpected errors phân biệt | BLOCKED / NOT_RUN | Chưa có k6/queue timeline |
| Scaling | 60→100→150→200 VU khi cần, mỗi mức giữ ≥15 phút, tối đa 25 phút nếu đang tiến triển; API desired tự tăng, thiếu placement, ASG/EC2 tự tăng, register, target healthy, nhiều request streams, alarm workload và SNS | BLOCKED / NOT_RUN | Chưa có scaling activity/video/CSV C3 |
| Recovery | Hạ tải, quan sát 30–45 phút; task/EC2 scale-in, target/DB/queue/alarm/UI về baseline | BLOCKED / NOT_RUN | Chưa có timeline sau tải |

`NOT_RUN` không được đổi thành `FAIL` chỉ vì thiếu điều kiện chạy; một lượt thực đã chạy mà vi phạm gate phải ghi `FAIL` và giữ nguyên dữ liệu lần lỗi. Task API tăng mà EC2 không tự tăng trong giới hạn cho phép thì ghi **hai tầng chưa chứng minh**, không suy ra PASS. Không dùng manual desired hoặc giảm capacity để tạo kết quả.

## Preflight và điểm chặn hiện tại

- k6 v2.4.0 đã được xác minh bằng đường dẫn tuyệt đối; shell agent chưa có `k6` trong PATH. AWS CLI/collector đã đọc được các dịch vụ cần thiết; nhịp 30 s quan sát qua ba mẫu, còn thiếu nhiều datapoint và chưa có timeline UTC đáng tin cậy. Không có file session B2 mới trong workspace; [gói B2](../../../evidence/assessment/b1b2-20261117a/summary.md) ghi 100 session cũ đều hết hạn. Vì vậy **không tạo request tải AWS** từ máy này.
- Ảnh Console C2 cho thấy task definition worker revision 10 cấu hình `EMAIL_BACKEND=disabled` và một task revision 10 `Running`; chưa có job test theo run ID `SKIPPED` và đối chiếu Brevo cùng cửa sổ. Trước C3 phải chốt C2 theo [runbook](runbook.md#c2--cửa-sổ-worker-disabled--restore).
- Trên runner **ngoài ASG được đo**, sửa Windows Time đang `not synchronized` (lệnh `w32tm /resync` hiện bị từ chối quyền) và xác nhận lại sai lệch clock; đo CPU/RAM/network liên tục khi chạy, bắt đầu từ mức nhẹ. Đọc lại ECS/ASG/EC2/ELB/CloudWatch/RDS/SQS/SNS đúng account/region, C1 collector sampling. Xác nhận API min 2/max 8, ASG min 2/max 6, target khỏe, image digest/schema, DB connection budget, RAM/ENI/placement theo AZ, queue/DLQ, alarm/SNS. Nếu thiếu một gate quan trọng thì dừng trước tải.
- B3 smoke nghiệp vụ phải được kiểm lại đúng cửa sổ, session B2 private còn TTL cho từng bài, seat/capacity và ca còn mở. Không gửi session token, cookie, credential, account/ARN thô vào Git hoặc log công khai. Không chạy C3 đồng thời C4/C5 fault/restore.

## Kiểm chứng script tại local

`node scripts/load/booking.test.mjs` **9/9 PASS**; `node scripts/load/platform.test.mjs` **4/4 PASS**; `node scripts/load/ecs-scaling.test.mjs` **2/2 PASS**; `node scripts/load/summarize-c3.test.mjs` **1/1 PASS**. `k6 version` xác nhận v2.4.0; `k6 inspect` đọc `catalogue.js` và `ecs-scaling.js` sau khi cấp `BASE_URL`. `node --check` cho các script C3 exit 0. Đây là kiểm tra logic/mã và một NDJSON fixture local cho bộ vẽ chart, **không phải k6 smoke hoặc số đo AWS**. Chưa có video hay chart từ dữ liệu C3 thật.

## Script và lệnh tái tạo trên runner được phép

`<...>` là giá trị private phải điền sau preflight. Mỗi run có thư mục riêng `.local/assessment/<run-id>/` ngoài Git; ghi UTC bắt đầu/kết thúc, commit script và SHA-256 trước khi chạy. Dùng `--out json` và summary private; làm sạch URL có ID, token/cookie, PII và định danh AWS trước khi đưa vào evidence. Collector C1 chạy song song với mỗi bài theo [lệnh C1](runbook.md#smoke-c1-chỉ-đọc), interval 15–30 giây; bucket CloudWatch vẫn là 60 giây. Không biến mẫu thiếu thành 0.

### 1. Baseline — queue theo trạng thái đã chốt, tải nhẹ 5 phút

Ghi service/task/EC2/ALB/DB/queue trước run. `catalogue.js` ramp 1 phút, giữ 5 phút, hạ 1 phút; chỉ 5 VU, phần đo là 5 phút giữ tải.

```powershell
k6 run -e BASE_URL='https://<approved-host>' -e VUS=5 `
  --summary-export='.local/assessment/<baseline-id>/k6-summary.json' `
  --out 'json=.local/assessment/<baseline-id>/k6-raw.json' `
  scripts/load/catalogue.js
```

### 2. Platform — admission off

Xác minh queue policy off trước và sau, 100 session/seat riêng còn hạn ít nhất 20 phút, ca mở qua hết bài. [platform.js](../../../scripts/load/platform.js) kiểm `/me` 100 user verified/ACTIVE, seat sẵn có, cookie và CSRF trước cửa sổ 15 phút; các preflight request phải loại khỏi actual RPS đo trong bài. Script phát cố định **24 read iterations/s** và **2 workflow iterations/s**. Chỉ kết luận 30 RPS khi hold, confirm, cancel đủ và số request thực trong cửa sổ tương ứng; `100 VU slots` là trần VU cấp phát, không phải tốc độ.

```powershell
k6 run -e BASE_URL='https://<approved-host>' -e SESSION_ID='<synthetic-session-id>' `
  -e SESSIONS_FILE='<private-path>/synthetic-sessions.json' `
  -e SESSION_EXPIRES_AT='<earliest-expiry-with-timezone>' `
  --summary-export='.local/assessment/<platform-id>/k6-summary.json' `
  --out 'json=.local/assessment/<platform-id>/k6-raw.json' `
  scripts/load/platform.js
```

Lưu `http_reqs` theo UTC, read/write p95, `platform_workflows_started/completed`, `platform_holds_ok/confirms_ok/cancels_ok`, `platform_unexpected_failure`, `dropped_iterations` và từng HTTP 409/429/5xx. Chạy invariant SQL read-only và UI probe bằng user khác; nếu thiếu một bước workflow, không ghi 30 RPS đạt. Giữ mọi lần lỗi.

### 3. Admission — queue on

Chỉ đổi queue policy trong cửa sổ được điều phối, chụp trạng thái/audit trước và sau. Không tắt rate limit. Dùng session private mới đủ TTL, không dùng 100 token B2 cũ. Chạy **hai run riêng**, mỗi run 5 phút, tăng từ 20 lên 50 chỉ khi gate ở mức 20 không vi phạm. Trả queue policy về baseline đã ghi khi kết thúc.

```powershell
k6 run -e BASE_URL='https://<approved-host>' -e SESSION_ID='<synthetic-session-id>' `
  -e SESSIONS_FILE='<private-path>/synthetic-sessions.json' -e SESSION_EXPIRES_AT='<expiry>' `
  -e REQUIRE_QUEUE_ENABLED=1 -e VUS=20 -e DURATION=5m `
  --summary-export='.local/assessment/<admission-20-id>/k6-summary.json' `
  --out 'json=.local/assessment/<admission-20-id>/k6-raw.json' scripts/load/booking.js

k6 run -e BASE_URL='https://<approved-host>' -e SESSION_ID='<synthetic-session-id>' `
  -e SESSIONS_FILE='<private-path>/synthetic-sessions.json' -e SESSION_EXPIRES_AT='<expiry>' `
  -e REQUIRE_QUEUE_ENABLED=1 -e VUS=50 -e DURATION=5m `
  --summary-export='.local/assessment/<admission-50-id>/k6-summary.json' `
  --out 'json=.local/assessment/<admission-50-id>/k6-raw.json' scripts/load/booking.js
```

Đối chiếu `booking_waiting_poll`, `booking_heartbeat`, `booking_admitted`, `booking_queue_wait_ms`, `booking_queue_expired`, `booking_seat_conflict`, `booking_unexpected_conflict`, `booking_rate_limited`, `booking_confirmed`, `booking_cancelled` và `booking_unexpected_error`; kiểm lease theo server time. Chỉ `sold_out`, `queue_waiting`, `queue_expired` tại hold được phân loại là 409 dự kiến; 409 khác và mọi 429 từ endpoint booking/queue hiện tại là unexpected, được đếm riêng. Không xóa status dự kiến khỏi raw/CSV; báo cáo tổng HTTP failed và unexpected tách nhau.

### 4. Scaling — một mức mỗi run, không manual scale

Đưa queue policy về **off** sau Admission và xác nhận trạng thái này trước Scaling để tách tải GET khỏi bài queue; ghi audit thay đổi. [ecs-scaling.js](../../../scripts/load/ecs-scaling.js) chỉ nhận VUS 60/100/150/200, giữ 15–25 phút và hạ tải 5 phút; mỗi VU thực hiện hai GET mỗi iteration, nghỉ mặc định 1 giây. Đây là tải theo VU, **không phải arrival rate cố định**. Ghi offered/actual RPS từ k6, mức VU thực, dropped/failed, CPU/memory và runner saturation. Trước mỗi mức, lưu baseline AWS riêng và xác minh API desired ≤8/ASG desired ≤6. Chỉ tăng mức sau khi gate còn an toàn; dừng tăng khi đã có bằng chứng EC2 tự tăng và giữ đủ thời lượng của mức hiện tại.

```powershell
# Thay <level> lần lượt bằng 60, 100, 150, 200; chỉ chạy mức tiếp nếu gate cho phép.
k6 run -e BASE_URL='https://<approved-host>' -e VUS=<level> `
  -e HOLD_MINUTES=15 -e PAUSE_SECONDS=1 `
  --summary-export='.local/assessment/<scaling-id>/k6-summary.json' `
  --out 'json=.local/assessment/<scaling-id>/k6-raw.json' `
  scripts/load/ecs-scaling.js
```

Đối chiếu theo timestamp: offered load → ECS API desired → pending vì thiếu placement thực (RAM/ENI/CPU/slot) → Capacity Provider/ASG activity → EC2 in-service và đăng ký ECS → task mới đúng digest → ALB healthy target → request streams từ nhiều API task. Cùng timeline có alarm workload thật, SNS delivery/subscription và Console video. Không coi chỉ CPU/ASG desired/ảnh tĩnh là chứng minh chuỗi. Nếu không có tăng EC2 trong giới hạn thì ghi chưa chứng minh hai tầng.

### 5. Recovery — không tạo tải mới

Sau mức cuối, tiếp tục collector/runner **30–45 phút**. So sánh từng mốc với baseline: ECS task/desired, EC2 in-service, target health, DB connections, queue/DLQ, alarm/SNS, latency và UI/probe nghiệp vụ. Chỉ đánh dấu phục hồi khi dữ liệu ở trạng thái được xác minh và không còn job synthetic có thể gửi mail sau cửa sổ. Không dùng thao tác scale-in thủ công làm bằng chứng.

## Gate dừng và gói evidence

Dừng tăng hoặc kết thúc tải ngay khi invariant sai, tất cả ALB target unhealthy, 5xx >5% liên tục 2 phút, DB connections chạm budget đã xác minh, vượt API max 8/ASG max 6, hoặc runner saturation làm phép đo không tin cậy. Ghi UTC, lý do, mức VU và số liệu trước/sau; giữ output lần lỗi và hạ tải có kiểm soát. Nếu chưa xác minh DB budget/placement/alarms thì dừng trước C3.

Mỗi run cần manifest (run ID, UTC, script hash/commit, runner ngoài ASG, account/region đã làm sạch, session manifest hash/expiry **không có token**, queue state, email backend, baseline, stop/rollback), k6 raw/summary private, CSV sanitized, collector metrics/activity/preflight, SVG tải–latency/tải–error/tải–task–EC2/resources/queue, invariant/UI probe và video link có mốc UTC. [chart.py](../../../scripts/assessment/observability/chart.py) tạo SVG từ collector CSV; [summarize-c3.mjs](../../../scripts/load/summarize-c3.mjs) tạo CSV theo phút UTC và ba SVG k6 từ NDJSON, chỉ xuất số tổng hợp và không sao chép tags/URL. Lệnh sau dùng cho từng run sau khi raw k6 đã được lưu private:

```powershell
# Với platform, lọc request preflight khỏi RPS. Thay 'platform' bằng 'booking'
# hoặc 'scaling' cho hai bài tương ứng; bỏ đối số này ở baseline.
node scripts/load/summarize-c3.mjs `
  .local/assessment/<run-id>/k6-raw.json `
  .local/assessment/<run-id>/charts 'platform'
```

Chart k6 cần đi kèm version/hash script và CSV nguồn để tái tạo; báo cáo p95 toàn cửa sổ lấy từ k6 summary, không lấy trung bình p95 từng phút. Nếu raw chứa session ID, ARN hoặc PII, giữ private, review CSV/SVG trước khi đưa bản đã che vào `evidence/assessment/<run-id>/`. **Video link: chưa có. CSV/chart C3 thực: chưa có.**
