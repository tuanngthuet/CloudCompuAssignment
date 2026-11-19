# B5 — Khôi phục ảnh S3 theo version

**Phần S3: PASS. B5 tổng thể: BLOCKED**, chưa kiểm liên kết DB và hiển thị qua app restored của B4. Làm theo [prompt B5](../../sprints/ke-hoach-nghiem-thu-4-ngay.md#b5-khôi-phục-ảnh-s3-theo-version-và-kiểm-liên-kết-db); không nhận S3 versioning thay backup database.

## Phạm vi và bằng chứng

Lượt `20261119T050938Z-b5-s3-restore` từ **2026-11-19T05:09:38.739888+00:00** đến **2026-11-19T05:10:04.533372+00:00**, region ap-southeast-2; account đã đối chiếu. Dùng một key mới, xác minh chưa có version/delete marker trước khi ghi. Không sửa ảnh đang dùng, DB, app, email hoặc cấu hình bucket.

- Bucket alias: `labseat-private-assets`; bucket thật/prefix giữ private.
- Key tương đối so với prefix app: `assessment/b5/76e341cb-2c1e-4ec7-9113-9906e44d660c/rooms/fixture.png`.
- SHA-256 full key: `ae991f70b5a86c14ada41fed28f3b7b30d8625676bbd6e6af6d5e601fb5ba718`.
- DB reference: **NOT_RUN**; chưa tạo bản ghi giả hoặc sửa DB nguồn để lấp phần thiếu.
- [Kết quả API/hash/private](../../../evidence/assessment/20261119T050938Z-b5-s3-restore/checks/results.json), [cleanup manifest](../../../evidence/assessment/20261119T050938Z-b5-s3-restore/cleanup-manifest.json).

## Bảng key/version/hash đã làm sạch

Cả ba dòng thuộc cùng key ở trên. Hash tính từ **bytes tải lại bằng authenticated S3 GET**, không dùng ETag thay SHA-256.

| Giai đoạn | Version ID | SHA-256 | Content type |
|---|---|---|---|
| before | `JmiLVA.SywILMOOJXEcJ5o78aTnlRBx_` | `17c0edfb565b41fbd252608537d227330abfd3aad8cf0a1d95db9f4fbea8e6ac` | image/png |
| overwritten | `AlvyXV5nlHipTnOftRwvrm66j2mV0P22` | `a7022db27680c96f426cdfb9ceecb72424948c8390146e882f7b24e7474f7a6a` | image/png |
| restored | `mU4g0DjmFqHmSSLfoJaW1q_8DVldRCqb` | `17c0edfb565b41fbd252608537d227330abfd3aad8cf0a1d95db9f4fbea8e6ac` | image/png |

## Kết quả thực tế

| Kiểm tra | Kết quả |
|---|---|
| Versioning / public access block | Enabled; cả4 public access block bật |
| Bản tốt ban đầu | Put ảnh synthetic, GET current đúng version/hash |
| Ghi đè lỗi có kiểm soát | PNG hợp lệ nhưng nội dung sai; GET current có version/hash khác bản tốt |
| Phục hồi | CopyObject từ version tốt vào chính key; tạo version current mới, không dùng delete để demo restore |
| Hash / content type | Bản restored trùng SHA-256 bản tốt, image/png; PNG signature/chunk CRC/zlib/kích thước800×480 hợp lệ |
| Quyền private | GET authenticated thành công; GET anonymous403; ACL không có public group |
| Cache | S3 GET cả3 giai đoạn trả Cache-Control:no-store; chưa kiểm browser/CDN/app cache |
| Cleanup | Xóa đúng3 version trong manifest sau lưu ảnh/hash; list lại còn0 version và0 delete marker |
| App và DB reference | NOT_RUN: B4 chưa có DB/app restored; images_verified=false |

“Lỗi” trong lượt này là nội dung ảnh S3 bị thay sai, đã đối chiếu bytes/hash; chưa phải quan sát lỗi qua UI app. Không kết luận B5 hoàn thành từ copy/put hoặc hash riêng lẻ.

## Ảnh trước / ghi đè / sau phục hồi

Các ảnh dưới là **object tải lại từ S3**, không phải screenshot app. Fixture tự tạo chỉ chứa sơ đồ synthetic và nhãn test, không có QR/thông tin người dùng.

![Bản tốt trước ghi đè](../../../evidence/assessment/20261119T050938Z-b5-s3-restore/images/before.png)

![Nội dung sai sau ghi đè](../../../evidence/assessment/20261119T050938Z-b5-s3-restore/images/overwritten.png)

![Bytes ảnh sau copy phục hồi](../../../evidence/assessment/20261119T050938Z-b5-s3-restore/images/restored.png)

## Cách tái tạo khi có app restored

1. Đọc bucket/prefix/versioning thật, kiểm account/owner; chọn key synthetic mới và manifest run riêng. Liên kết đúng bản ghi synthetic trên **DB restored**, không sửa ảnh/bản ghi người khác.
2. Put ảnh tốt, ghi version/hash; GET lại và kiểm ảnh qua app/DB reference. Sau đó put bản lỗi lên đúng key, GET lại và ghi lỗi quan sát từ app.
3. Dùng `s3api copy-object --copy-source BUCKET/KEY?versionId=GOOD_VERSION` để tạo current mới. Giữ các version cũ trong suốt diễn tập; không xóa version để làm bước phục hồi.
4. GET current, so SHA-256/content type/quyền private; đối chiếu DB reference và ảnh hiển thị qua app. Ghi cache headers/hành vi cache thực, xử lý cache trong phạm vi kiểm chứng nếu cần.
5. Chỉ khi cả ảnh và DB reference qua app đạt mới cập nhật images_verified=true ở B4 và dùng record RPO/RTO thật.
6. Giữ evidence trước cleanup. Liệt kê đúng key, so version/delete marker với manifest sở hữu rồi xóa chính các ID test; list lại phải trống. Không dùng delete recursive theo prefix hoặc sửa versioning/bucket policy.

Phiên bản/version IDs trong bảng đã được dọn, không dùng chúng để chạy lại; lượt mới phải có key/version/manifest mới. Chuỗi thao tác S3 đã thực thi được lưu trong JSON theo timestamp; vẫn cần một lượt gắn DB/app restored để nghiệm thu trọn B5.

## Phần còn thiếu

B4 chưa tạo DB/app restored nên chưa có DB reference, ảnh trước/sau qua app hay kiểm cache của app. Các mục này giữ NOT_RUN; `images_verified=false`, RPO/RTO tổng thể chưa chốt. Kết quả đã gộp vào [report B4](report.md#kết-quả-b5).

Nguồn: [AWS — copy version tốt thành current](https://docs.aws.amazon.com/AmazonS3/latest/userguide/RestoringPreviousVersions.html).
