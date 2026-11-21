# C6 — mục lục evidence và video

Mỗi đường dẫn dưới đây trỏ đến gói trong **workspace hiện tại**. A4/B1–B5 được sao chép từ bàn giao và một số còn untracked trên nhánh Người 3; kiểm lại sự hiện diện trên nhánh đích trước khi phát hành PR. Không chứa link tới `.local` hoặc dữ liệu xác thực.

| Task / run | Loại bằng chứng | Kết luận có thể dùng | Giới hạn/video |
|---|---|---|---|
| A1 R1/R2 | [Inventory](architecture/inventory.md), [package manifest](architecture/package-manifest.json) | Cấu hình khảo sát theo hai mốc; tài liệu final handoff | JSON/manifest gốc private, chưa Accepted; không có video fault |
| A2 | [Hava](architecture/hava.md), [ảnh infrastructure](architecture/diagrams/A2-hava-infrastructure.png) | Bốn view đã thu | Chưa chốt import timestamp/chênh AZ; ảnh không chứng minh scaling |
| A3 | [Source manifest](architecture/a3/source-manifest.json), [validation](architecture/a3/validation.md), [ERD](architecture/a3/erd.md) | Sơ đồ/ADR theo source | Chưa reviewer Accepted, không có trace runtime |
| A4 | [Source/hashes](architecture/a4/source-manifest.json), [validation](architecture/a4/validation.md), [diagram index](architecture/a4/README.md) | Baseline/S3 đối chiếu; PITR/fault ghi planned | Không có video C4/C5/B4 |
| B1/B2 `b1b2-20261117a` | [Summary](../../evidence/assessment/b1b2-20261117a/summary.md), [dataset](functional/dataset.md) | Count, 7 invariants, HTTP ảnh tại snapshot | Manifest/session/account private; session cũ hết hạn |
| B3 `20261119T034356Z-b3-functional` | [Manifest](../../evidence/assessment/20261119T034356Z-b3-functional/manifest.json), [checks](../../evidence/assessment/20261119T034356Z-b3-functional/checks/results.json), [CSV](functional/test-cases.csv), [ảnh reset](../../evidence/assessment/20261119T034356Z-b3-functional/screenshots/password-reset-success.png), [email đã che](../../evidence/assessment/20261119T034356Z-b3-functional/screenshots/sat-ticket-email-redacted.png) | 329 PASS/3 FAIL/2 BLOCKED/3 NOT_RUN; ảnh email đã che là derivative | Video demo **chưa có URL, duration hoặc access** trong manifest; ảnh QR gốc giữ private; X01–X03 NOT_RUN |
| B4 `20261119T043844Z-b4-preflight` | [Manifest](../../evidence/assessment/20261119T043844Z-b4-preflight/manifest.json), [checks](../../evidence/assessment/20261119T043844Z-b4-preflight/checks/results.json) | Preflight/34 test local, chưa PITR | Không có video DB restored/app; RPO/RTO null |
| B4/C1 `20261119T172832Z-b4-c1-preflight` | [Manifest](../../evidence/assessment/20261119T172832Z-b4-c1-preflight/manifest.json), [CSV](../../evidence/assessment/20261119T172832Z-b4-c1-preflight/metrics.csv), [charts](../../evidence/assessment/20261119T172832Z-b4-c1-preflight/charts/tasks-ec2-targets.svg) | Smoke chỉ đọc 4 mẫu | Có missing/delayed/over interval; không phải load/fault video |
| B5 `20261119T050938Z-b5-s3-restore` | [Manifest](../../evidence/assessment/20261119T050938Z-b5-s3-restore/manifest.json), [checks](../../evidence/assessment/20261119T050938Z-b5-s3-restore/checks/results.json), [cleanup](../../evidence/assessment/20261119T050938Z-b5-s3-restore/cleanup-manifest.json), [object images](../../evidence/assessment/20261119T050938Z-b5-s3-restore/images/restored.png) | S3 component PASS và cleanup key synthetic | Ảnh là object GET, không phải ảnh UI app restored; không có video tích hợp |
| C1/C3 `20261120-c3-live-readonly` | [Summary](../../evidence/assessment/20261120-c3-live-readonly/summary.md) | Collector smoke 3 mẫu, read-only | Raw CSV/manifest private; clock không đồng bộ; không có k6/video C3 |
| C2 `20261120T130757Z-c2-local` | [Manifest](../../evidence/assessment/20261120T130757Z-c2-local/manifest.json), [log](../../evidence/assessment/20261120T130757Z-c2-local/local-smoke.log) | Script test local | Không có AWS worker switch/SKIPPED/Brevo video |
| C3 | [Report](performance/load-report.md), [readiness](../../evidence/assessment/20261120T1432Z-c3-readiness/summary.md) | Gate/preflight | 5 bài AWS NOT_RUN; k6 CSV/summary/chart/video chưa có |
| C4 | [Report](performance/failover-report.md), [capacity](../../evidence/assessment/20261120-c4-capacity-recheck/summary.md), [Console observations](../../evidence/assessment/20261120T1455Z-c4-preparation/console-observations.md) | Read-only và local dry-run | Không có incident/rollback, metrics/video C4; ảnh Console chỉ là snapshot |
| C5 | [Readiness](../../evidence/assessment/20261120-c5-readiness/summary.md), [runbook](performance/fault-runbook.md#c5--rds-rồi-redis-failover-chưa-kích-hoạt) | RDS/Redis topology trước fault | Hai failover NOT_RUN; không có probe/video/role events sau fault |
| C6 `20261121-c6-readonly` | [Snapshot](../../evidence/assessment/20261121-c6-readonly/summary.md), [audit script](../../scripts/assessment/c6-audit.mjs) | Current health một thời điểm, link/hash audit | Clock runner stopped; không chứng minh baseline sau fault |

## Video cần bàn giao

| Video | Owner | Trạng thái | Để dùng làm bằng chứng cần |
|---|---|---|---|
| Demo B3 trên điện thoại thật, QR/check-in và role UI | Người 2/người cung cấp thiết bị | **MISSING** | URL kho nhóm, quyền xem, thời lượng, thiết bị/browser, run ID, mốc UTC và đối chiếu server audit |
| C3 Platform/Admission/scaling/recovery | Người 3 | **NOT_RUN** | Video có clock UTC, k6 run ID và các mốc ECS/ASG/ALB; kèm raw CSV/chart, không dùng video thay số đo |
| C4 compute AZ trước/during/sau và rollback | Người 3 | **NOT_RUN** | Target list đã che, timeline incident, target/placement/activity và probe nghiệp vụ |
| C5 RDS và Redis riêng | Người 3 | **NOT_RUN** | Events/role/AZ/DNS, reconnect, app/SQL probe và topology cuối từng bài |
| B4 PITR và B5 tích hợp app | Người 2 | **NOT_RUN** | DB/app private, marker/incident/ready UTC, UI/ảnh tốt-sai-phục hồi, cleanup |

Video/link chưa tồn tại thì để trống trong manifest tương lai, không tạo URL giả. Với clip có PII/QR/account, chỉ xuất bản bản đã che; bản gốc giữ private theo owner.
