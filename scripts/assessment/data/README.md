# B2 — Ảnh sơ đồ và gói dữ liệu/session bàn giao

**Hiện hành22/11: batch `demo-load-mechanic22`; ca21/11 đã cleanup/404. Xem mục cuối để lấy gói mới; các lệnh batch21 phía trên là lịch sử.**

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

## Bước 4. Gói 100 phiên AWS hiện hành

Dùng batch tải riêng `demo-load-mechanic21`, 100 user mới, 100 token và CSRF riêng; mapping 25 người mỗi vùng phòng, bốn vùng capacity45. Không dùng nhóm student301–400 hoặc lịch Chemistry/Physics demo làm gói tải hiện hành.

Gói private gồm manifest.json, synthetic-sessions.json, smoke-result.json, README.txt. Đã smoke 100 danh tính và vòng giữ–xác nhận–QR–hủy trên AWS thật; provider attempts0. Hạn phiên gói hiện tại là22:13:07 ngày21/11/2026, giờ Việt Nam. Kiểm expires_at thực trước mỗi phase; cấp lại rồi smoke khi cần, không sửa TTL trong file.

## Bước 5. Readiness và tách dữ liệu

Ca tải **Mechanic — Ca chịu tải riêng 21–22/11/2026**, SESSION_ID `3d7ca8f8-07fa-508e-abc7-3f0a7bf69d46`, mở đến00:00 ngày24/11/2026; tổng180suất. Ca Mechanic demo vẫn CANCELLED,68suất. Web kiểm chức năng dùng SAT và các ca demo có sẵn, không tạo thêm ca B2 WEB.

Manifest liên kết index phiên với user/event/lịch/phòng/vùng. Trước bài đo kiểm user ACTIVE/verified, ca chưa bắt đầu, chỗ còn đủ và TTL bao trùm phase. Gói đã smoke AWS chưa đồng nghĩa Người3 đã xác nhận nhận gói. [Cấu hình/backup/giới hạn](../../../docs/assessment/functional/dataset.md).

## Điều kiện đóng B2

- [ ] Nguồn/quyền dùng ảnh và phạm vi 6/12 ảnh được chốt.
- [ ] Có bằng chứng luồng admin upload/nhận diện/chỉnh vùng theo tiêu chí đã chốt.
- [x] 12 sơ đồ/poster hiện hành tải được; mapping đã đối chiếu ngày 18/11.
- [x] Guard/helper kiểm disposable và gói Mechanic riêng đã smoke AWS; phân biệt hai nguồn bằng chứng.
- [x] ≥100 phiên distinct, readiness/TTL và smoke đọc/ghi AWS đạt trong lượt21/11; phải kiểm lại hạn trước chạy.
- [ ] Người 3 nhận và dùng được gói bàn giao; phiên bản source/script được chốt.

Chưa đánh dấu B2 hoàn tất. Xem [bằng chứng số liệu](../../../evidence/assessment/b1b2-20261117a/summary.md).

## Retest công cụ và cách tái tạo —21/11/2026

Bảy test tích hợp trong test_tools.py đã PASS trên PostgreSQL16.16/Redis7.4.11 disposable; nguồn/hash/kết quả và giới hạn ở [evidence](../../../evidence/assessment/b1b2-20261117a/summary.md). Chạy với app dependencies, PYTHONPATH trỏ repo, APP_ENV=test, DATABASE_URL=TEST_DATABASE_URL trỏ DB mới kết thúc _test, REDIS_URL riêng, EMAIL_BACKEND=disabled, STORAGE_BACKEND=local và LOCAL_STORAGE_PATH tạm. Dùng `python -m app.migrate`, rồi `python -m pytest scripts/assessment/data/test_tools.py -q -p no:cacheprovider --junitxml=<private>/tests.xml`. Bộ kiểm tự tạo/cấp phiên/smoke/cleanup dataset local; raw logs và session giữ private. Không dùng lệnh này trên AWS hoặc DB demo.

