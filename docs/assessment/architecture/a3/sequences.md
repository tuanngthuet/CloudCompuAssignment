# A3 — Sequence theo source

Các endpoint ghi theo decorator trong file đã cung cấp; chưa xác minh prefix include_router tại app/main.py. Nhánh lỗi kết thúc yêu cầu; các bước tiếp theo chỉ áp dụng khi không lỗi. Các sơ đồ là phân tích source, không phải trace chạy thật.

## Giữ chỗ và admission

```mermaid
sequenceDiagram
    actor U as Sinh viên
    participant A as Booking API
    participant P as PostgreSQL
    participant R as Redis admission
    U->>A: POST /holds và CSRF
    A->>P: Đọc login_sessions, user
    opt Có Idempotency-Key
        A->>P: Khóa User, đọc key_hash và fingerprint
        alt Key đã có và fingerprint khớp
            P-->>A: Response đã lưu
            A-->>U: Trả response, không gia hạn hold
        else Key đã có nhưng fingerprint khác
            A-->>U: 409 idempotency_key_reused
        end
    end
    Note over A,P: Các bước dưới chỉ cho yêu cầu chưa replay và chưa lỗi
    A->>P: Khóa Users theo ID, SHARE LabSession, khóa SessionSeats theo seat_id
    A->>P: Đọc clock_timestamp, kiểm tra hồ sơ và cửa sổ đăng ký
    A->>P: Đổi HELD quá hạn liên quan thành EXPIRED, ghi audit
    alt Đã có HELD hợp lệ cùng chỗ
        A-->>U: Trả hold hiện có, không gia hạn
    else Tạo hold mới
        A->>P: Kiểm tra đăng ký khác cùng event, tìm slot trống
        alt Không còn slot
            A-->>U: 409 sold_out
        else Có slot
            A->>P: Đọc queue policy với shared lock
            opt Queue enabled
                A->>R: guard user và session
                alt WAITING hoặc NONE hoặc hết lượt
                    R-->>A: Không được admission
                    A-->>U: 409 queue_waiting hoặc queue_expired
                else Redis không khả dụng
                    A-->>U: 503 queue_unavailable
                else ADMITTED
                    R-->>A: generation
                end
            end
            Note over A,P: Chỉ đi tiếp nếu guard thành công hoặc queue tắt
            A->>P: Thêm HELD và audit, PlatformEvent
            A->>P: Lưu response idempotency nếu có key
            Note over A,P: Caller sở hữu commit/rollback, chưa có shared/http.py để kiểm tra
            opt Sau commit và có admission
                A->>R: consume generation
                Note over A,R: Lỗi consume được log, không hoàn tác vé đã commit
            end
            A-->>U: hold_id, expires_at, server_time
        end
    end
```

Nguồn và giới hạn: app/modules/booking/router.py:hold; service.py:hold; repository.py:lock; idempotency.py:execute; app/infrastructure/redis/admission.py:guard,release_after_commit.

Hold hết hạn tại min(DB clock + 180 giây, close_at). Giữ chỗ hiện có được trả lại trước guard; Redis không là kho lưu vé. Hàm require_for_exam nằm ngoài ZIP nên điều kiện hồ sơ chi tiết chưa được review.

## Xác nhận vé và outbox

```mermaid
sequenceDiagram
    actor U as Sinh viên
    participant A as Booking API
    participant P as PostgreSQL
    U->>A: POST /holds/{hold_id}/confirm
    A->>P: Xác thực phiên, CSRF và idempotency nếu có
    A->>P: Tìm reservation thuộc user
    A->>P: Khóa Users, LabSession, SessionSeats rồi refresh reservation
    alt Đã CONFIRMED hoặc CHECKED_IN
        A-->>U: Trả vé hiện có
    else HELD còn hạn và chưa close_at
        A->>P: Kiểm tra hồ sơ, đổi thành CONFIRMED và tạo ticket_code
        A->>P: Thêm OutboxEvent ReservationConfirmed
        A->>P: Thêm AuditEvent và PlatformEvent availability
        A->>P: Lưu response idempotency nếu có key
        Note over A,P: Các ghi dùng cùng session; commit do caller quản lý
        A-->>U: Vé xác nhận
    else Trạng thái hoặc thời gian không hợp lệ
        A-->>U: 409 conflict
    end
```

Nguồn và giới hạn: app/modules/booking/router.py:confirm; service.py:transition,audit; idempotency.py:execute.

Không gửi email trực tiếp trong transition. Việc hoàn tất giao dịch HTTP cần kiểm tra thêm app/shared/http.py; sequence không coi response thành công là bằng chứng test thực tế.

## Hủy đặt chỗ

```mermaid
sequenceDiagram
    actor U as Chủ vé
    participant A as Booking API
    participant P as PostgreSQL
    U->>A: POST /reservations/{id}/cancel
    A->>P: Xác thực phiên, CSRF và idempotency nếu có
    A->>P: Tìm vé thuộc user và khóa theo thứ tự booking
    A->>P: Refresh reservation, lấy DB clock
    alt Đã CANCELLED
        A-->>U: Trả vé đã hủy
    else HELD chưa hết hạn hoặc CONFIRMED trước start_at
        A->>P: Đổi status thành CANCELLED
        A->>P: Ghi AuditEvent và PlatformEvent availability
        A->>P: Lưu response idempotency nếu có key
        Note over A,P: Caller sở hữu transaction
        A-->>U: Vé CANCELLED
    else CHECKED_IN hoặc quá hạn điều kiện hủy
        A-->>U: 409 conflict
    end
```

