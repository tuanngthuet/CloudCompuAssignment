# B1 — Công cụ seed và bộ dữ liệu synthetic

Đầu ra `functional/dataset.md` theo B1 trong [kế hoạch sprint](../../sprints/ke-hoach-nghiem-thu-4-ngay.md). Ghi nhận ngày **18/11/2026**. Hướng dẫn B2 nằm tại [scripts/assessment/data/README.md](../../../scripts/assessment/data/README.md); số liệu kiểm chứng tại [evidence summary](../../../evidence/assessment/b1b2-20261117a/summary.md).

## Bước 1. Xác định đầu vào, target và phạm vi batch

- Models/schema: `0002_platform`; dùng ORM/service hiện tại, không dùng `app.cli seed` local/test để reset AWS.
- Target đã triển khai: https://labseat.id.vn, region `ap-southeast-2`, ECS cluster `labseat-lab`, RDS private.
- Batch: `b1b2-20261117a`; manifest ID: `0e5bff29-973d-589a-bbd0-afd3088d29c2`.
- Công cụ: `app/assessment_seed.py`; runner Windows: `scripts/assessment/data/run-one-off.ps1`.
- Chạy ECS one-off trong VPC, dùng task definition API hiện hành. Runner kiểm account, tải source qua S3 private, kiểm SHA-256 và dọn object staging theo version sau khi task dừng.
- File private nằm dưới `.local/assessment/<batch>/`, được loại khỏi Git. Không ghi DATABASE_URL, token, mật khẩu hoặc seed master vào evidence.

## Bước 2. Tạo tài khoản synthetic

Yêu cầu B1: 500 student, 2 admin demo mới, 6 staff; password hash đúng app, email/CCCD synthetic duy nhất; seed user đã xác minh không phát mail.

Đã triển khai đủ **508 tài khoản**, gồm 500 student, 2 admin, 6 staff. Snapshot 21:57:08 ngày 18/11/2026 (UTC+7) xác nhận cả 508 đã xác minh email. Student/staff có họ tên tiếng Việt theo yêu cầu người dùng.

Công cụ dùng hasher của app; mật khẩu riêng từng username được suy ra bằng HMAC-SHA256 với master private. Runner tạo master trong task, chỉ truyền bản mã RSA qua log; dữ liệu giải mã và `accounts.json` chỉ lưu private. Không chép mật khẩu vào tài liệu này.

## Bước 3. Tạo event, lịch và phân công staff

Yêu cầu B1: 12 event (6 exam/6 practice), 24 lịch; có sắp mở/đang mở/hết chỗ/đóng/check-in/kết thúc/hủy; phân công staff đúng lịch.

Đã có **6 exam, 6 practice, 24 lịch**, hai lịch mỗi ca. Snapshot xác nhận 11 event ACTIVE và 1 CANCELLED. Practice 10 là ca hủy; vì `/events` công khai chỉ trả ACTIVE nên chỉ thấy 11 ca của batch. Có 6 staff được phân công trên 6 lịch.

Tên ca đã được đổi trên web; dùng UUID trong manifest để xác định batch thay vì dựa vào tên hiển thị.

**Còn phải kiểm lại trước nghiệm thu:** các trạng thái thay đổi theo thời gian. Practice 07 đã kết thúc; Practice 09 đã đóng đăng ký; mốc sắp mở của Practice 08 đã qua. Một lịch TOEIC bật `checkin_enabled` nhưng ngày thi còn ở tương lai; chưa thể coi đó là bằng chứng luồng check-in đang hoạt động. Cần bổ sung/đặt lại fixture sắp mở, hết toàn bộ chỗ và check-in tại đúng cửa sổ demo, đồng thời kiểm staff của các lịch cần trình diễn.

## Bước 4. Tách dữ liệu chức năng và tải

| Mục | Cấu hình hiện hành |
| --- | --- |
| Nhóm user tải | student301–student400 |
| Lịch tải | `a243bee7-1ea1-58df-94f9-7f7d6cabb7f6`, Practice 12 |
| Sức chứa lịch tải | 42 vùng × 45 = **1.890 chỗ** |
| Lịch UI | `8ee5859b-8331-5dd6-9eaa-27660cf38b46`, Practice 11 |
| Sức chứa lịch UI | 34 vùng × 45 = **1.530 chỗ** |

Hai lịch dùng cùng batch nhưng khác lịch/nhóm tài khoản. Đây là **tách logic**, chưa phải hai batch độc lập functional/load như prompt B1 nêu. Cần chốt phương án này hoặc tạo batch độc lập; không ghi là đã hoàn thành yêu cầu tách batch.

Hai lịch đang mở đến 20:14:27 ngày 21/11/2026 (UTC+7). Lịch tải bắt đầu 14:14:27 ngày 25/11; lịch UI bắt đầu 08:14:27 ngày 25/11. Kiểm lại thời gian và capacity trước buổi đo; không tiếp tục dùng con số lịch tải 360 chỗ của bộ cũ.

## Bước 5. Tạo khoảng 300 reservation qua service nghiệp vụ

Công cụ `book` dùng admission và service giữ suất/xác nhận, có outbox/audit; không chèn thẳng reservation để bỏ qua constraints. Runner yêu cầu worker đã rollout ổn định với `EMAIL_BACKEND=disabled` trước khi tạo đăng ký thử. Chỉ sinh lượt xác nhận khi C2 đã chặn gửi mail.

