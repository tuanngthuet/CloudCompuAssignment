# Bắt đầu Task 1 / A1 trên Windows

Gói này chỉ thêm file trong `docs/assessment/architecture/`, không đổi app/Terraform và không commit/push tự động. Python collector không cài thêm package; cần Python3.9+ và AWS CLI v2.

## 1. Lấy source mới, giữ thay đổi cũ

Trong PowerShell tại repo đang làm (`C:\Users\dawn\Desktop\tv1-week1` nếu vẫn dùng bản này):

```powershell
git status
git fetch origin
```

Chỉ khi status sạch, ở nhánh làm việc của bạn (không phải main), lấy main bằng `git merge origin/main`. Nếu có conflict thì giải quyết trước; không reset/force. Không cần clone thêm hoặc xóa thư mục cũ.

Giải nén ZIP vào chỗ tạm, chép thư mục `docs` trong ZIP vào gốc repo để có:
`docs/assessment/architecture/collect-a1.py`. Nếu đã có file cùng tên do bạn tự sửa, so sánh trước khi thay.

## 2. Đăng nhập và kiểm tra đúng hệ thống

```powershell
aws sts get-caller-identity --profile tv1
```

Nếu hết phiên: `aws login --profile tv1`, rồi kiểm STS lại. Account dự kiến theo log cũ là 403030570855; xác nhận với chủ hệ thống nếu deployment đã chuyển tài khoản. Region khảo sát mới là **ap-southeast-2**, không dùng us-east-1 cũ. Không cần admin web hay mật khẩu DB cho A1.

## 3. Chạy collector CHỈ ĐỌC

```powershell
py -3 .\docs\assessment\architecture\collect-a1.py --profile tv1 --expected-account 403030570855
```

Nếu máy không nhận `py`, kiểm `python --version` rồi dùng `python` thay `py -3` nếu là Python3.9+.

Script chỉ gọi API trong allowlist. Không có apply, tạo/xóa tài nguyên, seed/reset DB, đăng nhập web, gửi mail hay đổi EMAIL_BACKEND. `--query` lọc output trước lưu nhưng AWS CLI có thể nhận response đầy đủ trong bộ nhớ; không bật debug, không log nguyên response. Metadata có thể chứa IDs/endpoint/trust policy nên vẫn giữ private.

Script tự chọn VPC khi đúng một VPC có tag Project=labseat. Nếu nhiều/không có VPC, dừng và kiểm VPC với quản trị; chạy lại với `--vpc-id vpc-...` đúng dự án. Cluster mặc định lấy từ source là labseat-lab; nếu khác dùng `--cluster TEN_THAT`. Các tham số chỉ chọn tài nguyên, không tạo tài nguyên.

Đầu ra mới mỗi lần:
`.local/assessment/<UTC>-A1-<suffix>/summary.md`, `manifest.json`, các JSON metadata.
Script kiểm `.local/` bị Git ignore trước khi lưu. Không có AWS credentials trong ZIP. Không gửi toàn bộ thư mục private lên Git/ChatGPT.

- COLLECTED: API đọc thành công, chưa có nghĩa cấu hình đúng hay task PASS.
- PARTIAL: ECS báo failures dù API thành công; phải kiểm tra.
- BLOCKED: quyền/phiên/mạng/CLI/target lỗi; ghi rõ, không suy không có tài nguyên.
- Exit2: có BLOCKED/PARTIAL; exit0: các API được gọi thành công, vẫn cần review và checklist bổ sung.

**Gửi trước `summary.md`** (chỉ tên phép đọc/status/error code), cùng VPC/cluster bạn xác nhận. Không gửi token, password, state, connection string hoặc env values. Từng JSON cần chia sẻ phải review bỏ IDs/endpoints nhạy cảm trước.

## 4. Hoàn tất inventory và bàn giao

Đọc `inventory.md` đã điền từ source. Đối chiếu JSON với từng dòng, ghi UTC và actual; mục chưa thu giữ UNKNOWN. Collector không thay thế IAM security audit, DNS, Hava, schema hoặc diễn tập.

Checklist bổ sung bằng Console/describe chỉ đọc: VPC DNS flags; EBS kích thước/mã hóa; capacity provider; ACM status/domain; DNS Tenten; IAM policies thực của các role; scheduled maintenance; SNS subscription confirmed (không copy email); S3 TLS policy/lifecycle; Redis subnet/ACL. Không bấm nút thay đổi hoặc đọc secret. Ghi AccessDenied chính xác đã làm sạch khi thiếu quyền.

Bản public sau review đưa vào `evidence/assessment/<run_id>/`, gồm summary/manifest đã ẩn thông tin không cần công khai. Không copy private JSON hàng loạt. `inventory.md` là tài liệu của Người1; phần app/runtime chỉ đề xuất với owner.

## 5. Cuối ngày tạo branch, commit/push theo yêu cầu nhóm

Chỉ khi đã kiểm đúng nhánh và review file:

```powershell
git switch -c assessment/architecture
```

Nếu nhánh đã có, dùng `git switch assessment/architecture` khi working tree cho phép. Không tự tạo lần hai hoặc dùng force.

```powershell
git add docs/assessment/architecture
git diff --cached --check
git diff --cached --stat
```

Đọc staged diff, kiểm không có raw/secret; rồi:

```powershell
git commit -m "docs(assessment): A1 inventory baseline and read-only collector"
git push -u origin assessment/architecture
```

Đây là hướng dẫn, gói chưa chạy các lệnh Git này. Nếu nhóm yêu cầu giữ nhánh cũ, dùng nhánh đã thống nhất. Commit source baseline với AWS BLOCKED được, nhưng không gọi A1 accepted.

## 6. Nguồn và kiểm tra công cụ

- AWS CLI query: https://docs.aws.amazon.com/cli/latest/userguide/cli-usage-filter.html
- ECS services: https://docs.aws.amazon.com/cli/latest/reference/ecs/describe-services.html
- ECS task definitions: https://docs.aws.amazon.com/cli/latest/reference/ecs/describe-task-definition.html
- Kế hoạch: `docs/sprints/ke-hoach-nghiem-thu-4-ngay.md`.
- `test-collector.py` dùng mock, không kết nối AWS; xem `validation.md` cho kết quả tại môi trường soạn gói.
