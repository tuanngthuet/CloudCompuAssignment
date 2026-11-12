# Báo cáo TV1 tuần 1

Package: W1-TV1 1.0.0, contract 3.0. Mục tiêu là hoàn thiện cấu hình mạng/S3 state độc lập để tích hợp cuối tuần. Tác giả triển khai có AI hỗ trợ tạo mã, tài liệu và kiểm tra local; TV1 phải đọc, chạy lại và giải thích được thiết kế.

## Đã chuẩn bị

Module network 2 AZ/6 subnet, IGW, 1 NAT, S3 gateway endpoint cho app và ba SG theo tầng. App chỉ nhận 8000 từ ALB, DB chỉ nhận 5432 từ app; không SSH public. Bootstrap state có versioning, AES256, Block Public Access và TLS-only. Root dùng account guard, backend S3 lockfile. Không tạo app, compute, RDS hoặc IAM của owner khác.

Đã có hướng dẫn Windows và triển khai/teardown cuối tuần. Xem evidence/validation.txt để biết chính xác kiểm tra nào đã chạy. Mock tests không phải AWS thật.

## Trạng thái

Định dạng và init provider đã đạt. Validate và mock test bị chặn vì môi trường không cho provider mở Unix socket; chưa thể nhận kiểm tra tĩnh đầy đủ đạt.

Code candidate để review, chưa Accepted. Gói chưa xác nhận toàn bộ tiêu chí Ready vì credit/quota/quyền thực chưa kiểm chứng. G1 chưa kiểm chứng. Không có AWS plan/apply/SSM/E2E thật; outputs ID thật chưa có. PowerShell script cần chạy lại trên máy Windows của TV1.

## Còn lại

TV1 phối hợp chủ tài khoản kiểm root MFA, quyền, credit, budget, quota và CLI auth; kiểm CIDR trước apply. TV2 review package; deploy mạng, đưa IDs thật cho TV2/TV3 và kiểm private/routing khi tích hợp. Hoàn thiện bảng chi phí bằng giá/usage thực, không dùng giả định làm evidence.

## Tiến độ cuối kỳ

M4 nộp báo cáo/code/video: 23/11/2026. M5 bảo vệ: 30/11/2026. Lịch tuần trong tài liệu là khung; nhóm chốt buổi tích hợp phù hợp hai mốc đã điều chỉnh.
