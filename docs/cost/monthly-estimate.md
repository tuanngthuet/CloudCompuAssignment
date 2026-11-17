# Lập dự toán chi phí LABSEAT

Dự toán phải dùng region, cấu hình và giá thực tại thời điểm triển khai; repository không chứa hóa đơn hoặc quote đã xác minh. Không tính credits vào chi phí vận hành chuẩn.

| Hạng mục | Đầu vào cần đưa vào dự toán |
|---|---|
| ECS/EC2 | ASG min/desired 2, max 6; loại instance demo t3.small, production t3.medium; giờ chạy, CPU credits và EBS gp3 |
| Network | ALB/LCU, public IPv4, NAT gateway theo AZ, NAT bytes, inter-AZ/Internet transfer; S3 gateway endpoint |
| PostgreSQL | RDS PostgreSQL 16, instance/storage/IOPS, Single-AZ hoặc Multi-AZ, backup/snapshot/restore |
| Redis | Demo EC2 với EBS/build AMI hoặc managed node; production managed replica và dữ liệu truyền |
| Storage/image | S3 dung lượng/requests và ECR image/storage/transfer |
| Background/email | SQS requests/retention/DLQ và gói transactional email Brevo theo lưu lượng thực |
| Monitoring | CloudWatch logs/retention/metrics/alarms/Container Insights, SNS |
| Vận hành | Domain, support, thuế, ngân sách restore/load test và dự phòng tăng tải |

Dùng AWS Pricing Calculator cho hạ tầng và trang giá tài khoản Brevo cho email; ghi ngày, region, currency, số giờ/tháng và các assumptions trong bản dự toán được phê duyệt. So sánh ít nhất steady-state desired 2, scaling tới max 6 và production HA. Không coi cấu hình autoscaling max là số máy luôn hoạt động.

Production cần network hai NAT (cấu hình network state riêng), RDS Multi-AZ và managed Redis replica. Ngân sách DB/ENI/task đặt trong [capacity](../deployment/capacity.md); thay cấu hình phải kiểm lại cả giá và khả năng placement. AWS Budgets/Cost Explorer được kiểm sau khi có deployment thật.
