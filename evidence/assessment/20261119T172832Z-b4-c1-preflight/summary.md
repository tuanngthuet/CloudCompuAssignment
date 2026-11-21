# C1 bàn giao — hỗ trợ B3/B4/B5 của người2

Nguồn collector/chart/runner nguyên bản từ assessment/load-resilience@7fa878a;6 test offline đạt. Smoke ngày20/11/2026 giờ Việt Nam:4 mẫu,252 dòng,0 lỗi API; có1 vòng30,78s và metric thiếu/chậm. CSV giữ status/source_at và EC2 ID đã thay alias. Hai chart chỉ minh họa quan sát, không phải tải/scaling/fault.

B4: SQL thật max_connections79, reserve3+2, non-reserved74, budget66 còn8; rolling ceiling65. Có9 client connections gồm probe,7 invariants zero rows. Quota DB1/40, storage20/100000GiB, snapshots0/100. ENI/memory chỉ cho cận trên slot, không chứng minh placement.

B3 X01–X03 vẫn NOT_RUN; B5 images_verified=false; PITR/RPO/RTO chưa có. Probe ECS chỉ đọc đã STOPPED; email worker disabled, không đổi dịch vụ/capacity/email. Không thay trạng thái nghiệm thu C1 của người3. [Chi tiết](checks/results.json).

Không thu chuỗi lock-wait DB, thời điểm failover Redis hay request stream nhiều API task; chưa chạy k6/kiểm saturation và đồng bộ clock khi tải. Không kết luận C1 đầy đủ từ smoke này.