prepare-handoff.ps1 mặc định yêu cầu cửa sổ14400giây (4giờ); helper Python trực tiếp mặc định3600giây. Chọn thời lượng bao trùm bài đo cộng phần dự phòng; không sửa TTL app hoặc kéo dài expires_at trong file. Cấp gói production sát lịch C3 sau kiểm readiness, không phát lại token local đã bị cleanup. SQL verify-batch.sql nhận CSV UUID user_ids/event_ids/room_ids từ manifest; không còn tham số batch_prefix. Muốn kiểm production phải truyền danh sách từ manifest private đúng batch, không dùng ID theo tên tìm kiếm.

Sáu ca dùng nguồn mạng đã được thu hồi theo yêu cầu người dùng; không còn là fixture nghiệm thu hiện hành. Kiểm web dùng ca demo có sẵn; ≥100 phiên AWS cho ca tải riêng đã smoke, còn xác nhận bàn giao độc lập của Người3 chưa có.

## Ca tải riêng có backup — cập nhật 21/11/2026

Yêu cầu mới đã được thực hiện bằng `demo_backup.py`, `protect-backup.ps1`, `isolated_load.py` và hai runner `prepare-isolated-one-off.ps1` / `run-isolated-load.ps1`. Các ghi chú “chưa có 100 phiên AWS mới” phía trên là lịch sử; gói mới đã smoke AWS, còn việc Người 3 xác nhận nhận gói vẫn chờ. Quy mô/thời hạn và backup ở [dataset](../../../docs/assessment/functional/dataset.md).

**Backup hiện có:** `.local/assessment/demo-load-20261121a/backup-manifest.private.json` chỉ tới logical dump AES-GCM và các version ảnh S3, kèm snapshot RDS `labseat-demo-before-load-20261120t201159z`. Thư mục private còn chứa `demo-backup.key`, `source-fingerprint.json`, `demo-fingerprint.json`, `assets-backup.private.json` và kết quả restore. Giữ các file này để khôi phục; không gửi cả thư mục cha cho Người 3.

**Khôi phục khi cần:**

1. Dừng thao tác ghi của bài tải; chọn một DB PostgreSQL 16.13 **mới, rỗng**, không chỉ định DB production. Tải đúng `logical_database.bucket/key/version_id` trong manifest bằng `aws s3api get-object --bucket <bucket> --key <key> --version-id <version> <file-private.aesgcm>`. Đối chiếu SHA-256 ciphertext trong manifest.
2. Giải mã vào thư mục private bằng `protect-backup.ps1 -Mode Decrypt -InputFile <file-private.aesgcm> -KeyFile <demo-backup.key> -OutputFile <restore.dump>`. Công cụ kiểm GCM và SHA plaintext, từ chối ghi đè. SHA plaintext phải trùng dataset.
3. Chỉ trên DB disposable mới đã xác nhận rỗng, nếu dump có `CREATE SCHEMA public`, bỏ schema public rỗng trước bằng `DROP SCHEMA public` (không CASCADE; phải dừng nếu có dữ liệu). Dùng `pg_restore --exit-on-error --no-owner --no-acl --dbname=<DB-moi> <restore.dump>`; cấp role/grant cho DB mới riêng vì dump không mang owner/ACL. Không chạy DROP hoặc `--clean` vào production.
4. Với từng record trong `assets-backup.private.json`, tải đúng `backup_key/backup_version`, đối chiếu SHA/content type rồi phục hồi vào bucket/prefix **mới** tương ứng `reference`. App thử phải trỏ DB và storage thử riêng, email disabled. Kiểm 27 bảng/hash, schema/constraints và 7 truy vấn `scripts/tests/db-invariants.sql`, sau đó smoke app trước khi quyết định dùng bản phục hồi.
5. Lựa chọn thứ hai là restore snapshot RDS sang DB identifier mới, private subnet/security group và secret thử riêng. Lượt này **chưa kiểm restore snapshot RDS**, chỉ logical dump đã được restore thực. Không tự đổi endpoint/secret production. Sau sự cố, việc chuyển production sang bản phục hồi cần được chốt cùng nhóm để tránh ghi đè dữ liệu mới hơn backup.

