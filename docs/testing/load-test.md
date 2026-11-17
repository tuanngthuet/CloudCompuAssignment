# Hai tầng autoscaling — AWS acceptance pending

Chỉ chạy trên môi trường synthetic được phép. AWS load test chưa được nghiệm thu. Trước khi tạo tải, kiểm API min2, ASG min2, healthy targets2, same image digest/schema, queue policy và dependency readiness. Load runner ở ngoài ASG.

```bash
k6 run -e BASE_URL=https://APPROVED_HOST -e VUS=60 \
  --summary-export=.local/k6-ecs.json scripts/load/ecs-scaling.js
# Nghiệp vụ và queue: accounts synthetic/profile đủ, ca practice và capacity phù hợp
k6 run -e BASE_URL=https://APPROVED_HOST -e SESSION_ID=SYNTHETIC_SESSION \
  -e ACCOUNTS_FILE=/PRIVATE/synthetic-accounts.json scripts/load/booking.js
```

Ramp2m/3m + hold15m cho thời gian ECS scaling, EC2 boot và ALB healthy; số VU/threshold phải tune từ dữ liệu. Không manual tăng desired để làm bằng chứng autoscale. Theo dõi song song (AWS_PROFILE/AWS_REGION phải explicit):

```bash
aws ecs describe-services --cluster CLUSTER --services API WORKER PUBLISHER
aws ecs list-container-instances --cluster CLUSTER
aws ecs describe-container-instances --cluster CLUSTER --container-instances INSTANCE_ARNS
aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names ASG
aws autoscaling describe-scaling-activities --auto-scaling-group-name ASG
aws application-autoscaling describe-scaling-activities --service-namespace ecs
aws elbv2 describe-target-health --target-group-arn TARGET_GROUP
```

Lưu snapshot theo timestamp mỗi15–30s, CloudWatch ECS CPU/memory/PendingTaskCount/RunningTaskCount, CapacityProviderReservation, ASG desired/inservice, ALB targethealth/requests/5xx/latency và RDS connections. Tiêu chí:

1. ECS target-tracking tự nâng API desired từ2 lên ít nhất3.
2. Dùng hết capacity thực tế theo ENI/memory khiến task provisioning/pending. Ghi registered/remainingResources chứng minh thiếu capacity, không chỉ đo CPU.
3. Capacity Provider tự nâng ASG desired và số EC2 in-service; activity và instance registration khớp timestamp.
4. Task mới đúng image thành healthy IP targets. Không lỗi dependency/đúng queue epochs.
5. Request logs từ nhiều API CloudWatch streams chứng minh traffic phân phối; không dựa vào tổng200 đơn thuần. RequestCountPerTarget/các metrics ALB hỗ trợ đối chiếu.
6. Alarm workload thật chuyển ALARM và SNS subscription đã xác nhận nhận notification. Không dùng SNS publish/manual desired thay bằng chứng.

[Capacity budget](../deployment/capacity.md) áp dụng cả rolling tasks. Nếu min80 target tạo sẵn EC2 thứ3 trước tải, ghi baseline thật; phải tiếp tục tạo tải đủ để thể hiện một lần tăng EC2 tự động nữa. Nếu tài nguyên vẫn đủ, task tăng không bắt buộc EC2 tăng: chưa đạt demo hai tầng, không claim pass. Dừng khi vượt connection budget/correctness gates hoặc unexpected5xx; ghi med/p95/p99, throughput, held/confirm/cancel, conflicts dự kiến, queue wait/grants riêng. Restore/failover tests và autoscale phải tách cửa sổ thời gian để phân tích.


## Bài nghiệm thu platform

`platform.js` cấp100 VU slots (60 đọc +40 ghi), giữ15 phút:24 request đọc/s và2 workflow/s gồm hold-confirm-cancel (6 request ghi/s), tổng30 request/s khi workflow hoàn tất. Yêu cầu100 tài khoản synthetic khác nhau đã xác minh email, đăng nhập trước, còn session ít nhất20 phút; ca mở đăng kí và chưa bắt đầu trong toàn bộ bài đo, capacity đủ và admission tắt. Giữ file private `{session_token,csrf_token,seat_id}` ngoài git; không dùng tài khoản/hồ sơ thật. Việc xác minh không bị bypass trong ứng dụng. Tải queue có bài `booking.js` riêng.

```bash
k6 run -e BASE_URL=https://APPROVED_HOST -e SESSION_ID=SYNTHETIC_SESSION \
  -e SESSIONS_FILE=/PRIVATE/synthetic-sessions.json \
  --summary-export=.local/platform-load.json scripts/load/platform.js
```

Gate: p95 đọc<500ms, ghi<1s, unexpected errors<1%, dropped iterations=0. Ghi actual RPS và workflow counts: nếu lỗi làm bỏ confirm/cancel thì không được gọi đó là30RPS đã đạt. Warm-up/session preparation tách khỏi15 phút đo;100 slots là mức concurrency cấu hình, không chứng minh100 request luôn đang xử lí đồng thời. Đo thêm saturation/fault cases khi cần. Không chạy k6 trên môi trường phục vụ thật trong lượt implement; chưa có số production được đo.
