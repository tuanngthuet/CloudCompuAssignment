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

**Đã sửa và kiểm local21/11:** assert_owned dùng UUID xác định theo batch, username/role, loại event và quan hệ event–lịch–phòng; tên hiển thị có thể đổi. Không bỏ guard. Đã kiểm tên tiếng Việt và12 cấu hình sơ đồ trên DB disposable; chưa chạy lại stage execute/cấp phiên/cleanup trên AWS sau bản sửa.

## Bước 7. Kiểm count, invariants và idempotency

- Bộ nền đã kiểm trên PostgreSQL 17 disposable: đúng quy mô, chạy lại không tăng số đăng ký seed; tạo session/smoke HTTP và cleanup đã được thử.
- Các stage ảnh được kiểm riêng về UUID, mã QR, trạng thái vé và chạy lại không tăng revision.
- Trên production, cả **7 truy vấn** trong `scripts/tests/db-invariants.sql` đều trả **0 dòng vi phạm** lúc 21:57:08 ngày 18/11/2026.
- verify-batch.sql đã chuyển sang danh sách UUID user_ids/event_ids/room_ids từ manifest private; đã kiểm đếm đúng sau đổi tên, không lấy danh sách ID bằng tìm prefix tên.
- Retest21/11 đã kiểm seed/idempotency, tên đã đổi,12 cấu hình sơ đồ/capacity17 của Practice10 và cleanup trên PostgreSQL16.16 disposable. Artwork dùng ảnh trắng synthetic với cùng geometry/stage, không nhận là đã tải lại ảnh người dùng hoặc nghiệm thu production.

## Bước 8. Cleanup chỉ dữ liệu thuộc batch

Công cụ có stage `cleanup`, yêu cầu `--execute --manifest-id <id>`, kiểm quan hệ ngoài batch và xóa theo thứ tự FK. Object không còn tham chiếu được cơ chế maintenance thu gom. Không truncate/reset hoặc xóa dữ liệu thật.

**Chưa chạy cleanup production:** batch còn dùng cho demo/nghiệm thu. Retest21/11 đã kiểm cleanup bộ tùy chỉnh local sau đổi tên: từ chối lịch ngoài batch, giữ user ngoài batch, chạy cleanup lại không lỗi. Đây là cleanup DB; cơ chế thu gom object storage của app không được nhận là đã chạy trên AWS.

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
- [x] Sửa ownership/truy vấn đếm theo UUID để hỗ trợ đổi tên; kiểm trên DB disposable.
- [x] Kiểm idempotency/cleanup sau12 cấu hình sơ đồ, đổi tên và capacity17 trên DB disposable.
- [ ] Có đủ fixture trạng thái và staff đúng lịch tại cửa sổ nghiệm thu.
- [ ] Chốt việc tách batch functional/load và phiên bản source/script bàn giao.

Chưa đánh dấu hoàn tất toàn bộ B1. Tài liệu này chỉ ghi đúng phần công việc B1; phần ảnh/session và các điểm còn thiếu của B2 nằm trong hướng dẫn bàn giao ở thư mục data.

## Rà soát phần có thể tự làm —21/11/2026

Bộ kiểm `python -m pytest scripts/assessment/data/test_tools.py -q -p no:cacheprovider` đạt **7 PASS,0 FAIL/ERROR/SKIP** trên DB/Redis disposable với APP_ENV=test, DATABASE_URL=TEST_DATABASE_URL kết thúc _test và email disabled. Gồm đủ508 user/12 event/24 lịch/300 reservation, hash app, seed/book idempotent; UUID/type/FK guard từ chối sai identity/quan hệ;12 cấu hình ảnh idempotent và capacity17;100 phiên distinct/digest/CSRF, TTL từ expires_at thực; smoke100 user/12 map và hold-cancel qua HTTP; bảy invariants zero rows trước cleanup; cleanup giới hạn batch và chạy lại an toàn. [Bằng chứng](../../../evidence/assessment/b1b2-20261117a/summary.md).

Chưa sửa trạng thái/thời gian ca demo hoặc tạo batch production mới: các fixture sắp mở/hết chỗ/check-in phải được kiểm và bố trí đúng cửa sổ, còn tách batch functional/load độc lập chưa được áp dụng vào bộ demo một batch hiện hành. Không gọi khả năng dùng hai batch ID/namespace khác nhau của helper là bằng chứng AWS đã tách batch. B3 hiện không còn FAIL regression; B4/B5 vẫn chờ fault ổn định. Không sửa endpoint/secret/APP_ENV hay bật email production trong lượt này.

## Cập nhật sau yêu cầu sao lưu và tách ca tải — 21/11/2026

Mục này thay thế riêng trạng thái “chưa tách batch production” ở trên. Bộ demo `b1b2-20261117a` được giữ nguyên; batch tải mới là `demo-load-20261121a`. Không chạy lại seed/reset bộ demo, không đổi lịch/ảnh/tài khoản demo để dùng làm ca tải.

