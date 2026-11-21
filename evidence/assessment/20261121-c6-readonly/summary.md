# C6 — snapshot AWS chỉ đọc, ngày 21/11/2026

AWS CLI `tv2-compute`, region `ap-southeast-2`: STS khớp account dự kiến (ID không đưa vào gói này). Windows Time trả `The service has not been started (0x80070426)`. Vì clock runner không đồng bộ, ngày là ngày phiên làm việc; **không có timestamp UTC đủ tin cậy để tính RTO hoặc ghép chính xác các API call**. Các API describe chạy tuần tự/theo nhóm, không phải snapshot nguyên tử. Không có lệnh tạo/sửa/xóa AWS.

| Nguồn đọc | Quan sát | Giới hạn |
|---|---|---|
| ECS `describe-services` | API 2/2, worker 1/1, publisher 1/1; pending 0; mỗi service có PRIMARY rollout COMPLETED | Chưa đối chiếu task digest, placement và request stream trong cùng run |
| ASG `describe-auto-scaling-groups` | min/desired/max **2/5/6**; 5 EC2 Healthy/InService, AZ 2a:3, 2b:2; không có suspended process | Desired 5 khác snapshot 4 ngày 20/11; không gọi đây là scale-in sau C3/C4, không chứng minh EC2 đăng ký ECS hoặc cấu hình subnet/constraint đã hoàn tác |
| ALB `describe-target-health` | Hai API target healthy, mỗi AZ một target | Chưa kiểm request distribution hoặc healthy liên tục |
| RDS `describe-db-instances` | `available`, Multi-AZ DB instance, AZ hiện tại 2b, không có pending modifications trong response chọn lọc | Không có failover C5 hay PITR; DB connections/budget và marker sau fault chưa đo |
| Redis `describe-replication-groups` | `available`, Multi-AZ/automatic failover enabled; primary 2a, replica 2b, node group 0001 | Không có event/probe failover C5 hay kiểm ACL/lease/PubSub trong run |
| Worker task definition | Service trỏ revision 10; `EMAIL_BACKEND=disabled`, `APP_ENV=production` trong task definition | Chưa đối chiếu từng running task/digest, job synthetic `SKIPPED`, Brevo attempt hoặc restore C2 |
| SQS `get-queue-attributes` | Queue và DLQ đều 0 visible, 0 not-visible, 0 delayed tại lần đọc | Số gần đúng một thời điểm; không chứng minh không còn job synthetic có thể gửi sau restore hoặc delivery thành công |

**Kết luận:** một số thành phần đang healthy tại lượt đọc, nhưng baseline cuối sau C3/C4/C5/B4/B5 **chưa thể xác nhận** vì các bài đó chưa chạy đủ và không có manifest/timeline hậu thử nghiệm. Không có video hoặc invariant SQL cùng cửa sổ. Không đổi ASG desired hay worker để tạo trạng thái mong muốn.
