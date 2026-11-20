# C6 — báo cáo tổng hợp nghiệm thu LabSeat

Ngày rà soát: 21/11/2026. Chủ trì tổng hợp: Người 3. **Kết luận chung: chưa nghiệm thu toàn bộ.** [Ma trận 17 nhóm yêu cầu](traceability-matrix.md) là nguồn truy vết từng kết luận; [mục lục evidence](evidence-index.md) phân biệt file đã có, private và video thiếu. Tài liệu này tổng hợp trạng thái của owner, không thực hiện thay các bài AWS còn thiếu.

## 1. Kiến trúc và nguồn release

Người 1 đã bàn giao [A1 inventory](architecture/inventory.md) từ các lượt AWS R1/R2, [A2 Hava](architecture/hava.md), [A3 ERD/sequence/ADR](architecture/a3/README.md) và [A4 sơ đồ fault/restore](architecture/a4/README.md). A1 là mô tả hiện trạng có Pending/Unknown; A2 có khác biệt phân bố AZ giữa các snapshot; A3 là phân tích source chờ reviewer Accepted; A4 có sơ đồ planned cho PITR/fault, chưa thành sơ đồ observed. Không gán commit tài liệu thành image release AWS.

[Manifest B3](../../evidence/assessment/20261119T034356Z-b3-functional/manifest.json) ghi API task definition/digest **lịch sử** và schema `0002_platform` được kiểm ở thời điểm khác, không chứng minh mọi phép thử cùng release. Các run mới cần ghi source commit công cụ tách khỏi commit đóng gói, task definition/image digest, schema, account/region, UTC và phase. C3/C4/C5 chưa có manifest run thật. Không ghép `packaged_at_utc` B3 hoặc timestamp local chưa đồng bộ vào incident/RTO.

## 2. Correctness và dữ liệu

[B1/B2 snapshot](../../evidence/assessment/b1b2-20261117a/summary.md) ghi 500 student, 2 admin, 6 staff, 12 event, 24 lịch, 303 reservation tại 18/11, bảy invariant zero rows. Đây là snapshot sau một số thao tác demo; helper ownership/cleanup sau đổi tên ca còn cần sửa, 100 session synthetic đều hết hạn. Số ảnh/sơ đồ và seat đã đối chiếu ở snapshot nhưng quyền nguồn/tiêu chí ảnh và kiểm upload còn thiếu.

[B3 CSV](functional/test-cases.csv) có **329 PASS, 3 FAIL, 2 BLOCKED, 3 NOT_RUN** trên 337 dòng. Ba FAIL optional regression thuộc avatar fixture, camera/CSP của test và map option; hai BLOCKED là profile fixture và video V01 chưa được cung cấp. Owner B3 phải phân loại lỗi sản phẩm hay bài test và retest, không gộp thành lỗi production chưa chứng minh. X01 sau tải, X02 sau fault, X03 sau restore vẫn NOT_RUN. B3 có lần mail thật lịch sử và ảnh đã che, nhưng không thay xác nhận C2 `SKIPPED`/Brevo trong cửa sổ C3–C5. Xem [report B3](functional/report.md).

## 3. Performance và autoscaling

