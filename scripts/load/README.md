# Load scenarios

[Runbook](../../docs/testing/load-test.md). `catalogue.js` kiểm tải danh sách; `booking.js` kiểm đăng nhập, admission, hold, confirm/cancel; `ecs-scaling.js` tạo tải cho demo hai tầng scaling. Chỉ chạy trên host được phép với dữ liệu synthetic. Kết quả local không xác minh AWS autoscaling.

`platform.js`:100 VU slots,30 request/s mục tiêu,15 phút; p95 đọc500ms/ghi1s, lỗi<1%. Xem yêu cầu dữ liệu và session private trong runbook.

`booking.js` có hai chế độ: `SESSIONS_FILE` dùng phiên synthetic B2 được cấp sẵn, hoặc `ACCOUNTS_FILE` đăng nhập như trước khi không truyền file session. Chế độ session cần `SESSION_EXPIRES_AT` là hạn sớm nhất có timezone từ manifest B2 (hoặc `expires_at` cho từng bản ghi), đủ cho `DURATION` cộng 5 phút. Mỗi VU dùng một token riêng; script kiểm `/me`, CSRF và `seat_id`. File private không đưa vào Git. Xem [quy trình C2](../../docs/assessment/performance/runbook.md#c2--chuẩn-bị-session-và-smoke-script).
