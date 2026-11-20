# Bộ tổng hợp nghiệm thu LabSeat — C6

**Trạng thái ngày 21/11/2026: bàn giao có giới hạn, chưa nghiệm thu toàn bộ.** Đây là mục lục và điểm vào cho [báo cáo cuối](final-report.md), [ma trận truy vết](traceability-matrix.md), [mục lục evidence/video](evidence-index.md) và [mô tả PR nháp](pr-description.md). Kế hoạch gốc: [nghiệm thu 4 ngày](../sprints/ke-hoach-nghiem-thu-4-ngay.md#c6-tổng-hợp-nghiệm-thu-git-và-khôi-phục-trạng-thái-cuối).

| Nhóm | Chủ sở hữu | Nguồn chính | Tình trạng C6 đọc được |
|---|---|---|---|
| A1–A4 kiến trúc | Người 1 | [Inventory](architecture/inventory.md), [Hava](architecture/hava.md), [A3](architecture/a3/README.md), [A4](architecture/a4/README.md) | Tài liệu/bản vẽ có; A3 chưa Accepted, A4 chờ kết quả fault/restore |
| B1–B3 dữ liệu/chức năng | Người 2 | [Dataset](functional/dataset.md), [B1/B2 snapshot](../../evidence/assessment/b1b2-20261117a/summary.md), [B3](functional/report.md) và [CSV gốc](functional/test-cases.csv) | Snapshot có; session B2 hết hạn, B3 còn FAIL/BLOCKED/NOT_RUN |
| B4/B5 recovery | Người 2 | [Báo cáo](recovery/report.md), [PITR](recovery/rds-pitr.md), [S3](recovery/s3-restore.md) | PITR chưa chạy; S3 component PASS, tích hợp app/DB chưa chạy |
| C1–C5 tải/fault | Người 3 | [C1/C2](performance/runbook.md), [C3](performance/load-report.md), [C4/C5](performance/failover-report.md) | Script và preflight có; bài AWS tải/fault/failover còn BLOCKED/NOT_RUN |

Đọc `BLOCKED` là thiếu gate/bằng chứng; `NOT_RUN` là chưa thực thi bài; `FAIL` là phép kiểm đã chạy nhưng không đạt. Một PASS local, một ảnh Console hoặc health 200 không chứng minh PASS bài AWS.

## Cách truy vết và tái tạo

1. Bắt đầu ở [ma trận](traceability-matrix.md), mở báo cáo owner và evidence cùng dòng. So khớp run ID, loại môi trường, source commit, app digest/schema, mốc UTC, thao tác, status và cleanup. Không ghép nhiều run thành một phép đo.
2. Chạy `node scripts/assessment/c6-audit.mjs` từ root repo để kiểm **hash các file được liệt kê trong 5 manifest, link Markdown tương đối và số dòng status B3**. Kết quả ngày 21/11 sau khi thêm tài liệu C6: 19/19 hash, 379/379 link tồn tại trong workspace, CSV B3 329 PASS/3 FAIL/2 BLOCKED/3 NOT_RUN. Hash khớp chứng minh toàn vẹn file, không chứng minh một bài AWS đã chạy.
3. Với lượt mới, dùng runbook của owner và manifest private `.local/assessment/<run-id>/`; chỉ phát hành tổng hợp đã che. Manifest private chứa ID, command/config, source commit, image digest/schema, mốc UTC, raw CSV/JSON và hash; **chưa có manifest private hoàn chỉnh cho các bài AWS C3–C5 chưa chạy**. Người nhận cần được bàn giao qua kênh riêng, không đưa session/token/password/raw AWS state vào Git.
4. [Snapshot C6 ngày 21/11](../../evidence/assessment/20261121-c6-readonly/summary.md) chỉ đọc được một phần baseline hiện tại. Clock runner không đồng bộ và không có run hậu fault; không dùng snapshot này để xác nhận rollback/scale-in hay RTO.

**Giới hạn nhánh hiện tại:** một số tài liệu/evidence A4 và B1–B5 là tệp untracked được sao chép từ bàn giao, chưa nằm trong commit nhánh `assessment/load-resilience`. Link tương đối ở đây mở được trong workspace hiện tại; PR/merge cần đưa đúng commit/nhánh của Người 1 và Người 2 vào nhánh đích trước khi coi bộ link trên Git là hoàn chỉnh. C6 không tự stage/commit chúng. Xem [mục lục evidence](evidence-index.md) và [mô tả PR](pr-description.md).
