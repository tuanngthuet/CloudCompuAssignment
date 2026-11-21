# C4 — Báo cáo diễn tập mất compute ứng dụng một AZ

**Kết luận: BLOCKED.** [Preflight AWS CLI chỉ đọc ban đầu](../../../evidence/assessment/20261120-c4-cli-preflight/summary.md) và [kiểm lại capacity hai AZ](../../../evidence/assessment/20261120-c4-capacity-recheck/summary.md) đã chạy đúng account/region. Chưa chuẩn bị isolation trên AWS, chưa stop EC2, chưa chạy probe fault/rollback và chưa có recovery time. Không tuyên bố mất toàn AZ hoặc phục hồi ứng dụng. C3 trong [báo cáo tải](load-report.md) còn năm bài AWS NOT_RUN; [B3](../functional/report.md) X02 sau fault NOT_RUN. ASG từng từ 4 lên 5 rồi trở về 4 EC2; mọi snapshot cũ không dùng để chọn target. [Runbook C4](fault-runbook.md) và [bộ script C4](../../../scripts/assessment/faults/) đã chuẩn bị nhưng các gate inject còn thiếu.

AWS ASG Activity cho thấy desired 4→5 do ECS managed scaling lúc 15:40:16Z, sau đó 5→4 lúc 16:15:32Z; tiếp theo có launch/termination để cân bằng AZ. Đây là activity tự động trước C4, không phải fault/recovery C4. [Evidence rút gọn](../../../evidence/assessment/20261120-c4-capacity-recheck/summary.md).

[Evidence chuẩn bị local](../../../evidence/assessment/20261120T1455Z-c4-preparation/summary.md) ghi rõ test với AWS giả và các phase chưa chạy; không dùng làm bằng chứng failover.

## Trạng thái từng phase

| Phase | Điều kiện đầu vào | Thực tế | Evidence | Trạng thái |
|---|---|---|---|---|
| Baseline/preflight | C3 kết thúc và app ổn định; B3 probe; C2 email disabled; clock/AWS profile; capacity AZ còn lại đủ CPU/RAM/ENI/IP **và một API overlap**, DB budget | Preflight mới: ASG desired 4, hai EC2 mỗi AZ, API target khỏe ở cả hai AZ. Fallback ENI từ EC2 cho máy không trunk cho phép xếp task mất: 2a→2b 1/1, 2b→2a 3/3. **Cả hai hướng `survivor_api_overlap=BLOCKED`** vì không còn thêm slot API sau thay. Clock chưa đồng bộ, C3/B3/C2/window/quyền rollback chưa hoàn tất. | [Capacity recheck](../../../evidence/assessment/20261120-c4-capacity-recheck/summary.md), [C3 readiness](../../../evidence/assessment/20261120-c3-live-readonly/summary.md) | BLOCKED |
| Prepare isolation | Lưu ASG subnet/processes, ECS constraints/tasks; hạn chế replacement về AZ sống sót, không chuyển task trước inject | Chưa chạy; chưa chứng minh ASG subnet update giữ nguyên task/EC2 ở AZ mục tiêu | Không có baseline/prepared C4 | NOT_RUN |
| Inject | Dry-run target list chốt, đối chiếu live ID/AZ/ASG; stop đồng thời đúng EC2 mục tiêu | Không stop EC2 | Không có incident/StopInstances response | NOT_RUN |
| Observe | Collector, HTTP nhẹ, B3 probe/invariants, task/target/ASG timeline UTC, video | Không có metrics/CSV/video C4 | Không có | NOT_RUN |
| Rollback | ASG subnets, ECS constraints, suspended processes, capacity tạm và phân bố hai AZ trở lại baseline | Không có thay đổi C4 để rollback; chưa chứng minh baseline sau fault | Không có final snapshot | NOT_RUN |

## Phân tách kết luận

