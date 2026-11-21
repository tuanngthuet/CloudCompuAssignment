# B1 — Công cụ seed và bộ dữ liệu synthetic

**Trạng thái hiện hành22/11: dùng batch `demo-load-mechanic22`; ca tải21/11 đã thu hồi. Xem mục bàn giao cuối tài liệu để lấy ID/hạn phiên mới.**

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

Kiểm chức năng trên https://labseat.id.vn dùng các ca demo có sẵn trong batch `b1b2-20261117a`; lượt kiểm lại 21/11 dùng **Kì thi SAT - Ca demo**. Không còn dùng Practice 12 hoặc student301–400 làm gói chịu tải hiện hành.

Ca tải tách riêng thuộc batch `demo-load-mechanic21`: **Mechanic — Ca chịu tải riêng 21–22/11/2026**, 100 user mới và 180 suất. Đây là bản sao poster/sơ đồ Mechanic; Practice 10 demo vẫn CANCELLED, 4 phòng ×17 =68 suất. Chi tiết và thời hạn phiên ở mục cập nhật cuối file.

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
- [x] Đã tách batch tải AWS riêng; kiểm TTL và smoke lại trước mỗi bài đo.

Chưa đánh dấu hoàn tất toàn bộ B1. Tài liệu này chỉ ghi đúng phần công việc B1; phần ảnh/session và các điểm còn thiếu của B2 nằm trong hướng dẫn bàn giao ở thư mục data.

## Rà soát phần có thể tự làm —21/11/2026

Bộ kiểm `python -m pytest scripts/assessment/data/test_tools.py -q -p no:cacheprovider` đạt **7 PASS,0 FAIL/ERROR/SKIP** trên DB/Redis disposable với APP_ENV=test, DATABASE_URL=TEST_DATABASE_URL kết thúc _test và email disabled. Gồm đủ508 user/12 event/24 lịch/300 reservation, hash app, seed/book idempotent; UUID/type/FK guard từ chối sai identity/quan hệ;12 cấu hình ảnh idempotent và capacity17;100 phiên distinct/digest/CSRF, TTL từ expires_at thực; smoke100 user/12 map và hold-cancel qua HTTP; bảy invariants zero rows trước cleanup; cleanup giới hạn batch và chạy lại an toàn. [Bằng chứng](../../../evidence/assessment/b1b2-20261117a/summary.md).

Các kết quả disposable trong mục này là lịch sử. Ca demo giữ nguyên; việc tách batch AWS đã thực hiện và được mô tả ở mục cập nhật bên dưới. Fixture trạng thái phải kiểm đúng thời điểm trình diễn, không dùng sáu ca thử đã thu hồi để nhận là hoàn tất. B3 hiện không còn FAIL regression; B4/B5 vẫn chờ fault ổn định. Không sửa endpoint/secret/APP_ENV hay bật email production trong lượt này.

## Cập nhật sau yêu cầu sao lưu và tách ca tải — 21/11/2026

Mục này thay thế riêng trạng thái “chưa tách batch production” ở trên. Bộ demo `b1b2-20261117a` được giữ nguyên; batch tải đã dùng ngày21/11 là `demo-load-mechanic21` (đã cleanup); batch `demo-load-20261121a` đã thu hồi. Không chạy lại seed/reset bộ demo, không đổi lịch/ảnh/tài khoản demo để dùng làm ca tải.

### Backup trước khi tạo dữ liệu tải

| Bản sao | Thời điểm giờ Việt Nam | Kiểm chứng |
| --- | --- | --- |
| RDS snapshot `labseat-demo-before-load-20261120t201159z` | 03:12:06 ngày 21/11 | `available`, encrypted, private; chưa thực hiện restore từ chính snapshot RDS |
| Logical dump public schema, exported transaction snapshot | 03:12:26 ngày 21/11 | Restore thực vào PostgreSQL 16.13 disposable; khớp 27 bảng, số dòng/hash, schema `0002_platform`, constraints; 7 invariants đều 0 |
| 27 object ảnh đang được tham chiếu | Trước lúc xác nhận backup 03:27 ngày 21/11 | Copy theo S3 version, tải lại kiểm SHA-256/content type; 8.195.242 byte |

