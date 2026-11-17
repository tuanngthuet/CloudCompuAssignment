"""ECS commands: python -m app.events publisher|worker. SIGTERM drains current I/O."""
import argparse
import signal
import threading
from app.modules.notifications.adapters import SQS, email_adapter
from app.modules.notifications.service import publish_batch, consume
from app.infrastructure.observability.metrics import emit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('role', choices=('publisher', 'worker'))
    args = parser.parse_args()
    stopped = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopped.set())
    queue = SQS()
    email = email_adapter() if args.role == 'worker' else None
    while not stopped.is_set():
        try:
            if args.role == 'publisher':
                publish_batch(queue, stopping=stopped.is_set)
                from app.modules.notifications.jobs import publish_platform
                publish_platform(queue)
                stopped.wait(2)
            else:
                from app.modules.notifications.jobs import process_webhooks
                from app.infrastructure.database.session import Session
                with Session.begin() as db:process_webhooks(db)
                from app.modules.admin.lifecycle import cancel_batch
                with Session.begin() as db:cancel_batch(db,limit=10)
                for message in queue.receive():
                    if stopped.is_set():
                        break
                    consume(message['Body'], email)
                    # A delete failure redelivers; durable delivery record suppresses it.
                    queue.delete(message['ReceiptHandle'])
        except Exception:
            # Do not log SDK/DB exceptions: they may contain personal data or secrets.
            emit('OutboxLoopFailure' if args.role == 'publisher' else 'WorkerFailure')
            stopped.wait(3)


if __name__ == '__main__':
    main()