**Cấp lại phiên và đóng gói:** mở tunnel SSM RDS local 15432 như quy trình đang dùng; có Docker image client `labseat-assessment-b1b2:local`, AWS CLI profile `labseat` còn hạn. Runner kiểm account, TLS/host, backup verified, demo fingerprint, cửa sổ/TTL và ownership UUID. Khi dùng đường dẫn AWS CLI đầy đủ, thêm `-Aws '<path-to-aws.exe>'`.

```powershell
# Không prepare lại bộ demo. Ca tải hiện tại đã tồn tại; không cần chạy prepare nữa.
./scripts/assessment/data/run-isolated-load.ps1 -Stage verify -Batch demo-load-mechanic21
./scripts/assessment/data/run-isolated-load.ps1 -Stage sessions -Batch demo-load-mechanic21 -MinimumValidSeconds 14400 -Execute
./scripts/assessment/data/run-isolated-load.ps1 -Stage smoke -Batch demo-load-mechanic21 -MinimumValidSeconds 14400 -Execute
```

`sessions` thu hồi/thay thế chỉ 100 phiên của batch tải rồi ghi TTL thực, không kéo dài TTL app. `smoke` kiểm 100 danh tính và một vòng đặt/hủy, kiểm worker email disabled ổn định trước khi xác nhận, rồi tạo lại ZIP private gồm đúng 4 file bàn giao. Nếu phiên hết hạn, chỗ đang chiếm hoặc demo/schema thay đổi, công cụ dừng; không sửa file hạn phiên để bỏ qua guard. Gói Mechanic hiện tại hết hạn22:13:07 ngày21/11/2026, giờ Việt Nam; chạy sau hạn hoặc không đủ cửa sổ phải cấp lại và smoke mới.

Người 3 giải nén ZIP private, kiểm `manifest.mapping`, TTL và 100 phiên trước bài đo; truyền `BASE_URL=https://labseat.id.vn`, `SESSION_ID=3d7ca8f8-07fa-508e-abc7-3f0a7bf69d46`, `SESSIONS_FILE=<path/synthetic-sessions.json>` cho kịch bản hỗ trợ file phiên. `platform.js` hiện yêu cầu admission-off; queue đang bật nên cần phối hợp cửa sổ/chính sách trước khi chạy. `booking.js` nhận trực tiếp `SESSIONS_FILE`; `ACCOUNTS_FILE` là chế độ đăng nhập tùy chọn khi không dùng phiên cấp sẵn. Không tự bật email, sửa script của Người 3 hoặc chạy tải trong bước chuẩn bị này. Người 2 cấp lại gói khi Người 3 cần; chưa nhận biên bản bàn giao từ Người 3 thì không ghi đã nghiệm thu.

**Sau khi Người 3 xác nhận đã dừng bài tải:**

```powershell
# Xem đúng phạm vi trước; chưa xóa khi thiếu -Execute.
./scripts/assessment/data/run-isolated-load.ps1 -Stage cleanup -Batch demo-load-mechanic21 -ManifestId 0a59f708-244e-5d0d-80d1-c3907727db17
# Chỉ thực thi sau bài đo:
./scripts/assessment/data/run-isolated-load.ps1 -Stage cleanup -Batch demo-load-mechanic21 -ManifestId 0a59f708-244e-5d0d-80d1-c3907727db17 -Execute
```

Cleanup kiểm quan hệ chéo, chỉ xóa 100user/event/ca/phòng/4vùng của batch Mechanic và dữ liệu con của UUID scope mới; chạy lại an toàn. Đối chiếu demo nghiệp vụ và 7 invariants trong cùng lượt, giữ backup và ảnh demo. Không truncate/reset. Queue lease được rời qua API khi smoke; các key cache của ca riêng có TTL, nếu phải dọn ngay chỉ xóa 5 key suffix `seq/waiting/admitted/entries/seen` của đúng epoch + SESSION_ID qua operator được phép, không xóa `labseat:queue:ready` hoặc đổi policy toàn hệ thống. Đây là bước sau tải, chưa chạy trên AWS; dry-run hiện chỉ thấy scope mới và các reservation smoke đã hủy.

