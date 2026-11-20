# B2 — Ảnh sơ đồ và gói dữ liệu/session bàn giao

Đầu ra hướng dẫn/session helper trong thư mục data theo B2 của [kế hoạch sprint](../../../docs/sprints/ke-hoach-nghiem-thu-4-ngay.md). B1 được ghi tại [dataset.md](../../../docs/assessment/functional/dataset.md). Hiện trạng và bằng chứng dưới đây đối chiếu ngày **18/11/2026**; không phải xác nhận phiên vẫn còn hiệu lực ở lần sử dụng tiếp theo.

## Bước 1. Chuẩn bị và ghi nguồn ảnh

Yêu cầu sprint: tìm 6 ảnh sơ đồ có nguồn/quyền dùng, ghi URL, giấy phép và thao tác chỉnh sửa trong [assets-sources.csv](../../../docs/assessment/functional/assets-sources.csv). Phân biệt ảnh sơ đồ với poster; không dùng dữ liệu phòng nhạy cảm. Chỉ đưa ảnh được phép phân phối vào Git.

Đã tích hợp poster/sơ đồ người dùng cung cấp cho12 ca; các phiên bản lịch sử được giữ trong CSV, bảng dưới đây xác định bản dùng tại snapshot18/11. Ngày21/11 đã thêm6 nguồn mạng public-domain/CC0 (b2-network-01…06) từ trang mô tả Wikimedia Commons. Chúng mới SOURCED_ONLY: GET file gốc đầu tiên trả HTTP429 nên chưa tải/chuyển định dạng/upload/chỉnh vùng; không nhận6 ảnh usable. Quyền nguồn mới không áp cho các ảnh người dùng gửi hoặc suy thành quyền phân phối chúng trong Git.

## Bước 2. Chuẩn hóa ảnh, upload và căn vùng

Yêu cầu sprint: PNG/JPEG/WebP, tối đa 5 MB, mỗi chiều tối đa 2048 px; upload qua admin, kiểm nhận diện và chỉnh tay 4–8 vùng có capacity mỗi ảnh.

Đã làm trên production: ảnh được chuẩn hóa và căn geometry; poster 1280×720. ElectricLab AVIF được đổi sang PNG trước khi tích hợp. Hai lịch của mỗi ca dùng cùng sơ đồ. Mỗi vùng có 45 suất, riêng Practice 10 có 17 suất theo ảnh.

| Ca | Poster hiện hành | Sơ đồ hiện hành | Vùng chọn | Chỗ/lịch |
| --- | --- | --- | ---: | ---: |
| Exam 01 | ĐHQG TP.HCM | HSA khu A, P.002–P.005 | 4 | 180 |
| Exam 02 | IELTS | IELTS, P.1–P.5 | 5 | 225 |
| Exam 03 | TSA | TSA, P.36–P.47 | 12 | 540 |
| Exam 04 | SAT | SAT, các phòng trong ảnh | 11 | 495 |
| Exam 05 | HSA-VNU | Khu nhà A, P.001–P.033 | 33 | 1.485 |
| Exam 06 | TOEIC | Sơ đồ SAT theo yêu cầu người dùng | 11 | 495 |
| Practice 07 | BioLab | BioRoom-da-cat, phòng 1–6 ở tầng 09–11 | 6 | 270 |
| Practice 08 | ComLab | ComRoom, P.001–P.020 | 20 | 900 |
| Practice 09 | ElectricLab | ElecRoom, P.01–P.18 | 18 | 810 |
| Practice 10 | MechanicLab | MachanicRoom, P.6225–P.6228 | 4 | 68 |
| Practice 11 | PhysicsLab | PhysicsRoom-da-chinh-sua, HN582–HN615 | 34 | 1.530 |
| Practice 12 | ChemisLab | ChemisRoom-da-chinh-sua, HN060–HN101 | 42 | 1.890 |

Practice 10 đang CANCELLED để phục vụ tình huống ca hủy; có ảnh trong DB nhưng không xuất hiện ở danh sách `/events` công khai, vốn chỉ trả ca ACTIVE.

