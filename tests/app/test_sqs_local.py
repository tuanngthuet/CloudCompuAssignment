"""Opt-in real SQS-compatible transport and worker process tests; never AWS."""
import json
import os
import subprocess
import sys
import time
import uuid
import pytest
if not os.getenv('TEST_SQS_ENDPOINT_URL') or not os.getenv('TEST_DATABASE_URL'):
    pytest.skip('Disposable ElasticMQ and PostgreSQL required', allow_module_level=True)
from urllib.parse import urlsplit
assert urlsplit(os.environ['TEST_SQS_ENDPOINT_URL']).hostname in ('sqs', 'localhost', '127.0.0.1')
from botocore.config import Config
import boto3
from sqlalchemy import select
from test_db import clean_db, data
from test_notifications import confirmed
from app.infrastructure.database.session import Session
from app.models import NotificationDelivery, OutboxEvent
from app.modules.notifications.adapters import SQS
from app.modules.notifications.service import publish_batch, consume


@pytest.fixture
def sqs(monkeypatch):
    endpoint = os.environ['TEST_SQS_ENDPOINT_URL']
    client = boto3.client('sqs', endpoint_url=endpoint, region_name='us-east-1',
        aws_access_key_id='local', aws_secret_access_key='local',
        config=Config(connect_timeout=2, read_timeout=10, retries={'max_attempts': 0}))
    name = 'test-' + uuid.uuid4().hex
    dlq = client.create_queue(QueueName=name + '-dlq')['QueueUrl']
    arn = client.get_queue_attributes(QueueUrl=dlq, AttributeNames=['QueueArn'])['Attributes']['QueueArn']
    url = client.create_queue(QueueName=name, Attributes={'VisibilityTimeout': '1',
        'RedrivePolicy': json.dumps({'deadLetterTargetArn': arn, 'maxReceiveCount': '2'})})['QueueUrl']
    monkeypatch.setenv('SQS_ENDPOINT_URL', endpoint)
    monkeypatch.setenv('SQS_QUEUE_URL', url)
    monkeypatch.setenv('APP_ENV', 'test')
    yield client, url, dlq
    client.delete_queue(QueueUrl=url); client.delete_queue(QueueUrl=dlq)


def test_real_transport_and_duplicate_ack(data, sqs):
    client, url, _ = sqs
    rid = confirmed(data)
    assert publish_batch(SQS()) == 1
    message = client.receive_message(QueueUrl=url, WaitTimeSeconds=1)['Messages'][0]
    with Session() as db: assert db.scalar(select(OutboxEvent)).published_at is not None
    class Email:
        calls = 0
        def send(self, *args): self.calls += 1; return 'mock'
    email = Email()
    consume(message['Body'], email)
    consume(message['Body'], email)
    assert email.calls == 1
    client.delete_message(QueueUrl=url, ReceiptHandle=message['ReceiptHandle'])
    assert not client.receive_message(QueueUrl=url, WaitTimeSeconds=1).get('Messages')


def test_poison_message_reaches_local_dlq(data, sqs):
    client, url, dlq = sqs
    client.send_message(QueueUrl=url, MessageBody='invalid-poison')
    for _ in range(2):
        message = client.receive_message(QueueUrl=url, WaitTimeSeconds=1)['Messages'][0]
        with pytest.raises(ValueError): consume(message['Body'], None)
        client.change_message_visibility(QueueUrl=url, ReceiptHandle=message['ReceiptHandle'], VisibilityTimeout=0)
    # Next receive causes redrive after maxReceiveCount; worker never ACKed poison.
    client.receive_message(QueueUrl=url, WaitTimeSeconds=1)
    assert client.receive_message(QueueUrl=dlq, WaitTimeSeconds=2)['Messages'][0]['Body'] == 'invalid-poison'


def test_worker_process_sends_and_sigterm_exits(data, sqs):
    rid = confirmed(data)
    publish_batch(SQS())
    process = subprocess.Popen([sys.executable, '-m', 'app.events', 'worker'],
        env=os.environ | {'EMAIL_BACKEND': 'mock'}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            assert process.poll() is None
            with Session() as db:
                delivery = db.get(NotificationDelivery, (rid, 'ReservationConfirmed'))
                if delivery and delivery.status == 'SENT': break
            time.sleep(.1)
        else: pytest.fail('Worker did not record mock email delivery')
        process.terminate(); process.wait(timeout=15)
        assert process.returncode == 0
    finally:
        if process.poll() is None: process.kill(); process.wait()


def test_publisher_process_publishes_and_sigterm_exits(data, sqs):
    confirmed(data)
    process = subprocess.Popen([sys.executable, '-m', 'app.events', 'publisher'],
        env=os.environ, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            assert process.poll() is None
            with Session() as db:
                event = db.scalar(select(OutboxEvent))
                if event.published_at: break
            time.sleep(.1)
        else: pytest.fail('Publisher did not checkpoint SQS publication')
        client, url, _ = sqs
        assert client.receive_message(QueueUrl=url, WaitTimeSeconds=1)['Messages']
        process.terminate(); process.wait(timeout=15)
        assert process.returncode == 0
    finally:
        if process.poll() is None: process.kill(); process.wait()
