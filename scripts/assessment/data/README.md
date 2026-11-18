# B2 — Ảnh sơ đồ và gói dữ liệu/session bàn giao

Đầu ra hướng dẫn/session helper trong thư mục data theo B2 của [kế hoạch sprint](../../../docs/sprints/ke-hoach-nghiem-thu-4-ngay.md). B1 được ghi tại [dataset.md](../../../docs/assessment/functional/dataset.md). Hiện trạng và bằng chứng dưới đây đối chiếu ngày **18/11/2026**; không phải xác nhận phiên vẫn còn hiệu lực ở lần sử dụng tiếp theo.

## Bước 1. Chuẩn bị và ghi nguồn ảnh

Yêu cầu sprint: tìm 6 ảnh sơ đồ có nguồn/quyền dùng, ghi URL, giấy phép và thao tác chỉnh sửa trong [assets-sources.csv](../../../docs/assessment/functional/assets-sources.csv). Phân biệt ảnh sơ đồ với poster; không dùng dữ liệu phòng nhạy cảm. Chỉ đưa ảnh được phép phân phối vào Git.

Đã làm: tích hợp poster và sơ đồ người dùng cung cấp cho cả 12 ca. File nguồn hiện ghi nhiều phiên bản ảnh lịch sử. **Còn thiếu:** URL gốc/giấy phép cho yêu cầu 6 ảnh trên mạng và đánh dấu rõ phiên bản đang dùng. Ảnh được người dùng gửi để demo chưa phải bằng chứng về quyền phân phối trong Git.

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

**Điểm phải xử lý trước khi chạy lại:** `assert_owned()` còn yêu cầu prefix tên event, trong khi các tên đã đổi trên web. Stage `sessions` có thể bị từ chối dù UUID đúng. Cần thay kiểm tra tên bằng kiểm tra ownership tương đương và kiểm trên DB disposable, không bỏ guard.

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

**Cần sửa trước khi smoke lại:** bảng số vùng hard-code chưa có `elec` (18), `physics` (34), `chemistry` (42), nên fallback 4–8 vùng báo lỗi với bộ mới. Cần kiểm theo manifest/UUID/capacity thực tế.

Sau khi xử lý guard và smoke, quy trình đã dùng trên Windows là giữ tunnel SSM đến RDS ở cổng 15432, rồi chạy:

```powershell
./scripts/assessment/data/prepare-handoff.ps1 -Batch b1b2-20261117a -Execute
```

Có thể truyền `-Aws <đường-dẫn-aws.exe>`, `-Profile`, `-Region`, `-TunnelPort` theo môi trường. Helper cần Docker image client `labseat-assessment-b1b2:local` và quyền AWS phù hợp. Không đưa DATABASE_URL/token/password vào tài liệu hoặc log.

Để kiểm riêng gói mới sau khi sửa helper:

```text
python scripts/assessment/data/smoke_sessions.py .local/assessment/b1b2-20261117a --base-url https://labseat.id.vn
```

Bàn giao qua kênh riêng cho Người 3: manifest, file session, tài khoản cần thiết, `SESSION_ID` lịch tải, TTL và kết quả smoke. `platform.js` nhận `SESSIONS_FILE` và `SESSION_ID`. Người 3 phải dùng được gói mà không tự sửa seed.

## Điều kiện đóng B2

- [ ] Nguồn/quyền dùng ảnh và phạm vi 6/12 ảnh được chốt.
- [ ] Có bằng chứng luồng admin upload/nhận diện/chỉnh vùng theo tiêu chí đã chốt.
- [x] 12 sơ đồ/poster hiện hành tải được; mapping đã đối chiếu ngày 18/11.
- [ ] Guard/helper smoke hoạt động với ca đổi tên và bộ ảnh hiện tại.
- [ ] Cấp lại ≥100 session distinct, readiness/TTL đạt, smoke đọc/ghi mới thành công.
- [ ] Người 3 nhận và dùng được gói bàn giao; phiên bản source/script được chốt.

Chưa đánh dấu B2 hoàn tất. Xem [bằng chứng số liệu](../../../evidence/assessment/b1b2-20261117a/summary.md).