Giao diện làm nền sơ đồ thành thang xám và giữ màu ở vùng có thể chọn; ảnh nền trắng có thể vẫn trắng sau khi chuyển thang xám. Các khu hỗ trợ không có vùng chọn.

**Còn thiếu theo B2:** bộ 12 sơ đồ/4–42 vùng khác tiêu chí gốc 6 ảnh/4–8 vùng. Cần có bộ nghiệm thu riêng đạt tiêu chí gốc hoặc ghi nhận điều chỉnh phạm vi; không tự sửa yêu cầu gốc. Các ảnh tùy chỉnh được áp dụng bằng ORM/ECS one-off, nên còn cần bằng chứng upload → nhận diện → chỉnh tay → lưu qua luồng admin.

## Bước 3. Chuẩn bị manifest và tài khoản bàn giao

Batch: `b1b2-20261117a`; manifest ID: `0e5bff29-973d-589a-bbd0-afd3088d29c2`.

Các file private nằm tại `.local/assessment/b1b2-20261117a/`:

- `manifest.json`: UUID ca/lịch/phòng, `seat_id`, nhãn, capacity, lịch tải/UI và hạn phiên.
- `accounts.json`: tài khoản/mật khẩu demo; chỉ bàn giao qua kênh riêng.
- `synthetic-sessions.json`: session dùng cho bài platform.
- `seed-master.txt`, khóa và dữ liệu vận chuyển: private, không đưa vào evidence/Git.

Mapping đã được cập nhật sau các lần thay sơ đồ. Ở lần kiểm tra 18/11, nhãn, capacity và `seat_id` của lịch đại diện cả 12 ca khớp API; hai lịch mỗi ca khớp số vùng/sức chứa theo DB.

## Bước 4. Tạo ít nhất 100 session distinct

Helper hiện có:

- `app.assessment_seed.create_sessions()` gọi hàm `auth.create_session()` hiện có; DB giữ digest theo cơ chế app.
- `prepare-handoff.ps1` gọi stage `sessions`, tạo manifest/accounts và chạy smoke.
- Tài khoản tải là student301–student400. Token/CSRF chỉ ghi vào file private; không dùng login HTTP hàng loạt hoặc tắt rate limit.

File dùng trực tiếp có dạng:

```json
[
  {"session_token": "<private>", "csrf_token": "<private>", "seat_id": "<uuid>"}
]
```

**Trạng thái tại 21:57:08 ngày 18/11/2026 (UTC+7):** DB có 100 fixture session thuộc 100 user riêng, nhưng **0 session còn hiệu lực**. Hạn thực tế từ 04:26:46 đến 04:28:24 cùng ngày. Manifest ghi mốc bảo thủ `2026-11-18T04:26:45.24717+07:00`. Phải cấp lại sát giờ đo.

**Đã sửa local21/11:** guard dùng UUID/type/quan hệ thay tên hiển thị; đã kiểm100 session trên bộ đổi tên/12 cấu hình sơ đồ. create_sessions kiểm event ACTIVE, user ACTIVE/verified và không pending email, số chỗ còn lại theo từng vùng, ca chưa bắt đầu và cửa sổ đủ dài. sessions_expire_at là min expires_at thực trong DB trừ1giây, không cộng8giờ từ đồng hồ client.

## Bước 5. Kiểm readiness và tách lịch tải/UI

| Mục | Giá trị đã đối chiếu ngày 18/11/2026 |
| --- | --- |
| Lịch tải | `a243bee7-1ea1-58df-94f9-7f7d6cabb7f6` — Practice 12, 1.890 chỗ |
| Lịch UI | `8ee5859b-8331-5dd6-9eaa-27660cf38b46` — Practice 11, 1.530 chỗ |
| Đóng đăng ký của hai lịch | 20:14:27 ngày 21/11/2026, UTC+7 |
| Bắt đầu lịch tải | 14:14:27 ngày 25/11/2026, UTC+7 |
| Bắt đầu lịch UI | 08:14:27 ngày 25/11/2026, UTC+7 |

Trước mỗi lần bàn giao: kiểm cửa sổ còn đủ dài, ca chưa bắt đầu/chưa hủy, user ACTIVE/verified, vùng còn chỗ và TTL bao trùm bài đo. Hiện tách theo lịch/tài khoản trong một batch; không ghi là đã tạo hai batch độc lập.

