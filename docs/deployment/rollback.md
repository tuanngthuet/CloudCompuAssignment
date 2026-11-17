# ECS rollback

`deploy/rollback.sh` dùng `.local/ecs-last-good.json` (đúng account/cluster), phục hồi API/worker/publisher task definitions đã qua release smoke gần nhất. Chạy với AWS_PROFILE/AWS_REGION/EXPECTED_AWS_ACCOUNT_ID và DEPLOY_CONFIG của môi trường. Script đợi bounded rollout rồi smoke đúng digest/DB. Không reverse migration, không đổi secret runtime về giá trị cũ: ECS inject giá trị SSM hiện tại khi start, nên phải sửa secret hỏng trước rollback nếu secret đã đổi.

Circuit breaker có rollback cho startup/ALB liveness failure. Thiếu capacity có thể stall; wrong DB có thể vẫn /healthz200. Script timeout/release smoke failure dừng và chẩn đoán, không coi old healthy ALB task là proof của candidate. Nếu release đã được ECS đánh dấu successful nhưng smoke fail, last-good vẫn giữ release trước. Thực hiện rollback thủ công sau khi xem events/ENI/RDS configuration; tránh blind redeploy. Lần deploy đầu chưa có last-good, phải sửa configuration và deploy lại; tắt traffic/maintenance nếu cần.

Schema head0002_platform. Image rollback phải tương thích schema và manual check-in policy; kiểm trong staging trước khi vận hành. Không xoá outbox/delivery/rows hoặc downgrade để rollback image. Event đã commit còn pending khi publisher/Brevo lỗi. Email đã gửi không thể thu hồi; crash acceptance có thể duplicate. Backup DB/state/deployment metadata theo quy trình trước thay đổi; kiểm restore RDS thật là AWS acceptance còn pending.

Nếu release vừa deploy thành công cũng đã trở thành last-good, script dùng `ecs-previous-good.json` để rollback về release thành công trước đó. Nếu candidate đang thất bại, dùng last-good hiện hữu. Lưu hai file cùng candidate metadata; không có previous thì script từ chối bịa một revision để rollback. Sau rollback smoke thành công, target được ghi lại last-good.

Release smoke kiểm các bảng/cột binary cần thay vì đòi Alembic revision bằng tuyệt đối HEAD của binary cũ; vì vậy schema mới hơn với additive columns/tables vẫn có thể rollback image. Contract migration làm mất cột phải chờ tất cả binary cũ ngừng dùng.

Head `0002_platform` bổ sung platform trên baseline đóng băng; migration giữ dữ liệu theo runbook. Chỉ chọn image tương thích model hiện tại; không downgrade để đổi image.

Maintenance schedule dùng definition được lưu theo last-good; deploy tắt lịch trước migration rồi bật cùng release sau smoke/dry-run. Khi rollback về release chưa có maintenance definition, giữ lịch tắt để operator cấu hình bản tương thích. Xem [maintenance](maintenance.md).
