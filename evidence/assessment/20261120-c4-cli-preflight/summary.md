# C4 — AWS CLI preflight chỉ đọc

Ngày chạy: 20/11/2026. Đồng hồ Windows **chưa đồng bộ** (`w32tm`: Leap Indicator 3, Stratum 0, Local CMOS Clock), nên `observed_at_utc` do runner ghi trong JSON không dùng để đo timeline/RTO. ASG activity bên dưới dùng timestamp do AWS trả về. Không có prepare, inject, rollback hay thay đổi AWS.

## Danh tính và phạm vi

- `aws sts get-caller-identity --profile tv2-compute --region ap-southeast-2`: account khớp LabSeat; không lưu credentials hoặc ARN người dùng trong repo.
- ECS API service có đúng một target group, running/desired = 2/2. Hai lần chạy `preflight.ps1` đọc STS, ASG, ECS, EC2, VPC subnet và ALB. Raw snapshot chỉ lưu trong `.local/assessment/c4-live-20261120/` (Git ignored).
- ASG ở hai snapshot: min 2, desired 5, max 6; 5 EC2 và 5 ECS container instances. Điều này **khác** ảnh Console trước đó (desired 4, 4 EC2). `describe-scaling-activities` trả một sự kiện Launching/Successful bắt đầu `2026-11-20T15:40:28.126Z`; chưa xác định nguyên nhân bằng chứng đầy đủ.
- Raw ASG activity 8 sự kiện lưu tại `.local/assessment/c4-live-20261120/asg-activity.private.json`, SHA-256 `1EC0DDA1A1E3A56D485D97C0E6803CB3119B65AE5C3BAD47782C7686CBAA1A5A`.

## Kết quả hai hướng AZ

| AZ mục tiêu | Target EC2/task | AZ còn lại | CPU/RAM còn lại theo ECS | Gate chính | Raw SHA-256 |
|---|---:|---|---:|---|---|
| 2a | 2 EC2, 1 API task | 2b: 3 EC2 | 5.376 CPU units / 3.051 MiB | Identity, EC2/ECS healthy, service stable, ALB healthy và API healthy ở hai AZ, provider→ASG, subnet IP, ASG limit: PASS. `exact_survivor_slots`: **BLOCKED** vì ECS không cung cấp `remainingResources.ENI`. | `32EE065A71C0F7545D2DBB246F00393D33FC5C390E556B6BFC44D1B01CFD3D74` |
| 2b | 3 EC2, 3 service tasks, gồm 1 API | 2a: 2 EC2 | 3.840 CPU units / 2.546 MiB | Cùng các gate PASS; `exact_survivor_slots`: **BLOCKED** vì thiếu ENI. | `9C58EF3E880D97979A1D59873930E0DB6D08D92CD1DFBBABBD5C8DD5966C27E0` |

Hai snapshot được đọc tuần tự, không phải một giao dịch nguyên tử. `survivor_remaining.eni=0` trong manifest là tổng mặc định khi nguồn ECS thiếu ENI, **không có nghĩa ENI thực tế bằng 0**. Không chọn AZ/EC2 để stop theo bảng này.

## Gate còn chặn thực hiện fault

- ENI/branch ENI hoặc task attachment capacity thực trên từng EC2 chưa xác minh; CPU/RAM cộng dồn không đủ chứng minh xếp được task. Cần kiểm placement thực và quota.
- Đồng hồ runner chưa đồng bộ; C3 trong báo cáo hiện còn AWS NOT_RUN; B3 probe/invariants và C2 email window chưa có evidence hoàn tất cho C4.
- Chưa xác minh không có fault/restore đồng thời, quyền prepare/inject/rollback và cửa sổ đã chốt. ASG vừa có thay đổi capacity so với ảnh; cần baseline ổn định mới.

**Kết luận: preflight đọc AWS đã thực hiện, inject vẫn BLOCKED.** Không có incident timestamp, fault metrics, video, RTO hoặc baseline sau rollback.
