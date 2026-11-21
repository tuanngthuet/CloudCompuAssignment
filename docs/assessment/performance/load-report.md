# C3 — Tải trên AWS thật

Target https://labseat.id.vn, ngày21/11/2026. **Đang thực hiện; chưa nghiệm thu toàn bộ C3.** Dùng ca Mechanic riêng180suất, batch `demo-load-mechanic21`, giữ nguyên ca demo có poster. [Backup/mapping/TTL](../functional/dataset.md).

| Gate | Kết quả đã kiểm |
| --- | --- |
| Backup | Logical dump restore/hash/schema27bảng/7invariants PASS; chưa restore chính RDSsnapshot |
| B3 | SATdemo có sẵn hold/confirm/cancel/QR/CSV/stafflookup/race cuối PASS; dọn45vé thử |
| B2 | 100distinctuser/session/CSRF; smokeAWS14:15–14:16; hạn22:13:07 ngày21/11 giờVN |
| Generator | Fargate riêng2vCPU/4GiB ngoàiASG, k6v1.0.0Linux; baselineClockDrift SYNCHRONIZED/bound0,6614495ms |
| Email | Workerrevision10 disabled/stable; smokejob/deliverySKIPPED, providerattempts0 |
| Tài nguyên | APImin2/max8, ASGmin2/max6, DBbudget51; targetkhỏe/DB8 trước tải |
| Metrics | Collector30s, giữ source_atCloudWatch/missing; monitorstale120s/targets/DB/giới hạn |

## Kết quả theo phase

| Phase | Kết quả | Trạng thái |
| --- | --- | --- |
| Baseline5VU | 14:34:00–14:41:01 giờVN;7467requests;17,7647RPS;p95=269,171ms;p99=585,146ms;max1276,048ms;HTTPfailure0% | PASS thresholdbaseline |
| Platform | 18:53:11–19:08:27 giờ VN; 27.106 requests, 29,735 RPS cả setup; 1.801/1.801 workflow hoàn tất; dropped0 | PASS ngưỡng Platform |
| Admission | 20 và50 VU, đủ5 phút mỗi mức; queueON | PASS ngưỡng checks>99% |
| Scaling | 60 VU bị dừng sớm do lỗi/độ trễ; không chạy mức cao hơn | FAIL, không đạt đủ hold15 phút |
| Recovery | Đã bắt đầu quan sát30 phút sau dừng tải; chưa kết luận scale-in cuối | Đang đo |

BaselineRPS là trung bình cả ramp1phút/hold5phút/rampdown1phút, không phải cam kết năng lực. [CSV và chart](../../../evidence/assessment/20261121-c3-mechanic/baseline/). EC2dao động4–5 quanh one-offtooling trước tải không tính là autoscalingC3. Chưa đủ kết luận sức chịu tải hoặc điểm nghẽn; correctness/performance/autoscaling phải đánh giá riêng.

Mã tải/collector từ Người3 commit e2431f3, bổ sung mapping nhiều user/phòng capacity45 và guard100user/token/CSRF.17testscript PASS chỉ kiểm logic, không thay số đo AWS. Dừng khi sai dữ liệu,0targetkhỏe,5xx>5% trong2phút,DB≥51,API>8/ASG>6 hoặc stale120s. Không chỉnh desired để dựng kết quả.

Sau tải phải phục hồi queueON, giữ emaildisabled, kiểm probe/7invariants, cleanup đúngmanifest, kiểm10bảng demo và thu hồi Redis/SSM/IAM/task/S3tạm. Các bước này và biểu đồresource/video cuối chưa được đánh dấu hoàn tất. [Runbook](runbook.md), [metrics](observability.md), [B3](../functional/report.md).

## Platform đã hoàn tất — 21/11

P95 đọc **339,745 ms**, ghi **406,087 ms**, đều dưới ngưỡng 500/1.000 ms. Có một HTTP502 ở availability lúc18:55:58, chưa xác định nguyên nhân; HTTP failure khoảng0,00369%, không được mô tả là không có lỗi. Cả1.801 hold, confirm và cancel đều thành công; dropped iterations0. Generator RAM cao nhất438,34 MiB/4GiB, CPU cao nhất3,40% của2vCPU, clock luônSYNCHRONIZED. [Summary và chart Platform](../../../evidence/assessment/20261121-c3-mechanic/platform/).

