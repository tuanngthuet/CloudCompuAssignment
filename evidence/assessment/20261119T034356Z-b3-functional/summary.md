# B3 — Tóm tắt bằng chứng

Task B3 của Người 2; dữ liệu B1/B2, AWS LABSEAT và regression disposable được phân biệt trong CSV. Run ID `20261119T034356Z-b3-functional` là lần gom đầu ra, không phải lần chạy lại toàn bộ test.

- Ma trận sau retest21/11: 341 PASS, 0 FAIL, 2 NOT_RUN, 1 BLOCKED (344 dòng).
- Toàn suite regression lịch sử: 275 PASS, 15 SKIP; API AWS 33 PASS; browser AWS 5 PASS; controller offline 39 PASS. Không dùng PASS local thay cho AWS.
- Quyền UI ba vai/sai lịch SAT đã bổ sung. Mail cửa sổ Brevo thật: hai thư DELIVERED và người nhận xác nhận Inbox; reset/login bằng mật khẩu tự chọn được người nhận xác nhận, session cũ revoked/challenge consumed. Email đã tắt lại.
- Bảy invariants zero rows trong các lần đo đã ghi; X01 PASS sau cửa sổ tảiAWS21/11 và recovery30phút;10bảng demo/7invariants đạt. Scaling60 performanceFAIL không bị đổi thànhPASS; X02–X03 vẫn NOT_RUN.
- Ảnh reset đã nhận. Ảnh email QR nguyên bản private; không public QR vé chưa check-in. Video chờ người dùng cung cấp, V01 BLOCKED; chưa có link kho nhóm/thời lượng/quyền truy cập để nghiệm thu.

Xem [report.md](../../../docs/assessment/functional/report.md), [test-cases.csv](../../../docs/assessment/functional/test-cases.csv), [demo-script.md](../../../docs/assessment/functional/demo-script.md). Chưa chốt toàn bộ B3.

Lượt optional ngày19/11 có avatar/map/camera FAIL, profile BLOCKED (fixture). Retest21/11 đã sửa thiết lập/kỳ vọng test và đạt34/34 test: avatar5, camera19, map5, profile5. Bảy invariants read-only zero rows;7 container và network nội bộ đã dọn. Kết quả lịch sử giữ nguyên ở remaining_regression, kết quả mới ở regression_retest_20261121 trong checks/results.json. Không có runtime release/AWS/email thật/ảnh/video mới; B3 còn V01 và X02–X03.

Bổ sung7case AWS trên SAT demo có sẵn ngày21/11: hold/confirm/cancel/replay/QR/CSV/staff lookup/race cuối và khôi phục remaining; cleanup45vé thử, không đổi cấu hình/vé gốc. Sáu ca B2 WEB và ca tải Vật lý cũ đã thu hồi.
