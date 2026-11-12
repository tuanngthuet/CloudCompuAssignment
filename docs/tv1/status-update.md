# Cập nhật hồ sơ sau kiểm tra Windows

Gói cập nhật 1.0.1 chỉ thay hồ sơ; không sửa Terraform hoặc gọi AWS. Chép ba thư mục docs, handoff, report từ ZIP vào gốc repo tv1-week1, chọn thay thế đúng các file trùng tên. Không xóa repo cũ, không git init lại.

Sau đó chạy ở gốc repo:

```powershell
git status --short
git add docs/tv1/account-budget.md docs/tv1/evidence/windows-check-summary.txt docs/tv1/refresh-checksums.ps1 docs/tv1/status-update.md handoff/tv1.json report/parts/tv1.md
powershell -NoProfile -ExecutionPolicy Bypass -File .\docs\tv1\refresh-checksums.ps1
git add handoff/files.sha256.json
git diff --cached --stat
git commit -m "docs(tv1): record Windows checks and GitHub baseline"
git push
```

Nếu một lệnh báo lỗi, dừng và xử lý trước khi commit. Script checksum không gọi Terraform/AWS, không đọc nội dung credential; chỉ tính SHA256 các file Git theo dõi, loại manifest tự tham chiếu và dừng khi thấy tên file nhạy cảm. Gói không gửi manifest băm sẵn vì .gitignore và kiểu xuống dòng trên máy bạn đã thay đổi; phải tính lại tại repo thật. Manifest băm working files hiện tại, không phải một cam kết nội dung giống hệt Git blob ở mọi OS.

Không cần chạy lại mock test chỉ vì thay đổi tài liệu. Log PASS đã cung cấp được ghi đúng là user-reported; nếu local-evidence/check-windows.txt có log đầy đủ, review không có secret rồi chép sang docs/tv1/evidence/windows-check-full.txt trước bước git add, và add file này riêng. Không thay thế summary bằng nội dung tự dựng.

Bước tiếp theo trước cuối tuần là chốt với quản trị: CLI auth cho tv1-network, MFA, quyền network/S3, quota, credit/hạn và budget. Chưa có các thông tin này thì tiếp tục để Pending; không đánh dấu Accepted hoặc G1 đạt. Không chạy apply trong bản cập nhật này.
