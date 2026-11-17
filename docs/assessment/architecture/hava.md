# A2 — Sơ đồ Hava của LabSeat

## 1. Phạm vi và nguồn dữ liệu

- Người thực hiện: TV1 — Người 1.
- Ngày tổng hợp: 17/11/2026.
- Nguồn Hava: LabSeat-AWS.
- Môi trường hạ tầng: labseat-lab-vpc.
- Môi trường container: labseat-lab.
- Region: ap-southeast-2 (Sydney).
- VPC: vpc-03a9cc66ccf66cf5a.
- CIDR: 10.20.0.0/16.
- Kết nối: IAM cross-account role HavaReadOnly-LabSeat.
- Policy đã gắn khi tạo role: ReadOnlyAccess.
- Last imported: chưa ghi nhận lại chính xác.
- Thời điểm đọc Last imported: chưa ghi nhận.

Hava đã hiển thị nguồn được import và sơ đồ của đúng VPC LabSeat.
Không sử dụng các môi trường AWS Demo làm bằng chứng.

## 2. Danh mục ảnh

Các đường dẫn dưới đây cần khớp với tên file thực tế trong repo.

| View | Đường dẫn ảnh | Ghi chú |
|---|---|---|
| Infrastructure | diagrams/a2-hava-infrastructure.png | Tổng quan hạ tầng |
| Extended Infrastructure | diagrams/a2-hava-extended.jpg | Chữ nhỏ; cần ảnh phóng to khi đọc thông số |
| Security Group | diagrams/a2-hava-security-group.png | Đọc được các cổng và quan hệ SG |
| Container | diagrams/a2-hava-container.jpg | Ảnh tổng quan hẹp; cần ảnh rõ hơn để đọc nhãn |

- Hình thức bằng chứng: ảnh chụp màn hình Hava.
- Chưa có bản export PDF/PNG trực tiếp được xác nhận.
- Thời điểm chụp chính xác từng ảnh: chưa ghi nhận.
- Giữ nguyên watermark Hava.
- Không dùng ảnh vẽ lại bằng AI làm bằng chứng Hava.
- Đuôi file phải đúng định dạng ảnh; không đổi JPEG thành PNG chỉ bằng cách đổi tên.

## 3. Kết quả quan sát và đối chiếu A1

### 3.1. Infrastructure và Extended Infrastructure

- Đã đối chiếu đúng VPC, CIDR và region với A1.
- Sơ đồ thể hiện hai AZ: ap-southeast-2a và ap-southeast-2b.
- Mỗi AZ có ba subnet: public, app và DB; tổng cộng sáu subnet.
- Nhận diện được IGW, ALB và hai NAT tại hai public subnet.
- Có biểu tượng S3 endpoint, Redis và PostgreSQL/RDS.
- Số lượng và vị trí EC2 cần đối chiếu theo thời điểm import thực tế.
  Không suy số máy chỉ từ biểu tượng được nhóm.
- Hai biểu tượng PostgreSQL không tự chứng minh có hai database độc lập. A1 ghi nhận một RDS instance cấu hình Multi-AZ.

### 3.2. Security Group

| Luồng được phép | Cổng |
|---|---|
| Internet → ALB | TCP 80, 443 |
| ALB → App | TCP 8000 |
| App → DB | TCP 5432 |
| App → Redis | TCP 6379 |
| App → Internet | TCP 80, 443 |
| Redis SG → Internet | TCP 443 |

- Các luồng chính khớp Security Group đã đọc trong A1.
- Mũi tên ALL thuộc egress của default SG; không có nghĩa toàn bộ tài nguyên đều mở mọi cổng.
- Chưa xác nhận tài nguyên nào đang sử dụng default SG.
- Sơ đồ thể hiện quyền cho phép, không chứng minh lưu lượng thực tế hoặc kiểm thử kết nối đã thành công.

### 3.3. Container

- View đã chụp thể hiện cluster labseat-lab.
- Quan sát được API 2 task, publisher 1 task và worker 1 task.
- Số lượng hiển thị khớp snapshot A1 theo tỷ lệ 2/1/1.
- Không khẳng định snapshot A1 và Hava được lấy đồng thời.
- Chưa suy ra health, image digest hoặc placement EC2/AZ chỉ từ ảnh Container; các thuộc tính đó tham chiếu bằng chứng A1.

## 4. Phạm vi hiển thị và giới hạn

| Nhóm tài nguyên | Mức độ quan sát trên ảnh |
|---|---|
| VPC, AZ, subnet | Nhìn thấy trên Infrastructure/Extended |
| IGW, NAT, ALB | Nhận diện được trên sơ đồ hạ tầng |
| EC2 | Có biểu tượng; số lượng/placement cần kiểm tra thêm |
| RDS, Redis | Có biểu tượng; thông số chi tiết đối chiếu A1 |
| S3 endpoint | Có biểu tượng trên sơ đồ hạ tầng |
| Security Group | Có view riêng và cổng truy cập |
| ECS services/tasks | Có view Container |
| S3 bucket, SQS/DLQ | Chưa nhận diện đầy đủ trong các ảnh |
| IAM, SSM | Chưa nhận diện đầy đủ trong các ảnh |
| CloudWatch, SNS, maintenance | Chưa nhận diện đầy đủ trong các ảnh |

Không xuất hiện trên các ảnh đã chụp không có nghĩa tài nguyên không tồn tại hoặc Hava không hỗ trợ. Cần kiểm tra view, bộ lọc, quyền import và dữ liệu nguồn trước khi kết luận.

Monthly Estimate hiển thị trên Hava là ước tính của công cụ, không phải hóa đơn AWS hoặc số credit thực tế đã tiêu thụ.

## 5. Nguồn đối chiếu A1

Tham chiếu inventory.md và bằng chứng gốc:

- R1: 20261117T103450Z-A1-200da2.
- R2: 20261117T122731Z-A1-a2a64a.
- Truy vấn ASG bổ sung: thời điểm chính xác chưa được ghi nhận.

Các snapshot phản ánh từng thời điểm riêng. Nếu tài nguyên thay đổi giữa A1 và lúc Hava import, ghi nhận sai khác cùng timestamp, không sửa bằng chứng cũ để làm chúng trùng nhau.

## 6. Trạng thái bàn giao A2

Đã kết nối Hava với AWS nhóm và thu được ảnh của bốn view: Infrastructure, Extended Infrastructure, Security Group và Container.
- Last imported trên Hava: 36 minutes ago.
- Thời điểm đọc Last imported: 11:37 PM 17/11/2026.
- Thời gian chụp ảnh: 11:37 PM 17/11/2026.

Còn cần hoàn thiện:
A2 ghi nhận sơ đồ và phạm vi hiển thị, không thay thế kiểm thử tải, autoscaling, failover, restore hoặc nghiệm thu nghiệp vụ.