Nguồn và giới hạn: app/modules/booking/service.py:transition; router.py:cancel.

Luồng người dùng hủy ở đây không thêm OutboxEvent gửi email hủy. Không gộp với admin lifecycle cancellation vì module admin/lifecycle.py không có trong ZIP.

## Check-in theo quyền admin hoặc staff

```mermaid
sequenceDiagram
    actor O as Admin hoặc staff
    participant A as Check-in API
    participant P as PostgreSQL
    O->>A: POST /admin/check-ins hoặc /staff/check-ins
    A->>P: Xác thực phiên, CSRF và vai trò
    A->>P: Tìm ticket theo ticket_code hoặc UUID
    opt Staff
        A->>P: Kiểm tra email_verified_at và StaffAssignment
    end
    A->>P: Khóa owner và actor theo ID, SHARE ca, khóa SessionSeats
    A->>P: Refresh reservation, kiểm tra scope lần nữa
    alt Đã CHECKED_IN
        A-->>O: Trả vé đã check-in
    else CONFIRMED và chính sách check-in hiệu lực
        A->>P: status CHECKED_IN, checked_in_at bằng DB clock
        A->>P: Ghi AuditEvent và PlatformEvent
        Note over A,P: Caller sở hữu commit/rollback
        A-->>O: Vé CHECKED_IN
    else Không đủ điều kiện
        A-->>O: ticket_not_eligible hoặc checkin_closed
    end
```

Nguồn và giới hạn: app/modules/checkin/router.py:check_in; staff.py:checkin,scoped; policy.py:scope,effective; app/modules/booking/service.py:transition.

Chính sách hiệu lực: checkin_enabled, chưa tới deadline nếu có, event ACTIVE nếu có. Deadline theo end_at/custom/manual. Không tự suy có điều kiện clock >= start_at. Lookup chỉ xem vé, không thực hiện check-in. Staff phải được phân công đúng ca, tài khoản ACTIVE và email đã xác minh.

## Publisher chuyển outbox sang hàng đợi

```mermaid
sequenceDiagram
    participant W as Publisher
    participant P as PostgreSQL
    participant Q as SQS adapter
    loop Mỗi dòng trong batch
        W->>P: BEGIN, SELECT pending FOR UPDATE SKIP LOCKED
        P-->>W: OutboxEvent tới available_at
        W->>P: Tăng attempts
        W->>Q: publish event_id, event_type, reservation_id
        alt Publish trả thành công
            W->>P: published_at bằng DB clock rồi commit
        else Publish ném lỗi
            W->>P: available_at cộng backoff rồi commit
        end
    end
    Note over P,Q: SQS nhận nhưng DB chưa commit có thể gây publish trùng
```

Nguồn và giới hạn: app/modules/notifications/service.py:publish_batch; adapters.py:SQS.publish.

Backoff min(300, 2 ** min(attempts, 8)) giây theo biểu thức source (thực tế lũy thừa bị chặn ở 256). Đây là cơ chế at-least-once có thể trùng; không phải atomic transaction giữa PostgreSQL và SQS. Chưa đọc entrypoint worker/ack nên không khẳng định thứ tự delete message.

## Worker xử lý email xác nhận

```mermaid
sequenceDiagram
    participant W as Worker consume
    participant P as PostgreSQL
    participant E as Email adapter
    W->>P: Kiểm tra envelope và OutboxEvent
    W->>P: Upsert rồi khóa NotificationDelivery
    alt Delivery SENT hoặc SKIPPED
        W-->>W: Bỏ qua bản trùng
    else Chưa hoàn tất
        W->>P: Tạo EmailJob với UUID5 từ reservation nếu chưa có, commit
        W->>P: dispatch khóa EmailJob và kiểm tra trạng thái, người nhận, vé
        alt Không đủ điều kiện
            W->>P: SKIPPED và commit
        else Đang gửi gần đây
            W-->>W: Ném lỗi để xử lý lại
        else Đã qua cửa sổ 29 phút kể từ send_started_at
            W->>P: UNKNOWN và commit
        else Có thể gửi
            W->>P: Đóng băng nội dung, SENDING, tăng attempts, commit
            W->>E: Gửi với job_id
            alt Provider trả thành công
                W->>P: Lưu provider_message_id, ACCEPTED và commit
            else Provider hoặc I/O lỗi
                W->>P: PENDING hoặc UNKNOWN theo loại lỗi
                W-->>W: Ném lỗi
            end
        end
        W->>P: Ánh xạ trạng thái job thành delivery SENT hoặc SKIPPED
    end
    Note over W,E: ACCEPTED hoặc delivery SENT chưa chứng minh email tới hộp thư
```

Nguồn và giới hạn: app/modules/notifications/service.py:consume; jobs.py:enqueue,dispatch; adapters.py:email_adapter.

Bước cập nhật delivery cuối chỉ chạy khi dispatch trả về bình thường. Nhánh email_job envelope đi thẳng vào dispatch. Code có adapter Brevo, mock (local/test), disabled; chưa biết EMAIL_BACKEND runtime. Webhook được xử lý riêng trong jobs.py; chưa kiểm thử gửi hoặc nhận webhook thực tế.