Lượt seed ban đầu tạo 300 đăng ký: 298 CONFIRMED, 1 CHECKED_IN, 1 CANCELLED. Smoke đầu tạo thêm một lượt hủy. Sau thao tác demo, snapshot **21:57:08 ngày 18/11** có:

| Trạng thái | Số lượng |
| --- | ---: |
| CONFIRMED | 300 |
| CHECKED_IN | 1 |
| CANCELLED | 2 |
| Tổng | **303** |

Có **303 email job gắn đăng ký của tài khoản batch, tất cả SKIPPED** tại snapshot. Đây là số liệu kiểm tra, không phải bằng chứng đã khôi phục Brevo sau cửa sổ thử. Việc đóng/mở cửa sổ email thuộc điều phối C2 của Người 3.

## Bước 6. Dry-run, execute và khả năng tái tạo

Công cụ mặc định chỉ in kế hoạch khi thiếu `--execute`, nhận batch ID và dùng UUID xác định theo batch. Ví dụ xem kế hoạch:

```text
python -m app.assessment_seed prepare --batch b1b2-20261117a
```

Runner Windows tương tự không thay dữ liệu khi thiếu `-Execute`:

```powershell
./scripts/assessment/data/run-one-off.ps1 -Stage prepare -Batch b1b2-20261117a -ExpectedAccount 403030570855
```

Trình tự đã dùng cho bộ nền: `prepare` → cấp session/bàn giao → xác nhận C2 tắt email → `book`. Stage `book` cần `--email-window-confirmed`; runner chỉ thực thi khi có `-Execute`. Các ảnh tùy chỉnh được áp dụng bằng stage riêng; bộ nền mới mặc định vẫn là sáu sơ đồ synthetic, không tự tái tạo đầy đủ 12 ảnh hiện hành nếu thiếu các ảnh nguồn private.

**Điểm chưa xử lý:** `assert_owned()` còn yêu cầu prefix tên event, trong khi các ca đã đổi tên. Các stage gọi guard này có thể bị từ chối trên batch hiện hành. Không dùng ví dụ dry-run làm bằng chứng rằng execute/cấp phiên/cleanup hiện đã chạy lại được. Cần giữ kiểm tra ownership nhưng chuyển sang cách xác thực phù hợp với UUID và quan hệ batch.

## Bước 7. Kiểm count, invariants và idempotency

- Bộ nền đã kiểm trên PostgreSQL 17 disposable: đúng quy mô, chạy lại không tăng số đăng ký seed; tạo session/smoke HTTP và cleanup đã được thử.
- Các stage ảnh được kiểm riêng về UUID, mã QR, trạng thái vé và chạy lại không tăng revision.
- Trên production, cả **7 truy vấn** trong `scripts/tests/db-invariants.sql` đều trả **0 dòng vi phạm** lúc 21:57:08 ngày 18/11/2026.
- `scripts/assessment/data/verify-batch.sql` hiện còn lọc event/lịch/reservation bằng prefix tên event. Tên đã đổi nên phần này có thể bỏ sót dữ liệu; cần sửa theo UUID batch. Snapshot mới dùng UUID, không dùng kết quả lọc tên cũ để kết luận dữ liệu mất.
- Chưa có bằng chứng chạy lại toàn bộ seed/idempotency/cleanup sau tất cả tùy chỉnh cuối. Phải kiểm trên DB disposable với tên đã đổi, 12 sơ đồ và capacity 17 của Practice 10.

## Bước 8. Cleanup chỉ dữ liệu thuộc batch

Công cụ có stage `cleanup`, yêu cầu `--execute --manifest-id <id>`, kiểm quan hệ ngoài batch và xóa theo thứ tự FK. Object không còn tham chiếu được cơ chế maintenance thu gom. Không truncate/reset hoặc xóa dữ liệu thật.

**Chưa chạy cleanup production:** batch còn dùng cho demo/nghiệm thu. Guard prefix tên hiện cũng cần xử lý trước khi có thể cleanup batch đã đổi tên. Bằng chứng cleanup cũ chỉ áp dụng cho bộ nền disposable, chưa chứng minh cleanup toàn bộ cấu hình tùy chỉnh cuối.

## Đầu ra và điều kiện đóng B1

| Đầu ra theo sprint | Vị trí |
| --- | --- |
| Công cụ seed/bàn giao/kiểm tra | `app/assessment_seed.py`, `scripts/assessment/data/` |
| Mô tả dataset | File này |
| Manifest và tài khoản private | `.local/assessment/b1b2-20261117a/` |
| Evidence count/invariants | `evidence/assessment/b1b2-20261117a/summary.md` |

- [x] Đủ 500 student, 2 admin, 6 staff, 12 event, 24 lịch và khoảng 300 đăng ký.
- [x] Snapshot production có 7 invariants bằng 0; dữ liệu demo/ảnh đã tích hợp.
- [x] Có dry-run, execute rõ ràng, batch/manifest ID và guard cleanup.
- [ ] Sửa ownership/truy vấn đếm để hỗ trợ tên ca hiện hành.
- [ ] Kiểm lại toàn bộ idempotency/cleanup trên DB disposable sau tùy chỉnh.
- [ ] Có đủ fixture trạng thái và staff đúng lịch tại cửa sổ nghiệm thu.
- [ ] Chốt việc tách batch functional/load và phiên bản source/script bàn giao.

Chưa đánh dấu hoàn tất toàn bộ B1. Tài liệu này chỉ ghi đúng phần công việc B1; phần ảnh/session và các điểm còn thiếu của B2 nằm trong hướng dẫn bàn giao ở thư mục data.