Dump đã mã hóa AES-256-GCM, upload vào S3 private rồi tải xuống, giải mã và đối chiếu đúng bytes đã restore. SHA-256 plaintext: `b4da172beb998ff9c95c14148a3ac757a3a7d0b54b8253442bcd652abcee27e8`. Backup được xác nhận trước khi ca tải được tạo lúc khoảng 03:36. Metadata đầy đủ, bucket/key/version, key giải mã và fingerprint nằm riêng trong `.local/assessment/demo-load-20261121a/`; không đưa dữ liệu dump hoặc key vào Git hay gói bàn giao Người 3. Giữ backup cho buổi demo cuối, Người 2 chịu trách nhiệm giữ key và metadata ở nơi lưu private của nhóm.

Đối chiếu constraints giữ raw DDL và chỉ chuẩn hóa hai enum check của `users` khi pg_dump chuyển vị trí cast varchar/text tương đương. Kiểm demo sau thao tác so sánh các PK gốc của 10 bảng nghiệp vụ; chỉ bỏ qua `users.last_activity_at` là metadata đăng nhập. Backup đầy đủ vẫn chứa trường này và toàn bộ 27 bảng. Không gọi kiểm nghiệp vụ này là byte-identical toàn DB: phiên đăng nhập/outbox/audit vận hành có thể phát sinh bình thường.

### Ca tải đã dùng và gói 100 phiên — đã thu hồi sau bài đo21/11

| Mục | Giá trị đã kiểm |
| --- | --- |
| Ca tải riêng | Mechanic — Ca chịu tải riêng 21–22/11/2026 |
| Batch / manifest | `demo-load-mechanic21` / `0a59f708-244e-5d0d-80d1-c3907727db17` |
| Event | `d3dd7bd8-d8de-5be2-a9aa-6ff6704ef361` |
| SESSION_ID | `3d7ca8f8-07fa-508e-abc7-3f0a7bf69d46` |
| Phòng sơ đồ | `ca17a86c-2c6a-5fc4-91f7-5e2c01cbaa64` |
| Vùng đăng ký | P.6225 (F1.08), P.6226 (F1.10), P.6227 (F1.12), P.6228 (F1.14) |
| Sức chứa | 4 vùng ×45 =180 suất; 25 phiên được gán mỗi vùng |
| Mở đăng ký | 14:02:19 ngày 21/11 đến 00:00 ngày 24/11/2026, giờ Việt Nam |
| Thời gian ca | 01:00–03:00 ngày 24/11/2026, giờ Việt Nam |
| User tải | 100 user mới `demo-load-mechanic21-s001`…`s100` |
| Hạn phiên gói đã smoke | 22:13:07 ngày 21/11/2026, giờ Việt Nam; phải cấp lại và smoke nếu không đủ thời gian bài đo |

Poster và ảnh được sao chép vào key riêng, đối chiếu SHA-256 với nguồn Mechanic demo. Chữ 17 thí sinh trên ảnh nguồn mô tả demo; capacity cấu hình riêng cho bài tải là45/vùng. Không sửa ảnh, lịch hoặc sức chứa Mechanic demo để phục vụ tải.

Gói private `.local/assessment/demo-load-mechanic21/handoff-person3.zip` gồm đúng **manifest.json, synthetic-sessions.json, smoke-result.json, README.txt**. Manifest có mapping phiên→user→ca→phòng→vùng và expires_at thực. Smoke trên AWS lúc14:15:20–14:16:02 ngày21/11 kiểm100 danh tính/token/CSRF riêng, đăng nhập/đăng xuất và giữ–xác nhận–QR–hủy; email SKIPPED, provider attempts0. Không công bố credentials hoặc nhận là Người3 đã ký nhận gói.

