# Fixture PostgreSQL TV3

Chạy trên DB mới, dành riêng cho test. Kết nối bằng cấu hình psql của máy local.

```powershell
psql -X -v ON_ERROR_STOP=1 -d labseat_tv3_fixture -f fixtures/tv3/schema.sql
psql -X -v ON_ERROR_STOP=1 -d labseat_tv3_fixture -f fixtures/tv3/verify.sql
psql -X -v ON_ERROR_STOP=1 -d labseat_tv3_fixture -f scripts/tests/db-invariants.sql
```

`verify.sql` kiểm tra hai partial unique index và giải phóng chỗ khi hold hết hạn, sau đó rollback toàn bộ dữ liệu mẫu. Bài kiểm tra luồng đồng thời nhiều kết nối cần app và migration chính thức. Fixture này chỉ mô tả schema logic, không dùng làm migration TV4 hoặc dữ liệu để apply AWS.
