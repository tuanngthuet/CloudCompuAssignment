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

Không tạo DB/app/secret/cache/object phục hồi, không đổi production endpoint/secret/data/config, worker email giữ disabled. Hai ECS probe nguồn chỉ đọc đã STOPPED/exit0; DB/network disposable local đã dọn. Chưa có ảnh/video restore vì chưa thực thi, không dựng bằng chứng thay thế.
