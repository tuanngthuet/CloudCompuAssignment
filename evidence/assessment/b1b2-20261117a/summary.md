# Bằng chứng B1/B2 — b1b2-20261117a

Theo cấu trúc evidence trong kế hoạch sprint. Báo cáo chỉ chứa số liệu và UUID kỹ thuật; không có mật khẩu, token hoặc DATABASE_URL.

## 1. Nguồn và thời điểm

- Website: https://labseat.id.vn; AWS `ap-southeast-2`.
- Snapshot RDS: **21:57:08 ngày 18/11/2026, UTC+7**, giao dịch `REPEATABLE READ READ ONLY`.
- ECS audit task: `98c3ead9a9114155b31c3ff4d72a60c3`; log `/labseat/lab/app`, stream `api/app/98c3ead9a9114155b31c3ff4d72a60c3`.
- Đếm theo UUID của batch, vì tên event đã được người dùng đổi trên web.
- HTTP chỉ đọc cùng đợt: `/events`, sơ đồ/ảnh phòng, ảnh poster và seats của lịch.
- Đợt ghi tài liệu không seed, sửa lịch, cấp phiên hoặc chạy tải.

## 2. Kết quả B1 tại snapshot

| Kiểm tra | Kết quả |
| --- | --- |
| Student/admin/staff | 500 / 2 / 6; tất cả đã xác minh email |
| Event/lịch | 12 event: 6 exam, 6 practice; 24 lịch |
| Trạng thái event | 11 ACTIVE, 1 CANCELLED (Practice 10) |
| Reservation | 303: 300 CONFIRMED, 1 CHECKED_IN, 2 CANCELLED |
| Email job gắn đăng ký của tài khoản batch | 303 SKIPPED |
| Staff assignment | 6 phân công, 6 staff, 6 lịch được phủ |
| Invariants | 7 truy vấn trong `scripts/tests/db-invariants.sql` đều 0 dòng vi phạm |

Lượt seed ban đầu tạo 300 đăng ký (298 CONFIRMED, 1 CHECKED_IN, 1 CANCELLED). Lượt smoke đầu bổ sung một đăng ký hủy; tổng hiện tại đã thay đổi do thao tác demo. Không dùng tổng 300/301 của lịch sử làm tổng hiện hành.

## 3. Kết quả B2 tại snapshot

- Cả **12 ảnh sơ đồ và 12 poster trả HTTP 200**.
- Lịch đại diện mỗi ca khớp manifest về nhãn, `seat_id`, capacity và số vùng. Snapshot DB xác nhận hai lịch mỗi ca cùng số vùng/sức chứa.
- Số vùng Exam 01–Practice 12: `4, 5, 12, 11, 33, 11, 6, 20, 18, 4, 34, 42`.
- Chỗ/lịch tương ứng: `180, 225, 540, 495, 1485, 495, 270, 900, 810, 68, 1530, 1890`.
- Practice 10 bị loại khỏi `/events` công khai vì CANCELLED; không phải mất dữ liệu hoặc thiếu ảnh.
- 100 fixture session thuộc 100 user riêng; **0 còn hiệu lực**. Hạn từ 04:26:46 đến 04:28:24 ngày 18/11/2026, UTC+7. Không chạy smoke đọc/ghi mới với gói đã hết hạn.

## 4. Bằng chứng kiểm thử và triển khai trước snapshot

- PostgreSQL 17 disposable với schema `0002_platform`: đã kiểm seed, tạo 100 phiên, booking qua service, chạy lại không nhân đôi, 7 invariants và cleanup bộ nền.
- Các stage tùy chỉnh ảnh đã kiểm riêng giữ ID/mã QR/trạng thái vé và chạy lại không tăng revision; các lần giảm/gỡ vùng có guard bảo vệ lịch sử đặt chỗ.
- Các stage áp dụng cấu hình cuối của Practice 07–12:

| Ca | Stage | ECS task |
| --- | --- | --- |
| Practice 07 | bio-map | `b9fdcdb7182f44e7af0541df6385d2d2` |
| Practice 08 | com | `b9fe42323e514a8bafe0078947a06d07` |
| Practice 09 | elec | `039216f8d8884c15904165e0d43a17e0` |
| Practice 10 | mechanic | `adfce21b85e3407daf498df2e4677018` |
| Practice 11 | physics | `70ed03933f3849cba735f564c5c99c60` |
| Practice 12 | chemistry | `3b9b5f1f2950470dbbf888824c9a752a` |