## Bước 6. Smoke đọc/ghi và bàn giao Người 3

`smoke_sessions.py` đã có: tải ảnh, kiểm danh tính qua `/me`, vào hàng chờ, giữ rồi hủy một suất. Lượt bàn giao ban đầu đã thành công; không coi đó là bằng chứng gói mới vẫn chạy được.

**Đã sửa local21/11:** smoke đối chiếu đúng tập seat UUID/nhãn/capacity từ schedule_rooms, không hard-code4–8 hoặc tên artwork; kiểm format/kích thước/bytes ảnh, timezone/TTL/cửa sổ từ server_time, distinct user/CSRF và số suất gán không vượt remaining. Luồng hold được hủy và rời queue trong finally. Bộ12 cấu hình gồm elec18/physics34/chemistry42 đã qua smoke100 user trên app local; không thay chứng cứ upload/nhận diện6 ảnh mạng qua admin.

Sau khi xử lý guard và smoke, quy trình đã dùng trên Windows là giữ tunnel SSM đến RDS ở cổng 15432, rồi chạy:

```powershell
./scripts/assessment/data/prepare-handoff.ps1 -Batch b1b2-20261117a -MinimumValidSeconds 14400 -Execute
```

Có thể truyền `-Aws <đường-dẫn-aws.exe>`, `-Profile`, `-Region`, `-TunnelPort` theo môi trường. Helper cần Docker image client `labseat-assessment-b1b2:local` và quyền AWS phù hợp. Không đưa DATABASE_URL/token/password vào tài liệu hoặc log.

Để kiểm riêng gói mới sau khi sửa helper:

```text
python scripts/assessment/data/smoke_sessions.py .local/assessment/b1b2-20261117a --base-url https://labseat.id.vn --minimum-valid-seconds 14400
```

Bàn giao qua kênh riêng cho Người 3: manifest, file session, tài khoản cần thiết, `SESSION_ID` lịch tải, TTL và kết quả smoke. `platform.js` nhận `SESSIONS_FILE` và `SESSION_ID`. Người 3 phải dùng được gói mà không tự sửa seed.

## Điều kiện đóng B2

- [ ] Nguồn/quyền dùng ảnh và phạm vi 6/12 ảnh được chốt.
- [ ] Có bằng chứng luồng admin upload/nhận diện/chỉnh vùng theo tiêu chí đã chốt.
- [x] 12 sơ đồ/poster hiện hành tải được; mapping đã đối chiếu ngày 18/11.
- [x] Guard/helper smoke hoạt động local với ca đổi tên/12 cấu hình geometry/capacity; chưa chạy lại AWS sau sửa.
- [ ] Cấp lại ≥100 session distinct, readiness/TTL đạt, smoke đọc/ghi mới thành công.
- [ ] Người 3 nhận và dùng được gói bàn giao; phiên bản source/script được chốt.

Chưa đánh dấu B2 hoàn tất. Xem [bằng chứng số liệu](../../../evidence/assessment/b1b2-20261117a/summary.md).

## Retest công cụ và cách tái tạo —21/11/2026

Bảy test tích hợp trong test_tools.py đã PASS trên PostgreSQL16.16/Redis7.4.11 disposable; nguồn/hash/kết quả và giới hạn ở [evidence](../../../evidence/assessment/b1b2-20261117a/summary.md). Chạy với app dependencies, PYTHONPATH trỏ repo, APP_ENV=test, DATABASE_URL=TEST_DATABASE_URL trỏ DB mới kết thúc _test, REDIS_URL riêng, EMAIL_BACKEND=disabled, STORAGE_BACKEND=local và LOCAL_STORAGE_PATH tạm. Dùng `python -m app.migrate`, rồi `python -m pytest scripts/assessment/data/test_tools.py -q -p no:cacheprovider --junitxml=<private>/tests.xml`. Bộ kiểm tự tạo/cấp phiên/smoke/cleanup dataset local; raw logs và session giữ private. Không dùng lệnh này trên AWS hoặc DB demo.