### Backup trước khi tạo dữ liệu tải

| Bản sao | Thời điểm giờ Việt Nam | Kiểm chứng |
| --- | --- | --- |
| RDS snapshot `labseat-demo-before-load-20261120t201159z` | 03:12:06 ngày 21/11 | `available`, encrypted, private; chưa thực hiện restore từ chính snapshot RDS |
| Logical dump public schema, exported transaction snapshot | 03:12:26 ngày 21/11 | Restore thực vào PostgreSQL 16.13 disposable; khớp 27 bảng, số dòng/hash, schema `0002_platform`, constraints; 7 invariants đều 0 |
| 27 object ảnh đang được tham chiếu | Trước lúc xác nhận backup 03:27 ngày 21/11 | Copy theo S3 version, tải lại kiểm SHA-256/content type; 8.195.242 byte |

Dump đã mã hóa AES-256-GCM, upload vào S3 private rồi tải xuống, giải mã và đối chiếu đúng bytes đã restore. SHA-256 plaintext: `b4da172beb998ff9c95c14148a3ac757a3a7d0b54b8253442bcd652abcee27e8`. Backup được xác nhận trước khi ca tải được tạo lúc khoảng 03:36. Metadata đầy đủ, bucket/key/version, key giải mã và fingerprint nằm riêng trong `.local/assessment/demo-load-20261121a/`; không đưa dữ liệu dump hoặc key vào Git hay gói bàn giao Người 3. Giữ backup cho buổi demo cuối, Người 2 chịu trách nhiệm giữ key và metadata ở nơi lưu private của nhóm.

Đối chiếu constraints giữ raw DDL và chỉ chuẩn hóa hai enum check của `users` khi pg_dump chuyển vị trí cast varchar/text tương đương. Kiểm demo sau thao tác so sánh các PK gốc của 10 bảng nghiệp vụ; chỉ bỏ qua `users.last_activity_at` là metadata đăng nhập. Backup đầy đủ vẫn chứa trường này và toàn bộ 27 bảng. Không gọi kiểm nghiệp vụ này là byte-identical toàn DB: phiên đăng nhập/outbox/audit vận hành có thể phát sinh bình thường.

### Ca tải và gói 100 phiên

- Event riêng: **Ca chịu tải riêng 21–22/11/2026 (không dùng demo)**, loại practice, ACTIVE.
- `SESSION_ID`: `5e024221-c858-5443-be0e-4dbd01fd8800`; phòng riêng `40086403-b7f1-5e9c-8810-d4324085638d`.
- 120 chỗ native grid, mỗi chỗ capacity 1; 100 student mới `demo-load-20261121a-s001`…`s100` được gán L001…L100, còn 20 chỗ dự phòng. Không dùng user hoặc phòng demo.
- Mở từ **03:31 ngày 21/11**, đóng **00:00 ngày 24/11/2026**, giờ Việt Nam. Nếu bài đo vượt mốc này phải bố trí lại cửa sổ trước, không sửa demo.
- 100 phiên distinct được cấp theo cơ chế app, TTL 8 giờ, gói đầu hết hạn **11:40:52 ngày 21/11/2026**. Phiên có thể bị thu hồi sớm; phải kiểm và cấp lại sát giờ đo nếu chạy muộn hơn.
- Smoke thực trên `https://labseat.id.vn` lúc 03:45–03:46: 100 `/me` đúng 100 user, 100 seat mapping riêng; một lượt login/logout bằng mật khẩu và giữ → xác nhận → đọc QR → hủy → rời queue thành công. Email job/delivery đều SKIPPED, provider attempts 0.
- Demo nghiệp vụ không đổi, 7 invariants bằng 0; cả 27 ảnh gốc và bản sao đã được đọc lại kiểm version/hash sau thao tác.

Gói private `.local/assessment/demo-load-20261121a/handoff-person3.zip` gồm **manifest.json, synthetic-sessions.json, smoke-result.json, README.txt**. Manifest có mapping tường minh từng index phiên → user → event/ca/phòng/chỗ, thời gian mở/đóng và hạn phiên. Không có backup key hoặc master mật khẩu trong gói. Hướng dẫn cấp lại/kiểm/dọn nằm ở [README data](../../../scripts/assessment/data/README.md).

Queue vẫn bật và email vẫn tắt. `platform.js` nhận file phiên nhưng cần cửa sổ admission-off do người chạy phối hợp; `booking.js` nhận file tài khoản, không nhận trực tiếp file phiên này. Chưa chạy bài tải, chưa nhận xác nhận Người 3 đã nhận/smoke gói và chưa dọn ca tải trên AWS. Sau bài đo cần Người 3 báo dừng để Người 2 chạy cleanup đúng manifest, kiểm lại demo và ghi kết quả thực; không đánh dấu bước tương lai là đã xong. Các fixture trạng thái/ảnh admin còn thiếu ở mục B1/B2 cũ vẫn giữ nguyên trạng thái.
