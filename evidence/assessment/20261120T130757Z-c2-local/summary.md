# C2 — kiểm thử script local

Run ID: `20261120T130757Z-c2-local`. Chủ sở hữu: Người 3. Nguồn: nhánh `assessment/load-resilience`, HEAD `7fa878ac7e7995c25777680e44fe2da36d1e619c` cùng thay đổi working tree; SHA-256 của `scripts/load/booking.js` ở manifest.

`node scripts/load/booking.test.mjs`: **7 PASS, 0 FAIL**. Các trường hợp: cookie/CSRF/seat và không login ở chế độ session; login/CSRF cũ ở chế độ credentials; từ chối credentials trùng user; từ chối session hết hạn; từ chối token trùng; xác minh user riêng qua `/me`; từ chối hai token thuộc cùng user. `node --check scripts/load/booking.js`: exit 0. [Log](local-smoke.log) là mô phỏng HTTP local, không có token B2 thật hoặc request tới AWS.

**C2 tổng thể BLOCKED.** Không có k6 trong PATH, AWS CLI profile hoặc file session B2 mới trên máy này. Chưa chuyển worker, chưa chạy booking smoke trên AWS, chưa kiểm job `SKIPPED`/Brevo, chưa khôi phục baseline. B1/B2 báo 100 session cũ đã hết hạn. Các bước còn lại và điều kiện dừng ở [runbook](../../../docs/assessment/performance/runbook.md#c2--cửa-sổ-worker-disabled--restore).
