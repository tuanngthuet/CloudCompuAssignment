"""Generate a synthetic email preview; no DB, Brevo key or network required."""
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import shutil
from uuid import UUID
from zoneinfo import ZoneInfo
from .content import EmailTicket, qr_png, render_confirmation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('.local/email-preview'))
    args = parser.parse_args()
    start = datetime(2026, 11, 20, 8, 0, tzinfo=ZoneInfo('Asia/Ho_Chi_Minh'))
    ticket = EmailTicket(UUID('00000000-0000-4000-8000-000000000001'), 'LABSEAT-DEMO-QR-NOT-A-REAL-TICKET',
        'Thực hành Lập trình Python', 'Khu thực hành Công nghệ thông tin', 'A101', start, start + timedelta(hours=2))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'qr.png').write_bytes(qr_png(ticket.ticket_code))
    shutil.copyfile(Path(__file__).resolve().parents[2] / 'static/labseat-email.png', args.output / 'labseat-logo.png')
    (args.output / 'confirmation.html').write_text(render_confirmation(ticket, 'https://labseat.example.com',
        'support@labseat.example.com', preview=True), encoding='utf-8')
    print(args.output / 'confirmation.html')


if __name__ == '__main__':
    main()
