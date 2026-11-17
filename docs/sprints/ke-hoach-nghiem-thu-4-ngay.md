# LABSEAT — Kế hoạch nghiệm thu 4 ngày cho 3 người

Ngày lập: 17/11/2026. Đây là tài liệu giao việc, chưa phải báo cáo kết quả thực hiện.

## 1. Mục tiêu, phạm vi và nguyên tắc chung

Thực hiện đầy đủ bộ diagram kiến trúc/security, dữ liệu và demo chức năng, kiểm thử tải/autoscaling, diễn tập mất compute một AZ, RDS/Redis failover và khôi phục RDS/S3. Ba người làm độc lập theo quyền sở hữu bên dưới, bàn giao qua manifest và bằng chứng có phiên bản.

### 1.1. Bối cảnh hệ thống

- Website: `https://labseat.id.vn`; AWS Sydney `ap-southeast-2`.
- Theo biên bản 17/11/2026: app `0.6.0`, schema `0002_platform`; FastAPI modular monolith, chung image cho API/publisher/worker.
- Một ECS cluster và một EC2 ASG qua hai AZ; API có hai task ban đầu, publisher/worker mỗi service một task. ASG min 2/max 6 máy `t3.small`; API max 8 task theo tài liệu hiện có. Phải xác minh lại khi bắt đầu.
- ALB HTTPS/ACM, DNS Tenten; RDS PostgreSQL private Multi-AZ; managed Redis primary/replica, TLS và ACL riêng; S3 private; outbox → SQS/DLQ → worker → Brevo; CloudWatch/SNS.
- RDS backup retention thực tế được ghi nhận là **1 ngày**, không phải mặc định Terraform 30 ngày. Chưa có bằng chứng nghiệm thu tải, failover hay restore.
- `Seat` có thể là một vùng phòng chứa nhiều người, không nhất thiết một ghế. Phân biệt `event_id`, `session_id`, `room_id`, `seat_id`.

Nguồn cần đọc trước khi làm:

1. [Biên bản AWS](../../evidence/current/aws-deployment.md), [README](../../README.md), [đặc tả](../dac-ta-he-thong.md).
2. [Kiến trúc](../architecture/current.md), [quyết định](../architecture/decisions.md), [capacity](../deployment/capacity.md).
3. [Load test](../testing/load-test.md), [concurrency](../testing/concurrency.md), [restore](../deployment/recovery.md).
4. [Ảnh sơ đồ](../image-seat-maps.md), [email](../deployment/brevo.md), [AWS runbook](../deployment/aws.md).

Tài liệu cũ có thể mâu thuẫn với biên bản mới. Mọi kết luận về trạng thái đang chạy phải đối chiếu AWS/source, ghi timestamp và nguồn; không sửa lịch sử bằng chứng để trông như đã đạt.

### 1.2. Yêu cầu “làm tối đa”

- Triển khai và kiểm chứng mọi đầu việc trong phạm vi; không dừng ở checklist, skeleton, đề xuất hoặc dữ liệu mẫu quá ít.
- Chủ động xử lí lỗi trong phần mình sở hữu, chạy lại bài bị ảnh hưởng, ghi cả lần lỗi và lần sửa. Không giảm ngưỡng đạt chỉ để báo cáo Pass.
- Nếu bị giới hạn quota, quyền, thời gian hoặc công cụ: hoàn thiện phần còn làm được; nộp chính xác lỗi, cách tái tạo, tác động, phần còn thiếu và bước tiếp theo.
- Không tự mở rộng sang đổi kiến trúc, tăng giới hạn tài nguyên hoặc xóa dữ liệu ngoài phạm vi để đạt demo.
- Tách **hoàn tất đầu việc** và **hệ thống đạt nghiệm thu**: một bài test có thể được thực hiện đầy đủ nhưng kết quả hệ thống vẫn Fail. Không được ghi Pass nếu chưa có bằng chứng.

### 1.3. Môi trường và quyền thay đổi

- AWS hiện tại là môi trường chạy kiểm thử; chỉ dùng tài khoản, ca, ảnh và giao dịch synthetic. Có cửa sổ gián đoạn riêng cho tải/fault.
- Người 1 đọc AWS, không chỉnh hạ tầng. Người 2 thay dữ liệu synthetic và tài nguyên restore tạm. Người 3 điều phối mọi thay đổi vận hành production.
- Không commit secret, mật khẩu, token, cookie, connection string, tfvars thật, Terraform state hoặc dữ liệu người dùng. Không sao chép nội dung file mật khẩu vào prompt AI.
- Không chạy các suite có truncate/reset trên DB AWS. Không dùng `APP_ENV=local/test` để vượt chặn seed/mock trên production.
- Trước mỗi tác động AWS: kiểm account/region, ID mục tiêu, baseline, điều kiện dừng và đường hoàn tác. Đây là bước trong runbook đã giao, không phải yêu cầu xin xác nhận lặp lại cho thao tác thuộc phạm vi được giao.
- Tải, AZ fault, RDS failover, Redis failover và restore acceptance chạy ở các cửa sổ riêng. Dừng traffic nếu có nguy cơ sai dữ liệu; phục hồi baseline trước bài kế tiếp.
- Không chuyển endpoint DB production sang DB restored. Restore dùng DB mới và ứng dụng kiểm chứng riêng; quota/chi phí tài nguyên tạm là điều kiện phải kiểm tra ngày 1.

## 2. Phân công, phụ thuộc và lịch 4 ngày

| Người | Mã task | Sở hữu | Không sửa trực tiếp |
|---|---|---|---|
| Người 1 | A1–A4 | Inventory, Hava, diagram, so sánh dịch vụ | Runtime app, seed, cấu hình scaling/fault |
| Người 2 | B1–B5 | Dữ liệu, chức năng, session fixture, restore RDS/S3 | Script tải, scaling production, endpoint DB production |
| Người 3 | C1–C6 | k6, collectors, email window, autoscaling, fault/failover, tổng hợp | Công cụ seed, schema nghiệp vụ, dữ liệu demo của người 2 |

| Thời điểm | Người 1 | Người 2 | Người 3 |
|---|---|---|---|
| Ngày 1 sáng | A1 khảo sát | B1 thiết kế/seed; preflight B4 | C1 dựng công cụ và preflight fault |
| Ngày 1 chiều | A2 Hava | B1/B2 bàn giao dữ liệu, ảnh/session | C1/C2 smoke; nhận manifest |
| Ngày 2 | A3 ERD/sequence/ADR | B3 test chức năng và regression | C3 tải chuẩn, queue, scaling |
| Ngày 3 | A4 sơ đồ sự cố/restore | B3 hoàn thiện; B4/B5 chuẩn bị đường restore | Chạy lại C3 nếu cần; hoàn thiện C4/C5 và rollback |
| Ngày 4 sáng | A4 thu bằng chứng | B3 kiểm nghiệp vụ sau từng fault | C4 compute AZ → ổn định → C5 RDS → ổn định → Redis |
| Ngày 4 chiều | Chốt bộ diagram | B4 RDS PITR và B5 S3; đo RPO/RTO | C6 hỗ trợ metrics, khôi phục baseline, tổng hợp |

**Các mốc bàn giao bắt buộc:**