Verify RDS sau Platform xác nhận demo không đổi và7invariants0. Đã bật lại queue:capacity10,lease120s,heartbeat5s,grace60s;1.802job/delivery của batch đềuSKIPPED, attempts0, toàn bộ vé thửCANCELLED. PolicyCPU tự tăng API2→3, policyrequests tiếp tục3→5; đã có5running/5healthy, không chỉnhdesired thủ công. ASG4→5 do managedcapacity80%; cần đối chiếu bài scaling/recovery trước khi nhận hoàn tất hai tầng.

## Admission đã hoàn tất

- 20 VU:5.772 requests,18,778 RPS;1.144 admitted/confirm/cancel; p95 HTTP119,985 ms, p95 chờ1 ms, max chờ5.039 ms. Một lỗi HTTP502 trên availability; tỷ lệ HTTP failure0,0173%.
- 50 VU:8.267 requests,26,614 RPS;1.308 admitted/confirm/cancel; p95 HTTP186,072 ms, p95 chờ10.113,95 ms, max15.722 ms. Một lỗi request; failure0,0121%. Không tăng capacity hàng chờ10.
- 240 mẫu chỉ đọc mỗi5 giây: waiting cao nhất30, admitted cao nhất10, active reservations cao nhất3. Đây là maxima lấy mẫu, không phải trace bao quát mọi thời điểm. [CSV/chart queue](../../../evidence/assessment/20261121-c3-mechanic/resources/admission.svg).
- Sau admission, verify RDS19:27:07 giờ Việt Nam xác nhận demo không đổi và7invariants0. Probe SAT demo hiện hữu trước scaling đã giữ–xác nhận–QR–hủy thành công, availability trả về như trước. Phiên student498 cũ được đăng nhập lại; không đổi mật khẩu.
- Check ENI/placement lúc19:30:6t3.small, tối đa3ENI/node; attached2/3/1/3/1/1. Không có placement constraint; spread theoAZ rồi binpackMEMORY. Đây là snapshot trong ramp, không ghi ngược là đã đo trước baseline.

## Scaling60 bị dừng an toàn — kết quả không đạt

Lượt19:27:49–19:35:22 giờ Việt Nam bị dừng sau khoảng7phút32giây, chưa hoàn tất hold15phút. Trong một phút CloudWatch ghi32target5xx/358requests (8,9%) và target response gần30giây. Operator dừng sớm để bảo vệ production, không đợi đủ12bucket; không tăng100/150/200VU và không đổi desired/policy/limits. [NDJSON-derived partial summary](../../../evidence/assessment/20261121-c3-mechanic/scaling60/partial-summary.json) giữ lỗi và toàn bộ các chart đã thu; không có k6summary hoàn chỉnh sauSIGTERM.

Bộ dừng cũ kiểm từng bucket10giây đều vượt5%, chặt hơn ý nghĩa tỷ lệ gộp2phút nên có thể phản ứng muộn. Đã sửa phép gộp và4unit safety tests đạt trong runtime không mạng/credentials. Thay đổi này phục vụ lượt sau; không nhận là đã chạy lại60VU hoặc đã sửa lỗi sản phẩm. Run hash nguồn cũ giữ nguyên trong receipt.

Probe HTTPS SAT demo sau dừng tải đã giữ–xác nhận–QR–hủy thành công, availability trở về như trước. Hậu kiểm RDS/cleanup đang thực hiện. Recovery chạy riêng30phút để quan sát tự giảm task/EC2; checkpoint này chưa đánh dấu hoàn tất.

Ba lỗi502 nhỏ ở Platform/admission khớp ba datapointELB5XX tại các phút tương ứng. Theo [định nghĩa AWS](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-cloudwatch-metrics.html), ELB5XX là lỗi phát sinh từ load balancer; chưa có root cause của lỗi lẻ. Mức60VU có target5xx và độ trễ~30giây; chưa có stacktrace để khẳng định nguyên nhân sâu, không suy ra RDS cạn tài nguyên chỉ từ latency.
