# C4 — kiểm lại capacity hai hướng AZ, chỉ đọc

Chạy trên nhánh `assessment/load-resilience`, source commit `09f768e168e03517a1636c1030059a7fd915b58a`; mã `preflight.ps1` tại lượt này có SHA-256 `54413EEDA33A50EA4322A45AB232B60F59BA8AF066487F179A22B7EBAE0000B3`. AWS profile đúng account dự kiến và region `ap-southeast-2`. Raw snapshot chỉ ở `.local/assessment/c4-recheck-20261120/`; không đưa ARN/EC2 ID vào Git. Đồng hồ runner vẫn chưa đồng bộ, nên thời gian UTC ghi trong raw không dùng làm mốc fault/RTO.

ASG tại hai snapshot tuần tự có desired/in-service **4**, min **2**, max **6**, chia **2 EC2 mỗi AZ**; bốn ECS task thiết yếu đang chạy. API target khỏe ở cả hai AZ. ECS không trả `remainingResources.ENI`; EC2 API cho biết `t3.small` tối đa **3 network interfaces**. Không container instance nào có thuộc tính trunk ENI; preflight dùng `maximum - interfaces đang gắn` làm số slot ENI bảo thủ, đồng thời kiểm CPU/RAM từng máy và subnet IP. Đây là phép xếp mô phỏng, cần kiểm lại live ngay trước mọi thay đổi.

| AZ mục tiêu | Task cần thay ở AZ còn lại | Slot ENI còn ở hai máy sống sót trước thay | Xếp được task mất | Thêm một slot API dự phòng sau thay | SHA-256 raw private |
|---|---:|---|---|---|---|
| `ap-southeast-2a` | 1 API | 0, 1 | PASS (1/1) | **BLOCKED** | `1FBC2FC86F515875F6552C4238919E39B21A197FEEF6845E2D9F4FEB3DC281DA` |
| `ap-southeast-2b` | 1 API + worker + publisher | 2, 1 | PASS (3/3) | **BLOCKED** | `2DEF426E352F04D720091F920A9BC9B0FD8FFD4C8A97F7FF22553091D62D73CA` |

Đây không phải xác nhận capacity đủ cho diễn tập: sau khi xếp các task cần thay, cả hai hướng đều không còn slot ENI cho một API overlap theo gate runbook. ASG từng có 5 EC2 ở [lượt C3 chỉ đọc](../20261120-c3-live-readonly/summary.md) nhưng giờ là 4; không dùng snapshot cũ để chọn EC2 hoặc tuyên bố ổn định.

Đọc thêm **AWS ASG Activity** (mốc do AWS trả): alarm target tracking của ECS managed scaling yêu cầu desired **4→5** lúc **15:40:16Z**; alarm low yêu cầu **5→4** lúc **16:15:32Z**. Sau đó ASG có activity cân bằng AZ với launch lúc **16:17:22Z** và termination lúc **16:17:32Z**, kết thúc lần lượt **16:19:27Z** và **16:18:16Z**. Một activity scale-in trước đó bị hủy vì các instance còn lại được bảo vệ. Không có C4 inject trong chuỗi này; đây là thay đổi capacity tự động trước diễn tập. Cần chờ baseline ổn định và đọc lại activity/placement, không gọi biến động này là recovery C4.

**Kết luận:** C4 BLOCKED, prepare/inject/observe/rollback NOT_RUN. Cần đồng bộ clock, chốt C3/B3/C2 và cửa sổ riêng, kiểm DB/runner/probe, chuẩn bị capacity ở AZ sống sót trong giới hạn ASG max6 rồi chạy lại preflight để đạt overlap; xác minh isolation không dịch chuyển task trước fault. Không có thay đổi AWS hoặc tải k6 trong lượt này.
