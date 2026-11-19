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
