# Timeline bằng chứng

Các mốc thuộc hai lượt độc lập; không phải timeline một sự cố toàn hệ thống. B3 run ID là thời điểm gom báo cáo, không dùng làm thời điểm tất cả test.

| UTC | Việt Nam (UTC+7) | Sự kiện |
|---|---|---|
| 2026-11-19T05:09:38.739+00:00 | 2026-11-19T12:09:38.739+07:00 | B5 bắt đầu lượt độc lập |
| 2026-11-19T05:09:49.248+00:00 | 2026-11-19T12:09:49.248+07:00 | B5 before |
| 2026-11-19T05:09:53.296+00:00 | 2026-11-19T12:09:53.296+07:00 | B5 overwritten |
| 2026-11-19T05:09:56.503+00:00 | 2026-11-19T12:09:56.503+07:00 | B5 restored |
| 2026-11-19T05:10:04.533+00:00 | 2026-11-19T12:10:04.533+07:00 | B5 kết thúc, gồm cleanup |
| 2026-11-19T05:15:03.216+00:00 | 2026-11-19T12:15:03.216+07:00 | Kiểm cleanup chỉ đọc: vẫn trống |
| 2026-11-19T17:28:32.683+00:00 | 2026-11-20T00:28:32.683+07:00 | C1 preflight bổ sung cho B4 |
| 2026-11-19T17:29:15.732+00:00 | 2026-11-20T00:29:15.732+07:00 | Mẫu collector đầu |
| 2026-11-19T17:29:35.882+00:00 | 2026-11-20T00:29:35.882+07:00 | SQL nguồn: budget/invariants |
| 2026-11-19T17:30:46.516+00:00 | 2026-11-20T00:30:46.516+07:00 | Mẫu collector cuối |
| 2026-11-19T17:33:50.533+00:00 | 2026-11-20T00:33:50.533+07:00 | Quota/capacity bổ sung |

Nguồn: [B5](evidence/20261119T050938Z-b5-s3-restore/checks/results.json) và [C1/B4](evidence/20261119T172832Z-b4-c1-preflight/checks/results.json). Các mốc stage là timestamp ghi nhận trong JSON, không phải thời điểm người dùng bắt đầu mất dịch vụ.
