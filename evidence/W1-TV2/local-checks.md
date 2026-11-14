# Kiểm tra độc lập W1-TV2

Chạy trên Windows với Python 3.12.14, Terraform 1.11.4 và Packer 1.13.1. Kết quả bên dưới đến từ môi trường local, kiểm tra tĩnh và mô phỏng.

| Kiểm tra | Kết quả |
| --- | --- |
| `python fixtures/tv2/smoke.py` | Pass. Process mở cổng loopback. `/healthz` và `/version` trả 200, `/holds` trả 404. |
| `python scripts/ami/build.py --mode fixture --app-dir fixtures/tv2 --app-version fixture-v1 --check-bundle` | Pass. Cùng bundle bị từ chối khi chọn `--mode release`. |
| Compile mã Python và thử `deploy/launch.py` với subprocess/exec được mô phỏng | Pass. Fixture bỏ qua SSM. Release nhận đúng biến, đòi `SecureString` và không in stderr của AWS CLI khi đọc lỗi. |
| `bash -n` trên `install-runtime.sh` và `start.sh` | Pass. |
| `packer fmt -check`, `packer validate -syntax-only` và `packer validate` với các nhãn `MOCK_ONLY` | Pass. Plugin Amazon 1.8.3. |
| `terraform fmt -check -recursive infra/modules` | Pass. |
| `terraform init -backend=false` và `terraform validate` trong bản sao tạm của từng module | Pass cho compute và observability. Provider AWS 6.73.0. |
| Hai Terraform plan trong bản sao tạm của observability với provider mô phỏng | Pass 2/2. Kiểm các trường của target tracking, alarm, SNS policy, dashboard và log retention. |

Systemd trên Amazon Linux 2023, quá trình build AMI, trạng thái target, luồng app thật, CloudWatch logs/metrics và SNS subscription chờ tích hợp cuối tuần.
