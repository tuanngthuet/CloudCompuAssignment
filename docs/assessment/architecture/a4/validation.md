# Kiểm tra A4 — cập nhật 21/11/2026

- Pin hai commit từ ZIP archive comment; kiểm ZIP không lỗi và đường dẫn giải nén an toàn.
- Đếm trực tiếp CSV B3: 337 dòng, 333 PASS/0 FAIL/1 BLOCKED/3 NOT_RUN; V01 BLOCKED, X01–X03 NOT_RUN. Không tạo CSV thứ hai. Kết quả/hash nằm tại b3-csv-verification.json.
- Kiểm 19 file trong 5 manifest nguồn: tất cả khớp. Text B khớp sau CRLF→LF (B4/B5/C1 có khai báo trong manifest); summary C2 cũng khớp sau chuẩn hóa LF. C2 local-smoke.log dùng raw bytes, không tự chuẩn hóa gây báo sai mismatch. Chi tiết source-hash-audit.json. Chưa đối chiếu report_sha256/source script hashes không có bytes tương ứng.
- C6 ghi 379/379 links là kết quả workspace owner ở snapshot cũ; A4 không chạy c6-audit và không lặp lại tuyên bố đó như kết quả riêng. Link nguồn pin commit có thể cần quyền GitHub, chưa kiểm truy cập web.
- Bằng chứng B4/B5/C1 đã kèm được giữ nguyên và đối chiếu hash. Manifest gốc có summary.md không đóng gói trong A4 như đã ghi ở bản trước; source-manifest.json liệt kê chính xác file đính kèm.
- B3 retest/C2 test do owner thực hiện; A4 không chạy test app/AWS. Raw C3–C6 private không có trong ZIP; summary được ghi nhận cùng giới hạn clock.
- Sơ đồ baseline đã đổi thành C6 snapshot 5 EC2; sơ đồ S3/PITR/fault giữ nguyên vì chưa có run mới tương ứng. PNG/SVG/DOT đều có; kiểm đóng gói trong package-checks.json.
- A4 không sửa A1–A3/app/migrations/B/C, không tự commit hoặc push. B4/B5 tích hợp/C4/C5 chưa nghiệm thu.
