# C3 readiness chỉ đọc — 20261120T1432Z-c3-readiness

Nguồn: runner Windows ngoài ASG theo xác nhận Người 3; nhánh `assessment/load-resilience`. Đây là kiểm tra preflight, **không phải run tải C3**. Không ghi token, cookie, password hoặc raw AWS state. Mốc UTC dưới đây lấy từ runner; Windows Time chưa đồng bộ nên phải đối chiếu lại sau khi sửa clock.

| Phép kiểm/lệnh | Kết quả quan sát |
|---|---|
| `C:\Program Files\k6\k6.exe version` | `k6.exe v2.4.0 (commit/dd9395906d, go1.26.11, windows/amd64)`, exit 0. `where.exe k6` không tìm thấy vì PATH của shell agent chưa cập nhật. |
| `Get-CimInstance Win32_OperatingSystem`, `Win32_Processor` | 14:32:45 UTC: 20 logical processors; 15,73 GiB RAM tổng, 2,85 GiB khả dụng. Chưa có số đo lúc tải. |
| `w32tm /query /status` | `Leap Indicator: 3 (not synchronized)`, `Stratum: 0`, `Last Successful Sync Time: unspecified`, `Source: Local CMOS Clock`. Clock gate BLOCKED. |
| `curl.exe --silent --show-error --max-time 15 --output NUL --write-out 'http=%{http_code} remote=%{remote_ip} duration=%{time_total}s' https://labseat.id.vn/healthz` | `http=200 remote=16.179.17.203 duration=0.762830s`; một GET chỉ đọc, không xác nhận dependencies dưới tải. |
| `curl.exe --silent --show-error --max-time 15 https://labseat.id.vn/lab-sessions` sau đó chỉ tổng hợp response trong PowerShell | 14:32:24 UTC: `queue_enabled=True`, 25 ca, 21 ca mở thêm ít nhất 16 phút theo đồng hồ runner. Không ghi raw response hoặc ID. Queue ON chặn bài Platform cần OFF; số ca mở không chứng minh có ca synthetic/100 seat. |
| `aws configure list-profiles` ngoài sandbox | Exit 0, output rỗng; không có profile để xác minh STS/account/region hoặc chạy collector C1 hiện tại. |
| `k6 inspect -e BASE_URL=https://labseat.id.vn` cho `catalogue.js`, `ecs-scaling.js` | Exit 0; đọc được options/stages local. Không tạo request. |
| Node test local và syntax | `booking.test.mjs` 9/9, `platform.test.mjs` 4/4, `ecs-scaling.test.mjs` 2/2, `summarize-c3.test.mjs` 1/1; `node --check` bốn script exit 0. Tổng 16/16 local, không phải phép đo AWS. |

Đối chiếu nguồn lịch sử: [B2](../b1b2-20261117a/summary.md) có 100 session đều hết hạn; [B3](../20261119T034356Z-b3-functional/summary.md) chưa có X01 sau tải; [C1/B4 smoke](../20261119T172832Z-b4-c1-preflight/summary.md) có metrics nhưng thiếu một số chiều và chưa chứng minh C3; [C2 local](../20261120T130757Z-c2-local/summary.md) chưa có job synthetic `SKIPPED`/Brevo/restore. Chi tiết và quyết định gate ở [báo cáo C3](../../../docs/assessment/performance/load-report.md).

**Kết luận:** C3 BLOCKED, cả năm bài AWS NOT_RUN; không có k6 summary, CSV/chart/video C3 thực. Không thay cấu hình AWS và không phát load.
