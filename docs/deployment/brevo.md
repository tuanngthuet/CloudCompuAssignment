# Email LABSEAT qua Brevo API

Email xác nhận dùng Brevo HTTP API `POST https://api.brevo.com/v3/smtp/email`. Luồng vẫn Confirm → PostgreSQL Outbox → publisher → SQS → worker; API đặt chỗ không gọi Brevo. Không thêm migration, không thay ticket/QR hay làm mất đăng kí khi email lỗi.

## Mẫu email

Header dùng logo LABSEAT hiện có (bản PNG tương thích email), dòng thương hiệu, đường kẻ xanh đậm. Nội dung gồm tên ca/sự kiện, ngày/giờ Việt Nam, phòng, mã đăng kí, QR check-in và website. Footer dành cho hệ thống đăng kí ca thi/thực hành, hỗ trợ tùy chọn và thông tin email tự động. Không gửi CCCD, điện thoại, mật khẩu hoặc hồ sơ cá nhân. Template HTML table/inline CSS, autoescape tên ca/phòng; không JavaScript/font ngoài/tracking bổ sung của ứng dụng.

[Xem desktop](../../evidence/current/email-desktop.png) · [mobile](../../evidence/current/email-mobile.png). Mẫu dùng dữ liệu giả và domain example; nội dung thực lấy từ PostgreSQL và cấu hình riêng.

Tự tạo preview, không cần API key, DB hoặc mạng:

```bash
python -m app.modules.notifications.preview --output .local/email-preview
# Mở .local/email-preview/confirmation.html
```

## Cấu hình local riêng, mặc định vẫn mock

| Biến | Nội dung |
|---|---|
| EMAIL_BACKEND | `brevo` khi chủ động bật gửi thật; compose chính vẫn `mock` |
| BREVO_API_KEY | Brevo API key qua ECS SSM hoặc môi trường do secret manager inject |
| BREVO_API_KEY_FILE | Đường dẫn file secret local; không dùng đồng thời với BREVO_API_KEY |
| BREVO_FROM_EMAIL | Sender đã đăng kí/xác minh trong Brevo |
| BREVO_FROM_NAME | Tên người gửi, mặc định LABSEAT |
| EMAIL_PUBLIC_BASE_URL | URL HTTPS công khai của LABSEAT, không query/fragment/credentials |
| EMAIL_SUPPORT_EMAIL | Địa chỉ hỗ trợ tùy chọn; bỏ trống thì footer không có dòng hỗ trợ |

Không dùng SMTP key thay API key. Trong Brevo, tạo API key, cấu hình sender/domain và kiểm tra tài khoản được bật transactional sending. Không cần gửi API key trong chat hoặc commit vào repo.

```bash
cp .env.brevo.example .env.brevo
mkdir -p .local/secrets/brevo
chmod 700 .local/secrets/brevo
# Dùng editor điền sender, public HTTPS website, support tùy chọn vào .env.brevo.
# Dùng editor lưu API key vào .local/secrets/brevo/api-key (một dòng, không dấu nháy).
chmod 444 .local/secrets/brevo/api-key
```

File secret read-only0444 để container uid10001 đọc được qua Compose secret mount; thư mục cha0700 ngăn tài khoản host khác đọc. Không đưa key vào environment của API/publisher hoặc build context. Nếu không dùng file, dùng secret manager inject BREVO_API_KEY trực tiếp vào worker. `.env.brevo` và `.local/` đã bị git ignore.

Sau khi cấu hình sender, website và secret, dùng lệnh sau để bật gửi email:

```bash
docker compose --env-file .env.brevo -f compose.yaml -f compose.brevo.yaml \
  --profile events up -d app sqs publisher worker
```

URL công khai phải phục vụ cùng LABSEAT API/DB để ảnh logo/QR tải được; localhost không phục vụ được email clients ở máy khác. Override chỉ chuyển worker sang Brevo và mount secret; không đổi queue/booking. Để về mock, chạy `docker compose --profile events up -d worker` bằng compose chính.

Bật cấu hình trước khi xác nhận một đăng kí mới có email để thử thật. Delivery đã SENT/SKIPPED, kể cả SENT từ mock, không tự gửi lại khi đổi backend. Không xoá hàng loạt delivery để thử email. Kiểm tra inbox/spam và transactional logs trong Brevo; messageId/SENT ở ứng dụng chỉ có nghĩa provider chấp nhận yêu cầu, không chứng minh inbox delivered.

## QR trong email

QR PNG đính kèm chứa **đúng ticket_code** đang dùng ở `/me/tickets/{id}/qr`; đã kiểm decode trong test. HTML dùng ảnh HTTPS từ `/email/tickets/{reservation_id}/{signature}/qr.png`. Chữ kí HMAC-SHA256 có scope `labseat-email-qr:v1`, key là ticket ngẫu nhiên256bit sẵn có; không đặt ticket_code hay email vào URL, không thêm signing secret hoặc bảng mới. URL là capability riêng cho ảnh vé đó, không tạo login session hay tự check-in. Signature sai/registration không tồn tại/vé bị huỷ/ca kết thúc →404, ảnh trả private/no-store/no-referrer. Check-in vẫn bắt buộc admin/auth/CSRF như trước.

Xử lí URL ảnh như dữ liệu riêng của vé; không đưa vào catalogue hoặc log raw URL. Request logger hiện tại dùng route template. Nếu sau này bật ALB/CDN/access logs, hạn chế quyền/retention hoặc redact đường dẫn có capability. Ảnh mail proxy/cache và tệp đính kèm có thể vẫn nhìn thấy sau khi huỷ; **backend vẫn từ chối check-in vé đã huỷ**, không dựa vào việc ảnh còn hiển thị.

