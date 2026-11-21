# Timeline bằng chứng — lịch sử và cập nhật 21/11

Các mốc thuộc hai lượt độc lập; không phải timeline một sự cố toàn hệ thống. B3 run ID là thời điểm gom báo cáo, không dùng làm thời điểm tất cả test.

| UTC | Việt Nam (UTC+7) | Sự kiện |
|---|---|---|
| 2026-11-19T05:09:38.739+00:00 | 2026-11-19T12:09:38.739+07:00 | B5 bắt đầu lượt độc lập |
| 2026-11-19T05:09:49.248+00:00 | 2026-11-19T12:09:49.248+07:00 | B5 before |
| 2026-11-19T05:09:53.296+00:00 | 2026-11-19T12:09:53.296+07:00 | B5 overwritten |
| 2026-11-19T05:09:56.503+00:00 | 2026-11-19T12:09:56.503+07:00 | B5 restored |
| 2026-11-19T05:10:04.533+00:00 | 2026-11-19T12:10:04.533+07:00 | B5 kết thúc, gồm cleanup |
| 2026-11-19T05:15:03.216+00:00 | 2026-11-19T12:15:03.216+07:00 | Kiểm cleanup chỉ đọc: vẫn trống |
| 2026-11-19T17:28:32.683+00:00 | 2026-11-20T00:28:32.683+07:00 | C1 preflight bổ sung cho B4 |
| 2026-11-19T17:29:15.732+00:00 | 2026-11-20T00:29:15.732+07:00 | Mẫu collector đầu |
| 2026-11-19T17:29:35.882+00:00 | 2026-11-20T00:29:35.882+07:00 | SQL nguồn: budget/invariants |
| 2026-11-19T17:30:46.516+00:00 | 2026-11-20T00:30:46.516+07:00 | Mẫu collector cuối |
| 2026-11-19T17:33:50.533+00:00 | 2026-11-20T00:33:50.533+07:00 | Quota/capacity bổ sung |

Nguồn: [B5](evidence/20261119T050938Z-b5-s3-restore/checks/results.json) và [C1/B4](evidence/20261119T172832Z-b4-c1-preflight/checks/results.json). Các mốc stage là timestamp ghi nhận trong JSON, không phải thời điểm người dùng bắt đầu mất dịch vụ.

## Ghi nhận đối chiếu tài liệu 20/11/2026

Người 2 xác nhận timeline S3 phù hợp timestamp JSON gốc; bản hiển thị chỉ giữ millisecond. Lượt đối chiếu tài liệu không có timestamp thực thi AWS mới, nên không chèn thành sự kiện incident/restore vào bảng trên. Commit A4 được đối chiếu là `39f7ab1cd3cdd925e55fae5c13b0a6a541e8fa3a`, tách biệt commit test và digest runtime.

## Cập nhật từ hai nhánh mới ngày 21/11

| Nguồn/mốc | Sự kiện | Giới hạn |
|---|---|---|
| B3 retest bắt đầu 20/11 17:38:05.692824 UTC (21/11 00:38:05.692824 Việt Nam) | Lượt local disposable; 34 test cuối đạt | Không phải clock cho phép đo AWS availability/RTO |
| AWS Activity 20/11 15:40:16Z | Managed scaling yêu cầu desired 4→5 | Không có C3 tải hoặc C4 inject trong lượt này |
| AWS Activity 20/11 16:15:32Z | Managed scaling yêu cầu 5→4 | Không gọi là recovery C4 |
| AWS Activity 20/11 16:17:22Z / 16:17:32Z | Launch/termination cân bằng AZ | Không ghép thành incident/rollback |
| C5 readiness ngày phiên 20/11 | Đọc RDS/Redis/ECS | Clock runner chưa đồng bộ; không gán UTC chính xác |
| C6 ngày phiên 21/11 | ASG 5 máy, 3 ở 2a và 2 ở 2b | Không có mốc UTC tin cậy cho toàn snapshot hoặc baseline hậu fault |

Nguồn pin commit tại [evidence-review.md](evidence-review.md). Không ép thứ tự các snapshot bằng clock runner chưa đồng bộ; không nội suy incident/ready hoặc đo RTO từ các ngày phiên. Các mốc S3 ở bảng lịch sử giữ nguyên.
