# C4 preparation — local only

Mốc ghi: 2026-11-20 14:55 UTC theo clock runner; Windows Time trước đó báo chưa đồng bộ, nên mốc này **không** dùng để đo incident/RTO. Không có AWS mutation, fault hoặc rollback thật.

| Bước | Kết quả |
|---|---|
| Đọc kế hoạch, Terraform và B3/C1/C3 | ASG/ECS nguồn dùng hai app AZ, Capacity Provider managed scaling/draining/protection; snapshot 19/11 có API hai AZ nhưng ENI remaining thiếu, không xác nhận đủ slot AZ sống sót. C3 AWS NOT_RUN, B3 X02 NOT_RUN. |
| `./scripts/assessment/faults/test_local.ps1` | PASS với AWS giả **chỉ trong local test**: preflight tìm target API/EC2 và đối chiếu target healthy ở hai AZ; kiểm khả năng xếp task trên từng EC2, trường hợp tổng CPU/RAM đủ nhưng tài nguyên phân mảnh vẫn BLOCKED; prepare/inject từ chối attestation thiếu; inject từ chối ASG còn hai AZ; prepare và rollback dry-run. Không gọi AWS thật. |
| PowerShell parser cho scripts C4 | Không có syntax error; kiểm tra này không xác minh AWS CLI semantics hoặc hoạt động isolation thật. |
| AWS C4 preflight/prepare/inject/observe/rollback | NOT_RUN. AWS CLI profile chưa có ở lượt kiểm C3; clock chưa đồng bộ; các gate C3/B3/C2 và ENI còn thiếu. |

Không có incident timestamp, target EC2 được chốt, C1 metric CSV, B3 probe/invariant trong fault, video hoặc `ready_and_verified_at`. Trạng thái C4: **BLOCKED**. Xem [runbook](../../../docs/assessment/performance/fault-runbook.md) và [báo cáo](../../../docs/assessment/performance/failover-report.md).
