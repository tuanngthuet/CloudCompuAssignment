# B4 — Preflight RDS PITR

**Đã kiểm chỉ đọc; diễn tập chưa chạy.** Thực hiện theo [prompt B4](../../sprints/ke-hoach-nghiem-thu-4-ngay.md#b4-rds-pitr-và-đo-rporto) và [runbook phục hồi](../../deployment/recovery.md). Các mục phụ thuộc phối hợp tạm chờ, không thực hiện thay người khác.

## Kết quả AWS

Snapshot **19/11/2026 11:43:53 UTC+7 / 04:43:53 UTC**. Nguồn đối chiếu duy nhất: [results.json — preflight](../../../evidence/assessment/20261119T043844Z-b4-preflight/checks/results.json#/preflight).

| Kiểm tra | Kết quả |
|---|---|
| Account / region | Đã đối chiếu account dự kiến; ap-southeast-2 |
| RDS | PostgreSQL 16.13, db.t4g.micro, available, 20 GiB gp3 |
| Bảo vệ | Multi-AZ, private, encrypted; KMS Enabled |
| Backup | Retention **1 ngày**; LatestRestorableTime **2026-11-19T04:38:11Z** |
| Cửa sổ automated backup | **2026-11-18T04:38:11Z → 2026-11-19T04:38:11Z** |
| Quota DB | Used1 / Max40; còn39 tại snapshot |
| Class/engine | Có option PostgreSQL16.13/db.t4g.micro/gp3 |
| Network/config nguồn | Subnet group Complete,2 AZ; SG active; parameter group in-sync |
| IAM simulation | 10 action restore/delete RDS, register/run/stop ECS, put/delete SSM, PassRole, KMS decrypt/create-grant: allowed |
| ECS services | API2/2, worker1/1, publisher1/1; pending0, rollout completed; digest trong JSON |
| ECS capacity | 4 container instance ACTIVE/agent connected; RAM còn505/505/1017/1529MiB; CPU1536/1536/1792/2048units |
| Email | Worker EMAIL_BACKEND=disabled |

Các số liệu là snapshot, phải đọc lại khi diễn tập. IAM simulation và class orderable không chứng minh restore sẽ thành công. RemainingResources không trả ENI; chưa chứng minh placement đủ cho app private. Runbook cũ ghi Terraform retention30 ngày; hiện trạng live tại lượt này là1 ngày.

## Kiểm DB nguồn

[SQL nguồn](../../../evidence/assessment/20261119T043844Z-b4-preflight/checks/results.json#/source_sql) lúc **19/11/2026 11:52:14 UTC+7 / 04:52:14 UTC**:

- Schema `0002_platform`; bảy invariants đều **0 vi phạm**.
- `track_commit_timestamp=off`. Marker helper ghi khoảng DB-clock trước COMMIT và sau acknowledgment; không nhận khoảng này là timestamp commit chính xác. Có thể tính cận trên RPO bảo thủ; không điền cận này vào trường exact của measure.py hoặc bật tracking/reboot nguồn để ép kết quả.

Hai ECS probe chỉ đọc đã STOPPED/exit0. Đây là kiểm DB nguồn, chưa chứng minh DB restored đúng.

## Chạy lại collector

```powershell
python scripts/assessment/recovery/preflight.py --profile labseat --region ap-southeast-2 --expected-account ACCOUNT_ID_PRIVATE --source-db labseat-lab --cluster labseat-lab --services labseat-lab-api labseat-lab-worker labseat-lab-publisher --output .local/assessment/b4-preflight.json
```

Thêm `--aws DUONG_DAN_AWS_EXE` nếu CLI chưa có trên PATH. Collector kiểm account trước, chỉ gọi API đọc và xuất metadata đã làm sạch; không lấy giá trị secret, không tạo/xóa tài nguyên. Nó không xác minh lịch phối hợp nên không tự đánh diễn tập PASS.

Phần chưa xác minh: IAM/KMS thực trên tài nguyên mới, network/egress/ENI cho app tạm và giá trị secret trỏ đúng DB/cache riêng. Phần thực thi và giới hạn đo được ghi tại [report.md](report.md).

Manifest dùng SHA-256 trên nội dung UTF-8 chuẩn hóa CRLF thành LF để đối chiếu nhất quán giữa Windows và GitHub.

## Bổ sung từ bàn giao người1 trên main

Đối chiếu `origin/main` tại commit **ff2bb56091a5e846e4ebc662d2ea44d1d6fbecf6**; không merge hoặc ghi đè tài liệu của người1. Tài liệu A1/A2/A3 có trên main, chưa có trong tv3/w1-package. Tham chiếu commit cố định để lần review sau không tự đổi nguồn. [Provenance/hash nguồn và phép đọc bổ sung](../../../evidence/assessment/20261119T043844Z-b4-preflight/checks/results.json#/person1_handoff).

| Nguồn người1 | Thông tin dùng được cho B4 | Giới hạn |
|---|---|---|
| [A1 inventory](https://github.com/tuanngthuet/CloudCompuAssignment/blob/ff2bb56091a5e846e4ebc662d2ea44d1d6fbecf6/docs/assessment/architecture/inventory.md) | App subnet10.20.10.0/24 và10.20.11.0/24; DB subnet10.20.20.0/24 và10.20.21.0/24; SG/port App→DB5432, App→Redis6379; RDS private/encrypted/Multi-AZ/retention1 ngày | Snapshot17/11, không phải cấu hình recovery hoặc kết quả restore |
| [A2 Hava](https://github.com/tuanngthuet/CloudCompuAssignment/blob/ff2bb56091a5e846e4ebc662d2ea44d1d6fbecf6/docs/assessment/architecture/hava.md) | Đối chiếu quan hệ subnet/AZ/network/container trước khi chọn môi trường app kiểm chứng | Timestamp ảnh/import chưa đầy đủ; không dùng làm kiểm chứng hiện trạng hoặc fault |
| [A3 ERD](https://github.com/tuanngthuet/CloudCompuAssignment/blob/ff2bb56091a5e846e4ebc662d2ea44d1d6fbecf6/docs/assessment/architecture/a3/erd.md) và [sequence](https://github.com/tuanngthuet/CloudCompuAssignment/blob/ff2bb56091a5e846e4ebc662d2ea44d1d6fbecf6/docs/assessment/architecture/a3/sequences.md) | Schema/khóa/ràng buộc và transaction của booking/check-in; đặt tiêu chí ownership/vé/session và workflow sau restore | Là phân tích source, chưa phải trace hay test restored app |
| [ADR Redis](https://github.com/tuanngthuet/CloudCompuAssignment/blob/ff2bb56091a5e846e4ebc662d2ea44d1d6fbecf6/docs/assessment/architecture/a3/adr/003-redis-admission.md), [ADR outbox](https://github.com/tuanngthuet/CloudCompuAssignment/blob/ff2bb56091a5e846e4ebc662d2ea44d1d6fbecf6/docs/assessment/architecture/a3/adr/004-outbox-email.md), [source review](https://github.com/tuanngthuet/CloudCompuAssignment/blob/ff2bb56091a5e846e4ebc662d2ea44d1d6fbecf6/docs/assessment/architecture/a3/supplement-review.md) | PostgreSQL giữ vé; Redis admission/PubSub là dependency riêng; email có outbox/SQS/worker; readyz chỉ kiểm DB | ADR còn Draft; không tự coi Accepted hoặc thay bằng chứng nghiệm thu |

Tám file source đã đối chiếu byte giữa main và nhánh này đều khớp: models, shared/http, booking/service, notifications/jobs, events, redis/admission, storage/objects và main. Hai khác biệt runtime-source ngoài tập này là assessment_seed.py và static/image-map.js; không tuyên bố toàn bộ source giống nhau hoặc digest đã được map tới commit.

### Xác minh bổ sung từ AWS chỉ đọc

Lúc **19/11/2026 12:21:46 UTC+7 / 05:21:46 UTC**:

- Hai subnet API10.20.10.0/24 và10.20.11.0/24 không tự gán public IPv4, đều có default route NAT active và route tới S3 gateway endpoint active; có1 S3 gateway endpoint available. Đây là network nguồn, chưa chứng minh network/SG của app restored hoạt động.
- Bucket ảnh cùng identity hash với lượt B5: policy Deny cho mọi principal/action S3 khi aws:SecureTransport=false, phủ bucket và objects; ObjectOwnership=BucketOwnerEnforced.
- Lifecycle Enabled, phạm vi toàn bucket, NoncurrentDays=30. Đây là giới hạn giữ version ảnh cũ, không bảo đảm mọi ảnh cũ luôn có đủ30 ngày phục hồi hoặc thay RDS retention1 ngày.

Như vậy đã bổ sung phần lifecycle/TLS policy mà A1 ghi Pending cho bucket ảnh; không sửa kết luận A1 gốc hoặc nhận là toàn bộ security audit đã hoàn tất. Effective IAM, endpoint policy, recovery prefix, ENI và probe tới tài nguyên mới vẫn cần kiểm lúc triển khai.

## Bàn giao C1 cho B4

B4 có đầu vào C1 trực tiếp theo sprint. Đã đọc [C1 nguồn](https://github.com/tuanngthuet/CloudCompuAssignment/blob/7fa878ac7e7995c25777680e44fe2da36d1e619c/docs/assessment/performance/observability.md) ở7fa878a và chạy collector nguyên bản,6 unit test offline đạt; chỉ bổ sung kết quả vào output người2, không sửa báo cáo/code của người3. [JSON/CSV/chart thực](../../../evidence/assessment/20261119T172832Z-b4-c1-preflight/checks/results.json). Lượt quan sát UTC19/11 17:28–17:31 tương ứng20/11 sau00:28 giờ Việt Nam, không phải tải/fault/restore.

| Phần C1 cần cho B4 | Kết quả bổ sung thực tế | Giới hạn |
|---|---|---|
| Collector baseline |4 mẫu/252 dòng; API running2, EC2 desired/InService4, healthy targets2;0 lỗi API |1 vòng30,78s;10 loại metric thiếu/chậm được giữ nguyên status, không đổi thành0 |
| DB connection budget |max_connections79; superuser reserve3, reserved2 → non-reserved74; budget66 dư8, rolling ceiling65 |9 client connections tại SQL snapshot gồm probe; không phải peak của tải/rollout |
| DB correctness |schema0002_platform;7 invariants zero rows; transaction read-only |Không thay kiểm DB restored; commit tracking vẫn off |
| Restore quotas |DB instances1/40; allocated storage20/100000GiB; manual snapshots0/100 |Không chứng minh IAM/KMS/create/restore thực thành công |
| Same API task |memory hard512MiB, CPU256units; đọc ENI attached và instance-type max thực |Không lấy capability trunking làm bằng chứng có trunk ENI; ECS ENI metric vẫn MISSING |
| Headroom theo AZ |Ước lượng cận trên cho cùng API task: AZ2a1slot, AZ2b3slots |Chỉ min(memory/CPU/physical ENI) tại snapshot; còn subnet IP, SG, constraint, reserved headroom và role; không đảm bảo placement hoặc phục hồi cả AZ |
| Worker/email |revision10, EMAIL_BACKEND=disabled; không đổi backend |Chưa thực hiện smoke mail C2 hoặc gửi mail |

Collector exit0 chỉ là thu được API; C1 nguồn vẫn ghi nghiệm thu BLOCKED và chưa được owner xác nhận lại. K6/clock/load-runner saturation, request stream và khả năng placement/fault còn phải xác minh. Snapshot capacity sau SQL probe không cùng thời điểm từng mẫu metrics. Có một ECS probe chỉ đọc tạm trong smoke, đã STOPPED/exit0; biến động task/resource do probe không phải autoscaling.

Các [chart task–EC2–targets](../../../evidence/assessment/20261119T172832Z-b4-c1-preflight/charts/tasks-ec2-targets.svg) và [RDS connections](../../../evidence/assessment/20261119T172832Z-b4-c1-preflight/charts/rds-connections.svg) lấy từ CSV, không dựng từ ảnh Console. Chạy lại collector theo cùng source/dimensions trước cửa sổ B4 thật và kiểm SHOW max_connections trên **DB restored** trước khi chốt connection budget của app tạm. Không tăng ASG/scale thủ công hoặc đổi production secret/endpoint trong lượt này.

## Đối chiếu C2 cho email isolation —20/11/2026

[Runbook C2 của người3](https://github.com/tuanngthuet/CloudCompuAssignment/blob/09f768e168e03517a1636c1030059a7fd915b58a/docs/assessment/performance/runbook.md) hỗ trợ đối chiếu worker baseline và cửa sổ email nguồn; B4 vẫn tự kiểm app restored có EMAIL_BACKEND=disabled, DB/secret riêng và không nối SQS/Brevo/publisher/worker/maintenance production theo [rds-pitr.md](rds-pitr.md). Disabled ở worker nguồn không tự cô lập app restored hoặc outbox/jobs đã được PITR phục hồi. Không đổi APP_ENV, không dùng mock backend trên production.

C2 tại commit09f768e chỉ có7 test HTTP mô phỏng PASS; smoke AWS, job SKIPPED/không gửi Brevo và restore baseline còn NOT_RUN/BLOCKED. Vì vậy snapshot revision10/disabled của B4 ngày19/11 vẫn là dữ liệu lịch sử, không được cập nhật thành xác minh hiện tại từ ảnh revision11/Brevo. Trước B4 thật, lấy cấu hình/task/digest và queue/job cùng cửa sổ; đối chiếu trạng thái cuối sau drain với người3. Nếu baseline đã disabled, không tạo rollout giả hoặc tự bật Brevo để hoàn thành C2. Lượt đối chiếu này không thay cấu hình AWS và không đổi kết luận preflight/PITR.

## Bổ sung từ preflight C3/C4 —21/11/2026

Đối chiếu commit người3 `c12a252e2b49b876dcdb1a1575d4462526cc0d03`; các snapshot được thu ngày20/11, không phải kiểm AWS mới của người2. Nguồn: [C3 read-only](https://github.com/tuanngthuet/CloudCompuAssignment/blob/c12a252e2b49b876dcdb1a1575d4462526cc0d03/evidence/assessment/20261120-c3-live-readonly/summary.md), [C4 capacity recheck](https://github.com/tuanngthuet/CloudCompuAssignment/blob/c12a252e2b49b876dcdb1a1575d4462526cc0d03/evidence/assessment/20261120-c4-capacity-recheck/summary.md).

| Thông tin mới | Ý nghĩa cho B4 |
|---|---|
| Collector C3 ba mẫu:187 dòng,151 OBSERVED/6 MISSING/30 MISSING_OR_DELAYED,0 OVER_INTERVAL; nhịp khoảng30s | Có cải thiện nhịp ngắn hạn so với lượt C1 cũ, nhưng clock runner chưa đồng bộ và CloudWatch Period=60s; không thay bằng chứng cửa sổ PITR/RPO/RTO. CSV/raw được người3 giữ private, ở đây chỉ dẫn bản summary công khai. |
| ASG snapshot C3 có5 EC2, C4 kiểm lại còn4, chia2 EC2/AZ; API target khỏe cả hai AZ | Không dùng số task/EC2 cũ như capacity hiện tại. AWS activity ghi managed scaling4→5 rồi5→4 và AZ rebalance, không phải tải C3 hoặc fault C4. Phải kiểm lại baseline/placement trước khi dựng app restored. |
| C4 dùng EC2 max interfaces trừ interfaces gắn thực khi ECS thiếu ENI; mô phỏng thay task2a→2b đạt1/1,2b→2a đạt3/3, cả hai thiếu thêm một slot API overlap | Đây là gate capacity của C4, không phải bằng chứng placement thật hoặc lý do tự tăng ASG cho B4. Cần kiểm CPU/RAM/ENI/IP/constraints và slot dành riêng cho app B4 cùng digest tại cửa sổ triển khai; không cộng tài nguyên toàn AZ để coi xếp được task. |
| RDS available/Multi-AZ, CloudWatch connections8; worker revision10 disabled trong snapshot C3 | Không thay SQL max_connections/reserve/budget mới, IAM/KMS/quota PITR hoặc email-isolation của app restored. Không ghi đè kết quả SQL/quota ngày19/11 bằng datapoint CloudWatch khác thời điểm. |

C3 còn BLOCKED; C4 inject/rollback chưa chạy và chưa có baseline sau fault. Vì vậy chưa đủ bàn giao “sau các fault ổn định” của B4; vẫn chờ C4/C5 theo kế hoạch. Clock runner người3 còn FAIL; phải ghi nguồn đồng hồ/độ lệch và timestamp timezone đủ tin cậy khi bàn giao incident/marker/ready. Không dùng thời gian từ các preflight này để tính RPO/RTO.

## Bổ sung snapshot C5/C6 —21/11/2026

Nguồn người3 tại commit `e2431f306df96abd8043680906e1286243dbf14a`: [C5 readiness ngày20/11](https://github.com/tuanngthuet/CloudCompuAssignment/blob/e2431f306df96abd8043680906e1286243dbf14a/evidence/assessment/20261120-c5-readiness/summary.md), [C6 read-only ngày21/11](https://github.com/tuanngthuet/CloudCompuAssignment/blob/e2431f306df96abd8043680906e1286243dbf14a/evidence/assessment/20261121-c6-readonly/summary.md). Đây là hai snapshot riêng do người3 thu; không có timestamp UTC runner đủ tin cậy và không phải snapshot nguyên tử hay preflight mới do người2 chạy.

| Quan sát | Giới hạn áp dụng cho B4 |
|---|---|
| RDS available, MultiAZ=true, DBClusterIdentifier=null, primary AZ2b; Redis available, primary2a/replica2b | Xác nhận topology tại snapshot; không phải kết quả C5, PITR hay kiểm correctness sau fault. C5 chưa inject và chưa đủ bàn giao ổn định. Không nhầm failover RDS nguồn với restore vào identifier mới của B4. |
| C6 ASG min/desired/max2/5/6,5 Healthy/InService chia2a:3/2b:2, suspended processes rỗng; hai target healthy | Mới hơn snapshot4 EC2 của C4 nhưng không chứng minh placement/capacity app restored hoặc rollback sau fault. Đọc lại CPU/RAM/ENI/IP, constraints, quota và DB budget đúng cửa sổ B4; không ép desired về4 để khớp tài liệu cũ. |
| C6 API2/2, worker/publisher1/1; worker service trỏ revision10 với EMAIL_BACKEND=disabled, APP_ENV=production; queue/DLQ0 visible/not-visible/delayed | Chưa đối chiếu từng running task/digest; số queue gần đúng không chứng minh job test đã SKIPPED/drain hoặc không gửi Brevo sau restore. App B4 vẫn phải có isolation riêng. |
| Windows Time stopped; chưa có invariants/marker/DB budget mới trong cửa sổ C5/C6 | Không dùng giờ local của các snapshot để tính incident/ready/RPO/RTO. Giữ SQL/quota lịch sử của B4 đúng ngày thu; không suy thành kết quả hiện tại hoặc kết quả DB restored. |

Không có failover C5 hay audit cleanup/chi phí toàn hệ thống trong các snapshot này. Điều kiện B4 sau fault ổn định vẫn chờ; chưa tạo DB/app/secret restored và không đổi email hoặc cấu hình AWS trong lượt rà soát.