Ảnh poster/sơ đồ của từng stage được đối chiếu SHA-256 với preview sau khi áp dụng. Đây là kiểm tra artifact/DB/API, không thay thế bằng chứng luồng admin upload/nhận diện cho B2.

## 5. Giới hạn kết luận

Giới hạn snapshot18/11: chưa kiểm lại seed/cleanup sau tùy chỉnh, guard/SQL phụ thuộc tên và smoke hard-code vùng. Những lỗi công cụ này đã được sửa/kiểm local21/11 như bên dưới; không ghi ngược là đã chạy lại AWS. Bộ6 ảnh mạng mới chưa usable/upload, phiên AWS cũ vẫn hết hạn, fixture đúng cửa sổ và tách batch độc lập chưa chốt. Vì vậy B1/B2 chưa nghiệm thu đầy đủ.

Nội dung từng bước và việc còn lại được ghi tại [B1 dataset](../../../docs/assessment/functional/dataset.md) và [B2 hướng dẫn bàn giao](../../../scripts/assessment/data/README.md).

## 6. Retest phần có thể tự làm —21/11/2026

Đã sửa guard theo UUID/type/FK, SQL đếm theo manifest, session readiness/TTL/capacity và smoke mapping động. **7 PASS** trên bộ đủ508 user/12 event/24 lịch/300 reservation;12 cấu hình ảnh sau đổi tên giữ revision khi chạy lại; Practice10 có4 vùng×17. Bảy invariants zero rows khi dữ liệu còn đủ300 reservation. Có100 session riêng, DB chỉ giữ digest và CSRF digest; smoke HTTP100 danh tính/12 map/hold-cancel đạt. Cleanup từ chối quan hệ ngoài batch, giữ user ngoài batch và chạy lại an toàn. Không có ảnh/video tạo mới hoặc tác động AWS. Các mốc UTC20/11 tương ứng21/11 ở Việt Nam; không dùng làm số đo RPO/RTO.

Sáu trang nguồn mạng được kiểm giấy phép và ghi trong CSV; tải file gốc đầu tiên bị HTTP429, các file tiếp theo chưa tải. Không nhận là đã upload/nhận diện/chỉnh4–8 vùng của6 ảnh này. Hai bộ test đầu dùng để chẩn đoán fixture thời gian; bộ cuối có invariants/capacity17 đạt; raw logs/XML/session giữ private.

