# Bàn giao để đóng A4

| Chủ sở hữu | Task | Đầu ra cần bổ sung |
|---|---|---|
| Người 3 | C4 | Run ID, mục tiêu fault compute/AZ, incident UTC, events, metric/probe trước–trong–sau, tác động request, rollback và thời điểm ổn định |
| Người 3 | C5 | Run riêng RDS và Redis: thời điểm failover, role/endpoint/events trước–sau, hành vi app, lỗi/retry, invariant và kết thúc ổn định |
| Người 3 | C6 | Chuỗi metrics cùng timeline, baseline sau thử nghiệm, đối chiếu tài nguyên/config, kết luận và hạn chế |
| Người 2 | B4 | Sau bàn giao ổn định: marker nguồn, PITR vào DB identifier mới, DB/app private riêng, cùng digest/schema, invariant DB restored và kiểm nghiệp vụ |
| Người 2 | B5 tích hợp | Lượt mới trên app restored: DB reference, ảnh tốt/sai/phục hồi qua app, S3 version/hash/MIME/private/cache, cleanup chính xác |
| Người 2 | B3 sau thử nghiệm | Kết quả X01–X03 theo cửa sổ tải/fault/restore, không dùng PASS cũ thay kiểm lại |
| Người 1 | A4 | Gắn run/commit/hash mới, cập nhật sơ đồ thực tế, tính số đo từ record đủ kiểm chứng, ghi đạt/chưa đạt từng mục |

Theo kế hoạch bàn giao hiện tại: C4/C5 → xác nhận ổn định → B4 + B5 tích hợp → kiểm nghiệp vụ sau restore → đo RPO/RTO → tổng hợp A4. Tách cửa sổ tải/fault/restore. Không tự gây lỗi, restore hoặc thay cấu hình để lấp phần bằng chứng còn thiếu trong lượt viết A4.

C1 hỗ trợ quota/capacity trực tiếp cho B4; C3 hỗ trợ tải/scaling nhưng không thay C4/C5. Người 3 không làm app restored thay Người 2. Source của công cụ và test local PASS không thay kết quả AWS.

Mỗi lượt mới cần: owner, run_id, source commit, release digest/schema, region và định danh đã làm sạch, timestamps UTC, thao tác thực tế, checks/probes, metric source_at/status, cleanup/rollback, các phần NOT_RUN. Giữ secret, token, PII và connection string ngoài gói công khai.

## Làm rõ phạm vi sau đối chiếu Người 2

A4 là đầu ra tổng hợp theo sprint, không bổ sung test, điều kiện nghiệm thu hoặc output mới cho B3/B4/B5. Bằng chứng tiếp tục đặt trong thư mục run theo sprint và được dẫn từ ba output B3 hiện có; Người 1 dùng lại các nguồn đó.

Khi có cửa sổ thật, bàn giao run ID **và phase**, commit công cụ tách khỏi commit đóng gói tài liệu, digest/schema của app thực sự được kiểm, marker/incident/target/ready UTC, probe nghiệp vụ và invariants trước/sau, metrics có source_at/status, cleanup/rollback. Không lấy thời điểm gom báo cáo làm thời điểm mọi test.

Người 2 chịu trách nhiệm DB identifier mới, DB/app private riêng và kiểm DB/nghiệp vụ/ảnh; **không chuyển production sang DB restored**. Chỉ ghi ready khi toàn bộ DB, nghiệp vụ và ảnh B5 đã đạt, rồi dùng record hợp lệ cho measure.py. Thứ tự C4/C5 ổn định → B4/B5 tích hợp → B3 sau restore → đo đủ bằng chứng → cập nhật A4 giữ nguyên.

B5 tích hợp phải kiểm cùng object và DB reference qua app ở cả ba giai đoạn tốt/sai/phục hồi. Không dùng version đã cleanup hoặc sơ đồ A4 làm bằng chứng ảnh hiển thị qua app; không chạy lại S3 độc lập chỉ để phản hồi A4.

## Ưu tiên sau khi đọc ZIP mới 21/11

- Người 3 cập nhật số B3 trong C6 từ commit functional-recovery 54b034e: 333 PASS, 0 FAIL, 1 BLOCKED, 3 NOT_RUN. Không yêu cầu retest lại bốn mục local đã đạt.
- Người 3 giải quyết clock, session B2 còn hạn, cửa sổ email và gate capacity/API overlap, rồi thực hiện C3/C4/C5 theo kế hoạch; C6 cần baseline hậu thử nghiệm thực tế. Không dùng snapshot 5 EC2 hoặc healthy 200 thay kết quả.
- Người 2 còn V01 video và X01–X03 theo cửa sổ thực; B4/B5 tích hợp vẫn chờ bàn giao ổn định theo sprint. Email isolation B4 đi theo runbook B4, không thêm yêu cầu hoàn thành toàn bộ C2.
- Tích hợp đúng commit A/B/C vào nhánh đích, kiểm lại link/hash trên cây Git đã tracked; không coi link mở được nhờ file untracked là PR đã đầy đủ.
- Người 1 cập nhật kết luận observed khi có run thật. A4 hiện là bàn giao có giới hạn; chưa đổi sơ đồ planned thành nghiệm thu.