- Cuối ngày 1: A1 có inventory; B1/B2 có manifest dữ liệu và session; C1 biết có đủ quota/capacity cho tải và restore không.
- Trước C3: B3 smoke chức năng đạt; session đủ hạn; C2 đã kiểm chứng email disabled.
- Trước C4/C5: C3 đã kết thúc, hệ thống ổn định; có probe nghiệp vụ và script hoàn tác.
- Trước B4: marker đã được ghi trước mốc sự cố; PITR khả dụng; app kiểm chứng không nối email/SQS production.
- C6 nhận báo cáo từ A4, B3–B5 và C3–C5; không chờ tới cuối ngày 4 mới kiểm thiếu evidence.

## 3. Chuẩn output, Git và cách giao AI

### 3.1. Cấu trúc đầu ra thống nhất

```text
docs/assessment/
  README.md                         # Người 3: mục lục, trạng thái, liên kết báo cáo
  architecture/                     # Người 1
    inventory.md
    diagrams/                       # .mmd/.drawio và bản xuất Hava
    components-and-decisions.md
    resilience.md
  functional/                       # Người 2
    dataset.md
    assets-sources.csv
    test-cases.csv
    report.md
    demo-script.md
  recovery/                         # Người 2
    preflight.md
    rds-pitr.md
    s3-restore.md
    report.md
  performance/                      # Người 3
    runbook.md
    observability.md
    load-report.md
    fault-runbook.md
    failover-report.md
  final-report.md                    # Người 3 tổng hợp, mỗi người duyệt phần mình
evidence/assessment/<run_id>/
  manifest.json
  summary.md
  metrics.csv                       # Đã loại dữ liệu nhạy cảm
  charts/                           # PNG/SVG, có script tái tạo
  screenshots/                      # Đã che PII/token
  checks/                           # Log đã làm sạch, kết quả invariants
.local/assessment/<run_id>/          # Không đưa lên Git
  accounts.json
  synthetic-sessions.json
  raw/                              # AWS responses/logs chưa làm sạch
```

Script mới: người 2 dùng `scripts/assessment/data/` và `scripts/assessment/recovery/`; người 3 dùng `scripts/assessment/observability/`, `scripts/assessment/faults/` và `scripts/load/`. Chỉ sửa file dùng chung sau khi ghi nhận người sở hữu trong task/PR.

- Markdown UTF-8; ngày giờ log là ISO 8601 UTC, lịch phối hợp dùng giờ Việt Nam UTC+7.
- `run_id`: `YYYYMMDDTHHMMSSZ-<scenario>`. Manifest ghi task ID, người chạy, commit SHA, image digest, schema, môi trường, khoảng đo, cấu hình, kết quả và đường dẫn bằng chứng.
- Kết quả có trạng thái `PASS`, `FAIL`, `BLOCKED`, `NOT_RUN`; không dùng `PASS` cho kiểm chứng local thay AWS.
- Bảng test CSV: `case_id,task_id,scenario,preconditions,steps,expected,actual,status,evidence,issue`.
- Báo cáo mỗi task: mục tiêu → cấu hình → cách chạy lại → kết quả thực tế → evidence → hạn chế/lỗi → hoàn tác và trạng thái cuối.
- Diagram nộp source chỉnh sửa được và PDF/PNG đọc được; có legend, timestamp, ranh giới hệ thống và nguồn. Không chỉ nộp ảnh chụp màn hình.
- Biểu đồ có đơn vị, múi giờ, scenario, tải thực tế và chú thích thời điểm scaling/fault. Nộp CSV và script tạo biểu đồ, không chỉ hình.
- Video: lưu tại kho nhóm có quyền phù hợp, ghi link/quyền truy cập/thời lượng trong báo cáo; không commit video lớn hoặc secret. Nếu Hava không cho xuất source, nộp định dạng export thực tế có được và ghi hạn chế, không giả source Hava.

### 3.2. Quy cách đưa lên Git

| Người | Branch gợi ý | Commit prefix |
|---|---|---|
| 1 | `assessment/architecture` | `docs(assessment): A1 ...` |
| 2 | `assessment/functional-recovery` | `feat(assessment): B1 ...`, `docs(assessment): B4 ...` |
| 3 | `assessment/load-resilience` | `test(assessment): C3 ...`, `docs(assessment): C6 ...` |

Mỗi task là một nhóm commit rõ ràng, có thể review riêng. Không `git add .`; stage đường dẫn cụ thể, đọc staged diff, kiểm secret và `git diff --cached --check` trước commit. AI chỉ commit/push/mở PR khi phiên làm việc đã được giao quyền đó; nếu chưa, chuẩn bị diff và nội dung PR để người phụ trách nộp.

PR phải ghi task ID, vấn đề/kết quả, file đầu ra, lệnh kiểm tra và kết quả, AWS đã tác động, evidence, việc hoàn tác, lỗi/chưa đạt còn lại. Không squash bỏ bằng chứng lần chạy thất bại khỏi báo cáo.

Không đưa thư mục `.local/` lên Git. Raw evidence nhạy cảm giữ riêng; bản công khai là bản đã làm sạch có danh mục trường bị lược bỏ. Tài khoản/endpoint/ID cần thiết để tái tạo được truyền qua manifest private; không in secret khi kiểm tra.

### 3.3. Prompt chung — ghép vào đầu mọi prompt task

Copy khối này, sau đó copy prompt task tương ứng. Cung cấp tài liệu này và manifest của task phụ thuộc; không cung cấp toàn bộ thư mục secret.

```text
Bạn đang hỗ trợ nhóm nghiệm thu LABSEAT trong repo hiện tại. Đọc
docs/sprints/ke-hoach-nghiem-thu-4-ngay.md, các hướng dẫn AGENTS.md/skill áp dụng
và nguồn của task trước khi làm. Mục tiêu là hoàn thành tối đa mọi yêu cầu của
task được giao, gồm công cụ, tài liệu, kiểm chứng thực và bằng chứng khi có quyền.

Làm đúng phạm vi sở hữu của người phụ trách. Khảo sát source/AWS trước khi kết luận;
không suy cấu hình đang chạy từ mặc định Terraform. Không bịa số đo, ảnh, diagram
hay kết quả AWS. Thiếu quyền/công cụ thì làm hết phần độc lập và ghi BLOCKED với
lỗi cụ thể, phần còn lại và cách tiếp tục. Không chỉ trả lời kế hoạch khi có thể
thực hiện phần đã được giao. Nếu phiên làm việc bị giới hạn chỉ lập kế hoạch,
hãy nêu rõ và bàn giao thiết kế/script dự kiến, không tự nhận đã thực thi.

Dữ liệu synthetic; không reset/truncate DB đang phục vụ, không đọc/in secret để
đưa vào báo cáo. Không hạ bảo mật hoặc sửa ngưỡng đạt để làm đẹp kết quả. Tác động
AWS chỉ trong phạm vi/cửa sổ đã giao; xác minh account/region/target, preflight,
điều kiện dừng và hoàn tác. Không tự chạy tải/fault chồng một bài khác.

Xuất file theo mục 3 của kế hoạch, có task ID, run_id, cách tái tạo, kết quả kiểm
tra, evidence, hạn chế và baseline cuối. Chỉ đánh PASS khi thỏa tiêu chí và có
bằng chứng. Chạy kiểm tra phù hợp với thay đổi; không chạy suite destructive trên
AWS. Cuối phiên báo file đã thay đổi, kiểm chứng đã chạy, kết quả và việc còn thiếu.
Không tự commit/push nếu chưa được giao quyền; chuẩn bị diff và mô tả PR.
```

