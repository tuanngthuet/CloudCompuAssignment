# C4 — ảnh Console do Người 3 cung cấp ngày 20/11/2026

Nguồn: 10 ảnh trong tin nhắn bàn giao C4. Bản gốc được giữ riêng tại `.local/assessment/c4-console-20261120/01.png` đến `10.png` (Git ignore); SHA-256 theo thứ tự ảnh:

| Ảnh | SHA-256 |
|---|---|
| 01 | `8BB197D419252B661FE8156C1DD0B86DDCDB75D49BCB2F1599B48ACA3573240B` |
| 02 | `FFD66449BB5D6CA311F1B0AD3A9F2B124D4B3491F2D56E67711362F9A325B407` |
| 03 | `3BA6F9AC3315719638D8442A59C4D075C9E6042AC0C60BD2AC7F6CE3C5FD7535` |
| 04 | `76726508197A42378F216BB55D3394EF286FB9488F8276CAC3F95F685B5E8BAA` |
| 05 | `9DFD4A30D0ABF06233708FBADD02AE7CA6A8B74DEC277E3AEEC3CBF51B428300` |
| 06 | `2CFEA8101978FA95ECE28833D51FCD6386484A8336E9F0CE46CF32A66D20C95B` |
| 07 | `BA4D608E63D2B366A959A67154B42B17BB9EF2EFC6F2A5C8178E40A003FDA80F` |
| 08 | `2D82E1DB2C456BCBB831E4F6C7A41548A11121D9312E48FD34DFD2F25AE1D13C` |
| 09 | `005E8E6486FF1565FF344688368379547216DFE24EA7AEAB6875BDAE7DBFBDB0` |
| 10 | `87C84DB6A7FF5F89B30857FEEC9974BAD8CC2F7C9779116CCFBAC55A3D5FFD6A` |

## Đọc được trực tiếp từ ảnh

| Nội dung | Ảnh | Quan sát |
|---|---|---|
| ASG app | 01–02 | Desired 4, min 2, max 6; 4 EC2 `InService/Healthy`, hai ở `ap-southeast-2a` và hai ở `ap-southeast-2b`; t3.small. ASG có hai app subnet. |
| ECS cluster | 03, 05 | 3 service active; 4 task đang chạy, 0 pending; 4 ECS container instance đăng ký. Task list còn có lịch sử task bảo trì; không đọc `Tasks (16)` như 16 task đang chạy. |
| Placement | 04–05 | Một API task đang chạy trên EC2 ở `ap-southeast-2a`. Một EC2 2a có 0 task, EC2 2a còn lại có 1; hai EC2 2b lần lượt có 2 và 1 task. Chưa ghép đầy đủ ARN/task IP ↔ ALB target trên cả hai AZ. |
| CPU/RAM | 05–06 | EC2 2a không có task hiển thị 2.048 CPU units và 1.529 MiB available. Hai EC2 2b lần lượt hiển thị khoảng 0,493 và 0,993 GiB available; EC2 đầu tương đương khoảng 505 MiB, dưới memory task API 512 MiB trong Terraform. Đây chỉ là snapshot, chưa chứng minh xếp được task sau fault. |
| Network/IP | 07–10 | Một EC2 2a đang running, một app subnet 2a hiển thị 247 IPv4 còn lại. Ảnh 10 cho thấy EC2 2a có hai network interface; không có số branch ENI/ENI slots còn lại trên từng ECS instance. |

Các trang Console hiển thị mốc **20/11/2026 khoảng 22:07–22:13 UTC+07:00**, tương đương khoảng **15:07–15:13 UTC**. Đây là thời gian hiển thị của Console, chưa có đồng bộ clock runner hoặc một snapshot AWS CLI cùng thời điểm. Ảnh không chứng minh `agentConnected`, ECS `remainingResources.ENI`, ALB target healthy ở cả hai AZ, DB/Redis/queue, ASG suspended processes, hoặc quyền mutate/rollback. Chưa có preflight private, target list khóa, prepare isolation hay inject. **Không dùng ảnh này để đánh PASS hoặc chọn EC2 cần stop.**

Kiểm tra runner sau khi nhận ảnh: `aws configure list-profiles` ngoài sandbox trả danh sách rỗng; `w32tm /query /status` báo `Leap Indicator: 3 (not synchronized)`, `Stratum: 0`, `Last Successful Sync Time: unspecified`, nguồn `Local CMOS Clock`. Vì vậy chưa chạy được preflight AWS CLI và không dùng clock runner để đo timeline/RTO.

**Cập nhật sau ảnh:** profile `tv2-compute` đã đăng nhập đúng account và [preflight AWS CLI chỉ đọc](../20261120-c4-cli-preflight/summary.md) đã chạy. ASG lúc đó có 5 EC2, khác snapshot 4 EC2 trong ảnh. Đồng hồ vẫn chưa đồng bộ; capacity ENI và các gate C4 khác còn BLOCKED.

**Kiểm lại sau đó:** [preflight capacity mới](../20261120-c4-capacity-recheck/summary.md) thấy ASG trở về 4 EC2 và xếp được task mất ở cả hai hướng AZ theo giới hạn ENI native của EC2; cả hai hướng thiếu một slot API overlap sau khi xếp. Đây là snapshot chỉ đọc, không thay thế baseline đúng cửa sổ fault. C4 vẫn BLOCKED, chưa prepare/inject.
