# B3 — Kiểm thử chức năng, regression và demo

## Mục tiêu

Thực hiện đúng **Prompt AI B3** trong [sprint](../../sprints/ke-hoach-nghiem-thu-4-ngay.md#b3-kiểm-thử-chức-năng-regression-và-demo): dùng dataset B1/B2, kiểm nghiệp vụ LABSEAT thật, ma trận expected/actual/evidence; phân biệt local/emulation/thiết bị thật; email giới hạn; SQL invariants read-only. Không chạy truncate/reset trên AWS.

**Chưa chốt toàn bộ B3.** Đã có kết quả chức năng/regression; X01 đang thu cửa sổ C3 thực và chưa chốt hậu kiểm hồi phục; X02/X03 chờ fault/restore, V01 chờ video người dùng cung cấp. Không đổi các mục đó thành PASS. Lần gom đầu ra `20261119T034356Z-b3-functional` không phải lần chạy lại test.

**Cập nhật sau retest21/11/2026:** ma trận344 dòng hiện **340 PASS,0 FAIL,1 BLOCKED (V01),3 NOT_RUN (X01–X03)**. Có7case AWS bổ sung dùng SAT demo có sẵn;333PASS trước đó vẫn giữ môi trường/provenance riêng. Các lỗi regression/fixture R001/R004/R006/R009 đã được xử lý và chạy lại đạt; chi tiết ở cuối báo cáo. Những số329 PASS/3 FAIL/2 BLOCKED bên dưới mô tả các lượt lịch sử trước retest, không phải tồn đọng hiện tại.

## Cấu hình

- AWS HTTPS: `https://labseat.id.vn`; run lịch sử API task definition `labseat-lab-api:10`, digest ghi trong [manifest](../../../evidence/assessment/20261119T034356Z-b3-functional/manifest.json).
- Regression: Python 3.12, PostgreSQL 16.16, Redis 7.4.11 disposable; database test/hostname test-db, không dùng DB AWS cho fixture destructive.
- Desktop: Edge/Playwright Core 1.65.1; controller Node offline tách khỏi HTTP thật.
- Điện thoại: iPhone XR/iOS/Safari theo người dùng và audit server; chưa có version OS/browser cụ thể hoặc video điện thoại mới.
- Bài bổ sung ngày 19/11 dùng hai lịch **Kì thi SAT - Ca demo** có sẵn, không tạo ca mới. Mật khẩu student475 hiện do người dùng tự chọn, không dùng lại password fixture cũ.
- Kết quả lịch sử trước đó có dùng ca synthetic B3, đã dọn theo yêu cầu. Không tái tạo các ca này để dựng bằng chứng mới.

## Cách kiểm và chạy lại

Ma trận [test-cases.csv](test-cases.csv) dùng đúng cột sprint: `case_id,task_id,scenario,preconditions,steps,expected,actual,status,evidence,issue`. Môi trường/role ghi trong preconditions; không dùng kết quả disposable làm bằng chứng đã chạy AWS.

- Regression: dùng suite có sẵn trong `tests/app` và `tests/app/ui.test.mjs`, chỉ trên runtime/DB/Redis disposable được guard cho phép. Sửa fixture avatar được giữ trong `tests/app/test_avatars.py`.
- AWS: dùng tài khoản B1/B2 đúng quyền; kiểm API trực tiếp và UI, hold/confirm/cancel, QR, realtime hai browser, CSV. Khi chạy lại phải dùng tài khoản còn hợp lệ và có lịch sử đúng bài; không dùng session/password đã bị reset hoặc ca đã xóa.
- Race suất cuối lịch sử chạy disposable; lượt bổ sung21/11 đã chạy concurrent HTTPS thật trên SAT demo:45suất giữ nguyên,43vé thử chuẩn bị, hai contender tranh suất cuối cho200/409 sold_out. Đã hủy/dọn đúng vé thử; không nhận đây là bài tải C3.
- Mail thật: cửa sổ riêng đã được người dùng cho phép, queue drain/quota trước gửi; hai API request bình thường qua publisher → SQS → worker Brevo, quan sát callback và người nhận. Không tự gửi lại job SKIPPED.
- Trước/sau tải/fault/restore: dùng `scripts/tests/db-invariants.sql` và probe nghiệp vụ đúng window ID/phase/target. Chỉ lấy kết quả các cửa sổ đã thực sự chạy theo ủy quyền; không đổi trạng thái dựa trên runbook dự kiến.

## Kết quả thực tế và bằng chứng

| Nhóm B3 | Kết quả đã có | Evidence |
| --- | --- | --- |
| Account/login/logout/profile/verify/reset; khóa user | API auth/profile/lock đã kiểm. Người dùng xác nhận reset và login student475 bằng mật khẩu tự chọn; server challenge consumed/session cũ revoked. | [API](../../../evidence/assessment/20261119T034356Z-b3-functional/checks/results.json#/api), [reset/login](../../../evidence/assessment/20261119T034356Z-b3-functional/checks/results.json#/reset_login), [mail](../../../evidence/assessment/20261119T034356Z-b3-functional/checks/results.json#/email) |
| Quyền UI/API ba vai | API trái quyền bị chặn; bổ sung 24 assertions menu/deep link ba vai. | [API](../../../evidence/assessment/20261119T034356Z-b3-functional/checks/results.json#/api), [UI](../../../evidence/assessment/20261119T034356Z-b3-functional/checks/results.json#/ui_and_qr) |
| CRUD event/lịch/ảnh/phòng; trùng lịch | Có assertions tạo/sửa/xóa, input sai, sửa sơ đồ/capacity và guard lịch. | API; [regression](../../../evidence/assessment/20261119T034356Z-b3-functional/checks/results.json#/regression_junit_xml) |
| Admission/heartbeat/expiry | Join AWS; FIFO/heartbeat/lease expiry/rejoin/fail-closed trong regression. | API; regression; [controller](../../../evidence/assessment/20261119T034356Z-b3-functional/checks/results.json#/node_ui_log) |
| Hold/confirm/cancel/replay/race/hết chỗ/hết hạn | HTTPS có giữ/xác nhận/hủy/replay; race/expiry/suất cuối được kiểm disposable, không nhận là tải C3. | API; regression |
| QR/check-in sai ca/đóng/lặp | Có mã sai, scope, đóng/lặp. Bổ sung payload QR SAT nhập khi chọn lịch SAT khác: từ chối, ẩn xác nhận, không POST check-in, vé vẫn CONFIRMED. Đây là lookup mã QR, không phải lần quét camera mới. | [UI/QR](../../../evidence/assessment/20261119T034356Z-b3-functional/checks/results.json#/ui_and_qr), [phone](../../../evidence/assessment/20261119T034356Z-b3-functional/checks/results.json#/phone), API |
| Realtime hai browser; CSV | Browser độc lập cập nhật không reload; admin CSV đúng vé, student bị từ chối. | [browser](../../../evidence/assessment/20261119T034356Z-b3-functional/checks/results.json#/browser), [SAT realtime](../../../evidence/assessment/20261119T034356Z-b3-functional/checks/results.json#/realtime), API |
| Mail giới hạn, quota, callback, Inbox/Spam | Hai thư bổ sung DELIVERED, một attempt/thư, tổng attempts 2; người nhận xác nhận cả hai Inbox. Quota trước gửi 300. Email đã tắt lại. | [mail](../../../evidence/assessment/20261119T034356Z-b3-functional/checks/results.json#/email) |
| Invariants | Bảy truy vấn zero rows trong các snapshot B3 đã lưu. Không thay kết quả trước/sau fault/load/restore. | [invariants](../../../evidence/assessment/20261119T034356Z-b3-functional/checks/results.json#/invariants) |
| Probe tải/fault/restore | X01–X03 NOT_RUN; người dùng xác nhận chưa có lịch. | CSV |
| Video student → admin/staff check-in | V01 BLOCKED, chờ người dùng cung cấp. Không nhận hai ảnh hoặc video cũ là video mới hoàn chỉnh. | [manifest](../../../evidence/assessment/20261119T034356Z-b3-functional/manifest.json), [kịch bản](demo-script.md) |

Ma trận lịch sử trước retest: **329 PASS, 3 FAIL, 3 NOT_RUN, 2 BLOCKED** (số dòng assertion/bằng chứng, không phải số yêu cầu độc lập). Toàn suite lịch sử: 275 PASS, 15 SKIP, 0 FAIL/ERROR; Node 39 PASS; API 33 PASS; browser 5 PASS. [Regression summary](../../../evidence/assessment/20261119T034356Z-b3-functional/checks/results.json#/regression_summary). 48 dòng kiểm deploy/migration/recovery/maintenance ngoài B3 đã bỏ khỏi ma trận; không xóa test gốc.

Hai ảnh người dùng đã nhận: [reset thành công](../../../evidence/assessment/20261119T034356Z-b3-functional/screenshots/password-reset-success.png) và email SAT có QR/nhãn Inbox. Bản email nguyên gốc chứa QR vé chưa check-in giữ private; nguồn/hash ở manifest. Đã thêm bản che QR/mã đăng ký theo yêu cầu người dùng; bản che là ảnh dẫn xuất có hỗ trợ AI, không thay thế bản gốc hoặc log giao thư. Không yêu cầu ảnh riêng cho mọi test khi đã có log hoặc video rõ ràng.

## Hạn chế và lỗi

| Mục | Mức độ / ảnh hưởng | Cách kiểm hoặc xử lý |
| --- | --- | --- |
| X01–X03 chưa chạy | Chưa đủ bằng chứng nghiệm thu phần cửa sổ phối hợp | Chạy probe nghiệp vụ và bảy invariants đúng trước/sau C3/C4/C5/B4/B5 khi nhóm có lịch. |
| Video chưa được cung cấp | Chưa đủ demo theo prompt | Người dùng gửi video trọn luồng trên ca có sẵn; ghi link kho nhóm/quyền truy cập/thời lượng. |
| Optional regression bổ sung | Retest21/11: avatar5, camera19, map5, profile5 đều PASS | Đã xử lý fixture/kỳ vọng test; giữ nguyên kết quả lỗi lịch sử và bằng chứng lượt mới ở cuối báo cáo. |
| Schema metadata | Đã lấy thêm bằng truy vấn read-only | RDS trả 0002_platform ngày 19/11/2026 lúc 04:01:04 UTC. Đây là snapshot hiện tại, không ghi ngược là đã thu tại run lịch sử. |
| Fixture avatar thiếu clean_db ban đầu | Lỗi thiết lập test, không phải lỗi runtime critical | Đã import fixture clean_db để mỗi test có dữ liệu sạch; suite cuối không còn fail/error. Chỉnh tên parameter chỉ phục vụ log đã hoàn nguyên vì không cần cho đầu ra B3. |
| Mật khẩu thử login 401 | Không xác nhận là lỗi sản phẩm | Người dùng chọn mật khẩu khác, đã xác nhận login; giữ log trung thực và phân biệt xác nhận thủ công. |

Chưa có lỗi runtime critical được xác nhận từ các case đã PASS. Không triển khai release app mới trong B3; nếu phát hiện/sửa lỗi runtime phải ghi release và nhờ C3 đo lại phần liên quan theo sprint.

## Hoàn tác và trạng thái cuối

Phân công staff bổ sung tạm để kiểm sai lịch đã gỡ; không check-in vé SAT của người dùng, vé vẫn CONFIRMED ở snapshot cuối. Email trở về worker revision 10/backend disabled sau hai thư, không phát lại skipped jobs. Mật khẩu tự chọn của student475 được giữ, không thu thập hoặc thay lại.

Đầu ra B3 chỉ gồm ba file functional/test-cases.csv, report.md, demo-script.md, cùng một thư mục bằng chứng `20261119T034356Z-b3-functional` có manifest/summary đúng quy cách chung. Đã xóa ba cây evidence cũ, các script/debug/backup trung gian thừa, hai script probe chưa dùng và video tự tạo cũ; không đụng tài liệu B1/B2, input ảnh của người dùng hoặc test gốc. Video để người dùng cung cấp sau.

Bộ thay đổi Git ban đầu sau dọn: ba tài liệu B3; năm file evidence (manifest.json, summary.md, checks/results.json, ảnh reset, ảnh email đã che); một dòng sửa fixture test_avatars.py. Các log/assertion được gom nguyên nội dung trong results.json, các mục CSV trỏ tới section bằng JSON pointer. Một dòng import clean_db được giữ vì thiếu nó làm các test avatar dùng trùng dữ liệu và lỗi; không sửa chức năng/runtime hoặc chỉ tiêu nghiệm thu.

### Ảnh email vé đã che thông tin

![Email xác nhận SAT — đã che QR và mã đăng ký](../../../evidence/assessment/20261119T034356Z-b3-functional/screenshots/sat-ticket-email-redacted.png)

Bản che thông tin có hỗ trợ imagegen; không dùng bản dẫn xuất để xác minh pixel hoặc dữ liệu ngoài hai vùng cần che. Bản gốc riêng/hash và callback/Inbox là nguồn đối chiếu chính. Ca SAT, ngày 23/11/2026, giờ 14:14–16:14 và phòng 72A+72B (A2-411) được đối chiếu với ảnh gốc.

## Phối hợp B4/B5 sau kiểm tra GitHub ngày 19/11/2026

Nhánh assessment/architecture ở b9bd5ab mới có A1; main ở ff2bb56 có A1 bàn giao cuối, A2 Hava và A3 ERD/sequence/ADR bản review. Chưa tìm thấy bằng chứng A4/C3/C4/C5 trên các remote đã kiểm. Các script tải có sẵn không chứng minh đã chạy tải hoặc fault; không suy thành viên chưa làm nếu họ chưa push. [Chi tiết nguồn](../../../evidence/assessment/20261119T034356Z-b3-functional/checks/results.json#/github_dependency_review).

Theo chỉ đạo người dùng mới nhất, phần chưa có kết quả được chờ theo kế hoạch. B4 ghi phụ thuộc diễn tập sau các fault ổn định; vì vậy chưa tạo DB/app/secret restored, chưa ghi incident/marker hay đo RPO/RTO. B5 cần app dùng DB restored nên cũng chưa thực thi. X01–X03 vẫn NOT_RUN.

Preflight kỹ thuật đã đọc AWS: source RDS available/private/encrypted/Multi-AZ, PostgreSQL16.13/db.t4g.micro, retention1 ngày, có LatestRestorableTime; quota DB còn39; class gp3 có thể đặt; KMS enabled; S3 versioning Enabled/public-block bật; mô phỏng IAM cần thiết allowed; ECS API/worker/publisher stable2/1/1. Quyền mô phỏng không được ghi thành restore PASS. SQL read-only trả schema0002_platform và bảy invariants zero rows. [Preflight](../../../evidence/assessment/20261119T034356Z-b3-functional/checks/results.json#/recovery_preflight).

Chưa phát sinh DB restored, không có phí lưu DB tạm từ lượt preflight này. Khi đủ điều kiện sẽ dùng DB/app/secret riêng, không đổi endpoint production; tạo đúng đầu ra recovery B4/B5 mà sprint yêu cầu và cleanup theo ID sau giữ bằng chứng.

## Lượt optional regression bổ sung ngày 19/11

Đã chạy 12 module browser cùng 6 bài SQS/Redis trên container riêng. Đây là lượt bổ sung cho 15 mục SKIP lịch sử, không phải chạy lại toàn bộ suite. Không thay đổi AWS, không gửi mail, không tạo ảnh/video. Kết quả từng assertion và timestamp tại [remaining_regression](../../../evidence/assessment/20261119T034356Z-b3-functional/checks/results.json#/remaining_regression).

- PASS: browser HTTP, queue, registration, event discovery, login modal, platform, refresh, UI và SQS/Redis restart/OOM.
- Avatar: 5 FAIL do bài đăng ký không điền email/họ tên bắt buộc; chưa tới bước upload. Mức độ: lỗi thiết lập bài test, chưa kết luận runtime. Repro: chạy test_avatar_browser với BROWSER_BASE_URL local.
- Profile: BLOCKED, generic seed không tạo profile-admin nên 5 login assertion trả 401. Cần fixture riêng trước khi kiểm tiếp.
- Map: 5 FAIL tại assertion số option editor-event sau lưu; thực tế 8 option, kỳ vọng tính từ danh sách admin. Mức độ: chưa phân loại lỗi sản phẩm; cần đối chiếu lọc quyền/event. Repro: test_image_map_browser trên seed local.
- Camera: 18 PASS, 1 FAIL ở test_navigation_stops_live_tracks: Playwright wait_for_function bị CSP chặn unsafe-eval. Mức độ: tương thích harness; không tắt CSP để ép PASS. Fake media không thay thế kiểm điện thoại thật.

Giữ kết quả chưa đạt trong ma trận; chưa thể chốt B3 ngoài phần video và cửa sổ phối hợp. Chỉ sửa môi trường build test (pin python slim-bookworm, timeout tải Playwright); chưa sửa hay phát hành runtime nên chưa có release mới để nhờ C3 đo lại.

## Sử dụng C1 bàn giao cho B3 —20/11/2026

Đã đọc [C1 của người3](https://github.com/tuanngthuet/CloudCompuAssignment/blob/7fa878ac7e7995c25777680e44fe2da36d1e619c/docs/assessment/performance/observability.md) tại7fa878a và chạy nguyên collector/chart/runner từ bản source private đã kiểm hash. [Smoke và DB supplement](../../../evidence/assessment/20261119T172832Z-b4-c1-preflight/checks/results.json):4 mẫu/252 dòng,0 lỗi API; có missing metrics và1 vòng vượt30s. Đây là cửa sổ quan sát riêng, không phải bài C3/C4/C5 hoặc restore.

C1 hỗ trợ ghép timestamp/source_at, task/EC2/target và dependency metrics với probe nghiệp vụ/invariants của B3. Probe SQL nguồn trong smoke trả7 invariants zero rows, nhưng không chứng minh kết quả trước/sau tải/fault/restore. X01–X03 vẫn NOT_RUN. Khi có cửa sổ thật, ghi run ID/phase/target/digest và thực hiện business probes cùng SQL đúng trước/sau; không lấy metrics, health200 hoặc ảnh Console thay kết quả nghiệp vụ. Không thay kết quả các lượt B3 lịch sử.

## Đối chiếu A4 của người1 —20/11/2026

Đã đối chiếu [bàn giao A4](../architecture/a4/handoff.md) và [rà soát bằng chứng](../architecture/a4/evidence-review.md) tại commit `39f7ab1cd3cdd925e55fae5c13b0a6a541e8fa3a`. Theo sprint, A4 nhận kết quả B/C để tổng hợp kiến trúc; A4 không phải một lượt kiểm thử mới hoặc điều kiện bổ sung cho B3. Nhận xét chưa có A4 ở phần rà soát GitHub ngày19/11 chỉ áp dụng tại thời điểm đó.

Gói snapshot mà A4 đã đọc thiếu CSV; bản chuẩn nằm tại [test-cases.csv](test-cases.csv), hiện có337 dòng:329 PASS,3 FAIL,2 BLOCKED,3 NOT_RUN. Đây là nguồn để người1 đối chiếu lại ma trận, không cần tạo CSV thứ hai. X01 (sau tải), X02 (sau fault), X03 (sau restore) vẫn NOT_RUN; video vẫn chờ người dùng.

Khi nhận cửa sổ thật, bàn giao người1 đúng run ID/phase, commit của công cụ và digest/schema của app được kiểm, mốc UTC, probe nghiệp vụ và invariants trước/sau, liên kết metrics có source_at/status và cleanup/rollback. Phân biệt commit đóng gói tài liệu với commit chạy test; không ghi timestamp gom báo cáo là timestamp mọi test. Giữ bằng chứng trong thư mục run theo sprint và dẫn từ ba output B3 hiện có.

## Phối hợp C2 cho B3 —20/11/2026

Đã đọc [runbook C2](https://github.com/tuanngthuet/CloudCompuAssignment/blob/09f768e168e03517a1636c1030059a7fd915b58a/docs/assessment/performance/runbook.md) và [smoke local](https://github.com/tuanngthuet/CloudCompuAssignment/blob/09f768e168e03517a1636c1030059a7fd915b58a/evidence/assessment/20261120T130757Z-c2-local/summary.md) của người3. Liên quan trực tiếp theo prompt B3: không gửi verify/reset/vé thật trong cửa sổ disabled; mail thật phải kiểm riêng khi Brevo bật, trong tổng hạn mức20 thư và quota còn lại, có callback và xác nhận Inbox/Spam.

C2 có7 test HTTP mô phỏng PASS cho booking sessions/credentials, CSRF, TTL và user riêng; chưa có smoke k6 AWS, job SKIPPED hay lượt switch/restore worker được kiểm chứng. Ảnh cấu hình revision11/Brevo không chứng minh service đã chuyển khỏi revision10/disabled. Các kết quả này không thay test API/UI/concurrency hoặc mail thật của B3 và không đổi trạng thái ma trận.

Trước X01/X02, người3 bàn giao run/phase/UTC, worker baseline và task chạy thực/digest, queue/job/attempts và bằng chứng không gửi trong cửa sổ. B3 vẫn kiểm nghiệp vụ/invariants trước–sau tải/fault. Khi kết thúc, đối chiếu drain job thử và trạng thái cuối với C2, không replay thư SKIPPED. Nếu cần kiểm mail sau restore backend, dùng giao dịch mới và tính chung hạn mức B3; không tự gửi lại hai thư B3 đã có bằng chứng. B2 cấp phiên mới sát giờ khi cần chạy script C2;100 phiên cũ đã hết hạn không được dùng để chốt readiness. Lượt đọc tài liệu này không cấp lại session, đổi worker hoặc gửi mail; giữ email disabled theo chỉ đạo hiện tại.

## Bàn giao C3/C4 mới cho B3 —21/11/2026

Nguồn người3 tại commit `c12a252e2b49b876dcdb1a1575d4462526cc0d03`: [C3 load-report](https://github.com/tuanngthuet/CloudCompuAssignment/blob/c12a252e2b49b876dcdb1a1575d4462526cc0d03/docs/assessment/performance/load-report.md), [C4 failover-report](https://github.com/tuanngthuet/CloudCompuAssignment/blob/c12a252e2b49b876dcdb1a1575d4462526cc0d03/docs/assessment/performance/failover-report.md). Đây là chuẩn bị và preflight chỉ đọc ngày20/11, không phải tải hoặc fault đã chạy. Năm bài C3 AWS còn NOT_RUN; C4 prepare/inject/observe/rollback chưa chạy. X01/X02 vẫn NOT_RUN, không dùng test script local, GET health200 hoặc ASG activity thay kết quả nghiệp vụ.

| Phần B3 | Bổ sung từ C3/C4 và cách phối hợp |
|---|---|
| X01 trước/sau tải | C3 yêu cầu smoke nghiệp vụ và bảy invariants đúng run/digest trước tải, kiểm lại sau từng mức và sau recovery. Xác nhận phiên B2 còn TTL, user/seat riêng và lịch còn mở;100 phiên cũ hết hạn. Platform cần queue OFF, Admission cần ON có audit; ghi baseline và kiểm khôi phục policy, không đổi policy trong lượt rà soát này. |
| X02 trước/sau fault | Người2 cung cấp probe synthetic nhẹ và invariants; người3 thu target/task/replacement/HTTP timeline, rollback và baseline hai AZ. Kiểm không mất vé/oversell; phân biệt lỗi tạm trong fault với kết quả sau ổn định. Chưa có incident hoặc lượt probe C4 thật để điền actual/PASS. C5 chưa có kết quả trong commit này. |
| Chất lượng timestamp | Runner người3 chưa đồng bộ Windows Time, nên UTC tự ghi không đủ làm mốc incident/recovery; cần sửa và xác minh độ lệch trước cửa sổ thật. Giữ source_at/status của metrics; thiếu/chậm không đổi thành0. Timestamp ASG do AWS trả không tự biến hoạt động managed scaling thành bài C3/C4. |

Các nội dung trên đã dẫn vào actual/evidence của X01/X02 trong [ma trận](test-cases.csv), giữ nguyên expected/status. Không chạy lại B3 hoặc tạo dữ liệu, ảnh/video hay thao tác AWS trong lượt đối chiếu này.

## Bàn giao C5/C6 cho B3 —21/11/2026

Nguồn người3 tại commit `e2431f306df96abd8043680906e1286243dbf14a`: [C5 readiness](https://github.com/tuanngthuet/CloudCompuAssignment/blob/e2431f306df96abd8043680906e1286243dbf14a/evidence/assessment/20261120-c5-readiness/summary.md), [runbook failover](https://github.com/tuanngthuet/CloudCompuAssignment/blob/e2431f306df96abd8043680906e1286243dbf14a/docs/assessment/performance/fault-runbook.md) và [ma trận C6](https://github.com/tuanngthuet/CloudCompuAssignment/blob/e2431f306df96abd8043680906e1286243dbf14a/docs/assessment/traceability-matrix.md). C5 mới đọc topology/events; RDS và Redis inject đều NOT_RUN, clock runner đang stopped, chưa có probe/invariants cùng cửa sổ. X02 vẫn NOT_RUN; không lấy snapshot hoặc role hiện tại làm kết quả sau fault.

| Cửa sổ X02 | Phần người2 kiểm và bàn giao theo B3/C5 |
|---|---|
| RDS failover | Đọc lại giao dịch/vé đã commit và bảy invariants trước fault; duy trì probe synthetic nhẹ, ghi lỗi/timeout/reconnect và kiểm workflow/SQL sau ổn định. Người3 ghi AZ/events/DNS và thời gian; health200 hoặc DB available chưa đủ kết luận nghiệp vụ phục hồi. |
| Redis failover sau khi RDS/app ổn định | Dùng baseline và run ID riêng; kiểm admission join/wait/grant/heartbeat/expiry, lease/epoch và PubSub/realtime; đối chiếu vé đã commit và không cấp hold vượt capacity. Nếu operator recovery ảnh hưởng thứ tự chờ phải ghi thao tác/thời gian/ảnh hưởng; không hứa state Redis nguyên vẹn. |

Hai bài vẫn nằm trong X02, không thêm case PASS hoặc gộp thời gian thành RTO PITR. Người3 chốt quyền/quota và cửa sổ email disabled; người2 bàn giao probe/SQL đã làm sạch với run/phase/digest/schema và UTC đã đồng bộ. Không tự kích hoạt failover để bổ sung báo cáo.

C6 đối chiếu đúng337 dòng:329 PASS,3 FAIL,2 BLOCKED,3 NOT_RUN; đây là tổng hợp, không phải retest. Phần người2 còn phải bàn giao là triage/retest các lỗi optional/fixture đã ghi ở trên, video do người dùng cung cấp và X01–X03 trong cửa sổ thật. Dẫn bằng chứng từ CSV/report/manifest hiện có; phân biệt commit công cụ, digest được kiểm và commit đóng gói. Không nhận số kiểm link/hash C6 trên workspace người3 là kết quả audit mới của nhánh này, vì C6 ghi nhiều file B chỉ là bản sao untracked.

## Hoàn tất regression có thể tự làm —21/11/2026

Đã xử lý và chạy lại bốn module còn FAIL/BLOCKED trong Docker local, network internal không mở cổng host; PostgreSQL16.16/Redis7.4.11, Python3.12.16, Playwright1.49.1/Chromium. App dùng APP_ENV=test, EMAIL_BACKEND=disabled, storage local; không có publisher/worker gửi mail, AWS calls, runtime deployment hoặc ảnh/video mới. Mốc UTC trong XML thuộc20/11, tương ứng sau00:38 ngày21/11 ở Việt Nam; không dùng thời gian này làm số đo availability/RPO/RTO.

| Case / module | Nguyên nhân và chỉnh sửa | Kết quả mới |
|---|---|---|
| R001 / test_avatar_browser | Bổ sung email đăng ký duy nhất; giữ nguyên email khi lưu tên hiển thị để không vô tình gọi luồng đổi email. full_name không phải trường bắt buộc ở bước đăng ký. |5/5 PASS |
| R004 / test_camera_browser | Dùng Chromium đã cài nếu không chỉ định CHROME_BIN; chờ videoWidth và track ended bằng assertion/evaluate tương thích CSP. Không nới CSP hoặc bỏ kiểm track. |19/19 PASS; camera fake media/API mock, không thay kiểm điện thoại thật |
| R006 / test_image_map_browser | So đúng tập ID admin events có room, gồm fallback session; giữ email fixture, tránh CCCD trùng, tách giờ ca giữa viewport để không trùng lịch của user seed. Giữ kiểm sức chứa, vé/QR và khóa editor sau có vé. |5/5 PASS |
| R009 / test_profile_browser | Dùng admin/password của seed; fixture xác minh student qua account challenge service, chỉ cho APP_ENV=test và DATABASE_URL=TEST_DATABASE_URL kết thúc _test; CCCD duy nhất mỗi case. Giữ kiểm chặn thiếu hồ sơ, resume, lưu/reload và xóa dữ liệu khỏi UI khi logout. |5/5 PASS |

Tổng **34 PASS,0 FAIL/ERROR/SKIP** cho bốn module trong lượt retest; không cộng với34 test công cụ B4 hoặc coi là chạy lại toàn suite. Bảy truy vấn scripts/tests/db-invariants.sql sau lượt profile chạy transaction REPEATABLE READ READ ONLY đều zero rows. [Kết quả mới, từng test/source hash/versions/cleanup](../../../evidence/assessment/20261119T034356Z-b3-functional/checks/results.json#/regression_retest_20261121); phần remaining_regression giữ nguyên các lỗi ngày19/11. Các lượt chẩn đoán trong retest cũng đã có lỗi fixture và rate-limit counters tích lũy; lượt cuối dùng DB disposable mới, không tắt/sửa rate limit. Không đổi FAIL thành PASS dựa vào suy luận.

Để tái tạo: dựng môi trường disposable theo tests/app/browser.Dockerfile, migrate DB *_test và seed admin/6 student với SEED_PASSWORD=BROWSER_TEST_PASSWORD riêng; gán email synthetic duy nhất và email_verified_at cho user seed. Giữ DB/Redis fixture mới giữa các lượt để không kế thừa counters. Chạy từng module bằng `python -m pytest tests/app/test_avatar_browser.py -q -p no:cacheprovider --junitxml=<private>/avatar.xml` và tương tự camera/image_map/profile. Cần BROWSER_BASE_URL trỏ app local, BROWSER_TEST_ALLOWED=local-demo-only, RUN_CAMERA_BROWSER_TESTS=1, DATABASE_URL=TEST_DATABASE_URL, APP_ENV=test, EMAIL_BACKEND=disabled và storage local. Fixture xác minh email của profile là tiền điều kiện local; không nhận là mail thật đã gửi/nhận.

Đã dọn đúng7 container và network có nhãn run; PostgreSQL dùng tmpfs, không tạo volume, không dọn tài nguyên khác. Logs/XML chẩn đoán giữ private, chỉ kết quả/hash đã làm sạch được gộp vào evidence hiện có; không thêm output công khai. C6/A4 đã dẫn ở trên là snapshot trước retest này; người3 cần dùng commit B3 mới khi tổng hợp. **Phần còn lại của B3 chỉ là V01 video và X01–X03 cần cửa sổ phối hợp.** B4/B5 không được chạy vượt thứ tự kế hoạch; trạng thái và RPO/RTO/images_verified giữ nguyên.

## Kiểm lại bằng ca demo có sẵn trên AWS —21/11/2026

Lượt14:23–14:30 dùng **Kì thi SAT - Ca demo**, student498 và staff04/admin có sẵn. UI giữ/xác nhận/hủy, API replay, QR PNG/ownership, CSV và staff lookup đều PASS. Phòng đã hết chỗ không chọn được. Race suất cuối trên capacity45 không sửa lịch/capacity: một200, một409 sold_out; sau hủy các vé thử, remaining trả về44 như trước. Đây là kiểm chức năng AWS, không phải số liệu chịu tải.

[Bảy kết quả và cleanup](../../../evidence/assessment/20261119T034356Z-b3-functional/checks/results.json#/existing_demo_retest_20261121). Đã dọn45reservation thử đã hủy và45job SKIPPED, provider attempts0. Không đổi vé gốc/student475, event/lịch/vùng demo. Verify14:31:07:10bảng nghiệp vụ gốc không đổi (trừ metadata last_activity_at),7invariants0.

![Xác nhận SAT demo có sẵn](../../../evidence/assessment/20261119T034356Z-b3-functional/screenshots/sat-existing-demo-confirmed.jpg)

Sáu ca B2 WEB và ca tải Vật lý cũ đã thu hồi; không dùng ảnh của chúng làm bằng chứng hiện tại. C3 dùng Mechanic riêng180suất; Mechanic demo68suất giữ nguyên. Xem [dataset](dataset.md) để lấy ID/hạn phiên hiện hành. V01 vẫn chờ video; staff lookup lượt này không thay camera điện thoại thật. X01 chưa đóng vì mới có tải nền, chưa đủ các cửa sổ C3 và hậu kiểm; X02/X03 vẫn chưa chạy.