## 4. Người 1 — Kiến trúc và security

### A1. Inventory AWS và đối chiếu tài liệu

**Đầu vào:** biên bản AWS, Terraform, runbook; quyền AWS chỉ đọc. **Phụ thuộc:** không.

**Công việc:** kiểm kê compute/network/data/security/messaging/observability/deployment; ghi ID đối chiếu private, cấu hình, quan hệ, AZ, phiên bản, backup, nguồn và thời điểm. Xác minh số EC2 thực tế, NAT thực tế, task/service, retention và trạng thái Multi-AZ. Liệt kê mâu thuẫn với tài liệu cũ; không sửa biên bản lịch sử.

**Output:** `architecture/inventory.md`, evidence baseline và manifest. Bàn giao danh sách tài nguyên cho C1, B4.

**Hoàn thành:** mọi nhóm tài nguyên có nguồn đối chiếu; phân biệt confirmed/unknown; không còn dùng giả định 2 EC2 cố định hoặc retention 30 ngày cho AWS hiện tại.

**Prompt AI A1:**

```text
Bối cảnh: LABSEAT đã chạy ở ap-southeast-2; biên bản 17/11/2026 mới hơn một số
tài liệu kiến trúc. Bạn làm A1 cho người 1, chỉ đọc AWS và source.
Nhiệm vụ: kiểm kê đầy đủ tài nguyên, quan hệ, security, cấu hình thực và các điểm
mâu thuẫn. Đọc evidence/current/aws-deployment.md, infra và tài liệu kiến trúc;
dùng AWS describe/list phù hợp, không apply hoặc đọc giá trị secret.
Hướng làm: ghi timestamp và nguồn cho từng kết luận; account/resource identifiers
chi tiết để private nếu cần; baseline thực tế phải phục vụ Hava, tải và restore.
Output: docs/assessment/architecture/inventory.md và evidence đã làm sạch theo
mục 3. Kèm checklist phần đã đối chiếu/chưa truy cập được và manifest bàn giao.
Hoàn thành khi mọi nhóm dịch vụ có cấu hình và nguồn hoặc BLOCKED cụ thể; không
coi nội dung Terraform mặc định là bằng chứng AWS.
```

### A2. Hava: infrastructure, network, security và ECS

**Đầu vào:** A1; Hava và quyền đọc phù hợp. **Phụ thuộc:** inventory sơ bộ A1.

**Công việc:** kết nối Hava qua read-only cross-account role; xuất infrastructure/extended, security, container views; kiểm quan hệ, subnet, route, port, SG và service/task. Role kết nối do người có quyền vận hành cấu hình; người 1 không tự cấp quyền ghi. Bổ sung chú thích cho tài nguyên Hava bỏ sót; kiểm định dạng export khả dụng của gói đang dùng.

**Output:** `architecture/diagrams/`, hướng dẫn refresh/export, bảng coverage so với inventory.

**Hoàn thành:** đủ các view, đọc rõ ở bản export; tất cả thành phần inventory được thể hiện hoặc giải thích phần chưa thể hiện; không dùng security view thay phân tích IAM/app security.

**Prompt AI A2:**

```text
Bối cảnh: bạn làm A2 cho người 1, dùng inventory A1 của LABSEAT AWS hai AZ.
Nhiệm vụ: tạo bộ infrastructure/network/security/ECS diagram bằng Hava.io.
Hướng làm: xác minh khả năng và export hiện tại từ tài liệu Hava chính thức;
chỉ dùng kết nối AWS read-only. Đối chiếu từng view với inventory, hiện subnet,
route, SG/port và mapping EC2-service-task. Không tự dựng tài nguyên không tồn tại.
Nếu không thao tác Hava được, hoàn tất inventory mapping và hướng dẫn thao tác,
ghi rõ chưa có Hava export; không giả ảnh là bản xuất từ Hava.
Output: docs/assessment/architecture/diagrams/ với export thực, chú thích/legend,
timestamp và file hướng dẫn refresh; bảng coverage. Source bổ sung chỉnh sửa được.
Hoàn thành khi mọi view đã đối chiếu và file xuất đọc được, phần thiếu được nêu rõ.
```

### A3. Sơ đồ logic, ERD và giải thích chọn dịch vụ

**Đầu vào:** A1/A2, models, router/service, architecture decisions.

**Công việc:** context/component, ERD, sequence booking/check-in/email, deployment và hai tầng scaling. Thêm IAM roles, SSM injection, TLS/ACL, cookie/CSRF, quyền student/staff/admin, ảnh private. Mỗi thành phần mô tả nhiệm vụ, dữ liệu, kết nối, quyền, lỗi và giới hạn. So sánh ECS/EC2–Fargate–EKS; ALB–NLB–API Gateway; RDS PostgreSQL–Aurora–DynamoDB; managed Redis–Redis EC2; S3–EFS/lưu local; SQS–SNS–EventBridge; Brevo–SES; Parameter Store–Secrets Manager; CloudWatch/SNS–tự vận hành.

**Output:** diagram source/export và `architecture/components-and-decisions.md`.

**Hoàn thành:** ERD khớp schema/source; sequence có happy path và lỗi; so sánh theo nhu cầu/chi phí/vận hành, có nguồn chính thức cho nhận định kỹ thuật và ghi rõ quyết định lịch sử hay đánh giá bổ sung.

**Prompt AI A3:**

```text
Bối cảnh: LABSEAT là FastAPI modular monolith, PostgreSQL giữ correctness, Redis
admission/PubSub, outbox-SQS-worker-Brevo; bạn làm A3 cho người 1.
Nhiệm vụ: đọc models/migration/router/service để vẽ context, component, ERD,
sequence hold-confirm-cancel/check-in/email, deployment và scaling. Mô tả mỗi
thành phần và toàn bộ cặp dịch vụ cần so sánh trong A3 của kế hoạch.
Hướng làm: vẽ Mermaid/draw.io, export ảnh; kiểm FK/cardinality và trạng thái thực;
ghi port/trust boundary/quyền tương ứng. Tách lý do được dự án ghi nhận với đánh
giá mới; dùng nguồn chính thức khi so sánh khả năng AWS, không khẳng định dịch vụ
nào luôn tốt/rẻ hơn. Không bổ sung WAF/CloudFront/CI nếu AWS không có.
Output: architecture/diagrams/ và components-and-decisions.md, liên kết nguồn.
Hoàn thành khi reviewer lần theo được request, dữ liệu, quyền và lỗi xuyên hệ thống.
```

### A4. Diagram resilience và chốt bộ kiến trúc

**Đầu vào:** runbook B4/B5/C4/C5; evidence sau diễn tập.

**Công việc:** vẽ trước–trong–sau mất compute AZ, RDS/Redis failover, PITR và S3 version recovery; thể hiện endpoint, dữ liệu bền vững/tạm, đường phục vụ còn lại, điểm đo thời gian. Cập nhật trạng thái sau ngày 4, chỉ rõ thiết kế kỳ vọng so với kết quả quan sát.

