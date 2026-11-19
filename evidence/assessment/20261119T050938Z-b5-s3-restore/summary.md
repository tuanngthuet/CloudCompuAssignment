# B5 — S3 version restore

S3 component PASS: key synthetic mới,3 version, overwrite/copy-good-version, GET hash/content-type/PNG/private403 đạt. Cleanup PASS:0 version/delete marker còn lại.

B5 tổng thể BLOCKED: DB reference/app restored chưa kiểm; images_verified=false. Ảnh là object tải lại từ S3, không phải UI screenshot. Chi tiết [báo cáo B5](../../../docs/assessment/recovery/s3-restore.md), [checks/results.json](checks/results.json), [cleanup-manifest.json](cleanup-manifest.json).
