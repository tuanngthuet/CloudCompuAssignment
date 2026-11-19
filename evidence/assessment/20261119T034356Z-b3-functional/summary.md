# B3 — Tóm tắt bằng chứng

Task B3 của Người 2; dữ liệu B1/B2, AWS LABSEAT và regression disposable được phân biệt trong CSV. Run ID `20261119T034356Z-b3-functional` là lần gom đầu ra, không phải lần chạy lại toàn bộ test.

- Ma trận: 329 PASS, 3 FAIL, 3 NOT_RUN, 2 BLOCKED.
- Toàn suite regression lịch sử: 275 PASS, 15 SKIP; API AWS 33 PASS; browser AWS 5 PASS; controller offline 39 PASS. Không dùng PASS local thay cho AWS.
- Quyền UI ba vai/sai lịch SAT đã bổ sung. Mail cửa sổ Brevo thật: hai thư DELIVERED và người nhận xác nhận Inbox; reset/login bằng mật khẩu tự chọn được người nhận xác nhận, session cũ revoked/challenge consumed. Email đã tắt lại.
- Bảy invariants zero rows trong các lần đo đã ghi; C3/C4/C5/B4/B5 chưa có lịch nên X01–X03 vẫn NOT_RUN.
- Ảnh reset đã nhận. Ảnh email QR nguyên bản private; không public QR vé chưa check-in. Video chờ người dùng cung cấp, V01 BLOCKED; chưa có link kho nhóm/thời lượng/quyền truy cập để nghiệm thu.

Xem [report.md](../../../docs/assessment/functional/report.md), [test-cases.csv](../../../docs/assessment/functional/test-cases.csv), [demo-script.md](../../../docs/assessment/functional/demo-script.md). Chưa chốt toàn bộ B3.

Lượt optional bổ sung đã chạy: 11 mục PASS; avatar/map/camera FAIL, profile BLOCKED (fixture). Chi tiết và repro trong report/results.json; không coi là lỗi critical runtime đã được xác nhận, cũng không coi B3 đã hoàn tất. Chỉ dùng môi trường disposable, không tác động AWS.