[C1 collector](performance/observability.md) có code/chart và AWS smoke; một lượt 3 mẫu đọc mỗi khoảng 30 giây, CloudWatch period 60 giây, vẫn có metric missing/delayed và clock runner chưa đồng bộ. [C2](performance/runbook.md#c2--cửa-sổ-worker-disabled--restore) có script session/credentials mode đạt test local; AWS smoke với session B2 mới, job synthetic `SKIPPED`, kiểm provider và restore chưa hoàn tất.

[C3 report](performance/load-report.md) giữ cả **5 bài AWS NOT_RUN**. Offered load của bài Platform được **cấu hình** 24 read/s + 2 workflow/s × 3 write = 30 request/s; **actual throughput, read/write p95, unexpected error, dropped iterations, ECS/EC2 scale peak và recovery đều chưa đo**. Không có cơ sở kết luận ngưỡng read p95 <500 ms, write p95 <1000 ms, error <1% hay hai tầng autoscaling. ASG từng biến động 4→5→4 trước diễn tập; activity đơn lẻ không phải bằng chứng C3. Snapshot C6 mới thấy desired 5; không coi là kết quả bài tải.

## 4. Availability và recovery

[C4 report](performance/failover-report.md) ghi preflight hai AZ, nhưng tại lần kiểm tra cả hai hướng thiếu một slot API overlap. Isolation, stop EC2, observe và rollback NOT_RUN. Không có downtime hoặc chứng cứ app phục vụ từ AZ còn lại sau fault. [C5 readiness](../../evidence/assessment/20261120-c5-readiness/summary.md) xác nhận loại RDS Multi-AZ DB instance và Redis replication group; **RDS và Redis failover thật đều NOT_RUN** vì C4 chưa ổn định và gate C5 khác chưa đạt. Health 200, topology snapshot hoặc role hiện tại không chứng minh recovery.

[B4 report](recovery/report.md) có preflight AWS/SQL và 34 test công cụ trên PostgreSQL disposable đạt. Marker/incident/PITR vào DB riêng, app private và nghiệp vụ trên DB restored **NOT_RUN**; **RPO và RTO = null, chưa đo**. [B5](recovery/s3-restore.md) đã chứng minh riêng S3 version restore trên key synthetic, hash/MIME/private và cleanup ba version đạt; kiểm DB reference/ảnh qua app restored, cache và `images_verified` vẫn thiếu. Không dùng ảnh object S3 làm ảnh UI.

## 5. Snapshot hiện tại và baseline cuối

[AWS read-only ngày 21/11](../../evidence/assessment/20261121-c6-readonly/summary.md): ECS API 2/2, worker 1/1, publisher 1/1; ASG min/desired/max 2/5/6, 5 Healthy/InService chia 2a:3 và 2b:2, suspended processes rỗng; hai ALB targets healthy ở hai AZ; RDS/Redis available. Worker service trỏ revision 10 có `EMAIL_BACKEND=disabled` và `APP_ENV=production`; SQS chính/DLQ đều 0 visible/in-flight/delayed tại một lần đọc. Không thay desired count để đưa về 4.

**Chưa xác minh baseline sau toàn bộ bài:** C3–C5/B4 chưa có run hậu fault/restore; runner Windows Time đang stopped; ECS task placement/digest, DB budget, alarm/SNS delivery, email provider, queue job identity, temporary DB/app/secret/object và chi phí chưa được audit cùng cửa sổ. SQS `ApproximateNumberOfMessages=0` không chứng minh toàn bộ job synthetic đã được xử lý đúng. [B5 cleanup manifest](../../evidence/assessment/20261119T050938Z-b5-s3-restore/cleanup-manifest.json) chỉ xác nhận key synthetic S3 của B5 đã dọn. Không kết luận hệ thống đã trở về cấu hình cuối mong muốn hoặc không phát sinh chi phí.

## 6. Integrity, link, Git và tái tạo

Chạy `node scripts/assessment/c6-audit.mjs` trong workspace: **19/19 file** ở năm manifest B3/B4/B5/C1-support/C2-local khớp SHA-256 (raw hoặc CRLF→LF theo manifest), **379/379 link tương đối** trong Markdown assessment tồn tại, CSV B3 đếm đúng 337 dòng status. Kiểm hash không chứng minh hình ảnh/metric là phép đo thật; C1/C3/C4/C5 chỉ có summary read-only/local, chưa có manifest công khai cho bài AWS nghiệm thu. B1/B2 manifest và C3–C5 private run artifacts cần owner bàn giao ngoài Git. [Evidence index](evidence-index.md) ghi rõ video thiếu.

Trên nhánh `assessment/load-resilience`, nhiều nguồn A4/B1–B5 là bản sao **untracked**. Chúng không tự xuất hiện trên PR C6; cần tích hợp commit của owner đúng nhánh và kiểm link lại trên Git. C6 không stage tệp B, session, token, password, ảnh QR gốc hay raw AWS state. [Mô tả PR nháp](pr-description.md) ghi dependency và checklist review.

## 7. Việc cần bàn giao đúng owner

| Owner | Việc cần chốt và retest | Bằng chứng trả về |
|---|---|---|
| Người 1 | A1 Pending, A2 chênh AZ/timestamp, A3 ADR/release review; sau fault/restore cập nhật A4 | reviewer decision, commit/digest/schema, sơ đồ observed và nguồn hash |
| Người 2 | B1 guard/cleanup; B2 session mới và quyền ảnh; triage B3 FAIL/BLOCKED, video và X01–X03; B4 PITR và B5 tích hợp app | manifest/run ID/window, CSV/SQL/probe, DB/app riêng, cleanup, RPO/RTO record |
| Người 3 | Đồng bộ clock; C1/C2 AWS smoke/email; C3 năm bài; C4 capacity/isolation/fault/rollback; C5 tuần tự RDS→Redis; đối chiếu baseline/chi phí cuối | raw private + evidence sanitized, k6/collector CSV/charts/video, events, business invariants, rollback manifest |

**Tiêu chí đóng C6:** từng dòng [ma trận](traceability-matrix.md) có evidence cùng window/release hoặc lý do thiếu rõ; các owner ký duyệt; link trên nhánh đích mở được; baseline cuối và cleanup được kiểm sau run; không còn kết luận PASS giả từ script/local/preflight. Điều kiện này hiện **chưa đạt**.