prepare-handoff.ps1 mặc định yêu cầu cửa sổ14400giây (4giờ); helper Python trực tiếp mặc định3600giây. Chọn thời lượng bao trùm bài đo cộng phần dự phòng; không sửa TTL app hoặc kéo dài expires_at trong file. Cấp gói production sát lịch C3 sau kiểm readiness, không phát lại token local đã bị cleanup. SQL verify-batch.sql nhận CSV UUID user_ids/event_ids/room_ids từ manifest; không còn tham số batch_prefix. Muốn kiểm production phải truyền danh sách từ manifest private đúng batch, không dùng ID theo tên tìm kiếm.

Sáu nguồn mạng trong assets-sources.csv có trang cấp quyền cụ thể; file nguyên gốc chưa tải do HTTP429 ở request đầu. Các mục upload/nhận diện/chỉnh4–8 vùng, API proof của chính6 ảnh đó và ≥100 session AWS mới/Người3 smoke vẫn chưa hoàn thành. Không sửa sáu ca demo hoặc thay bộ12 ảnh hiện hành để lấp phần thiếu.

## Ca tải riêng có backup — cập nhật 21/11/2026

Yêu cầu mới đã được thực hiện bằng `demo_backup.py`, `protect-backup.ps1`, `isolated_load.py` và hai runner `prepare-isolated-one-off.ps1` / `run-isolated-load.ps1`. Các ghi chú “chưa có 100 phiên AWS mới” phía trên là lịch sử; gói mới đã smoke AWS, còn việc Người 3 xác nhận nhận gói vẫn chờ. Quy mô/thời hạn và backup ở [dataset](../../../docs/assessment/functional/dataset.md).

**Backup hiện có:** `.local/assessment/demo-load-20261121a/backup-manifest.private.json` chỉ tới logical dump AES-GCM và các version ảnh S3, kèm snapshot RDS `labseat-demo-before-load-20261120t201159z`. Thư mục private còn chứa `demo-backup.key`, `source-fingerprint.json`, `demo-fingerprint.json`, `assets-backup.private.json` và kết quả restore. Giữ các file này để khôi phục; không gửi cả thư mục cha cho Người 3.

**Khôi phục khi cần:**

1. Dừng thao tác ghi của bài tải; chọn một DB PostgreSQL 16.13 **mới, rỗng**, không chỉ định DB production. Tải đúng `logical_database.bucket/key/version_id` trong manifest bằng `aws s3api get-object --bucket <bucket> --key <key> --version-id <version> <file-private.aesgcm>`. Đối chiếu SHA-256 ciphertext trong manifest.
2. Giải mã vào thư mục private bằng `protect-backup.ps1 -Mode Decrypt -InputFile <file-private.aesgcm> -KeyFile <demo-backup.key> -OutputFile <restore.dump>`. Công cụ kiểm GCM và SHA plaintext, từ chối ghi đè. SHA plaintext phải trùng dataset.
3. Dùng `pg_restore --exit-on-error --no-owner --no-acl --dbname=<DB-moi> <restore.dump>`; cấp role/grant cần thiết cho DB mới riêng vì dump không mang owner/ACL. Không chạy `--clean` vào production.
4. Với từng record trong `assets-backup.private.json`, tải đúng `backup_key/backup_version`, đối chiếu SHA/content type rồi phục hồi vào bucket/prefix **mới** tương ứng `reference`. App thử phải trỏ DB và storage thử riêng, email disabled. Kiểm 27 bảng/hash, schema/constraints và 7 truy vấn `scripts/tests/db-invariants.sql`, sau đó smoke app trước khi quyết định dùng bản phục hồi.
5. Lựa chọn thứ hai là restore snapshot RDS sang DB identifier mới, private subnet/security group và secret thử riêng. Lượt này **chưa kiểm restore snapshot RDS**, chỉ logical dump đã được restore thực. Không tự đổi endpoint/secret production. Sau sự cố, việc chuyển production sang bản phục hồi cần được chốt cùng nhóm để tránh ghi đè dữ liệu mới hơn backup.

