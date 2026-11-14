# W1-TV2 — Triển khai và giám sát LabSeat

TV2 chuẩn bị tầng chạy ứng dụng theo contract v3. Mạng và security group do TV1 bàn giao. TV3 bàn giao instance profile, cấu hình kết nối và mã định danh RDS. TV4 cung cấp bản phát hành ứng dụng. Hai module Terraform nhận các giá trị đó qua biến đầu vào.

## Thiết kế

- ALB công khai chuyển lưu lượng đến FastAPI trên cổng `8000` của các EC2 private. Target group dùng `/healthz` để kiểm tiến trình. Runbook kiểm `/readyz` riêng trên app thật để xác nhận kết nối DB. ASG dùng `t3.small`, đặt `min/desired/max = 2/2/4` khi khởi tạo và dùng EBS gp3 20 GB mã hóa.
- AMI chứa runtime và app theo phiên bản. Launch Template dùng phiên bản số, ASG chạy instance refresh khi cấu hình thay đổi. Runtime nhận cấu hình môi trường qua Parameter Store bằng instance profile. Khi ghép app thật, TV3 và TV4 chạy migration một lần trước refresh.
- Chính sách target tracking khởi điểm ở 300 yêu cầu trên mỗi target mỗi phút, với warmup 120 giây lấy từ ASG. Dashboard theo dõi lưu lượng, số target khỏe, p95 phản hồi target, 5xx của ALB và app, CPU, dung lượng ASG và kết nối RDS. Log ứng dụng dùng nhóm `/labseat/lab/app` với thời gian lưu 7 ngày. Một alarm riêng gửi SNS khi lưu lượng vượt 300 yêu cầu trên mỗi target trong cả hai kỳ 60 giây.

## Kiểm tra trong tuần và bàn giao

Gói W1 gồm hai module Terraform, runtime `systemd`, bộ tạo AMI, fixture kiểm tra health và runbook tích hợp. Manifest [`handoff/tv2.json`](../../handoff/tv2.json) ghi phiên bản gói, đầu vào cần nối, kết quả kiểm tra đã chạy và đường dẫn bằng chứng nếu có. Kiểm tra fixture đánh giá tiến trình mẫu, kiểm tra Terraform đánh giá cấu hình của module.

## Chờ tích hợp và nghiệm thu G1

| Kiểm chứng trên AWS | Trạng thái | Bằng chứng cần thu |
|---|---|---|
| Ghép đầu vào thật, build AMI từ release TV4 và triển khai qua ALB | Chờ tích hợp | Mã phiên bản release, AMI, phiên bản Launch Template, kết quả triển khai |
| Hai EC2 private cùng phiên bản app thật, cả hai target `Healthy`, app kết nối DB | Chờ tích hợp | Target health, phiên bản từng máy, `/readyz` và kết quả E2E |
| Giám sát hoạt động và email đăng ký SNS được xác nhận | Chờ tích hợp | Dashboard có metric, log stream từ từng máy và trạng thái subscription |

## Kế hoạch kiểm chứng tuần 2

Khi nhóm chốt baseline G1, TV2 chuẩn bị k6 trên local, sau đó chạy từ ngoài ASG trong buổi chung để kiểm chứng tăng tự động từ 2 lên ít nhất 3 target khỏe, alarm vào `ALARM` và email SNS tương ứng. Hồ sơ đo ghi VU, RPS, thời lượng, phiên bản, p95, tỷ lệ 5xx và tách riêng phản hồi 409. Mục tiêu là p95 dưới 1 giây và 5xx dưới 1% tại mức tải đã công bố. Sau khi dừng tải, nhóm kiểm thử thay một EC2 và ghi thời điểm target mới trở lại `Healthy`, cùng kết quả kiểm vé, phiên và ảnh trước và sau. Rollback AMI áp dụng khi phiên bản app cũ tương thích schema hiện tại.
