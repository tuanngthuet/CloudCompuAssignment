# W1-TV3 RDS S3 IAM và phục hồi

Gói TV3 nhận contract v3, không đọc remote state hoặc thư mục của TV1, TV2, TV4. Chạy lệnh từ thư mục gốc repo.

## Kiểm tra độc lập

```powershell
terraform fmt -check -recursive infra/modules/data
terraform fmt -check -recursive infra/modules/iam
terraform -chdir=infra/modules/data init -backend=false
terraform -chdir=infra/modules/data validate
terraform -chdir=infra/modules/iam init -backend=false
terraform -chdir=infra/modules/iam validate
```

Không đưa thư mục `.terraform/`, state, file tfvars chứa bí mật hoặc dữ liệu DB vào gói bàn giao. Tích hợp dùng lockfile của root chung. Xem [fixture PostgreSQL](../../fixtures/tv3/MOCK_ONLY.md) để kiểm tra hai ràng buộc và xử lý hold hết hạn. Truy vấn `scripts/tests/db-invariants.sql` chỉ đọc và trả về chi tiết các nhóm trùng. Kiểm tra kết quả thứ hai để phân biệt hold đến hạn chờ xử lý với hold thiếu thời hạn.

## Nối đầu vào và đầu ra cuối tuần

| Nguồn | Dữ liệu và đích |
|---|---|
| TV1 | `project`, `environment`, hai `db_subnet_ids` thuộc hai AZ, `db_sg_id` vào module data. Kiểm route DB chỉ local và 5432 từ SG app. |
| TV3 và TV4 | `db_name` vào data. `db_endpoint` (host:port), `db_name`, `app_bucket_name` dùng để cấu hình app. |
| Module data | `app_bucket_arn` vào IAM. `db_instance_identifier` cho dimension của dashboard TV2. |
| TV2 và nhóm tích hợp | `log_group_arns` của log group app đã tạo trước. Nếu module monitoring cần output compute, tách phần tạo log group khỏi phần dashboard/alarm trong root tích hợp để tránh vòng phụ thuộc. |
| TV3 | `parameter_prefix_arn` kết thúc bằng `parameter/labseat/lab/`, không có wildcard. Truyền `kms_key_arn` nếu SecureString dùng CMK. |
| Module IAM | `app_instance_profile_name` vào Launch Template TV2. Dùng SSM Agent từ 3.3.40.0 trong AMI. Agent dùng kênh `ssmmessages` và cần kết nối HTTPS ra endpoint AWS qua NAT. |

Kiểm tra plan trước khi áp dụng tại buổi chung. RDS PostgreSQL 16, `db.t4g.micro`, gp3 mã hóa 20 GB, Single-AZ, backup 7 ngày. Bucket app mã hóa SSE-S3, chặn public, yêu cầu TLS và mặc định không tự xóa objects khi destroy.

### Cấp cấu hình và chạy migration

1. RDS quản lý mật khẩu quản trị trong Secrets Manager. Người vận hành được cấp quyền lấy bí mật quản trị qua kênh đã duyệt. Instance profile của app chỉ đọc cấu hình trong Parameter Store.
2. Cùng TV4 tạo danh tính PostgreSQL dành cho migration và danh tính runtime có quyền DML phù hợp. Không cấp quyền quản trị RDS cho app. Ghi `DATABASE_URL` runtime vào SecureString dưới `/labseat/lab/` qua quy trình không echo giá trị, không chuyển qua chat, shell history, Terraform state, AMI hoặc user-data. Nếu dùng CMK, kiểm tra key policy và quyền giải mã trong đúng đường dẫn Parameter Store.
3. TV3/TV4 đối chiếu mapping vật lý, kiểm backup và chạy migration/seed đúng release một lần từ môi trường có đường đến DB. Không chạy fixture. Sau refresh, kiểm `/readyz`, E2E qua ALB, query bất biến và tải ảnh trên A rồi đọc trên B.

### Kiểm quyền bằng instance profile thực

Dùng object thử duy nhất và parameter kiểm thử vô hại do người vận hành tạo. Ghi tên phép kiểm, mã lỗi và thời điểm. Không in giá trị parameter hay URL DB.

| Kỳ vọng | Phép kiểm |
|---|---|
| Allow | Put/Get/Delete object thử dưới `rooms/`. Đọc object đã chuẩn bị dưới `releases/`. Liệt kê bằng prefix `rooms/` và `releases/`. |
| Allow | Đọc SecureString dưới `/labseat/lab/` với giải mã, kiểm kết quả bằng mã thoát. Kết nối SSM và ghi stream trong log group app. |
| Deny | Put/Delete object thử dưới `releases/`, đọc key nằm ngoài cả hai prefix, liệt kê bucket không có prefix. |
| Deny | Đọc parameter vô hại ngoài `/labseat/lab/` và ghi vào log group thử nằm ngoài danh sách. Kiểm lỗi AccessDenied với tài nguyên đã xác nhận tồn tại. |

## Runbook backup, restore và cleanup

1. Kiểm tra retention và thời điểm restore khả dụng. Trước bài thử, ghi marker dữ liệu vô hại, ID, thời gian UTC, phiên bản app/schema và mốc backup/PITR được chọn.
2. Sau khi dừng thử tải và hoàn tất thử thay EC2, restore snapshot hoặc PITR thành **DB instance mới**, dùng DB subnet group và SG private. Xác minh mã hóa, instance identifier, endpoint, trạng thái và thời gian.
3. TV3/TV4 tạo hoặc xác minh lại thông tin xác thực phù hợp cho DB restore, cấp cấu hình tạm cho bản app kiểm chứng và kiểm `/readyz`, marker, bản ghi đại diện, luồng đọc/ghi. Đối chiếu kết quả với dữ liệu tại mốc backup và ghi timeline đến khi app dùng được DB restore.
4. Trả app về DB chính, kiểm lại, thu hồi cấu hình tạm và dọn DB thử theo lịch nhóm. Lưu evidence đã che bí mật trước khi dọn. Với DB chính, chỉ tắt deletion protection sau buổi sử dụng cuối. Chọn final snapshot identifier chưa tồn tại và theo dõi snapshot còn tính phí.

## Tài liệu kỹ thuật

- Cấu hình RDS và mật khẩu quản trị do dịch vụ quản lý. [Terraform aws_db_instance](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/db_instance)
- Kích thước gp3 cho PostgreSQL. [Amazon RDS DB instance storage](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_Storage.html)
- Quyền và kênh kết nối Session Manager. [AWS Systems Manager message APIs](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-setting-up-messageAPIs.html)