**Output:** `architecture/resilience.md`, bộ diagram cuối, liên kết báo cáo B/C.

**Hoàn thành:** mọi bài diễn tập có sơ đồ và evidence tương ứng hoặc trạng thái chưa chạy; không gọi compute fault là mất toàn bộ AZ; PDF/PNG/source mở được và không lộ secret.

**Prompt AI A4:**

```text
Bối cảnh: bạn làm A4 cho người 1. Nhóm sẽ test compute một AZ, RDS/Redis failover
và restore RDS/S3, tách cửa sổ; AWS hiện tại backup RDS ghi nhận 1 ngày.
Nhiệm vụ: mô tả và vẽ resilience trước/trong/sau từng bài, bổ sung đường restore
vào DB mới và app kiểm chứng riêng, điểm đo RPO/RTO, ảnh S3 theo version.
Hướng làm: lấy runbook và evidence của B4/B5/C4/C5; chưa chạy thì ghi planned,
đã chạy mới ghi observed. Không vẽ đường chuyển production sang DB restored.
Output: architecture/resilience.md, diagram source/export và mục lục bộ kiến trúc.
Hoàn thành khi sơ đồ khớp kết quả và inventory, có giới hạn kết luận cho từng bài.
```

## 5. Người 2 — Chức năng, dữ liệu và khôi phục

### B1. Công cụ seed và bộ dữ liệu synthetic

**Đầu vào:** models/schema hiện tại, quyền one-off task/DB phù hợp. **Phụ thuộc:** không; A1 hỗ trợ target.

**Công việc:** 500 student, 2 admin demo mới, 6 staff; 12 event gồm 6 exam/6 practice, 24 lịch; khoảng 300 reservation hợp lệ. Có trạng thái sắp mở/đang mở/hết chỗ/đóng/check-in/kết thúc/hủy. Tách dataset chức năng và tải; ca tải mở xuyên suốt cửa sổ và đủ capacity. Phân công staff đúng lịch.

Viết công cụ ORM chạy ECS one-off trong VPC: dry-run, execute rõ ràng, batch ID, manifest ID, idempotent và cleanup chỉ dữ liệu thuộc batch. Hash mật khẩu đúng app; email/CCCD synthetic duy nhất. Seed tài khoản đã xác minh không tạo mail; tạo reservation qua service nghiệp vụ để giữ constraints/outbox/audit. Việc sinh reservation chỉ chạy khi C2 đã chặn gửi mail. Không dùng seed local hoặc reset trên AWS.

**Output:** `scripts/assessment/data/`, `functional/dataset.md`, private manifest/tài khoản và evidence count/invariants.

**Hoàn thành:** đủ quy mô trên, chạy lại không nhân đôi, cleanup giới hạn đúng batch, không sửa dữ liệu thật; invariants zero rows. Nếu bắt buộc thay quy mô, ghi lý do và số thực tế, không âm thầm cắt yêu cầu.

**Prompt AI B1:**

```text
Bối cảnh: bạn làm B1 cho người 2 trên LABSEAT schema 0002_platform. AWS DB đang
phục vụ; app.cli seed chỉ local/test và không phù hợp bài nghiệm thu này.
Nhiệm vụ: viết công cụ seed ORM và bộ dữ liệu đúng số lượng/trạng thái B1; chạy
trong VPC qua one-off task khi phiên có quyền. Tách batch functional/load.
Hướng làm: đọc models/service/constraints; dùng hasher hiện có, synthetic verified
users và service nghiệp vụ cho reservation; phối hợp C2 trước phần sinh email.
Dry-run mặc định, execute rõ ràng, idempotent và cleanup theo manifest/FK đúng thứ
tự; không truncate/reset hoặc đổi APP_ENV. Không xuất mật khẩu vào evidence.
Output: scripts/assessment/data/, functional/dataset.md; manifest/accounts private
dưới .local/assessment/. Kiểm count, tính đúng và chạy lại an toàn trên DB disposable
trước AWS. Hoàn thành khi đủ dữ liệu và invariants đạt, có cách tái tạo và cleanup.
```

### B2. Ảnh sơ đồ và gói dữ liệu/session bàn giao

**Đầu vào:** B1, luồng quản trị ảnh, API/session service. **Phụ thuộc:** tài khoản/ca B1.

**Công việc:** tìm 6 ảnh sơ đồ trên mạng, ưu tiên quyền sử dụng rõ ràng, ghi URL/giấy phép và chỉnh sửa. Chuẩn hóa PNG/JPEG/WebP ≤5 MB, mỗi chiều ≤2048 px; upload qua admin, kiểm nhận diện và chỉnh tay 4–8 vùng/ảnh có capacity. Phân biệt ảnh sơ đồ với poster event. Không dùng dữ liệu phòng nhạy cảm.

Tạo ≥100 session distinct đúng hàm tạo session hiện có cho synthetic accounts; token ngẫu nhiên, DB chỉ lưu digest như app, CSRF đúng và TTL đủ toàn bài đo. Không ghi plaintext token vào DB/log. File B2 có `{session_token,csrf_token,seat_id}` cho platform; manifest mapping ca/phòng và private credentials cho bài khác. Kiểm distinct user, readiness, ca chưa bắt đầu và thời hạn trước bàn giao. Giữ ca riêng để người kiểm UI thao tác trong lúc tải.

**Output:** `functional/assets-sources.csv`, hướng dẫn/session helper trong thư mục data, private manifest/session. Ảnh được phép phân phối mới đưa lên Git; ảnh khác giữ theo nguồn hoặc private.

**Hoàn thành:** đủ 6 ảnh usable; mapping đúng UUID/capacity; session thử qua API đọc/ghi thành công, không vướng giới hạn login hàng loạt; người 3 dùng được mà không tự sửa seed.

**Prompt AI B2:**

```text
Bối cảnh: bạn làm B2 cho người 2. LABSEAT nhận diện vùng tứ giác trong ảnh;
Seat là vùng phòng nhiều người. k6 platform cần 100 session riêng, login HTTP
bị giới hạn 50 lần/15 phút/IP nên không đăng nhập hàng loạt trong bài đo.
Nhiệm vụ: tìm 6 sơ đồ có nguồn/quyền dùng, upload/nhận diện/chỉnh 4–8 vùng mỗi ảnh;
chuẩn bị session và manifest để người 3 chạy tải. Đọc docs/image-seat-maps.md và
auth service. Dùng hàm tạo session hiện có cho user synthetic, bảo toàn digest,
CSRF và TTL; luồng login thật vẫn để B3 kiểm HTTP. Không tắt auth/rate limit.
Output: assets-sources.csv, session helper và tài liệu bàn giao; token/password
chỉ .local, file session tương thích platform.js. Hoàn thành khi mapping/ảnh/session
đã kiểm bằng API và người 3 smoke được. Không coi ảnh chỉ tải về là đã tích hợp.
```

### B3. Kiểm thử chức năng, regression và demo

**Đầu vào:** B1/B2; app AWS. **Phụ thuộc:** dữ liệu cơ bản.

