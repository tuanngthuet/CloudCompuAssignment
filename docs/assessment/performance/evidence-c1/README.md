# C1 — Ảnh AWS Console do người dùng cung cấp

Ngày tiếp nhận: 19/11/2026. Nguồn: ảnh đính kèm trong cuộc trao đổi C1. Các file PNG trong thư mục này đã được che kín account, ARN, instance ID, endpoint và định danh vận hành bằng các vùng đen cố định. Hash SHA-256 bên dưới áp dụng cho **bản đã che**. Bản gốc và bảng đối chiếu hash nằm trong `.local/assessment/c1-originals/` (Git ignored), chỉ dùng để kiểm tra nội bộ. Thời điểm chụp chính xác của từng ảnh chưa được xác nhận; timestamp hiển thị trong UI chỉ là thời điểm cập nhật của màn hình tương ứng. Đây là minh chứng giao diện theo từng thời điểm, **không phải** CSV collector hoặc bằng chứng tải/scaling theo chuỗi thời gian.

| File | Nội dung | SHA-256 bản đã che |
|---|---|---|
| [01-ecs-services.png](./01-ecs-services.png) | Cluster và 3 services | `c9b3b52f00688ce5af0e8cbe26571d6bfc5d59b3e3d4d06b0ce094f6ae044b3d` |
| [02-ecs-tasks.png](./02-ecs-tasks.png) | Danh sách ECS tasks | `89c81fadc83be26339e68eb512807346f2caf599e775d1e88acd0d42872e102c` |
| [03-ecs-infrastructure-loading.png](./03-ecs-infrastructure-loading.png) | ECS infrastructure khi provider đang loading | `7b80146156dd8eb5371dedde9232b649868e3871cb4552583e14da782bed46b1` |
| [04-api-service.png](./04-api-service.png) | API service và ALB target health | `62029a7b3ed894e3acb56193c26aeac07bbdac1cd89f388a57e28efdae0fa459` |
| [05-api-service-metrics.png](./05-api-service-metrics.png) | Đồ thị ECS service trong Console | `bdd0735aecf5bba15738556b630ce3b1c90a120739a67141df2cdd9eaeb98842` |
| [06-asg-details.png](./06-asg-details.png) | ASG desired/min/max | `98b4f5b29b03771ed1a4607b3919b8cd1501d8395073ccea0a5db65ec5991079` |
| [07-asg-instances.png](./07-asg-instances.png) | ASG instances và AZ | `bd857b6d614e11619a4e4364a0ef5a787122a5724776cb444a22a39c02a6c458` |
| [08-asg-activity.png](./08-asg-activity.png) | Lịch sử scaling activity | `9520f50ed510cd07b5e9efd11c0a95ff83575a15b241fac6dc6fa702ae2cbfad` |
| [09-ecs-infrastructure-capacity.png](./09-ecs-infrastructure-capacity.png) | Provider, task count và RAM khả dụng trên 4 máy | `0cf1f713e624fdcf075177d2c1c8d018f5c71a49081b1ed0e905ba1375508413` |
| [10-ecs-container-instance.png](./10-ecs-container-instance.png) | Tài nguyên một container instance AZ 2b | `04a8de80f200b330d2d18b644221d9964dfb7277cf491d86a4a143b45897c148` |
| [11-rds-configuration.png](./11-rds-configuration.png) | RDS configuration, Multi-AZ và cấu hình DB | `d7e8105a39df92b6c89c61bc27f0b286a3bc6ca96138a338be88491d11fd9094` |
| [12-rds-backups.png](./12-rds-backups.png) | RDS backup retention và danh sách snapshot | `537a67523f71a429e4d20f829d5657f96c588bb2cdb5500621a90ada99c82aae` |
| [13-rds-metrics-core.png](./13-rds-metrics-core.png) | RDS connections, CPU và CPU credits | `35052ac34cdea829401a06c95fc75e255f63495f778234474dd3d4239dc5e16e` |
| [14-rds-metrics-resources.png](./14-rds-metrics-resources.png) | RDS memory, storage, I/O và network | `e40e2e6f80e1b758ede118f14b335c1edfbecd0b57b61d3cea6de80759042339` |
| [15-rds-service-quotas-denied.png](./15-rds-service-quotas-denied.png) | Service Quotas báo Access denied | `3bd0fb067325274fb66157ea08b58da46f2b4a76224b203e75e6e309f57bd126` |
| [16-rds-read-latency.png](./16-rds-read-latency.png) | ReadLatency trong Console, hai đơn vị hiển thị | `9485de6d42e444710b694a8e1f545cf3fc49e06b72ffbf760756b4a7d313f19e` |
| [17-rds-write-latency.png](./17-rds-write-latency.png) | WriteLatency trong Console, hai đơn vị hiển thị | `9fd1af8d8c6e53dac7fc3b6fe7a189ea5be63a0f9212d547b940ff91d91be3d2` |
| [18-redis-replication-group.png](./18-redis-replication-group.png) | Redis replication group và bảo mật | `921a10c1d70b7e426c6b8fcf5b4e9780b3912d0634f1bb12f054bbcc1189a90c` |
| [19-redis-nodes.png](./19-redis-nodes.png) | Hai node Redis và role tại thời điểm ảnh | `64e630d933405dc7f4e48e53bd33a5d8f798d2f88e7f6cd26f7111b4f5ba98cc` |
| [20-redis-node-metrics.png](./20-redis-node-metrics.png) | Dashboard metrics theo hai node Redis | `41917ca9ff0abcba2890729240c97ce046c4d6e51bafbdb1af64a9a91432df58` |

Các vùng che có thể ẩn một phần nội dung phụ, nhất là cột mô tả ASG activity; kết luận chi tiết trong báo cáo dựa trên bản gốc nội bộ. Kiểm tra lại mức độ được phép chia sẻ với nhóm trước khi xuất bản ra ngoài dự án. Quan sát và giới hạn diễn giải nằm trong [observability.md](../observability.md). AWS smoke/preflight thực tế vẫn `BLOCKED` hoặc `NOT_RUN`.