- **Correctness:** chưa có probe và bảy invariant trước/trong/sau C4; NOT_RUN.
- **Availability/failover:** chưa có incident và mốc `ready_and_verified_at`; NOT_RUN. Health 200 của C3 readiness không phải evidence C4.
- **Placement/auto replacement:** chưa có target list hiện tại, ASG replacement ở AZ còn lại hoặc task/ALB traffic sau fault; NOT_RUN.
- **Recovery/baseline:** chưa khôi phục hoặc đối chiếu hai AZ sau fault; NOT_RUN.

## Việc tiếp theo

1. Chốt cửa sổ C4 sau C3, B3, C2; sửa clock và cấu hình AWS profile đúng account/region, quyền read và rollback.
2. [Preflight.ps1](../../../scripts/assessment/faults/preflight.ps1) đã chạy chỉ đọc ở cả hai hướng AZ, dùng số interface EC2 gắn thực tế và giới hạn loại máy khi ECS thiếu ENI/trunk. Cả hai hướng thiếu **một API overlap**. Chuẩn bị capacity AZ sống sót theo change record, trong ASG max6, rồi chạy lại baseline đúng cửa sổ C4; xác minh placement/ENI/IP/DB và ASG activity. Không dùng target list trong snapshot cũ.
3. Thử prepare isolation từng bước theo [runbook](fault-runbook.md), kiểm không có task/EC2 bị chuyển trước inject. Nếu không bảo đảm, rollback và giữ C4 BLOCKED.
4. Chỉ khi gate PASS mới inject, observe và rollback, ghi timeline/metrics/probe/video cùng run ID. Kết luận PASS chỉ khi app phục hồi ở AZ còn lại và hai AZ trở về baseline.

Raw AWS state của preflight được giữ trong `.local/assessment/` (Git ignore); bản evidence công khai chỉ có số tổng hợp và hash. Không tạo session/credential mới. Tài liệu và script C4 đã được push trong commit `c12a252`; việc push không phải bằng chứng nghiệm thu C4.

## C5 — RDS và Redis failover

**Kết luận: BLOCKED; RDS inject NOT_RUN; Redis inject NOT_RUN.** [Preflight C5 chỉ đọc](../../../evidence/assessment/20261120-c5-readiness/summary.md) xác nhận loại tài nguyên và topology tại snapshot, không có tác động failover. [C4](fault-runbook.md) chưa inject/rollback và chưa có bằng chứng baseline hai AZ sau diễn tập; [C3](load-report.md) còn năm bài AWS NOT_RUN. Windows Time trên runner không chạy, B3 probe/invariants và C2 mail window chưa được xác nhận trong cửa sổ C5. Không dùng snapshot `available` hay ECS rollout hoàn tất để vượt gate.

| Bài | Baseline read-only | Inject/observe | Business/SQL sau fault | Cấu hình cuối đã kiểm | Kết luận |
|---|---|---|---|---|---|
| RDS Multi-AZ DB instance | `available`, `MultiAZ=true`, không thuộc DB cluster, primary AZ `ap-southeast-2b`; hai Events backup trong 24 giờ | Không gọi `reboot-db-instance`; không có outage, DNS/reconnect hoặc timeline fault | NOT_RUN | Chỉ snapshot trước fault, không có topology hậu fault | BLOCKED / NOT_RUN |
| Redis replication group | `available`, Multi-AZ/automatic failover enabled; node group `0001`, primary `ap-southeast-2a`, replica `ap-southeast-2b`; Events replication group 24 giờ trả rỗng | Không gọi `test-failover`; quota toàn account chưa xác minh; không có events chuyển role | NOT_RUN | Chỉ snapshot trước fault | BLOCKED / NOT_RUN |

Không có CSV/chart/video hoặc RTO C5; không điền số giả. Chạy lại [runbook C5](fault-runbook.md#c5--rds-rồi-redis-failover-chưa-kích-hoạt) khi C4 và các gate được chứng minh đạt, rồi cập nhật mỗi hàng bằng evidence run riêng.
