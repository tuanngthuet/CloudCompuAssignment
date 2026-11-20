# Đối chiếu bằng chứng A4

## Snapshot nguồn

| Gói | Nhánh | Commit từ ZIP archive comment |
|---|---|---|
| A4-functional-recovery.zip | assessment/functional-recovery | `05ea11cf3008a42b33e766841320896f4a10eaba` |
| A4-load-resilience.zip | assessment/load-resilience | `7fa878ac7e7995c25777680e44fe2da36d1e619c` |

Commit snapshot ZIP khác commit ghi tại thời điểm từng run. Giữ nguyên cả hai loại trong source-manifest.json và manifest gốc. Không gán commit ZIP cho image runtime: baseline ghi API digest `sha256:8cf4b144a8c1260b22ad4a6be6277d5d3b66552cdeda407dab894258243256ee`, schema `0002_platform`.

## B4 và baseline mới nhất

Nguồn [B4 preflight](evidence/20261119T043844Z-b4-preflight/checks/results.json) và [C1 smoke do Người 2 chạy](evidence/20261119T172832Z-b4-c1-preflight/checks/results.json).

- RDS Available/Multi-AZ, retention thực **1 ngày**; LatestRestorableTime `2026-11-19T17:23:02+00:00`. Không thay bằng mặc định Terraform 30 ngày.
- 2 API RUNNING, cùng digest, trên AZ 2a/2b; worker/publisher 1 task mỗi service; 2 ALB healthy targets. ASG desired/InService 4, min 2/max 6; placement EC2: 1 máy 2a, 3 máy 2b.
- SQL lúc 17:29:35 UTC: max_connections=79, reserve=3+2, non-reserved=74. Budget 66 còn 8; rolling ceiling 65. 9 kết nối SQL gồm probe; CloudWatch 8 là nguồn/thời điểm khác, không phải mâu thuẫn.
- 7 invariant trả 0 dòng trên **DB nguồn**. Không chuyển thành database_invariants_passed của DB restored.
- Quota snapshot: DB 1/40, storage 20/100000 GiB, manual snapshots 0/100. Bổ sung này cập nhật điểm quota chưa rõ trong ảnh Console cũ; không tự chứng minh quyền/KMS hay restore thành công.
- Slot ước tính tối đa: AZ2a=1, AZ2b=3, dựa CPU/RAM/ENI; là cận trên, chưa chứng minh đặt task hay chịu mất AZ. Không suy ASG còn máy là đủ headroom.

[CSV](evidence/20261119T172832Z-b4-c1-preflight/metrics.csv): 4 mẫu, 252 dòng; OBSERVED 211, MISSING 8, MISSING_OR_DELAYED 32, OVER_INTERVAL 1. Một vòng 30,78s vượt chu kỳ yêu cầu 30s. ALB RPS 0 trong mẫu; không có tải, latency/SLO hoặc traffic phân phối được kiểm chứng. Giữ nguyên status/source_at, không điền số 0 cho dữ liệu thiếu.

Ảnh Console C1 cũ và báo cáo C1 ghi BLOCKED trước smoke bổ sung. Smoke mới là bằng chứng thật được bổ sung từ nhánh Người 2, nhưng không tự đổi nghiệm thu C1 toàn bộ thành PASS.

## B5 — phần đã chạy

Nguồn [kết quả](evidence/20261119T050938Z-b5-s3-restore/checks/results.json) và [cleanup](evidence/20261119T050938Z-b5-s3-restore/cleanup-manifest.json). Một key synthetic chưa tồn tại: Put tốt → Put nội dung sai → CopyObject từ version tốt tạo current mới. Không dùng xóa làm thao tác phục hồi.

Hash before/restored bằng nhau; overwritten khác. Ba file PNG đính kèm khớp hash khai báo. Anonymous GET=403, authenticated GET và MIME image/png đạt theo JSON; đây là bằng chứng do nhóm bàn giao, không phải lượt gọi AWS mới của Người 1.

![Trước ghi đè](evidence/20261119T050938Z-b5-s3-restore/images/before.png)
![Nội dung sai](evidence/20261119T050938Z-b5-s3-restore/images/overwritten.png)
![Sau khôi phục](evidence/20261119T050938Z-b5-s3-restore/images/restored.png)

Ảnh trên là **bytes object tải từ S3**, không phải ảnh chụp app. Cleanup báo xóa đúng 3 versions, còn 0 versions/0 delete markers; kiểm lại 05:15:03 UTC vẫn trống. Các version đã dọn không thể dùng lại cho lượt tích hợp.

## Khoảng trống

B3 chưa có X01–X03 sau tải/fault/restore. Báo cáo B3 có PASS local và AWS riêng; không dùng tổng PASS để chứng minh phục hồi. Gói không chứa test-cases.csv được báo cáo dẫn tới, nên số tổng B3 được ghi nhận theo báo cáo/manifest, không tái tính ma trận.

Không có run C4/C5, incident/events, probe trong/sau fault hoặc phục hồi baseline C6. HA được bật và snapshot Available chỉ là cấu hình/trạng thái. Không đủ dữ liệu đo downtime, RPO/RTO hoặc availability 30 ngày.

Nguồn đọc thêm tại commit cố định: [B3 report](https://github.com/tuanngthuet/CloudCompuAssignment/blob/05ea11cf3008a42b33e766841320896f4a10eaba/docs/assessment/functional/report.md), [B4/B5 report](https://github.com/tuanngthuet/CloudCompuAssignment/blob/05ea11cf3008a42b33e766841320896f4a10eaba/docs/assessment/recovery/report.md), [C1 report](https://github.com/tuanngthuet/CloudCompuAssignment/blob/7fa878ac7e7995c25777680e44fe2da36d1e619c/docs/assessment/performance/observability.md). Đây là đường dẫn truy vết từ archive, chưa kiểm truy cập web; repo có thể yêu cầu đăng nhập.
