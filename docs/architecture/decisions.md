# Quyết định kiến trúc LABSEAT

| Quyết định | Lý do và hệ quả |
|---|---|
| Modular monolith, chung image | Giữ API/UI/nghiệp vụ, tách process theo command chứ không tách microservices |
| Một cluster, một ASG, ba services | API/worker/publisher chia capacity; publisher overlap an toàn với SKIP LOCKED |
| Hai tầng scaling | Service task count theo nhu cầu; Capacity Provider tăng EC2 khi thiếu resources, không EC2 target tracking độc lập |
| PostgreSQL locks/slots giữ nguyên | Đã có concurrency tests; không thay bằng counter hoặc bỏ unique constraints |
| Additive migrations | Nâng schema giữ dữ liệu; không backfill email hoặc tự mở check-in |
| At-least-once + delivery lock | Không mất confirmed event; Brevo acceptance/crash có thể duplicate, không exactly-once |
| Healthz shallow, smoke đúng release | ALB sống qua shared outage; one-off image mới kiểm DB/schema, không chấp nhận old task |
| SSM injection/execution role | Runtime không đọc secret bằng EC2 role; CA inline vẫn kiểm certificate/hostname |
| Demo/production tách profile | Demo một NAT/SingleAZ DB/RedisEC2 hoặc managed1node; production MultiAZ/managedRedis2node/2NAT opt-in |
| CLI deployment và last-good | Timeout/exit checks, rollback cả services, không rollback schema; không hosted CI/CD |

Capacity assumptions và limitations: [capacity](../deployment/capacity.md). S3/DB không có shared transaction; cleanup mồ côi vẫn là operator maintenance, email worker không xoá ảnh.
