# C3 — Tải AWS thật ngày21/11/2026

Target https://labseat.id.vn. **Platform/admission đạt ngưỡng kịch bản; scaling60 FAIL, đã dừng an toàn; recovery30phút và cleanup đã thực hiện.** Không kết luận đạt60VU ổn định. Các kết quả này thuộc batch `demo-load-mechanic21` đã thu hồi; gói cấp lại22/11 là chuẩn bị riêng, không phải chạy lại C3.

Backup logical restore/hash/schema27bảng/7invariants PASS trước thay đổi; snapshotRDS available nhưng chưa restore chính snapshot. Ca Mechanic riêng180suất,100user/token/CSRF riêng đã smokeAWS; demo68suất giữ nguyên. [Backup/mapping](../functional/dataset.md).

Generator Fargate2vCPU/4GiB ngoài ASG, Linuxk6v1.0.0; clockmetadata SYNCHRONIZED. Không nhận Windowscontroller đã sửa NTP. API:10/schema0002_platform/digest `sha256:8cf4b144a8c1260b22ad4a6be6277d5d3b66552cdeda407dab894258243256ee`; không deploy appfix. Worker:10 emaildisabled; trialjob/deliverySKIPPED,attempts0. API2–8task,ASG2–6node,DBstopbudget51connections; không chỉnhdesired/policy để dựng autoscaling.

## Số đo thực

Giờ Việt Nam ngày21/11. RPS là trung bình trên khoảng ghi được. Baseline và Platform cách nhau vài giờ, không phải chuỗi liên tục.

| Phase | Khoảng đo | Requests / RPS | Độ trễ/lỗi | Kết luận |
| --- | --- | --- | --- | --- |
| Baseline5VU |14:34:00–14:41:01; ramp1/hold5/down1phút |7.467 /17,765 |p95 269,171ms;p99 585,146ms;HTTPerror0 |PASS ngưỡng |
| Platform |18:53:11–19:08:27;15phút |27.106 gồm setup /29,735 |p95đọc339,745ms/ghi406,087ms;1HTTP502,0,00369% |PASS;1.801workflow hoàn tất,dropped0 |
| Admission20VU |khoảng19:12–19:17;5phút |5.772 /18,778 |p95HTTP119,985ms;1HTTP502,0,0173%;chờp95 1ms/max5.039ms |PASS checks>99%;1.144confirm/cancel |
| Admission50VU |khoảng19:19–19:24;5phút |8.267 /26,614 |p95HTTP186,072ms;1HTTP502,0,0121%;chờp95 10.113,95ms/max15.722ms |PASS checks>99%;1.308confirm/cancel |
| Scaling60VU |19:27:49–19:35:22;dừng trong hold |5.426response ghi được /khoảng12 |189HTTP500=3,4832%;p95nearest-rank5.735,37ms;p9955.978,585ms |FAIL;không đủ hold15phút |
| Recovery |19:37:22–20:07:23;30phút |Không phát tải nghiệp vụ |API tự3→2,ASG tự6→5,targetkhỏe |OBSERVED tự giảm hai tầng |

[CSV/chart/summary](../../../evidence/assessment/20261121-c3-mechanic/). Scaling có NDJSON-derived partial-summary, không có k6summary hoàn chỉnh sauSIGTERM. RPS khoảng12 tính trên spanresponse452,31s, không phải throughputsteady đạt ngưỡng. Không chạy100/150/200VU sau lỗi.

QueueON capacity10/lease120s/heartbeat5s/grace60s; chỉ Platform có cửa sổOFF rồi khôi phụcON. Observer chỉ đọc240mẫu/5s: waitingmax30,admittedmax10,activeReservationsmax3. Đây là maxima lấy mẫu, không phải mọi thời điểm. Queuewait đo sau responsejoin, không gồm latencyHTTPjoin.

## Autoscaling và giới hạn

API tự2→3 doCPU18:59:01, rồi3→5 do requestpolicy19:01:43; đã đạt5running/5healthy. ASG tự4→5 lúc18:55:30, rồi5→6 lúc19:10:25. ASG đã dao động nền4–5 do capacityprovider/tooling; không gán mọi activity cho tải. Sau tải, API3→2 policy19:49:18/fulfilled19:49:50; ASG6→5 policy19:55:32/termination19:56:31. Không chỉnhdesired thủ công. Sau recovery:2task/2healthy,ASG5,DBkhoảng8connections; không nhận đã về minimum2 hoặc đúng4node. [Activities/charts](../../../evidence/assessment/20261121-c3-mechanic/resources/).

Scaling60 chạm32target5xx/358request trong1phút=8,9% và targetresponse gần30s; operator dừng riêng generator. CPUAPI khoảng89% đầu ramp,DBkhoảng10%/connections≤15,desired/running3,pending0; snapshotENI không thấy cạn chỗ. **Chưa có stacktrace đủ để xác nhận rootcause.** Không khẳng định DBpooldeadlock hoặcCPU là nguyên nhân sâu; cần điều tra app trước tăng tải tiếp. Ba502 lẻ khớp ELB5XX phút tương ứng; [AWS phân biệt ELB5XX phát sinh ở loadbalancer](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-cloudwatch-metrics.html), không gộp với target500 của60VU.

Guard cũ yêu cầu từng bucket10s đều>5%, có thể phản ứng muộn hơn tỷ lệ gộp2phút. Đã sửa weightedwindow,4unit safetytests PASS trong runtime không mạng; không nhận đã rerun60VU.17testscript PASS chỉ kiểm công cụ. Sourcehash thực thi giữ trong runsummary, khác source sửa cho lượt sau.

Collector cũ dùng sai namespaceCapacityProviderReservation; giữ MISSING gốc, xuất readback lịch sử namespaceđúng riêng có provenance. Capacityprovider target80%/placement spreadAZ trước binpackMEMORY cần rà soát theo [AWS ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cluster-auto-scaling.html); đây là hướng điều tra, cấu hình chưa đổi. [Chất lượng metrics](observability.md).

## Hậu kiểm/cleanup

SATdemo có sẵn hold→confirm→QR→cancel trước tải, giữa phase và sau dừng; availability trở lại. DBhậu kiểm20:15:14:scope tải còn0user/event/schedule/seat/reservation;10bảng nghiệp vụ demo theo PKgốc không đổi (chỉ bỏ qua users.last_activity_at),7invariants0.12poster/map demo đọc được/SHAkhớpbackup. Không nhận toàn27bảng production byte-identical sau đăng nhập/outbox/audit.

Đã cleanup100user/1event/1schedule/4vùng/4.254vé tảiCANCELLED,job/deliverySKIPPED attempts0; dọn2véSATprobe bổ sung. Dọn5Rediskey đúngepoch/ca,2ảnh bản sao hiện hành/registryrow; versionảnh lịch sử giữ retention. Đã xóa Redisoperator tạm/2SSMparams/inlineIAMpolicytạm, giữuser/policygốc. Đã xóa18versionstaging/deregister20taskdefinitiontạm, không sửaAPI:10/backup/ảnhdemo. Token/ZIP/master cũ đã loại khỏi bàn giao. [Receipt](../../../evidence/assessment/20261121-c3-mechanic/closure.json).

[Runbook](runbook.md),[B3](../functional/report.md). B3video và X02fault/X03restore chưa hoàn tất; recovery30phút này không thay fault/PITR/S3restore. Gói22/11 cóID/TTL riêng, chưa chạy tải, giữ chờ đo và cleanup sau đó.