**Công việc:** test account/login/logout/profile/verify/reset; khóa user; quyền student/staff/admin cả UI/API; CRUD event/lịch/ảnh/phòng; admission/heartbeat/expiry; hold/confirm/cancel/replay/race suất cuối; hết hạn/hết chỗ/trùng lịch; QR/check-in sai ca/đóng/lặp; realtime hai browser; CSV. Kiểm desktop và điện thoại thật; ghi device/browser, nếu thiếu thì không nhận là đã kiểm camera mobile.

Test mail thật riêng tối đa 20 thư trong quota còn lại; tài khoản/inbox do nhóm kiểm soát. Kiểm inbox/spam và callback, không coi provider accepted là inbox delivered. Thực hiện khi Brevo bật, ngoài cửa sổ disabled. Trước/sau tải/fault/restore: probe nghiệp vụ và invariants read-only. Không chạy fixture destructive trên production.

**Output:** `functional/test-cases.csv`, `report.md`, `demo-script.md`, bằng chứng và video student → admin/staff check-in. Lỗi chức năng sửa trong nhánh người 2, ghi release mới và nhờ C3 đo lại phần liên quan.

**Hoàn thành:** mọi nhóm trên có case và kết quả; invariants zero rows; không còn lỗi critical chưa được phản ánh vào kết luận. Demo trọn luồng; lỗi còn lại có mức độ, cách tái tạo và ảnh hưởng.

**Prompt AI B3:**

```text
Bối cảnh: bạn làm B3 cho người 2, dùng dataset B1/B2. Cần chứng minh chức năng
LABSEAT chạy thật, đồng thời kiểm đúng dữ liệu trước/sau các bài tải và sự cố.
Nhiệm vụ: thực hiện toàn bộ nhóm test B3 của kế hoạch, gồm phân quyền trực tiếp
API, concurrency suất cuối, QR/check-in, realtime, CSV và mail thật giới hạn.
Hướng làm: lập CSV expected/actual/evidence, thực thi với synthetic data; không chạy
suite truncate/reset vào AWS. Kiểm camera trên thiết bị thật nếu có và ghi rõ
mock/emulation/real. Phối hợp C2 để không gửi mail trong window disabled. Dùng
scripts/tests/db-invariants.sql read-only; lỗi có repro và regression sau sửa.
Output: functional/test-cases.csv, report.md, demo-script.md, ảnh/video đã che dữ
liệu nhạy cảm. Hoàn thành khi mọi case có trạng thái thật và demo end-to-end,
không coi endpoint health trả 200 là đủ nghiệm thu nghiệp vụ.
```

### B4. RDS PITR và đo RPO/RTO

**Đầu vào:** recovery runbook, A1, C1 quota/capacity, marker synthetic. **Phụ thuộc:** preflight ngày 1; diễn tập sau các fault ổn định.

**Công việc:** xác minh PITR/retention 1 ngày hiện tại, `LatestRestorableTime`, quota, IAM/KMS và loại DB được account cho phép. Chuẩn bị app kiểm chứng private tạm dùng cùng digest, DB mới, secret riêng; không dùng production ALB route hoặc SQS, publisher/worker/maintenance production. Synthetic workflows kiểm qua probe trong VPC; email disabled. Không đổi secret production.

Ghi marker commit mỗi phút bằng DB clock trước `incident_at`; chọn PITR target ≤incident và trong cửa sổ khả dụng. Không phá DB nguồn; `incident_at` là mốc sự cố giả định của bài restore. Khôi phục DB identifier mới, private/encrypted và parameter/subnet/SG phù hợp. Không seed/reset trên restored DB.

Kiểm schema, counts/hash, marker gần nhất trước incident, constraints, ownership và vé/session. Khởi động app kiểm chứng, thực hiện login, vé/QR, hold-confirm-cancel/check-in bằng synthetic data, đối chiếu ảnh với B5. RPO=incident−commit mới nhất phục hồi được trước incident; RTO=ready-and-verified−incident. Mục tiêu RPO≤900 giây, RTO≤3600 giây. Dùng scripts/recovery/measure.py và JSON đúng yêu cầu; không lấy thời điểm DB available làm RTO hoàn tất. Ghi thêm thời gian chuẩn bị, restore DB, rollout và kiểm chứng để thấy phần nào nằm ngoài cửa sổ đo.

**Output:** `recovery/preflight.md`, `rds-pitr.md`, `report.md`, sanitized JSON/evidence; script trong `scripts/assessment/recovery/`.

**Hoàn thành:** ứng dụng restored sử dụng được, invariants/ảnh đạt, số đo có marker gốc và timestamp timezone; không sửa DB nguồn. Nếu quota chặn, nộp lỗi/quota cụ thể và trạng thái BLOCKED, không thay local restore làm kết quả AWS. Cleanup DB/app/secret tạm theo ID sau lưu evidence; DB snapshot nếu giữ lại phải ghi chi phí/người sở hữu.

**Prompt AI B4:**

```text
Bối cảnh: bạn làm B4 cho người 2. RDS LABSEAT Multi-AZ, retention được ghi nhận
1 ngày; cần nghiệm thu PITR thật, mục tiêu RPO≤15 phút/RTO≤60 phút, chưa phải SLA.
Nhiệm vụ: chuẩn bị preflight từ ngày 1, marker mỗi phút và restore vào DB mới;
chạy app kiểm chứng cùng digest, private, endpoint/secret riêng. Đọc recovery.md
và scripts/recovery/measure.py. Tuyệt đối không đổi endpoint production hoặc
để restored app/publisher/worker nối SQS và mail thật production.
Hướng làm: xác minh LatestRestorableTime/quota/IAM/KMS; ghi mốc incident giả định,
PITR target, marker commit thực, schema/count/hash/invariants; kiểm nghiệp vụ và
ảnh với B5 trước ready_and_verified_at. Không khẳng định đã đo gián đoạn production
trong bài này. Ghi cả thời gian provisioning và cleanup tài nguyên đúng ID.
Output: recovery/preflight.md, rds-pitr.md, report.md, script và sanitized evidence.
Hoàn thành khi số đo có chứng cứ và app restored chạy đúng; vượt mục tiêu ghi FAIL.
```

### B5. Khôi phục ảnh S3 theo version và kiểm liên kết DB

**Đầu vào:** B4, bucket/prefix/versioning thực tế, ảnh synthetic riêng.

**Công việc:** tạo ảnh synthetic version tốt, ghi version ID/hash; liên kết đúng bản ghi synthetic. Ghi đè bằng ảnh lỗi trong phạm vi object test, kiểm lỗi thực tế rồi copy version tốt thành current. Không xóa version vĩnh viễn, không động ảnh người khác. Xác minh SHA-256, content type, private access, ảnh hiển thị và DB reference từ app kiểm chứng. Ghi ảnh hưởng cache nếu có; không kết luận ảnh đã khôi phục chỉ từ put thành công.

**Output:** `recovery/s3-restore.md`, bảng key/version/hash đã làm sạch, evidence ảnh trước/sau; kết quả gộp vào recovery report B4.

**Hoàn thành:** phiên bản phục hồi có hash đúng và hiển thị qua app; DB reference nhất quán. RPO/RTO tổng thể chỉ chốt khi B4 và B5 cùng đạt. Dọn mọi version/delete marker thuộc object test theo manifest sau ghi bằng chứng.

**Prompt AI B5:**