```json
{
  "task_ids": [
    "B1",
    "B2"
  ],
  "scope": "Disposable PostgreSQL16.16/Redis7.4.11, local HTTP and local storage only; APP_ENV=test and email disabled; no AWS/data/demo configuration changes.",
  "source_commit_before_changes": "6c7070834bb9581e81cc2cf81be394a38cfa438c",
  "source_worktree_modified": true,
  "started_at_utc": "2026-11-20T18:03:49.946337+00:00",
  "duration_seconds": 57.131,
  "tests": 7,
  "passed": 7,
  "failures": 0,
  "errors": 0,
  "skipped": 0,
  "test_cases": [
    "test_counts_hashes_and_idempotency",
    "test_renamed_custom_catalogue_and_sessions",
    "test_guard_rejects_identity_and_relationship_changes",
    "test_handoff_rejects_ineligible_windows",
    "test_smoke_rejects_bad_private_bundle_before_http[expired]",
    "test_smoke_rejects_bad_private_bundle_before_http[duplicate-csrf]",
    "test_cleanup_refuses_foreign_reference_and_preserves_other_data"
  ],
  "checks_before_cleanup": {
    "users": 508,
    "students": 500,
    "admins": 2,
    "staff": 6,
    "events": 12,
    "schedules": 24,
    "reservations_before_smoke": 300,
    "maps": 12,
    "zone_range": [
      4,
      42
    ],
    "mechanic_zones": 4,
    "mechanic_capacity": 17,
    "invariant_rows": [
      0,
      0,
      0,
      0,
      0,
      0,
      0
    ],
    "sessions": 100,
    "distinct_users": 100,
    "idempotent_custom_maps": true
  },
  "cleanup": {
    "aws_changes": false,
    "checked_at_utc": "2026-11-20T18:05:30.4373425Z",
    "remaining_containers": 0,
    "volumes_created": 0,
    "internal_network_removed": true,
    "run": "b1b2-tools-20261121",
    "remaining_networks": 0,
    "containers_removed": 5
  },
  "source_sha256_lf": {
    "app/assessment_seed.py": "8c5a43f09185681ba58a2b3518eee9624d1b365ff7ea1178e644e4aa0e40b3a4",
    "scripts/assessment/data/verify-batch.sql": "fbf5fd27d5a4d22023f2915c3fd5e79d62ecfe99fe2a2558ed4f8237e3ca55ae",
    "scripts/assessment/data/smoke_sessions.py": "9aad315c4364bbecff6320b56217c3ef1b695dfb0fa27fb0fef24082e60b5b64",
    "scripts/assessment/data/prepare-handoff.ps1": "97ec345c9fc109b99d1b3aa046343427fb122c9961127fa3444a1c0954316658",
    "scripts/assessment/data/test_tools.py": "3df0422accd442af583f6c677fb64ed8c60a7c655deece975e90a954eb3394de"
  },
  "private_junit_sha256_raw": "acbcdd43b65e12e4c4e1a450edee4e478634b7a240cf7cb64d026883d4a70053",
  "reproduction": "python -m app.migrate; python -m pytest scripts/assessment/data/test_tools.py -q -p no:cacheprovider --junitxml=<private>/tests.xml with explicit disposable DB/Redis and local storage",
  "asset_sources": {
    "count": 6,
    "csv": "docs/assessment/functional/assets-sources.csv",
    "state": "SOURCED_ONLY",
    "page_license_verified_on": "2026-11-21",
    "first_original_get_url": "https://upload.wikimedia.org/wikipedia/commons/d/d7/Floor_plan1.jpg",
    "first_original_get_http_status": 429,
    "remaining_original_files_not_requested": true,
    "files_downloaded": 0,
    "admin_uploads_of_these_six": 0
  },
  "limitations": [
    "Artwork integration test used white synthetic raster fixtures with final geometry/configuration, not original user image pixels.",
    "No new production session handoff or person3 smoke; old AWS tokens remain expired.",
    "No AWS fixture-window changes or independent functional/load batch migration.",
    "B3 video/X01-X03 and B4/B5 integrated rehearsal still depend on their planned windows.",
    "No complete storage GC, billing audit or AWS cleanup acceptance claimed."
  ]
}
```

## Đối chiếu web và thu hồi ca thử —21/11/2026

Sáu ca `[B2 WEB]` dùng nguồn HNUE đã được xóa trên AWS lúc13:59:28:6event,6lịch,6phòng,24vùng và5reservation thử; không xóa user demo, guard ngoài scope PASS. Ảnh và bảng sáu ca thử cũ không còn dùng làm bằng chứng hiện hành. Nguồn ảnh trong assets-sources.csv được đánh dấu WITHDRAWN.

B3 kiểm lại **Kì thi SAT - Ca demo** có sẵn: UI giữ/xác nhận/hủy; replay; QR/ownership; staff04 lookup; CSV; phòng hết chỗ; race suất cuối200/409 sold_out.45reservation thử đã hủy/45job SKIPPED được dọn lúc14:30:12, provider attempts0; không đổi lịch/capacity/vé gốc. Camera thật không được kiểm lại ở lượt này.

Ca tải riêng đã dùng ngày21/11 (nay đã cleanup) là **Mechanic — Ca chịu tải riêng 21–22/11/2026**, batch `demo-load-mechanic21`,4×45=180 suất,100phiên đã smoke. Mechanic demo4×17=68 giữ nguyên. Ca tải Vật lý cũ đã cleanup; backup gốc vẫn giữ. [Cấu hình và hạn phiên](../../../docs/assessment/functional/dataset.md).

Verify AWS lúc14:31:07:10bảng nghiệp vụ demo theo PK gốc không đổi, chỉ bỏ qua users.last_activity_at;7invariants đều0. Không gọi đây là hậu kiểm hoàn tất C3 hoặc bằng chứng mọi fixture trạng thái đã đủ.

Gói hiện hành22/11 là `demo-load-mechanic22` với ID/phiên mới; xem dataset để lấy hạn thực. Gói21/11 đã thu hồi, không dùng ZIP cũ.