Test an toàn của công cụ mới: `python -m pytest scripts/assessment/data/test_isolated_load.py -q -p no:cacheprovider` chỉ chạy khi APP_ENV=test, DATABASE_URL=TEST_DATABASE_URL kết thúc `_test`, host `backup-verify-db` disposable. Kiểm enum constraint normalization fail-closed, prepare idempotent, 100 phiên/chỗ riêng, từ chối cleanup khi có lịch ngoại scope, cleanup lặp lại và giữ nguyên toàn bộ 27 bảng. Không chạy test này vào DB demo.

### Cấu hình hiện hành: Mechanic riêng, giữ nguyên demo

Batch `demo-load-mechanic21`, 4vùng ×45 =180 suất; poster/sơ đồ sao chép riêng từ Practice10. Nguồn demo vẫn4×17=68 và CANCELLED. Mapping100 dòng,25user/vùng; không yêu cầu100seat_id khác nhau vì vùng phòng có nhiều suất. `platform.js` kiểm100token/CSRF/user riêng và tổng người gán không vượt remaining capacity.

Stage `mechanic-map` có ownership/cross-scope/history guards, copy và kiểm hash ảnh. Không chạy stage này khi đang có vé hoạt động hoặc bài tải đang chạy. Ca Vật lý cũ đã cleanup; không chạy lại `physics-map` để tái tạo nó. Runner mặc định batch Mechanic; mọi lệnh bàn giao/cleanup vẫn nên ghi rõ `-Batch` và manifest.

Ba test an toàn chọn lọc trên backup restore PostgreSQL16.13 đạt3PASS: enum fail-closed; fixture/session/cleanup guard; clone Mechanic/idempotency/100phiên và bảo toàn demo. Test disposable không thay smoke AWS. Xem cấu hình, hạn phiên và trạng thái cleanup thực tại [dataset](../../../docs/assessment/functional/dataset.md).

## Trạng thái sau lượt C3 ngày21/11

Batch `demo-load-mechanic21` đã cleanup sau các bài đo; ZIP/phiên cũ không còn hợp lệ. Các lệnh verify/sessions/smoke phía trên mô tả thao tác khi fixture còn tồn tại. Muốn chạy lại phải có backup được kiểm chứng, prepare một fixture riêng với CloseAt mới, áp dụng mechanic-map rồi cấp phiên/smoke; không sửa ca demo. Không chạy cleanup hoặc nhận gói cũ là sẵn sàng cho lượt mới.

## Gói hiện hành22/11 — thay ca Mechanic404 đã thu hồi

Batch `demo-load-mechanic22` đã prepare/mechanic-map trênAWS,180suất, không sửa ca Mechanic demo. Không prepare lại hoặc dùng ID/ZIP21/11. [ID/hạn phiên/backup đã kiểm](../../../docs/assessment/functional/dataset.md#bàn-giao-cấp-lại-ngày22112026--mechanic-riêng-mới). ZIP runtime hiện hành chứa đúng `load/manifest.json`, `load/synthetic-sessions.json`, `load/smoke-result.json`, `handoff-status.private.json`; thay gói flatunderscore trước đó. Giải nén vào thư mục batchprivate trên máy chạy, giữ nguyên cấu trúc load/. Trỏ SESSIONS_FILE vào load/synthetic-sessions.json, không đổi nội dung token/expiry.

Khi cần cấp lại, dừng lượt đo cũ, mở tunnelSSM/TLS và dùng `run-isolated-load.ps1 -Stage sessions -Batch demo-load-mechanic22 -MinimumValidSeconds 21600 -Execute`, rồi `-Stage smoke` cùng batch/minimum. Đóng lại gói4file/checksum sau smoke; chạy `runtime-handoff.private.py` trong thư mục private batch của Người2 để kiểm lại100phiên qua HTTPS và tạo ZIP runtime đúng4đường dẫn; đối chiếu runtime-handoff-receipt.json và file .zip.sha256. Cấp lại thu hồi100phiên cũ; phải báo người chạy dùng ZIP mới. Các lệnh batch21/11 bên trên chỉ còn là lịch sử. Load-master/backupkey tách khỏi ZIP, không gửi cả thư mục private hoặc commit credentials. Lượt22/11 mới chuẩn bị, chưa chạy chịu tải và chưa cleanup.