Brevo transactional API không cung cấp Content-ID inline image trong hợp đồng gửi, nên không dựa vào `cid:` hoặc data URI dễ bị mail clients chặn. Dùng hosted scoped image và attachment base64 theo [Send transactional email API](https://developers.brevo.com/reference/send-transac-email); [hướng dẫn ảnh transactional của Brevo](https://community.brevo.com/t/does-transactional-email-support-embedded-image/6665). Mail client có thể chặn ảnh remote; PNG đính kèm là phương án dùng offline. Xem thêm [cấu hình sender trước khi gửi](https://developers.brevo.com/docs/send-a-transactional-email).

## AWS ECS

Không nhập Brevo key vào Terraform tfvars hoặc task environment plaintext. Khi chọn `email_backend="brevo"`:

- Tạo SSM SecureString `/labseat/lab/BREVO_API_KEY` qua công cụ secret riêng.
- Cấu hình Terraform `brevo_from_email`, `brevo_from_name`, `email_public_base_url`, `email_support_email`.
- Execution role được đọc parameter để inject, **chỉ worker task definition nhận BREVO_API_KEY**; API/publisher/migration không nhận key.
- Worker role chỉ cần SQS; API key Brevo được inject qua execution role. HTTPS outbound qua NAT hiện có.
- Register/deploy release mới theo runbook ECS; secret rotation không tự cập nhật task đang chạy.

Production tfvars example dùng Brevo; sender/domain/API key cần cấu hình trong tài khoản của người vận hành.

## Độ tin cậy và kiểm thử

Brevo request timeout bounded, không follow redirects và không tự retry POST. HTTP401/403/429/5xx, timeout hoặc response thiếu messageId →rollback delivery, giữ reservation CONFIRMED, không ACK SQS để retry/DLQ theo policy. Response body/API key/recipient/QR không được đưa vào exception text. Unique delivery + row lock giữ dedup trước đó; crash/timeout sau provider accept trước DB commit vẫn có thể gửi trùng, không exactly-once.

Tests dùng HTTPX MockTransport, PostgreSQL/Redis disposable và ElasticMQ; không gửi mạng tới Brevo. [Evidence](../../evidence/current/README.md) ghi kết quả thật. Browser preview kiểm layout desktop/mobile, không phải nghiệm thu Gmail/Outlook/inbox thực. Live sender/domain/quota/API key và delivery thực chờ cấu hình của người vận hành.

## Xác minh tài khoản, webhook và gửi lại

API và worker phải dùng chung AUTH_LINK_SIGNING_KEY≥32 ký tự, riêng môi trường; production inject qua SSM. BREVO_WEBHOOK_TOKEN≥32 ký tự chỉ cho API kiểm Bearer callback, không đưa vào trình duyệt. Compose Brevo override nhận thêm hai file `.local/secrets/brevo/auth-signing-key` và `webhook-token`; tạo giá trị ngẫu nhiên bằng password manager hoặc Python secrets, chmod thư mục0700/file0444 như API key. Không gửi secret trong chat. Không đặt đồng thời biến trực tiếp và biến *_FILE.

Đăng kí tài khoản → lưu hồ sơ/email → gửi liên kết xác minh → bấm xác nhận trong trang LABSEAT. Mọi ca cần email đã xác minh trước queue/hold/confirm. Link verify24 giờ; reset30 phút, một lần. Quên mật khẩu trả thông điệp chung, đổi mật khẩu cần mật khẩu cũ. Các mail này dùng durable jobs, template LABSEAT và public website của worker.

Đăng kí transactional webhook trong Brevo tới `https://HOST/webhooks/brevo`, auth `{type: bearer, token: <BREVO_WEBHOOK_TOKEN>}` qua giao diện/API Brevo. Chọn sent/request, delivered, hardBounce, softBounce, blocked, spam, invalid, deferred và error nếu provider hỗ trợ. Subscription names có thể khác event payload; backend xử lí `hard_bounce`, `soft_bounce`, `invalid_email`, `request` và các payload tương ứng. Endpoint lưu inbox trước khi trả202; worker hoặc maintenance đối chiếu và cập nhật trạng thái. Không gửi Authorization này từ JavaScript.

Job dùng idempotencyKey UUID, payload/sender snapshot từ lần gửi đầu. Brevo TTL30 phút; không tự retry kết quả chưa rõ quá29 phút. UNKNOWN cần admin đối chiếu transactional log; không suy ra thư thất lạc hay gửi thêm tự động. ACCEPTED chỉ có ACK API; DELIVERED là callback giao tới máy chủ nhận, không chứng minh inbox người dùng đã đọc. Bounce vĩnh viễn/spam/blocked tạo suppression. Mở Quản trị → Email để xem trạng thái, gửi lại vé và gỡ suppression có audit; chủ vé cũng có nút gửi lại, tối thiểu60 giây/lần và tối đa3/ngày/vé.

Kiểm thử repository dùng HTTPX MockTransport, không gửi thư thật. Chỉ sau khi sender/domain, DNS, API key và webhook được cấu hình thực mới nghiệm thu giao nhận, bounce và callback auth. Tham chiếu chính thức: [idempotency](https://developers.brevo.com/docs/heterogenous-versions-batch-emails), [transactional webhooks](https://developers.brevo.com/docs/transactional-webhooks), [webhook API](https://developers.brevo.com/reference/create-webhook).
