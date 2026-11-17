# A1 — Kiểm tra công cụ tại môi trường soạn gói

- Ngày: 17/11/2026; source baseline `b29675d0e22bf76e2a4b3c91e04f1bb68193c891`.
- Python AST parse: PASS cho collector và offline tests.
- 7 unittest offline: PASS; subprocess AWS được mock, không gọi AWS.
- Mọi JMESPath query đi qua đường thu thập giả lập được compile với jmespath1.1.0: PASS.
- Kiểm tra: chặn API ghi/đọc secret, account sai dừng, nhiều VPC dừng, AccessDenied không lưu raw error, timeout BLOCKED, ECS partial không nhận thành công, task batching101->100+1, manifest NOT_REVIEWED.
- Chưa kiểm chạy collector bằng AWS CLI thật hoặc Windows; chưa xác minh API permissions/target, chi phí, deployment hoặc runtime.
- Không chạy Terraform, app, DB, load, mail, fault; không dùng mật khẩu trong ảnh/chat.
- `COLLECTED` trong output mock là nhãn nội bộ test, không phải evidence AWS.
- Gói chỉ thêm docs/assessment/architecture; không commit/push.

Lệnh kiểm tra trên máy (stdlib, không gọi AWS):

```powershell
py -3 .\docs\assessment\architecture\test-collector.py
```

Query compile là kiểm tra developer bổ sung nếu có module jmespath; user không cần cài nó để chạy collector.