Sau lượt kiểm SAT, verify AWS lúc14:31:07 xác nhận 10 bảng nghiệp vụ demo theo PK gốc không đổi (ngoại trừ metadata last_activity_at), cả7 invariants bằng0. Đây không phải xác nhận toàn bộ C3 hoặc hậu kiểm sau tải; C3 còn phải thu đủ bài đo và hậu kiểm. Bản logical backup gốc đã được giải mã/restore kiểm lại trên PostgreSQL16.13 trước khi tạo batch Mechanic.

### Ca đã thu hồi và bằng chứng hiện tại

- Sáu ca `[B2 WEB]` đã xóa lúc13:59:28 ngày21/11: 6event,6lịch,6phòng,24vùng,5reservation thử; guard ngoài scope PASS, không xóa user demo. Các nguồn mạng đã đánh dấu WITHDRAWN trong assets-sources.csv; không dùng ảnh những ca này làm bằng chứng trạng thái web hiện tại.
- Ca tải Vật lý cũ `demo-load-20261121a` đã cleanup theo manifest:100user,1event,1lịch,34vùng và3reservation thử đã hủy. Demo unchanged và7 invariants0. Gói phiên cũ không còn hợp lệ. **Giữ backup gốc** trong thư mục batch cũ để khôi phục demo.
- B3 kiểm lại bằng SAT demo có sẵn;45reservation thử đã hủy và45job SKIPPED được dọn đúng scope, không đổi event/lịch/vùng hoặc vé gốc. Chi tiết ở [report.md](report.md).
- Các fixture sắp mở/check-in và video chưa được kiểm đủ tại cửa sổ trình diễn vẫn ghi thiếu; không tạo thêm ca demo để thay yêu cầu này.

### Sau bài đo: ca tải đã thu hồi

Đã cleanup đúng manifest `0a59f708-244e-5d0d-80d1-c3907727db17`:100user,1event,1lịch,4vùng và4.254reservation thử đãCANCELLED. Trước khi dọn,4.254job/delivery đềuSKIPPED, attempts0. Guard ngoài scope và kiểm10bảng demo/7invariants PASS trong lượt cleanup. Queue key chỉ dọn đúng ca tải, không sửa globalready hoặc policy. Recovery30phút đã kết thúc:API tự3→2/ASG6→5; hậu kiểmDB20:15:14 ngày21/11 đạt, xem báo cáoC3.

Gói phiên nêu trên là bằng chứng đã cấp/smoke và dùng cho C3, **không còn dùng đăng nhập sau cleanup**. Ảnh Mechanic trong evidence là snapshot trước khi thu hồi, không phải ca đang còn trên web. Các ca demo gốc và backup mã hóa vẫn giữ. Muốn Người3 đo một lượt mới cần chuẩn bị ca riêng/gói phiên mới và smoke lại, không dùng ZIP đã thu hồi.

## Bàn giao cấp lại ngày22/11/2026 — Mechanic riêng mới

**Gói hiện hành: `demo-load-mechanic22`.** Gói21/11 đã thu hồi sau đo và hết hạn, không dùng lại ID hoặc ZIP cũ. Kiểm DB lúc00:32:07 22/11/2026 xác nhận event/room/schedule cũ đều0; hai route hợp lệ phòng/ca trả404 khi kiểmHTTP lại, event cũ vắng trong /events, phù hợp receipt cleanup đúng scope. Cleanup đã dọn audit con synthetic, nên không nhận là còn applicationaudit xóa; receipt thực thi được giữ private. Mechanic demo gốc vẫn CANCELLED,4×17=68, không được chuyển thành ca tải.

| Mục hiện hành | Giá trị |
| --- | --- |
| Event | `85118912-6af6-5df9-aaa6-fe84bb35b399` |
| SESSION_ID | `bc3967ba-bb2c-528e-be60-a4eac4b8c15c` |
| Room | `19cd2275-f986-511a-9d4f-189886579b6f` |
| Manifest cleanup | `087bb044-3175-5793-96b7-5fa3a584ecdc` |
| Sức chứa |4 vùng×45=180;25user riêng/vùng; mapping đủ100hàng trong manifest private |
| Đóng đăng ký |00:00:00 25/11/2026, giờ Việt Nam; ca bắt đầu sau đóng1giờ |
| Hạn phiên bảo thủ |**08:38:38 22/11/2026**, giờ Việt Nam; đọc expires_at từng phiên, không chỉnh hạn trong file |

