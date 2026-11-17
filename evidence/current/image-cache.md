# Cache ảnh công khai — production 17/11/2026

Release: `ecs-0.6.0-image-cache-20261117T060424Z`. API/publisher/worker rollout COMPLETED; deployment driver đã hoàn tất migration idempotent, exact-release DB smoke và maintenance dry-run, ghi last-good release.

Ảnh đại diện ca và sơ đồ đã công bố trả `Cache-Control: public, max-age=86400` khi `v` khớp file ảnh hiện tại. URL thay đổi khi thay ảnh. URL không có/sai phiên bản, preview qua `key`, response lỗi và dữ liệu nghiệp vụ giữ `no-store`; các route có policy riêng vẫn giữ policy đó. Không thêm Redis hoặc CDN.

Kiểm tra local: 24 tests đạt (cache policy, health, storage/input); 4 tests cache đạt thêm trong image release đã build. Kiểm tra HTTP production: 10 trường hợp đạt, gồm hai ảnh versioned, URL không version/sai version, preview, danh sách ca, availability, truy cập hồ sơ chưa đăng nhập và ảnh không tồn tại. Xem [kết quả HTTP](image-cache-verification.json).

Ca demo vẫn có 25 phòng, mỗi phòng 45 suất, tổng 1.125 suất. Đây là kiểm chứng cấu hình HTTP, chưa phải benchmark hoặc bằng chứng browser cache hit. Lần tải đầu vẫn đi qua API/S3; lượt truy cập lại có thể dùng cache trình duyệt nếu còn fresh. Reload cưỡng bức hoặc tắt cache trong DevTools có thể vẫn tạo request mạng.
