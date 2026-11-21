# C5 — snapshot readiness chỉ đọc ngày 20/11/2026

Nguồn: AWS CLI profile `tv2-compute`, region `ap-southeast-2`; STS khớp account dự kiến (giữ ID private). Runner Windows Time trả `The service has not been started (0x80070426)`, nên **không dùng giờ local làm mốc UTC/RTO**. Lệnh CLI chỉ đọc đã chạy: `sts get-caller-identity`, `rds describe-db-instances`, `rds describe-events --duration 1440`, `elasticache describe-replication-groups`, `elasticache describe-events --duration 1440`, `ecs describe-services`. Không chạy API mutate/failover.

| Gate | Quan sát thật | Trạng thái |
|---|---|---|
| RDS type | Một PostgreSQL DB instance `available`, `MultiAZ=true`, `DBClusterIdentifier=null`, AZ hiện tại `ap-southeast-2b`, không có pending modifications trong response chọn lọc | PASS tại snapshot; kiểm lại ngay trước run |
| RDS events | Hai event backup ở 13:25:08.672Z và 13:27:41.105Z ngày 20/11; không có event failover trong response 24 giờ | PASS cho truy cập Events, không phải bằng chứng failover |
| Redis topology | Replication group `available`, Multi-AZ và automatic failover enabled; node group `0001` available, primary 2a, replica 2b | PASS tại snapshot; kiểm lại ngay trước run |
| Redis event/quota | `describe-events` cho replication group trong 24 giờ trả `[]`; không có audit/account-wide quota hoặc CloudTrail đủ để xác nhận số test failover còn lại | BLOCKED cho quota |
| ECS service | API 2/2, worker 1/1, publisher 1/1; pending 0; PRIMARY rollout COMPLETED | PASS tại snapshot; digest, target, queue và nghiệp vụ chưa kiểm |
| C4/C3/C2/B3 | C4 chưa inject/rollback; C3 năm bài AWS NOT_RUN; C2 SKIPPED/Brevo chưa chốt; B3 X02/X03 chưa chạy cùng window | BLOCKED |
| Clock, business probe, SQL | Windows Time stopped; chưa có probe/marker/invariants ngay trước và sau C5 | BLOCKED |

**Quyết định:** RDS `reboot-db-instance --force-failover` NOT_RUN; Redis `test-failover` NOT_RUN. Không có metrics/probe/video fault, thời gian phục hồi hoặc topology sau fault. Đây chỉ là bằng chứng readiness, không phải PASS C5. Xem [runbook](../../../docs/assessment/performance/fault-runbook.md#c5--rds-rồi-redis-failover-chưa-kích-hoạt) và [báo cáo](../../../docs/assessment/performance/failover-report.md#c5--rds-và-redis-failover).