100user/token/CSRF riêng đã cấp mới, yêu cầu tối thiểu6giờ ở lúc cấp và smoke. SmokeAWS kiểm100 /me, normalpasswordlogin/logout, hold→confirm→QR→cancel, queueleave; emailSKIPPED/attempts0. Hạn là TTL thực của app, không kéo dài đến ngày đóng đăng ký. Nếu chạy muộn hoặc không đủ cả bài đo, cấp lại và smoke sát giờ; không dùng gói hết hạn.

Gói private hiện hành ở `.local/assessment/demo-load-mechanic22/delivery/mechanic22-runtime.private.zip`: ZIP gồm đúng `load/manifest.json`, `load/synthetic-sessions.json`, `load/smoke-result.json`, `handoff-status.private.json`. Mapping đủ100user/ca/phòng/vùng nằm trong manifest; SHA-256 của ZIP và4file ở `runtime-handoff-receipt.json`, cùng file `mechanic22-runtime.private.zip.sha256`. Gói flat tênunderscore trước đó đã được thay thế về định dạng; không dùng checksumZIP cũ. Load-master ở `load/load-master.txt` của batch, tách khỏi ZIP; README nêu công thức HMAC và quy trình cấp tài khoản riêng. Không có master hoặc backupkey trong ZIP. Không nhận Người3 đã ký nhận hoặc lượt tải mới đã chạy.

Backup vẫn là bản21/11 trước tải, giữ snapshotRDS available/encrypted và logicaldumpAES-GCM trênS3private. Ngày22/11 đã tải đúngversion, kiểm cipher/plainSHA, giải mã, restore thựcPG16.13:27bảng/hash/schema0002_platform/constraints khớp,7invariants0;27ảnh nguồn/bản sao theoversion/hash đạt. Đây là xác minh lại backup cũ, không gọi là snapshot toànDB mới22/11. `delivery/backup-proof/` chứa manifest/fingerprint/checksum/restoreverification/audit404/demoproof; dump và key không đưa vào ZIP. Chỉ bỏ qua metadata users.last_activity_at khi so10bảng nghiệp vụ demo; không nhận toàn27bảng production byte-identical sau vận hành.

[Receipt công khai đã loại credentials](../../../evidence/assessment/demo-load-mechanic22/results.json). Ca riêng mới đang giữ cho lượt tải tiếp; cleanup sau khi dừng đo, không xóa ngay khi bàn giao. Các kết quả C3 ngày21/11 thuộc ca cũ, không chuyển sang gói22/11.

### Cập nhật runtime lúc02:02 ngày22/11/2026

Kiểm lại trực tiếpHTTPS production từ02:00:43 đến02:02:06 giờVN:100/100 danh tính khớp mapping,100token/CSRF riêng,4vùng180suất còn đủ cho25user/vùng, readyz và sơ đồ/lịch hợp lệ. Đây là kiểm chỉ đọc; không cấp lại phiên hoặc chạy lại workflow/email/restore. Smoke đầy đủ00:42–00:43 và backuprestore00:32 vẫn giữ mốc gốc.

Thời điểm hết hạn thực của100phiên trải từ **08:38:39.182493 đến08:40:14.112456 ngày22/11 (+07:00)**; hạn bảo thủ cả gói là **08:38:38.182493**, sớm hơn phiên đầu1giây. Không nhận phiên còn dùng được sau hạn này.

SHA-256 ZIP runtime đúng4đường dẫn: `7b335641b91549711631f8bed5b1158c51df6d5091290cd49f22cb1afb5916f2`. Receipt công khai có checksum từng file và mapping4vùng; token, mapping100user chi tiết, master và keybackup vẫn giữ private. Backup/fingerprint/restoreproof trước đó được giữ nguyên, không dùng timestamp đóng gói thay timestamp kiểm DB/restore.
