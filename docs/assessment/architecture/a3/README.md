# A3 — ERD, Sequence và ADR của LabSeat

Người thực hiện: Người 1 / TV1. Ngày soạn: 18/11/2026.
Trạng thái: bản phân tích source để review; chưa Accepted.

## Nội dung

- [ERD và từ điển 26 bảng](erd.md): 7 sơ đồ theo nhóm, PK/FK/nullable, ràng buộc đầy đủ từ model.
- [7 sequence](sequences.md): giữ chỗ; xác nhận; hủy; check-in; publisher; email worker; vòng worker/ack SQS.
- [Kết quả kiểm tra](validation.md).
- [Nguồn và SHA-256](source-manifest.json).
- `diagrams/`: 14 file Mermaid .mmd có thể chỉnh sửa; nội dung cũng nhúng trong các file Markdown.
- `adr/`: 5 ADR về nhất quán DB, idempotency, admission Redis, outbox/email, phiên và quyền check-in.

## Cách đưa vào repo và xem

Giải nén ZIP vào thư mục tạm rồi copy thư mục `docs` vào gốc repo LabSeat.
Các file mới nằm dưới `docs/assessment/architecture/a3/`; không thay thế A1, hava.md hoặc ảnh A2.
Mở erd.md/sequences.md trên giao diện Markdown có hỗ trợ Mermaid. Nếu preview VS Code chỉ hiện code, mở file trên GitHub sau khi push, hoặc dùng renderer Mermaid đã được nhóm cài.
Đã kèm 7 ảnh ERD PNG và SVG trong diagrams/rendered/. Các ảnh được dựng bằng Graphviz từ cùng dữ liệu sơ đồ; nhãn cạnh ghi FK và số lượng quan hệ. Sequence vẫn ở dạng Mermaid.

```powershell
git status --short -- docs/assessment/architecture/a3
git add -- docs/assessment/architecture/a3
git diff --cached --stat
git commit -m "docs(A3): add source-based ERD sequences and ADR drafts"
git push
```

Chỉ chạy commit/push sau khi kiểm tra staged files và đang ở đúng nhánh nhóm quy định.

## Phạm vi và giới hạn

- Đã đọc 3 file model/migration và A3-source.zip; ZIP dùng đường dẫn rút gọn, ánh xạ lại theo danh sách file user cung cấp.
- Chưa có commit SHA: không gán tài liệu này cho một release đã deploy.
- Không sửa runtime app, seed, scaling/fault hoặc dữ liệu AWS.
- Model/migration không chứng minh schema RDS hiện tại đã ở revision 0002.
- Sequence chỉ mô tả code; chưa có request trace/test tải/restore/failover.
- Đã bổ sung app/shared/http.py: transaction dùng db.begin quanh yield; cập nhật last_activity là transaction riêng sau giao dịch nghiệp vụ.
- ZIP thiếu profiles/service.py và accounts/service.py: không giải thích chi tiết require_for_exam, active và throttle vượt quá call site.
- Đã đọc main.py: router được include không thêm prefix. cli.py chỉ có seed/create-user/queue-settings/queue-recover. app/events.py là entrypoint publisher/worker và đã xác minh consume trước delete ở cấp source.
- Cấu hình EMAIL_BACKEND, COOKIE_SECURE và AWS environment không có trong gói; không khẳng định giá trị runtime.
- ADR là mô tả lựa chọn quan sát được và phân tích đánh đổi, cần owner xác nhận lý do quyết định.
- A2 Hava mô tả hạ tầng; A3 mô tả dữ liệu và hành vi source. Không dùng số EC2 để suy số bảng hay số task.

## Bước chốt với reviewer

1. Xác nhận source commit của các file đã gửi.
2. Đã review transaction, route wiring và app/events.py; đối chiếu lệnh ECS runtime nếu cần xác minh entrypoint triển khai.
3. Đối chiếu schema runtime/revision nếu rubric yêu cầu as-built.
4. Render sơ đồ, kiểm tra chữ và xuất ảnh theo định dạng yêu cầu báo cáo.
5. Owner xác nhận các ADR và reviewer ghi Accepted riêng.

## Xem ảnh ERD trực tiếp

- [erd-01-booking](diagrams/rendered/erd-01-booking.png)
- [erd-02-auth-staff](diagrams/rendered/erd-02-auth-staff.png)
- [erd-03-audit](diagrams/rendered/erd-03-audit.png)
- [erd-04-notifications](diagrams/rendered/erd-04-notifications.png)
- [erd-05-support](diagrams/rendered/erd-05-support.png)
- [erd-06-platform](diagrams/rendered/erd-06-platform.png)
- [erd-07-maintenance](diagrams/rendered/erd-07-maintenance.png)

Các nhóm 06/07 có bảng độc lập vì source không khai báo FK; không nối quan hệ giả.