```text
Bối cảnh: bạn làm B5 cho người 2. LABSEAT lưu ảnh S3 private; S3 versioning
không thay backup database. B4 đang kiểm app dùng DB restored riêng.
Nhiệm vụ: diễn tập một object ảnh synthetic bị ghi đè và phục hồi version tốt.
Hướng làm: ghi key/version/hash và DB reference; tạo bản lỗi có kiểm soát, copy
version tốt thành current, xác minh SHA-256/content type/quyền private và hiển thị
thật qua app kiểm chứng. Không ghi đè ảnh khác hoặc xóa version vĩnh viễn để demo.
Output: recovery/s3-restore.md, evidence và cleanup manifest; cập nhật B4 để chỉ
đánh images_verified=true khi thực sự đạt. Hoàn thành khi ảnh và DB reference
đúng, thao tác tái tạo được và tài nguyên test được dọn sau giữ evidence.
```

## 6. Người 3 — Hiệu năng, quan sát và fault/failover

### C1. Công cụ tạo tải, quan sát và preflight

**Đầu vào:** A1, runbook tải/capacity; máy runner ngoài ASG. **Phụ thuộc:** không cho tooling; B2 cho smoke.

**Công việc:** kiểm phiên bản k6/CLI, account/region, thời gian hệ thống, runner CPU/network; app min/healthy targets, image/schema, DB connection budget thực tế, ENI/memory, queue policy, alarms/SNS, quota restore và capacity cho fault. Không giả định trunking hoặc mọi instance đặt được ba task.

Collector snapshot 15–30 giây: ECS desired/running/pending và container resources; ASG desired/in-service/activity; target health; CloudWatch CPU/memory/EC2 credits/CapacityProviderReservation/ALB RPS, latency, 4xx/5xx/RDS connections, CPU, latency, locks/Redis connections, latency, failover/SQS depth, oldest age, DLQ. Chỉ dùng metric thực sự có; bổ sung phép đo khi cần và ghi độ phân giải/thiếu dữ liệu, không bịa metric absent. Request stream evidence chứng minh nhiều task nhận traffic.

**Output:** `performance/observability.md`, collector/chart scripts và một smoke run có evidence.

**Hoàn thành:** metrics khớp timestamp, biểu đồ tái tạo được từ CSV, thấy được task và EC2 riêng; quota/capacity thiếu có hành động rõ từ ngày 1.

**Prompt AI C1:**

```text
Bối cảnh: bạn làm C1 cho người 3. LABSEAT một ECS/EC2 ASG, t3.small có giới hạn
RAM/ENI và CPU credits; task tăng chưa chứng minh EC2 tăng. AWS nghiệm thu pending.
Nhiệm vụ: chuẩn bị runner k6 ngoài ASG, preflight và collector 15–30 giây, xuất
metrics/CSV/chart cho toàn bộ nhóm trong C1. Đọc capacity.md/load-test.md và A1.
Hướng làm: dùng AWS describe/metrics đúng dimensions, tách desired/running/pending,
ASG in-service và ALB healthy. Kiểm DB max_connections/budget, quota restore và
capacity AZ còn lại. Đo runner để tránh nhầm runner saturation thành app saturation.
Output: performance/observability.md và scripts/assessment/observability/; smoke
evidence thật, ghi missing metrics. Hoàn thành khi chart tái tạo được và có baseline
đủ để phân tích scaling/fault, không chỉ screenshot dashboard.
```

### C2. Cửa sổ email và chuẩn bị script nghiệp vụ

**Đầu vào:** B2 sessions, email runbook. **Phụ thuộc:** C1, B2.

**Công việc:** ghi worker task definition/digest/backend ban đầu; hoàn tất job thật rồi chuyển worker `EMAIL_BACKEND=disabled`, không đổi APP_ENV. Kiểm rollout, job synthetic `SKIPPED`, không gửi Brevo, publisher/worker vẫn chạy. Trạng thái disabled ảnh hưởng mọi email mới; phối hợp để không có verify/reset thật trong cửa sổ này. Sau bài test, drain job test trước khôi phục Brevo; không tự gửi lại skipped mail.

Sửa `booking.js` để nạp session chuẩn bị trước qua `SESSIONS_FILE`, giữ đường login cũ khi không dùng file; mỗi VU gắn user riêng, CSRF đúng. Test smoke không chạm rate limit hoặc dùng tài khoản chung. Giữ `platform.js` chuẩn 24 read/s +2 workflow/s×3 write=30 RPS; không dùng VUS để giả đổi arrival rate.

**Output:** cập nhật script và `performance/runbook.md` về email/session, evidence backend trước/sau và smoke.

**Hoàn thành:** booking script dùng được manifest B2; confirmed event không phát mail khi disabled; sau cửa sổ job test xử lí hết, Brevo/baseline khôi phục và kiểm một mail trong tổng hạn mức 20 thư.

**Prompt AI C2:**

```text
Bối cảnh: bạn làm C2 cho người 3. Seed verified users tránh verify mail nhưng
confirm vé vẫn sinh mail; quota nhóm là 300/ngày. Mock backend không được dùng
production; app đã có EMAIL_BACKEND=disabled, job sẽ SKIPPED.
Nhiệm vụ: triển khai quy trình disabled/restore worker trong cửa sổ chung, kiểm
không gửi thư; bổ sung booking.js nhận session B2 và giữ chế độ credentials cũ.
Hướng làm: lưu backend/task definition baseline, hoàn tất job thật trước chuyển,
không tắt publisher/worker để che backlog. Kiểm cookie/CSRF/user distinct và TTL;
không tắt rate limit. Khôi phục Brevo sau xử lí job test, không replay skipped mail.
Output: script và performance/runbook.md, smoke evidence; không commit token.
Hoàn thành khi script chạy thật với sessions và email switch/restore đã kiểm chứng.
```

### C3. Tải chuẩn, admission, autoscaling và biểu đồ

**Đầu vào:** B1/B2, B3 smoke, C1/C2. **Phụ thuộc:** đủ readiness và email disabled.

| Bài | Thiết lập cố định | Kết quả cần ghi |
|---|---|---|
| Baseline | Tải nhẹ 5 phút | Số task/EC2/targets thực, latency, connections |
| Platform | 100 VU slots, 30 RPS, 15 phút; admission off | Actual RPS, workflow counts, read/write p95, errors/dropped |
| Admission | 20 rồi 50 VU, mỗi mức 5 phút; admission on | Wait/grant/expiry/heartbeat, expected conflict và unexpected error |
| Scaling | 60→100→150→200 VU khi cần; giữ mỗi mức ≥15 phút, tối đa 25 phút nếu scaling còn tiến triển | Task và EC2 tự tăng, placement, healthy targets, alarm/SNS |
| Recovery | Hạ tải, theo dõi 30–45 phút | Task/EC2 scale-in, baseline và UI sau tải |

Scaling dùng `ecs-scaling.js`; điều chỉnh script để stage nối tiếp rõ ràng nếu cần, ghi offered/actual load. Dừng tăng khi đã có bằng chứng EC2 tự tăng; giữ API max8/ASG max6. Nếu workload không làm EC2 tăng trong giới hạn, báo chưa chứng minh, không manual tăng desired hoặc giảm capacity để giả autoscale.

