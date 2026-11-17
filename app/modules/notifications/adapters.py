"""AWS adapters with bounded I/O; local operation needs no AWS credentials."""
import os
import uuid
import boto3
from botocore.config import Config


def aws_client(service):
    config = Config(connect_timeout=3, read_timeout=10, retries={'max_attempts': 0})
    endpoint = os.getenv('SQS_ENDPOINT_URL') if service == 'sqs' else None
    kwargs = {}
    if endpoint:
        if os.getenv('APP_ENV', 'local') not in ('local', 'test'):
            raise ValueError('Custom SQS endpoints are restricted to local/test')
        kwargs.update(aws_access_key_id='local', aws_secret_access_key='local')
    return boto3.client(service, region_name=os.getenv('AWS_REGION', 'us-east-1'),
                        endpoint_url=endpoint, config=config, **kwargs)


class SQS:
    def __init__(self):
        self.client = aws_client('sqs')
        self.url = os.environ['SQS_QUEUE_URL']

    def publish(self, body):
        self.client.send_message(QueueUrl=self.url, MessageBody=body)

    def receive(self):
        # Shorter than the SDK read timeout. One message, one bounded DB transaction.
        return self.client.receive_message(QueueUrl=self.url, MaxNumberOfMessages=1,
            WaitTimeSeconds=5, VisibilityTimeout=120).get('Messages', [])

    def delete(self, receipt):
        self.client.delete_message(QueueUrl=self.url, ReceiptHandle=receipt)


class MockEmail:
    def send_message(self, recipient, message, job_id):
        return 'mock-' + str(job_id)

    def send(self, recipient, reservation):
        # Deliberately no recipient, ticket or profile logging.
        return 'mock-' + str(uuid.uuid4())



def email_adapter():
    backend = os.getenv('EMAIL_BACKEND', 'disabled')
    if backend == 'mock' and os.getenv('APP_ENV', 'local') in ('local', 'test'):
        return MockEmail()
    if backend == 'brevo':
        from .brevo import BrevoEmail
        return BrevoEmail()
    if backend == 'disabled':
        return None
    raise ValueError('Invalid EMAIL_BACKEND')
