# Load scenarios

[Runbook](../../docs/testing/load-test.md). `catalogue.js` kiểm tải danh sách; `booking.js` kiểm đăng nhập, admission, hold, confirm/cancel; `ecs-scaling.js` tạo tải cho demo hai tầng scaling. Chỉ chạy trên host được phép với dữ liệu synthetic. Kết quả local không xác minh AWS autoscaling.

`platform.js`:100 VU slots,30 request/s mục tiêu,15 phút; p95 đọc500ms/ghi1s, lỗi<1%. Xem yêu cầu dữ liệu và session private trong runbook.