Gate platform: p95 đọc<500ms, ghi<1s, unexpected errors<1%, dropped iterations=0; actual 30 RPS trong cửa sổ 15 phút với workflow đầy đủ; invariants zero rows. 100 VU slots không có nghĩa 100 request đang xử lí cùng lúc. Kiểm UI bằng tài khoản khác trong khi tải; expected 409/429 phải phân loại theo scenario, không xóa khỏi báo cáo để làm đẹp.

Dừng tải khi sai dữ liệu, toàn bộ target unhealthy, 5xx>5% liên tục 2 phút hoặc DB connections chạm budget đã xác minh. Chuỗi scaling: load → API desired tăng → thiếu placement → Capacity Provider/ASG tăng → EC2 register → task healthy nhận traffic. Có request streams, alarm workload thật và SNS nhận thông báo; SNS publish thủ công không thay bằng chứng.

**Output:** `performance/load-report.md`, lệnh tái tạo, CSV/k6 summary, biểu đồ tải-latency, tải-errors, tải-task-EC2, resources và queues; video scaling.

**Hoàn thành:** mọi bài có số thực, gate và evidence; báo riêng correctness/performance/autoscale. Chỉ nói app hoạt động bình thường ở mức tải đã đo khi cả UI/nghiệp vụ và SLO đạt. Giữ evidence lần lỗi và đo lại sau fix.

**Prompt AI C3:**

```text
Bối cảnh: bạn làm C3 cho người 3; app AWS chưa nghiệm thu tải. C1 có collector,
C2 đã chặn mail, B2 có sessions và B3 smoke nghiệp vụ. Không chạy trên runner
trong ASG, không chạy đồng thời fault/restore.
Nhiệm vụ: thực hiện đầy đủ năm bài và ngưỡng C3 trong kế hoạch, tối đa 200 VU,
API max8/ASG max6; thu dữ liệu thực và video/biểu đồ có thể tái tạo.
Hướng làm: ghi baseline từng run, queue on/off đúng scenario, 30RPS platform là
arrival rate cố định chứ không là VU. Đối chiếu workflow thực và dropped iterations;
chứng minh task placement/EC2 registration/traffic streams/alarm-SNS theo timestamp.
Không manual scale desired để chứng minh autoscale; dừng theo gate, ghi mọi lần lỗi.
Output: performance/load-report.md, script/config tái tạo, sanitized k6/CSV/charts/
video link. Hoàn thành khi kết luận cho từng mức có evidence; không đạt thì FAIL,
không tăng EC2 trong giới hạn thì chưa chứng minh hai tầng, không suy diễn Pass.
```

### C4. Diễn tập mất compute một AZ

**Đầu vào:** A1, C1 capacity, B3 probe; C3 đã kết thúc. **Phụ thuộc:** app baseline ổn định, email disabled.

**Phạm vi:** mất nhóm compute ứng dụng tại AZ mục tiêu; không phá subnet/NAT/RDS/Redis và không tuyên bố thử toàn AZ outage.

**Công việc:** viết runbook/script preflight → inject → observe → rollback. Chọn AZ có API task đang phục vụ, ghi instance/task IDs. Chuẩn bị AZ còn lại đủ slot cho dịch vụ thiết yếu theo ENI/RAM thực; ghi rõ capacity chuẩn bị thủ công, không dùng làm bằng chứng autoscaling C3.

Thiết kế cấu hình tạm để replacement chỉ sang AZ còn lại mà không di chuyển/drain task mục tiêu trước tác động: lưu subnet/placement/ASG process config gốc; tránh AZ rebalance làm di chuyển trước fault. Kiểm cơ chế thực tế trong dry-run, nếu không bảo đảm thì đánh BLOCKED phần AZ failover thay vì chỉ restart task rồi gọi là AZ outage. Script không được dừng instance vừa tạo ngoài danh sách mục tiêu đã chốt. Không dùng auto-apply Terraform để hoàn tác những thay đổi không liên quan.

Dừng đột ngột EC2 mục tiêu; duy trì probe synthetic nhẹ. Ghi mất target/task, lỗi HTTP/nghiệp vụ, task replacement/healthy, alarms và thời gian phục hồi. Hoàn tác placement/subnet/process config, khôi phục phân bố hai AZ, kiểm ready/dependency/invariants và cleanup capacity tạm sau ổn định.

**Output:** `performance/fault-runbook.md`, script faults, evidence timeline và phần compute trong `failover-report.md`.

**Hoàn thành:** tác động đúng compute mục tiêu, có bằng chứng workload phục hồi ở AZ còn lại; không mất vé/oversell; baseline hai AZ được khôi phục, hoặc báo lỗi/rollback còn thiếu rõ ràng. Mốc kết thúc bài phục hồi tối đa 60 phút; không hứa zero downtime.

**Prompt AI C4:**

```text
Bối cảnh: bạn làm C4 cho người 3. Phạm vi được giao là mất compute ứng dụng một
AZ có kiểm soát, không phải phá toàn AZ. Tải C3 đã kết thúc, B3 cung cấp probe.
Nhiệm vụ: viết và kiểm runbook/script preflight-inject-observe-rollback, đủ capacity
ở AZ còn lại, chặn replacement quay về AZ mục tiêu, dừng đột ngột đúng EC2 đã chốt.
Hướng làm: khảo sát ASG subnet/AZRebalance/ECS placement và resource slots thực;
cấu hình tạm không được drain/chuyển task trước fault. Lưu config baseline, dry-run
target list và hoàn tác đầy đủ, không dùng terminate nhầm nhóm hoặc subnet/network
fault ngoài scope. Nếu không thực hiện được isolation đúng nghĩa, ghi BLOCKED,
không đổi nhãn restart đơn lẻ thành mất AZ. Traffic nhẹ, metrics liên tục, invariants.
Output: performance/fault-runbook.md, scripts/assessment/faults/, timeline/evidence
và report. Hoàn thành khi app phục hồi ở AZ còn lại và baseline hai AZ được trả lại.
```

### C5. RDS và Redis failover, chạy tuần tự

**Đầu vào:** C4 ổn định, B3 probe, A1 resource IDs; email disabled.

**RDS:** xác minh đúng Multi-AZ DB instance; dùng reboot with failover, không nhầm DB cluster API. Ghi AZ trước/sau, RDS events, DNS/reconnect, lỗi/timeout, DB readiness và nghiệp vụ. Kiểm marker/transaction/vé commit trước fault. Không failback tự động chỉ để đẹp sơ đồ; ghi topology cuối thực tế.

**Redis:** đợi RDS/app ổn định rồi test failover ElastiCache đúng replication group/node group; xác minh API/quota test failover hiện tại. Ghi primary/replica và events; kiểm TLS/ACL/reconnect, readiness admission, lease/queue epoch và PubSub/realtime. Không giả định queue Redis không mất dữ liệu; DB giữ correctness. Nếu cần operator recovery theo runbook thì ghi đầy đủ thao tác/thời gian/ảnh hưởng thứ tự chờ. Vé đã commit không bị mất; không cấp hold vượt sức chứa.

