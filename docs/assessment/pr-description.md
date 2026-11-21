# Nội dung PR nháp — tổng hợp C6 LabSeat

## Mục đích

Tổng hợp nghiệm thu 4 ngày theo [README](README.md), [báo cáo cuối](final-report.md), [ma trận](traceability-matrix.md) và [evidence/video index](evidence-index.md). Bản này ghi trạng thái thật và owner của phần thiếu, **chưa đề nghị đánh PASS toàn bộ**.

## Thay đổi trong phạm vi Người 3

- Thêm báo cáo C6, ma trận 17 nhóm yêu cầu, evidence/video index và snapshot AWS chỉ đọc ngày 21/11.
- Thêm `scripts/assessment/c6-audit.mjs` để kiểm hash manifest, link tương đối và số status B3; không gọi AWS hoặc đọc secret.
- Cập nhật runbook/báo cáo C4/C5 đang có trong working tree: C5 chỉ preflight, failover thật chưa chạy.

## Kết quả xác minh

- `node scripts/assessment/c6-audit.mjs`: 19/19 file được liệt kê trong 5 manifest khớp SHA-256; 379/379 link tương đối sau khi thêm tài liệu C6; B3 329 PASS/3 FAIL/2 BLOCKED/3 NOT_RUN. Chạy lại sau khi tích hợp nhánh A/B.
- AWS CLI read-only: ECS 2 API + 1 worker + 1 publisher running, ASG desired 5 với 5 Healthy/InService, hai ALB targets healthy ở hai AZ, RDS/Redis available, queue/DLQ xấp xỉ 0. [Chi tiết và giới hạn](../../evidence/assessment/20261121-c6-readonly/summary.md).
- Windows Time chưa chạy; snapshot không tạo timeline UTC hoặc chứng minh rollback/chi phí. C3–C5 và B4/B5 tích hợp vẫn thiếu bài thật.

## Phụ thuộc và giới hạn merge

- Nhiều file A4/B1–B5 từ bàn giao đang **untracked trên nhánh `assessment/load-resilience`**. PR của Người 3 chỉ nên stage/commit tài liệu và script thuộc phạm vi mình; tích hợp commit Người 1/Người 2 ở nhánh đích rồi chạy lại audit/link. Không tự commit bản sao B hoặc tài liệu A4.
- C3 năm bài AWS, C4 compute AZ, C5 RDS/Redis, B4 PITR, B5 qua app restored và B3 X01–X03 chưa có kết quả nghiệm thu. RPO/RTO chưa đo. Video B3 và các clip fault/load còn thiếu.
- C2 worker disabled trong snapshot không chứng minh job `SKIPPED` hoặc Brevo không gửi trong cửa sổ mới. Temporary resources và bill chưa được audit cuối kỳ.

## Checklist trước khi review/merge

- [ ] Owner A/B/C đối chiếu dòng mình trong [ma trận](traceability-matrix.md); sửa nguồn gốc ở nhánh của owner, không ghi đè lịch sử.
- [ ] Tích hợp đúng commit A4/B1–B5; `node scripts/assessment/c6-audit.mjs` pass sau tích hợp và mọi link mở trên PR.
- [ ] Chạy `git diff --check`, xem `git diff --cached --name-only` và staged diff; quét token/password/session/raw AWS/QR/PII; không dùng `git add .`.
- [ ] Bàn giao manifest/raw private qua kênh riêng cho người tái tạo, chỉ đưa bản sanitized vào Git.
- [ ] Sau các run còn thiếu, cập nhật evidence/CSV/chart/video, đối chiếu baseline cuối, cleanup/quota/chi phí và trạng thái thực; reviewer xác nhận trước khi đánh Accepted.

**PR nên ở trạng thái Draft** đến khi các phụ thuộc và gate trên được xử lý. Nội dung này là mô tả để người dùng dùng khi tạo PR; không có PR nào được tạo bởi lượt C6 này.
