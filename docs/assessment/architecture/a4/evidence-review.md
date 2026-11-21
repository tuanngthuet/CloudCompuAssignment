# Đối chiếu bằng chứng — 21/11/2026

## B3: retest đã giải quyết bốn mục local

Đọc trực tiếp [CSV chuẩn](https://github.com/tuanngthuet/CloudCompuAssignment/blob/54b034e2f40d92ce4c00d4f9792706008a972279/docs/assessment/functional/test-cases.csv) và [báo cáo B3](https://github.com/tuanngthuet/CloudCompuAssignment/blob/54b034e2f40d92ce4c00d4f9792706008a972279/docs/assessment/functional/report.md): **337 dòng, 333 PASS, 0 FAIL, 1 BLOCKED, 3 NOT_RUN**. [Kết quả đếm tại A4](b3-csv-verification.json) lưu hash nguồn và các case còn lại.

R001/avatar, R004/camera, R006/image map và R009/profile đã retest **34 test PASS** trong môi trường disposable; sửa fixture/test contract. Không phải 34 dòng CSV mới, không cộng thành tổng suite hoặc kết quả AWS mới. Camera dùng fake media/mock API. [JSON retest](https://github.com/tuanngthuet/CloudCompuAssignment/blob/54b034e2f40d92ce4c00d4f9792706008a972279/evidence/assessment/20261119T034356Z-b3-functional/checks/results.json) giữ lỗi lịch sử và kết quả mới riêng; run `20261120T173805Z-b3-regression-retest`, tương ứng 21/11 giờ Việt Nam.

**C6 `e2431f3` vẫn ghi 329 PASS/3 FAIL/2 BLOCKED/3 NOT_RUN:** đó là snapshot trước retest. A4 dùng nguồn B3 mới, không coi các lỗi đã xử lý là tồn đọng hiện tại. V01 vẫn BLOCKED vì video; X01/X02/X03 vẫn NOT_RUN. Người 3 cần cập nhật C6 từ commit B3 mới.

## C2: có công cụ, chưa nghiệm thu cửa sổ AWS

[Run local C2](https://github.com/tuanngthuet/CloudCompuAssignment/blob/e2431f306df96abd8043680906e1286243dbf14a/evidence/assessment/20261120T130757Z-c2-local/summary.md) ghi 7/7 PASS và syntax pass. [Runbook](https://github.com/tuanngthuet/CloudCompuAssignment/blob/e2431f306df96abd8043680906e1286243dbf14a/docs/assessment/performance/runbook.md)/[C3 report](https://github.com/tuanngthuet/CloudCompuAssignment/blob/e2431f306df96abd8043680906e1286243dbf14a/docs/assessment/performance/load-report.md) có kiểm bổ sung booking 9/9, platform 4/4, scaling 2/2, summarize 1/1; các lượt khác nhau, không cộng như test độc lập.

Quan sát worker revision 10 có EMAIL_BACKEND=disabled chưa thay job synthetic SKIPPED, kiểm Brevo và khôi phục đúng baseline trong cùng cửa sổ. **C2 tổng thể BLOCKED.** Nhận định trước đây “có C2” chỉ xác nhận đã có tài liệu/code/evidence local, không phải C2 AWS hoàn tất.

## C3: readiness thật, chưa phát tải

[C3 read-only](https://github.com/tuanngthuet/CloudCompuAssignment/blob/e2431f306df96abd8043680906e1286243dbf14a/evidence/assessment/20261120-c3-live-readonly/summary.md) có một mẫu 67 dòng và lượt ba mẫu 187 dòng riêng. Ba mẫu có 151 OBSERVED/6 MISSING/30 MISSING_OR_DELAYED; nhịp khoảng 30s theo clock runner, không có OVER_INTERVAL. Raw CSV/private manifest không nằm trong archive, nên đây là số liệu theo summary owner, không tái đếm CSV tại A4.

Windows Time chưa đồng bộ; còn thiếu/chậm ENI và các metrics. k6 đã xác minh qua đường dẫn tuyệt đối, không còn kết luận đơn giản “chưa cài k6”. Gate còn thiếu session B2 mới, clock, C2 mail window, B3 smoke/invariants cùng cửa sổ, DB budget/placement và queue policy đúng bài. Năm bài Baseline/Platform/Admission/Scaling/Recovery AWS vẫn NOT_RUN; actual RPS/p95 chưa đo.

## C4: kết quả capacity mới, inject vẫn chưa chạy

[Capacity recheck](https://github.com/tuanngthuet/CloudCompuAssignment/blob/e2431f306df96abd8043680906e1286243dbf14a/evidence/assessment/20261120-c4-capacity-recheck/summary.md) ghi ASG 4 máy, hai máy mỗi AZ. Mô phỏng xếp task thay được 1/1 khi mất compute 2a và 3/3 khi mất compute 2b. **Cả hai hướng thiếu thêm một slot API overlap**; không kết luận đủ capacity cho diễn tập. ENI fallback dựa EC2 interfaces và giới hạn loại máy, không phải ECS đã trả telemetry ENI còn lại.

[Báo cáo C4/C5](https://github.com/tuanngthuet/CloudCompuAssignment/blob/e2431f306df96abd8043680906e1286243dbf14a/docs/assessment/performance/failover-report.md) giữ prepare/inject/observe/rollback NOT_RUN. Activity tự động 4→5→4 trước diễn tập có nguồn AWS timestamps; không phải C3 load test hay C4 recovery.

## C5 và C6

[C5 readiness](https://github.com/tuanngthuet/CloudCompuAssignment/blob/e2431f306df96abd8043680906e1286243dbf14a/evidence/assessment/20261120-c5-readiness/summary.md) thấy RDS Multi-AZ DB instance available, Redis replication group available/HA bật; Redis quota test failover toàn account chưa chốt. Không gọi force-failover RDS hoặc test-failover Redis. Không có probe/events chuyển role/CSV fault/RTO C5.

[C6 snapshot](https://github.com/tuanngthuet/CloudCompuAssignment/blob/e2431f306df96abd8043680906e1286243dbf14a/evidence/assessment/20261121-c6-readonly/summary.md) thấy API 2/2, worker/publisher 1/1, pending 0, ASG min/desired/max **2/5/6**, 5 Healthy/InService (2a:3, 2b:2), hai ALB targets healthy (mỗi AZ một target); RDS/Redis available. Worker service trỏ revision 10 disabled; chưa đối chiếu từng running task/digest. Queue/DLQ count 0 chỉ là số gần đúng ở một thời điểm.

Đây là snapshot đọc tuần tự, không nguyên tử, clock runner không đồng bộ, chưa đủ timestamp UTC để ghép mọi API call. **Không xác nhận baseline sau fault, rollback/scale-in, digest hoặc invariant SQL cùng cửa sổ.** Thay sơ đồ baseline A4 bằng snapshot mới, không kéo số DB budget/retention lịch sử sang làm quan sát cùng run C6.

[Báo cáo cuối C6](https://github.com/tuanngthuet/CloudCompuAssignment/blob/e2431f306df96abd8043680906e1286243dbf14a/docs/assessment/final-report.md) ghi kiểm workspace 19/19 hash và 379/379 links; các file A/B untracked khi kiểm có thể không nằm trong commit nhánh C. A4 kiểm riêng 19 hash nguồn hai ZIP mới, không nhận 379 links là kết quả của A4 hoặc của PR đã tích hợp.

## B4/B5 không đổi trạng thái

[B4 report mới](https://github.com/tuanngthuet/CloudCompuAssignment/blob/54b034e2f40d92ce4c00d4f9792706008a972279/docs/assessment/recovery/report.md) đã tiếp nhận C2–C6 nhưng vẫn chưa PITR, chưa có marker/incident/target/ready và DB/app restored. Không chuyển production sang DB restored. Email isolation của B4 cần xác minh riêng; không tự thêm điều kiện phải hoàn thành toàn bộ C2 trước PITR.

[B5 report](https://github.com/tuanngthuet/CloudCompuAssignment/blob/54b034e2f40d92ce4c00d4f9792706008a972279/docs/assessment/recovery/s3-restore.md) và [evidence S3 đã kèm](evidence/20261119T050938Z-b5-s3-restore/checks/results.json) giữ **S3 component PASS / B5 tổng thể BLOCKED**. Ba PNG là bytes S3 GET, không phải UI. Hash before=restored, overwritten khác; cleanup đúng ba version, còn 0; DB reference/app/cache vẫn NOT_RUN. Cần lượt tích hợp mới sau B4; version cũ đã xóa không dùng để kiểm app sau này.
