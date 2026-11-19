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
