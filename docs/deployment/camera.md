# Quét QR check-in và HTTP demo

Camera dùng getUserMedia và BarcodeDetector khi có; jsQR 1.4.0 đóng gói trong ứng dụng làm decoder fallback. Video và ảnh được giải mã cục bộ.

## Sử dụng

1. Đăng nhập quản trị, mở Quản trị → Checkin.
2. Nhấn **Quét QR** để mở popup cỡ vừa, cho phép quyền camera rồi đưa QR trên vé vào ô vuông sáng. Vùng ngoài ô được làm tối, dải quét có animation khi camera đang hoạt động. Ưu tiên camera sau nếu có; camera laptop vẫn dùng được.
3. Khi đọc được, camera tự tắt và tra cứu thông tin vé/hồ sơ. Nhấn **Xác nhận check-in** khi nút xuất hiện. Quét QR không tự gửi yêu cầu check-in.
4. Có thể dùng **chụp / chọn ảnh QR** (JPEG/PNG/WebP tối đa5MB,20megapixel), hoặc nhập nội dung mã vé. Ảnh được giải mã cục bộ, không upload.

Hệ thống báo riêng trường hợp thiếu quyền, không tìm thấy camera, thiết bị đang bận hoặc địa chỉ không cho phép camera. Rời trang quản trị, đăng xuất, đóng popup bằng nút × / Esc / bấm ra ngoài, hoặc đọc xong đều dừng stream; request quyền/decoder trả về muộn không được điền mã sau khi đã tắt.

## Không cần dựng HTTPS cho local

| Địa chỉ | Camera trực tiếp | Ảnh QR / nhập mã |
|---|---|---|
| http://localhost:8000 hoặc http://127.0.0.1:8000 |Có, nếu có thiết bị và được cấp quyền |Có |
| HTTP qua IP/domain khác localhost |Trình duyệt chặn vì không phải secure context |Có; input capture có thể mở ứng dụng chụp ảnh tùy thiết bị |
| HTTPS |Có, nếu có thiết bị và được cấp quyền |Có |

Đây là giới hạn trình duyệt, không thể bỏ bằng JavaScript. Không cần bật browser flags hoặc tắt bảo vệ trình duyệt. Local Compose đang dùng HTTP và không cần cấu hình certificate. [MDN getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia), [BarcodeDetector compatibility](https://developer.mozilla.org/en-US/docs/Web/API/BarcodeDetector).

Nếu muốn demo AWS bằng HTTP, `infra/environments/demo/terraform.tfvars.example` đặt `allow_http_demo=true`, `acm_certificate_arn=null`: listener80, cookie secure=false, không cần ACM. Production vẫn hỗ trợ HTTPS. Repository change không thực thi AWS deployment. Brevo API dùng HTTPS do Brevo cung cấp, không yêu cầu bạn tự cấp certificate cho kết nối API đó; URL ảnh trong email thực vẫn theo cấu hình public HTTPS riêng trong [Brevo runbook](brevo.md). HTTP demo có thể giữ email mock như hiện tại.

## Kiểm thử

[Kết quả kiểm tra](../../evidence/current/README.md). Tests kiểm vùng quét, animation, reduced-motion, đóng popup, keyboard, responsive, jsQR fallback, ảnh QR, lỗi quyền và HTTP ngoài localhost. Decoder đọc ROI 76% ở giữa, trùng ô sáng. Camera vật lí trên thiết bị người dùng cần kiểm riêng.

Chạy lại browser tests với Python có Playwright và Chrome local:

```bash
RUN_CAMERA_BROWSER_TESTS=1 python -m pytest tests/app/test_camera_browser.py -q
node tests/app/ui.test.mjs
```

Browser fixture chạy HTTP server riêng, DB URL giả không kết nối được và mock toàn bộ API nghiệp vụ. Không đọc mật khẩu admin local, tạo đăng kí thật hoặc check-in vé thật.