Không dùng healthz đơn thuần kết luận app phục hồi. Không can thiệp cưỡng bức lần thứ hai khi bài trước chưa ổn định. Nếu mất đường phục vụ ngoài dự kiến, dừng traffic và bắt đầu hoàn tác/phục hồi; các lỗi dependency dự kiến phải được đo, không che khỏi biểu đồ. Mỗi bài có ngưỡng kết thúc 60 phút và ghi thời gian thực tế, không gộp với RTO PITR.

**Output:** cập nhật `fault-runbook.md`, `failover-report.md`, metrics/probe/video và invariants B3.

**Hoàn thành:** cả hai bài đã thực thi và có kết quả đúng; topology/role chuyển được kiểm chứng, nghiệp vụ phục hồi, không sai dữ liệu; bài chưa chạy/không được phép có BLOCKED cụ thể.

**Prompt AI C5:**

```text
Bối cảnh: bạn làm C5 cho người 3, sau C4 đã ổn định. RDS PostgreSQL Multi-AZ và
ElastiCache Redis primary/replica của LABSEAT cần failover thật, không mô phỏng local.
Nhiệm vụ: RDS reboot-with-failover rồi đợi ổn định, sau đó Redis test-failover;
dùng API đúng loại tài nguyên và kiểm quota/tài liệu AWS chính thức hiện tại.
Hướng làm: baseline role/AZ/endpoint/events, probe nhẹ xuyên suốt, đo lỗi/reconnect
và nghiệp vụ phục hồi. Redis kiểm ACL/lease/epoch/PubSub và ghi operator recovery
nếu cần; không hứa queue state nguyên vẹn. DB invariants/vé commit phải đúng.
Không chạy stress cùng lúc, không tự thay endpoint DB production để che lỗi.
Output: fault-runbook.md, failover-report.md, sanitized metrics/probes/video,
thời gian từng bài và cấu hình cuối. Hoàn thành khi hai bài có evidence riêng;
healthz=200 hoặc role đổi mà nghiệp vụ chưa chạy lại không đủ Pass.
```

### C6. Tổng hợp nghiệm thu, Git và khôi phục trạng thái cuối

**Đầu vào:** A1–A4, B1–B5, C1–C5. **Phụ thuộc:** mọi báo cáo có trạng thái, kể cả Fail/Blocked.

**Công việc:** lập ma trận yêu cầu → task → bằng chứng → kết luận; các chương kiến trúc/chức năng/hiệu năng/AZ/failover/PITR/S3. Tách correctness, performance, availability và recovery. Ghi offered/actual RPS, latency, lỗi, task/EC2 đầu–đỉnh–cuối, alarm, tác động UI, downtime và RPO/RTO. Thống kê lỗi, fix/retest, giới hạn và việc chưa đạt.

Xác minh email Brevo/queue policy/placement/ASG processes đã trả baseline; healthy targets và hai AZ như cấu hình mong muốn; không còn app/DB/secret/object tạm ngoài danh sách giữ có chủ đích. Việc scale-in chưa hoàn tất phải ghi trạng thái, không cưỡng bức giảm chỉ để chụp số đẹp. Chốt chi phí tài nguyên phát sinh dựa trên thông tin khả dụng, không hứa miễn phí.

**Output:** `docs/assessment/README.md`, `final-report.md`, mục lục evidence/video, bảng trạng thái task, nội dung PR cuối. Các chủ sở hữu duyệt phần mình.

**Hoàn thành:** mọi yêu cầu có dòng kết luận và evidence/lý do thiếu; file/link mở được; kiểm diff/secret trước đưa Git; baseline cuối được xác minh; không tuyên bố toàn bộ đạt nếu một gate còn Fail/Blocked/Not run.

**Prompt AI C6:**

```text
Bối cảnh: bạn làm C6 cho người 3, tổng hợp bộ nghiệm thu 4 ngày của 3 người.
Nhiệm vụ: đọc toàn bộ báo cáo A/B/C và evidence, lập traceability matrix và báo
cáo cuối với trạng thái thật cho kiến trúc, chức năng, tải/scaling, compute AZ,
RDS/Redis failover, RDS PITR/S3, RPO/RTO. Không tự điền kết quả còn thiếu.
Hướng làm: kiểm link, manifest/release/time window, số liệu và baseline cuối;
đối chiếu email/queue/placement/ASG/temporary resources. Yêu cầu đúng owner hoàn
thiện phần thiếu thay vì tự sửa chồng file. Ghi Fail/Blocked, lỗi và retest rõ.
Output: docs/assessment/README.md, final-report.md, evidence/video index và PR
description. Kiểm staged diff/secret; không đưa token/password/raw state lên Git.
Hoàn thành khi mỗi yêu cầu truy được tới chứng cứ và kết luận có giới hạn rõ,
người khác tái tạo được bài đo từ runbook và manifest private được bàn giao.
```

## 7. Checklist nghiệm thu chung cuối đợt

- [ ] A1–A4: inventory, bộ Hava và sơ đồ bổ sung, mô tả thành phần/so sánh dịch vụ, diagram sự cố/restore.
- [ ] B1/B2: đúng quy mô dữ liệu, nguồn ảnh, session/mapping riêng, công cụ seed/cleanup đã kiểm.
- [ ] B3: ma trận test có thực tế/evidence, demo end-to-end, invariants và lỗi còn lại.
- [ ] C1–C3: runbook tái tạo, metrics gốc đã làm sạch, biểu đồ/video, gate tải chuẩn và hai tầng scaling.
- [ ] C4/C5: compute AZ/RDS/Redis có window, timeline, probe nghiệp vụ, kết quả và baseline cuối riêng.
- [ ] B4/B5: DB mới/app riêng, PITR markers, S3 version/hash, app dùng được, RPO/RTO đo đúng.
- [ ] Không vượt quota mail do test; không còn backlog synthetic có thể gửi thật sau khôi phục.
- [ ] Dọn tài nguyên tạm đúng manifest; lưu evidence và ghi tài nguyên giữ lại/chi phí/người sở hữu.
- [ ] Git chỉ chứa output đã làm sạch; file source/export/chart/report/video link truy cập được.
- [ ] C6: ma trận tất cả yêu cầu, kết luận có bằng chứng; phần chưa đạt không bị bỏ hoặc đổi thành Pass.

Đợt giao việc chỉ được đánh **hoàn thành toàn bộ** khi checklist có kết quả xác thực. Nếu vướng blocker, bàn giao đầy đủ phần đã thực hiện và danh sách thiếu; giữ trạng thái chưa hoàn tất cho yêu cầu đó thay vì bỏ bớt phạm vi.

## 8. Nguồn công cụ và thao tác cần xác minh khi thực hiện

- [Hava AWS views](https://docs.hava.io/new/quick-aws-overview), [Hava security](https://www.hava.io/our-security).
- [ECS managed scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-scaling-behavior.html).
- [RDS reboot with failover](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_RebootInstance.html).
- [RDS point-in-time restore](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PIT.html).
- [ElastiCache failover](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/AutoFailover.html).
- [S3 previous versions](https://docs.aws.amazon.com/AmazonS3/latest/userguide/RestoringPreviousVersions.html).

Nguồn này phục vụ hướng thực hiện; thông số thực tế/quota/API phải được đối chiếu tại thời điểm chạy. Bản thân tài liệu kế hoạch không phải bằng chứng đã thao tác Hava hay AWS.
