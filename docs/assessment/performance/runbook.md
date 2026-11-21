# C3 — Thực thi AWS và cleanup

Chỉ target https://labseat.id.vn và batch `demo-load-mechanic21`. Kiểm [backup/TTL/mapping](../functional/dataset.md), workeremaildisabled ổn định, B3smoke, clock/targets/DB/limits trước tải. Không chạy đồng thời fault/restore. Giữ credentials/rawlogs private.

## Thứ tự

1. Baseline5VU bằng `scripts/assessment/observability/cloud-runner.ps1 -Phase baseline`.
2. Queueoperator `begin`, chờ recovery_not_before, `disable`; kiểmOFF rồi `-Phase platform`15phút. Xong `enable` và kiểmready/baselinepolicy.
3. QueueON: `-Phase admission20`, rồi `-Phase admission50`,5phút/mức.
4. `-Phase scaling60`; tăng100/150/200 chỉ khi chưa thấy EC2out, cònTTL/gates/headroom. Hold15phút/mức, không chỉnhdesired.
5. `-Phase recovery`30phút; quan sát đến45phút nếu cần, đối chiếu activities/task/instance thực.

`cloud-runner.ps1` Start trảreceipt riêng. ChờSTOPPED rồi `-Stage Collect -Receipt <private-receipt> -Aws <aws.exe>`. Không Start lại khi chưa rõ taskcũ. Bundlehashverified, Fargate2048CPU4096MiB ngoàiASG, ClockDrift phảiSYNCHRONIZED/bound≤100ms, TTL≥2giờ. Dùng Linuxk6binary đã kiểm; không cài vàoEC2ứng dụng.

`cloud-queue.ps1 -Operation status|begin|disable|enable|finish` dùng operatorqueue-onlytạm và2SSMsecretreferences. Không đổiACL/passworduserRedis hiện hữu. Recovery_pending phải drain/finish để phục hồi, không để website chờkhi kết thúc.

## Cấp lại và evidence

`run-isolated-load.ps1 -Stage sessions -Batch demo-load-mechanic21 -MinimumValidSeconds 14400 -Execute`, sau đó cùngbatch `-Stage smoke ... -Execute`. Cần tunnelSSM/TLSverifyfull/backupverified. Không kéo dài TTLtrongfile. Gói4file private đúngmanifest, không chứa backupkey/master.

Collector C1 `collect.py`/runner.ps1 với inventorythực, interval30s,DBbudget51. `node scripts/load/summarize-c3.mjs <private-metrics.ndjson> <public-phase-dir>` tạoCSV/SVG đã loạiURL/token/PII; `chart.py` vẽmetricsresources, giữgaps. Không biến thiếu thành0.

## Kết thúc

Sau tất cả loadtaskdừng: probe/invariants, cleanupdryrun rồi execute đúngbatch vàmanifest `0a59f708-244e-5d0d-80d1-c3907727db17`, kiểm10bảngdemo/7invariants, giữ backup. Gói phiên chuyểnRETIRED khi cleanup. Gỡ đúngRedisusertạm khỏigroup/đợiactive/deleteuser, xóa2SSMparams vàinlinepolicytạm; không sửaTerraformpolicy. Dọn taskdefinitionrevisions/S3versions theo receipts sau tảiartifact về, dừng monitor/collector/tunnel của lượt này. Ghi riêng bước chưa làm và kết quảFAIL.
