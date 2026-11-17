# Capacity và connection budget

Default EC2 t3.small: 2 vCPU/2GiB. Agent dành riêng 384MiB OS/runtime. Mỗi API/worker/publisher/one-off task khai báo 256 CPU units, hard memory512MiB. CPU lý thuyết 8 task, memory tối đa3 task trước overhead bổ sung; awsvpc ENI thực tế có thể chỉ còn2 task/instance khi không bật trunking. Không bật/trông chờ trunking mặc định. Kiểm số ENI/agent registered/remainingResources trên AWS trước nghiệm thu; task memory phải đo lại với image detection/OpenCV và upload đồng thời.

Hai instances ban đầu có thể chỉ đặt được4 task: API2+worker1+publisher1. Migration/smoke hoặc rollout cần Capacity Provider tăng thêm instance. ASG2/2/6, targetCapacity80 không bảo đảm dư ENI. Tối đa6 instance x2 task ≈12 slots giả định: API8+background2 còn2 slots cho migration hoặc từng bước rolling. 100/200 cho phép overlap tối đa gấp đôi nhưng không đòi đặt toàn bộ gấp đôi ngay; peak/background overlap hoặc drain có thể chạm trần và stall. Không cam kết max8 sẽ luôn triển khai được; đo rồi tăng ASG max/instance type hoặc giảm API max, giữ budget DB. t3.medium tăng RAM nhưng không tự bảo đảm nhiều ENI hơn.

Budget bảo thủ, kể cả số task được phép overlap:

```
ceil(API max8 × maximumPercent200/100) × 1 Uvicorn × (business2 + counter1) = 48
+ worker2 (rolling) × pool1                                  = 2
+ publisher2 (rolling) × pool1                               = 2
+ reserve12 (migration/smoke pool3 + operator/monitor/system) = 12
= 64 + maintenance1 = 65 <= configured budget66
```

Terraform từ chối ASG khi tổng vượt budget. Reserve12 giả định chỉ một migration/smoke đang chạy; không chạy hai deploy cùng môi trường. Kiểm `SHOW max_connections`, RDS DatabaseConnections và `scripts/tests/pool-budget.sql` bằng role thích hợp trong VPC. Budget66 là yêu cầu phải xác minh, không phải kết quả đo RDS micro. Redis pool4/API process; rolling ceiling16API →64 app clients cộng operator/monitor.

Capacity Provider là chủ duy nhất của EC2 scaling; Terraform ignore desired ASG. Service scaling là lớp riêng, Terraform ignore service desired và task definition do CLI deploy quản lý. Không phải lần tăng ECS task nào cũng tăng EC2. Managed termination protection/ASG scale-in protection và managed draining được bật; deployment circuit breaker không sửa được thiếu ENI/capacity.

Tham chiếu: [ECS managed scaling behavior](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-scaling-behavior.html). Đây là capacity planning, chưa phải bằng chứng placement/scale thật.

API budget3 chia hai connection nghiệp vụ và một durable rate counter; không phát sinh connection ngoài budget. Worker/publisher/maintenance pool1; maintenance không tạo counter engine. Tổng rolling worst-case65/66, reserve12 vẫn cần đo với RDS max_connections thật.