**Cấp lại phiên và đóng gói:** mở tunnel SSM RDS local 15432 như quy trình đang dùng; có Docker image client `labseat-assessment-b1b2:local`, AWS CLI profile `labseat` còn hạn. Runner kiểm account, TLS/host, backup verified, demo fingerprint, cửa sổ/TTL và ownership UUID. Khi dùng đường dẫn AWS CLI đầy đủ, thêm `-Aws '<path-to-aws.exe>'`.

```powershell
# Không prepare lại bộ demo. Ca tải hiện tại đã tồn tại; không cần chạy prepare nữa.
./scripts/assessment/data/run-isolated-load.ps1 -Stage verify
./scripts/assessment/data/run-isolated-load.ps1 -Stage sessions -MinimumValidSeconds 14400 -Execute
./scripts/assessment/data/run-isolated-load.ps1 -Stage smoke -MinimumValidSeconds 14400 -Execute
```

`sessions` thu hồi/thay thế chỉ 100 phiên của batch tải rồi ghi TTL thực, không kéo dài TTL app. `smoke` kiểm 100 danh tính và một vòng đặt/hủy, kiểm worker email disabled ổn định trước khi xác nhận, rồi tạo lại ZIP private gồm đúng 4 file bàn giao. Nếu phiên hết hạn, chỗ đang chiếm hoặc demo/schema thay đổi, công cụ dừng; không sửa file hạn phiên để bỏ qua guard. Gói đầu hết hạn 11:40:52 ngày 21/11, giờ Việt Nam; chạy ngày mai phải cấp lại và smoke mới.

Người 3 giải nén ZIP private, kiểm `manifest.mapping`, TTL và 100 phiên trước bài đo; truyền `BASE_URL=https://labseat.id.vn`, `SESSION_ID=5e024221-c858-5443-be0e-4dbd01fd8800`, `SESSIONS_FILE=<path/synthetic-sessions.json>` cho kịch bản hỗ trợ file phiên. `platform.js` hiện yêu cầu admission-off; queue đang bật nên cần phối hợp cửa sổ/chính sách trước khi chạy. `booking.js` dùng `ACCOUNTS_FILE`, không dùng trực tiếp gói phiên này. Không tự bật email, sửa script của Người 3 hoặc chạy tải trong bước chuẩn bị này. Người 2 cấp lại gói khi Người 3 cần; chưa nhận biên bản bàn giao từ Người 3 thì không ghi đã nghiệm thu.

**Sau khi Người 3 xác nhận đã dừng bài tải:**

```powershell
# Xem đúng phạm vi trước; chưa xóa khi thiếu -Execute.
./scripts/assessment/data/run-isolated-load.ps1 -Stage cleanup -ManifestId fcbac39e-8ef7-53a7-809a-e2f867cd7f66
# Chỉ thực thi sau bài đo:
./scripts/assessment/data/run-isolated-load.ps1 -Stage cleanup -ManifestId fcbac39e-8ef7-53a7-809a-e2f867cd7f66 -Execute
```

Cleanup kiểm quan hệ chéo, chỉ xóa user/event/ca/phòng/120 seat và dữ liệu con của UUID scope mới; chạy lại an toàn. Đối chiếu demo nghiệp vụ và 7 invariants trong cùng lượt, giữ backup và ảnh demo. Không truncate/reset. Queue lease được rời qua API khi smoke; các key cache của ca riêng có TTL, nếu phải dọn ngay chỉ xóa 5 key suffix `seq/waiting/admitted/entries/seen` của đúng epoch + SESSION_ID qua operator được phép, không xóa `labseat:queue:ready` hoặc đổi policy toàn hệ thống. Đây là bước sau tải, chưa chạy trên AWS; dry-run hiện chỉ thấy scope mới và các reservation smoke đã hủy.

Test an toàn của công cụ mới: `python -m pytest scripts/assessment/data/test_isolated_load.py -q -p no:cacheprovider` chỉ chạy khi APP_ENV=test, DATABASE_URL=TEST_DATABASE_URL kết thúc `_test`, host `backup-verify-db` disposable. Kiểm enum constraint normalization fail-closed, prepare idempotent, 100 phiên/chỗ riêng, từ chối cleanup khi có lịch ngoại scope, cleanup lặp lại và giữ nguyên toàn bộ 27 bảng. Không chạy test này vào DB demo.
