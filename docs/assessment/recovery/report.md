# B4 — Báo cáo RDS PITR và RPO/RTO

**Kết luận: đã hoàn thành chuẩn bị công cụ và preflight; B4 chưa nghiệm thu PITR.** Các phần phụ thuộc phối hợp tạm chờ theo [sprint B4](../../sprints/ke-hoach-nghiem-thu-4-ngay.md#b4-rds-pitr-và-đo-rporto), không làm thay người khác.

| Yêu cầu B4 | Trạng thái thực tế | Bằng chứng |
|---|---|---|
| PITR/retention/window/quota/class/KMS | Đã kiểm AWS chỉ đọc | [preflight.md](preflight.md), [JSON](../../../evidence/assessment/20261119T043844Z-b4-preflight/checks/results.json#/preflight) |
| IAM/capacity/digest/email/network | Có simulation/snapshot; chưa chứng minh quyền và placement thực | Cùng nguồn preflight |
| Marker mỗi phút, incident, target | Helper đã test local; chưa chạy series trên nguồn | [Quy trình](rds-pitr.md), [test](../../../evidence/assessment/20261119T043844Z-b4-preflight/checks/results.json#/tool_validation) |
| App private cùng digest, DB/secret riêng | Builder PLAN_ONLY đã test; chưa provision/deploy | scripts/assessment/recovery/app_plan.py và restore_plan.py |
| Schema/count/hash/constraints/ownership/vé/session | Helper read-only đã test; chưa chạy trên DB restored | scripts/assessment/recovery/db_checks.py |
| Login/QR/hold-confirm-cancel/check-in, ảnh B5 | Chưa thực hiện trên app restored | NOT_RUN |
| RPO≤900s, RTO≤3600s | Chưa đo; timestamp và số đo đều null | [execution](../../../evidence/assessment/20261119T043844Z-b4-preflight/checks/results.json#/execution) |
| Cleanup | Marker cleanup và guard DB cleanup-plan đã test local; chưa có tài nguyên restored để dọn | Test và execution |

## Kiểm chứng công cụ

Lượt cuối **34 PASS,0 FAIL/ERROR/SKIP** trên PostgreSQL disposable:29 test công cụ và5 test measure.py có sẵn. Bao gồm guard host/TLS, source/target/time/role/secret, marker commit/verify, cleanup đúng run/idempotent/crash, hash và vi phạm capacity. Nhánh commit tracking off đã kiểm ở lượt29 test trước; lượt cuối kiểm tracking on. Các lượt trùng nhau, không cộng thành số test độc lập. Đây không phải test workflow app restored hoặc kết quả PITR AWS.

Kiểm DB nguồn lúc04:52:14UTC: schema0002_platform và7 invariants zero rows. Nguồn có track_commit_timestamp off; cách ghi khoảng commit và giới hạn kết luận RPO nằm trong [preflight](preflight.md#kiểm-db-nguồn). Không tự điền timestamp exact hoặc đổi tiêu chí đo.

## Phần còn lại — tạm chờ

Theo sprint, diễn tập sau khi C4/C5 ổn định; chưa có handoff trên các nhánh đã kiểm tại thời điểm thu evidence. Khi đủ cửa sổ: đọc lại preflight, chốt tài nguyên/policy/network riêng, ghi marker nguồn, restore DB, rollout app private, kiểm đầy đủ nghiệp vụ/ảnh B5, đo thật rồi cleanup. Quy trình chi tiết ở [rds-pitr.md](rds-pitr.md). Chưa đổi B3 X03 thành PASS.

## Trạng thái cuối

Trong lượt B4 không tạo DB/app/secret/cache/object phục hồi, không đổi production endpoint/secret/data/config, worker email giữ disabled. Hai ECS probe nguồn chỉ đọc đã STOPPED/exit0; DB/network disposable local đã dọn. Chưa có ảnh/video của app restored/PITR vì các bước này chưa thực thi; ảnh object S3 của B5 được ghi riêng bên dưới.

## Kết quả B5

Đã thực thi riêng phần S3 trên một key synthetic mới: bản tốt → bản ghi đè sai nội dung → CopyObject version tốt thành current. GET/hash/content type/private đạt; đã dọn đúng3 version, còn0 version/delete marker. Bằng chứng và bảng key/version/hash trong [s3-restore.md](s3-restore.md).

B5 tổng thể vẫn BLOCKED: chưa kiểm DB reference và ảnh qua app restored của B4. `images_verified=false`; `b5_images=NOT_RUN`, RPO/RTO vẫn null. Ảnh evidence là object GET từ S3, không phải UI screenshot; không dùng kết quả S3 độc lập thay kiểm chứng app/DB.

Rà soát B5 ngày19/11: prompt đã có bằng chứng cho riêng lớp S3; kiểm cleanup lại05:15:03UTC vẫn0 version/delete marker. Bảng trách nhiệm và phần NOT_RUN nằm trong [s3-restore.md](s3-restore.md#đối-chiếu-prompt-và-phần-cần-phối-hợp): người3 bàn giao ổn định C4/C5, người2 thực hiện B4 rồi lượt B5 tích hợp mới. Không coi app restored là việc của người3 hoặc dùng ảnh object thay kiểm UI/DB.

## Kết hợp bàn giao người1

Đã đọc A1/A2/A3 trên main commit `ff2bb56` và đưa thông tin liên quan vào [preflight](preflight.md#bổ-sung-từ-bàn-giao-người1-trên-main), [kế hoạch B4](rds-pitr.md#áp-dụng-bàn-giao-người1-vào-môi-trường-kiểm-chứng-b4). Bổ sung subnet/SG-port, giới hạn readyz, DB/Redis/outbox và vai trò của prefix ảnh private. Tám file source đối chiếu khớp; không coi ADR Draft là quyết định đã Accepted hoặc bản Hava là kết quả fault/restore.

Đã xác minh mới chỉ đọc lúc05:21:46UTC: route NAT/S3 endpoint của hai subnet API; TLS-only bucket policy, BucketOwnerEnforced và lifecycle noncurrent30 ngày của bucket ảnh. Các mục này bổ sung độ rõ của preflight; không thực hiện thay C4/C5, không tạo DB/app restored hoặc đo RPO/RTO. Trạng thái B4 trong evidence hiện vẫn là chuẩn bị/preflight; không có run PITR được ghi nhận để đánh hoàn thành. B1–B3 không bị chạy lại hoặc sửa kết quả.

B5 đã bổ sung từ A3 cách nối session→room/layout→DB key→S3 prefix/object và đối chiếu storage_objects (không có FK bảo đảm object tồn tại). Suite cache source có sẵn đã chạy offline4 PASS; route published có thể cache24 giờ theo tên file, độc lập với S3 VersionId. Đây là kiểm contract bằng mock, không phải kiểm DB/app restored; images_verified vẫn false. Chi tiết trong [s3-restore.md](s3-restore.md#liên-kết-db-và-đường-dẫn-ảnh-cần-kiểm-theo-a3).

## Tích hợp C1 vào B4 —20/11/2026

B4 cần C1 quota/capacity trực tiếp. Đã dùng collector7fa878a từ nhánh người3 cho một smoke chỉ đọc và bổ sung SQL max_connections/reserve, quota RDS, RAM/CPU/ENI theo AZ. Chi tiết ở [preflight](preflight.md#bàn-giao-c1-cho-b4) và [evidence](../../../evidence/assessment/20261119T172832Z-b4-c1-preflight/checks/results.json).

Budget66 phù hợp non-reserved limit74 của DB nguồn tại snapshot; rolling ceiling65. Headroom placement chỉ là cận trên1slot AZ2a/3slots AZ2b, chưa chứng minh tài nguyên còn lại đủ cho fault hoặc app restored. Smoke có metric thiếu/chậm và1 vòng vượt interval nên không tự đánh C1 accepted. Chưa chạy PITR/deploy restored app hoặc chốt RPO/RTO; không đổi trạng thái C4/C5/B4/B5 vì có baseline mới.

## Đối chiếu A4 của người1 —20/11/2026

Đã dùng [bàn giao A4](../architecture/a4/handoff.md), [đánh giá recovery](../architecture/a4/recovery-assessment.md) và [sơ đồ PITR planned](../architecture/a4/diagrams/rendered/a4-03-pitr-pending.svg) tại commit `39f7ab1cd3cdd925e55fae5c13b0a6a541e8fa3a` để đối chiếu kế hoạch B4. A4 là đầu ra tổng hợp nhận runbook/evidence B4/B5/C4/C5 theo sprint, không chứng minh đã có DB restored. Không bổ sung một bài diễn tập ngoài prompt.

Thứ tự giữ nguyên: người3 bàn giao C4/C5 đã ổn định → người2 chạy B4 và B5 tích hợp trong cửa sổ riêng → kiểm nghiệp vụ sau restore của B3 → chốt số đo đủ bằng chứng → người1 cập nhật A4. Người2 vẫn chịu trách nhiệm DB identifier mới, DB/app private riêng, cùng digest/schema và kiểm DB/nghiệp vụ/ảnh; không chuyển production sang DB restored.

Trong lượt thật, ghi owner/run ID, commit công cụ tách với commit đóng gói và digest/schema được kiểm, region/định danh đã làm sạch, marker/incident/target/ready UTC, checks và metric source_at/status, cleanup/rollback. Chỉ ghi ready sau khi DB, nghiệp vụ và ảnh B5 đạt; dùng record hợp lệ cho measure.py theo [rds-pitr.md](rds-pitr.md). Giới hạn A4 xác nhận vẫn giữ: source invariants, retention và LatestRestorableTime không thay kiểm DB restored; failover không thay PITR. B4 vẫn BLOCKED, RPO/RTO null và images_verified=false. Không có tài nguyên hay thao tác AWS mới trong lượt đối chiếu này.

## Sử dụng C2 trong B4 —20/11/2026

Đã bổ sung [preflight email isolation](preflight.md) từ runbook người3 tại commit `09f768e168e03517a1636c1030059a7fd915b58a`: phân biệt baseline worker nguồn với cấu hình app restored, kiểm task/digest và drain job cùng cửa sổ, không replay SKIPPED hoặc tự bật Brevo. C2 local PASS không phải bằng chứng switch/restore AWS. Đây là phối hợp đáp ứng yêu cầu email disabled/cô lập SQS của B4, không thêm điều kiện phải hoàn thành toàn bộ C2 trước PITR. B5 không có đầu vào C2 riêng; yêu cầu cô lập app của B5 đã đi qua B4 nên giữ nguyên s3-restore.md. RPO/RTO null, images_verified=false và trạng thái chờ phối hợp không đổi.

## Đối chiếu C3/C4 cho B4/B5 —21/11/2026

Đã bổ sung [preflight](preflight.md) từ commit người3 `c12a252e2b49b876dcdb1a1575d4462526cc0d03`: capacity thay đổi5→4 EC2, giới hạn ENI/API overlap và clock chưa đồng bộ. [C4 report](https://github.com/tuanngthuet/CloudCompuAssignment/blob/c12a252e2b49b876dcdb1a1575d4462526cc0d03/docs/assessment/performance/failover-report.md) chưa có inject/observe/rollback hoặc xác nhận baseline sau fault; C3 cũng chưa chạy tải. Đây là bằng chứng tiền điều kiện còn thiếu, không phải handoff fault đã ổn định để bắt đầu B4.

Người3 cần bàn giao run/target/incident UTC đủ tin cậy, probes/metrics cùng cửa sổ, kết quả rollback và baseline ổn định sau C4/C5; người2 kiểm nghiệp vụ/invariants rồi thực hiện B4/B5 trong cửa sổ riêng, không đồng thời load/fault. Không phát sinh yêu cầu chạy C3/C4 thay người3. B5 chỉ hưởng thông tin này qua môi trường restored của B4; s3-restore.md và kết quả S3 độc lập giữ nguyên. B4/B5 tích hợp còn BLOCKED, X03 NOT_RUN, images_verified=false và RPO/RTO null; không có restore hoặc thao tác AWS mới.
