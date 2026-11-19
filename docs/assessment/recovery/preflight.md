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
