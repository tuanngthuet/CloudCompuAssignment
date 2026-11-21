# C1/C3 — Metrics thực

Collector từ Người3 commit e2431f3. Lượt21/11: `20261121T073249Z-C1-1f8bc6` trướcbaseline và `20261121T114346Z-C1-042424` khi tiếp tục. Rawinventory/metrics/activities/manifest giữprivate; publicsanitized loạiaccount/ARN/IP/instanceID.

Theo dõi ECSdesired/running/pending/CPU/RAM; ASGdesired/in-service/activities/registeredinstances/CPUcredits; ALBhealthy/requests/latency/errors; RDSconnections/CPU/freeRAM; Redis; SQS/DLQ/age; emailSKIPPED; generatorClockDrift/cgroupCPU/RAM. Đối chiếu bằngtimestampUTC đúngphase, tách tasktooling/deploy khỏi load.

Collector30s, CloudWatchbucket60s và cóđộtrễ. MISSING_OR_DELAYED không phải0. Giữsource_at vàgaps trongchart. CPUcreditinstancealias phảiổnđịnh. ControllerWindows chưa có xác nhậnNTP; clockrequest dùngFargatemetadataSYNCHRONIZED, không nhậncontroller đã sửa.

`runner.csv` mỗi10s; fallbackcgroupv1/v2 từphase saubaseline. ThiếuCPU/RAM thì ghi thiếuheadroom. `summarize-c3.mjs` loại preflight vàtạoRPS/latency/error/workflowphútUTC; `chart.py` vẽresources từmetrics.csv. Không nhậnCPUtăng là chứngminhEC2autoscale. [Kết quả](load-report.md), [runbook](runbook.md).
