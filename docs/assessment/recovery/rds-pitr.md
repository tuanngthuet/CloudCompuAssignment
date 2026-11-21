# B4 — Quy trình PITR và công cụ

**Diễn tập NOT_RUN.** Đây là quy trình chuẩn bị theo [prompt B4](../../sprints/ke-hoach-nghiem-thu-4-ngay.md#b4-rds-pitr-và-đo-rporto), không phải biên bản restore thành công. Kết quả hiện tại: [preflight](preflight.md), [báo cáo](report.md).

## Trình tự khi đủ cửa sổ diễn tập

1. Nhận bàn giao sau fault ổn định; xác nhận không trùng tải/fault. Đọc lại account/region, restore window/quota/IAM/KMS/capacity và digest API.
2. Chuẩn bị DB mới, secret/role/network/cache riêng và app private cùng digest. Không dùng production ALB route, SQS, publisher/worker/maintenance hoặc mail thật. Chốt ID/run/owner vào manifest private.
3. Ghi marker synthetic mỗi phút bằng DB clock và giữ chứng cứ COMMIT; snapshot schema, counts/hash, constraints, ownership, vé/session của tập synthetic ổn định. Không truncate/reset hay thay dữ liệu người dùng.
4. Ghi incident_at có timezone là **sự cố giả định**, không phá nguồn hoặc tuyên bố downtime production. Chọn PITR target≤incident, trong restore window và bao phủ marker.
5. Restore DB instance identifier mới, private/encrypted, subnet/SG/parameter phù hợp. Ghi topology target rõ ràng; không suy cấu hình target từ source. Không đổi endpoint/secret production hoặc seed/migrate/reset restored DB.
6. Ghi riêng request/provisioning/DB available/app rollout. DB available chưa kết thúc RTO. Qua probe trong VPC, đối chiếu marker/schema/count/hash/constraints/ownership/vé và bảy invariants trước workflows mới.
7. Trên app restored kiểm login, vé/QR, hold→confirm→cancel và staff check-in đúng quyền; chạy lại invariants. Kiểm ảnh B5: version/hash/private access/DB reference/hiển thị thực; không suy từ put thành công.
8. Chỉ ghi ready_and_verified_at khi mọi kiểm chứng đạt. Lưu record đo và evidence đã che; vượt mục tiêu ghi FAIL. Sau đó cleanup đúng ID/tags và kiểm source/baseline; snapshot giữ lại phải ghi owner/chi phí.

## Collector và marker/snapshot

Collector AWS chỉ đọc được hướng dẫn trong [preflight.md](preflight.md#chạy-lại-collector). Các helper DB dưới đây lấy DATABASE_URL từ environment/secret; không in URL/password. Trên AWS chạy trong VPC cùng digest, đưa script qua kênh private có kiểm hash như công cụ B1/B2.

```powershell
python scripts/assessment/recovery/db_checks.py markers --expected-host SOURCE_HOST --run-id UUID_CUA_LUOT --samples 3 --interval 60 --output .local/b4-markers.json
python scripts/assessment/recovery/db_checks.py snapshot --expected-host DB_HOST --scope .local/b4-scope.json --output .local/b4-db-check.json
python scripts/assessment/recovery/db_checks.py verify-markers --expected-host RESTORED_HOST --record .local/b4-markers.json --incident-at INCIDENT_ISO8601 --output .local/b4-marker-check.json
python scripts/assessment/recovery/db_checks.py cleanup-markers --expected-host DB_HOST --record .local/b4-markers.json --output .local/b4-marker-cleanup.json
```

- `markers` và `cleanup-markers` mặc định plan-only; thêm `--execute` chỉ trong bước đã chốt. RDS host bắt buộc sslmode=verify-full.
- Marker dùng platform_events sẵn có, kind assessment_b4_marker, subject UUID/run, ID uuid5/sequence; published_at khác null nên publisher không gửi marker sang SQS. Mỗi mẫu transaction riêng, cách≥60giây. Planned IDs lưu trước khi ghi để cleanup xử lý cả crash sau COMMIT; không ghi đè manifest hoặc tái sử dụng ID đã commit. Cleanup giới hạn đúng ID/run/kind thuộc manifest.
- Scope JSON private có đủ sáu khóa users/events/rooms/seats/lab_sessions/reservations, mỗi khóa1..2000 UUID synthetic đã chốt. Chọn bản ghi ổn định, tránh tài khoản đang demo.
- Snapshot dùng REPEATABLE READ READ ONLY và bảy SELECT từ scripts/tests/db-invariants.sql; xuất schema/count/SHA256 của tập ID/cột đã chọn, constraint chưa validate và ownership. Ticket_code chỉ tham gia hash trong RAM; không xuất raw row/QR/profile/password. Hash không đại diện toàn DB/hồ sơ. So baseline theo PITR target trước workflows mới.
- Verify đối chiếu ID/timestamp với manifest nguồn, chỉ lấy marker được acknowledgment trước incident. Phân biệt cận trên RPO với timestamp commit chính xác theo [giới hạn đo](preflight.md#kiểm-db-nguồn); không tự tạo record hoàn thành.

## Builder PITR, ECS và cleanup

```powershell
python scripts/assessment/recovery/restore_plan.py --source-db .local/b4-source-db.json --config .local/b4-restore-config.json --output .local/b4-restore-plan.json
python scripts/assessment/recovery/app_plan.py --source-task .local/b4-source-task.json --config .local/b4-app-config.json --output .local/b4-app-plan.json
python scripts/assessment/recovery/restore_plan.py --cleanup-db-state .local/b4-restored-db-current.json --existing-plan .local/b4-restore-plan.json --output .local/b4-db-cleanup-plan.json
```

Source DB/task lấy từ AWS describe; tất cả input/output giữ private. Builder chỉ viết JSON, **không submit AWS request**.

| Config | Trường bắt buộc / giới hạn |
|---|---|
| Restore | run_id UUID, target_db labseat-b4-*, owner, incident_at, restore_time, earliest_restorable_time, security_groups riêng, multi_az boolean |
| App | run_id cùng lượt DB, family labseat-b4-*, taskRoleArn/executionRoleArn riêng, region, cluster, bucket, prefix assessment/b4/RUN/, subnets, security_groups, secrets |
| App secrets | Đúng năm SSM ARN riêng: DATABASE_URL, REDIS_URL, REDIS_USERNAME, REDIS_PASSWORD, REDIS_CA_CERT |

Restore builder giữ class/storage/subnet/parameter nguồn, target private khác source; kiểm time/window và topology target chọn rõ. App builder giữ immutable API digest, chỉ uvicorn API; bỏ inherited command/env/secrets/sidecar/mounts, không mang SQS/Brevo/background services; mail disabled.

Trước submit phải xác minh secret resolve đúng endpoint restored/cache riêng; IAM giới hạn đúng SSM/S3 prefix test và không dùng production queues; SG/route/egress/ENI/capacity và logging/probe transport thực. App private HTTP có COOKIE_SECURE=false chỉ cho task tạm; không đổi production. Prefix storage riêng cần B5 chuẩn bị object/version và DB reference phù hợp, không tự có ảnh nguồn.

Submit riêng restore_input/register_task_input/run_task_input, không submit wrapper. Sau register pin revision ARN mới vào run input, không dùng family latest. Chưa có ID/role/secret/network live hoặc deployment thật trong đầu ra này.

Cleanup builder yêu cầu target đúng manifest, khác source, đúng run/owner tags và không deletion-protected. Nó chỉ xuất delete input cho DB tạm, skip final snapshot/delete automated backups, không tự xóa. Đọc lại account/region/state/tags ngay trước thực thi, giữ evidence và dừng app trước. Task/role/secret/cache/SG/object test phải dọn riêng theo manifest; không dò/xóa tài nguyên ngoài phạm vi.

## Đo RPO/RTO

Record thật theo scripts/recovery/measure.py gồm incident_at, ready_and_verified_at, latest_recovered_commit_at (ISO8601 có timezone, latest≤incident≤ready), database_invariants_passed, images_verified và evidence_paths. Không lấy LatestRestorableTime làm commit marker hoặc DB available làm ready-and-verified.

```powershell
python scripts/recovery/measure.py .local/recovery-record.json
```

RPO=incident−commit mới nhất phục hồi được trước incident, mục tiêu≤900giây; RTO=ready-and-verified−incident, mục tiêu≤3600giây. Ghi cả chuẩn bị/provisioning/rollout/verification/cleanup, không loại thời gian trong cửa sổ đo để làm đẹp số liệu. Hiện chưa có record đo thật.

Nguồn API: [AWS RDS PITR](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PIT.html), [AWS CLI PITR](https://docs.aws.amazon.com/cli/latest/reference/rds/restore-db-instance-to-point-in-time.html). Kết quả test công cụ xem [report.md](report.md#kiểm-chứng-công-cụ).

## Áp dụng bàn giao người1 vào môi trường kiểm chứng B4

Nguồn và timestamp tại [preflight — bàn giao người1](preflight.md#bổ-sung-từ-bàn-giao-người1-trên-main). Các yêu cầu dưới là kế hoạch cho tài nguyên recovery, chưa được apply lên AWS:

- Dùng app private subnet đã kiểm làm cơ sở chọn vị trí probe/app; DB restored trong DB subnet phù hợp, private/encrypted. Tạo SG recovery riêng: app nhận8000 từ SG probe; DB nhận5432 từ SG app recovery; cache riêng nhận6379 từ SG app recovery. SG app production của A1 chỉ nhận8000 từ ALB nên không mặc định dùng lại cho probe private. Giữ egress/TLS/S3 endpoint phù hợp, không gắn production ALB.
- Tách execution role lấy đúng secret/ECR và task role chỉ đọc/ghi prefix ảnh test. Có route S3 và policy TLS không chứng minh role có quyền; kiểm URL DB, TLS Redis/ACL, prefix/storage và SSM injection thực trước workflows.
- A3 xác nhận DB là nguồn bền vững cho vé; clone DB không phục hồi lease/epoch/PubSub trong Redis. Kiểm admission/recovery generation trên cache/DB restored riêng trước hold; không dùng Redis production để làm bài restored app có vẻ chạy được.
- Dữ liệu restored có thể chứa pending outbox/email jobs từ source. Không chạy publisher/worker/maintenance của môi trường restored với SQS/Brevo production. Giữ mail disabled; xác minh DB commit/ownership/ticket và workflow thực, không lấy healthz/readyz200 làm ready_and_verified_at.
- Với B5, ghi actual room/event image reference và resolved S3 key từ đúng prefix app kiểm chứng; dùng HTTPS và private access, lưu version/hash trước ghi đè. Noncurrent lifecycle30 ngày có thể loại version cũ; chọn version thực sự còn tồn tại, kiểm app và DB reference rồi mới chốt images_verified.

B1/B2 dataset và các lượt B3/B4 đã ghi trước đó được giữ nguyên. Việc bổ sung A1/A2/A3 không chạy lại seed, không đổi tiêu chí và không thay NOT_RUN thành PASS cho PITR, app restored hay RPO/RTO.
