"""Offline tests only; no AWS calls. Run: py -3 <this file>."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('a1', Path(__file__).with_name('collect-a1.py'))
a1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a1)

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.args = argparse.Namespace(profile='tv1',region='ap-southeast-2',expected_account='123456789012',vpc_id='',cluster='labseat-lab',commit='offline')
        self.c = a1.Collector(self.args, Path(self.temp.name))
    def test_write_denied_before_process(self):
        with patch.object(a1.subprocess, 'run') as run:
            with self.assertRaises(ValueError):
                self.c.call('bad','ec2','terminate-instances','Instances')
            with self.assertRaises(ValueError):
                self.c.call('secret','ssm','get-parameter','Parameter')
            run.assert_not_called()
    def test_access_denied_has_no_raw_error(self):
        response = subprocess.CompletedProcess([],254,'','An error occurred (AccessDenied) private-token-value')
        with patch.object(a1.subprocess,'run',return_value=response):
            self.assertIsNone(self.c.call('denied','ec2','describe-vpcs','Vpcs'))
        manifest = (self.c.dest/'manifest.json').read_text()
        self.assertIn('AccessDenied',manifest)
        self.assertNotIn('private-token-value',manifest)
        self.assertEqual(self.c.rows[0]['status'],'BLOCKED')
    def test_timeout_is_blocked(self):
        with patch.object(a1.subprocess,'run',side_effect=subprocess.TimeoutExpired('aws',1)):
            self.c.call('timeout','ec2','describe-vpcs','Vpcs')
        self.assertEqual(self.c.rows[0]['status'],'BLOCKED')
    def test_ecs_partial_not_success(self):
        response = subprocess.CompletedProcess([],0,json.dumps({'services':[], 'failures':[{'reason':'MISSING'}]}),'')
        with patch.object(a1.subprocess,'run',return_value=response):
            self.c.call('ecs','ecs','describe-services','{services:services,failures:failures}')
        self.assertEqual(self.c.rows[0]['status'],'PARTIAL')
    def test_wrong_account_stops(self):
        with patch.object(self.c,'call',return_value={'Account':'000000000000'}) as call:
            with self.assertRaises(RuntimeError): a1.collect(self.c)
            self.assertEqual(call.call_count,1)
    def test_ambiguous_vpc_stops(self):
        with patch.object(self.c,'call',side_effect=[{'Account':'123456789012'},[{'ID':'vpc-a'},{'ID':'vpc-b'}]]) as call:
            with self.assertRaises(RuntimeError): a1.collect(self.c)
            self.assertEqual(call.call_count,2)
    def test_all_paths_allowed_queries_and_chunking(self):
        commands=[]
        def fake(cmd,**kwargs):
            commands.append(cmd)
            service, op = cmd[1:3]
            self.assertIn(op,a1.ALLOWED[service])
            self.assertFalse(kwargs['shell'])
            self.assertNotIn('--no-paginate',cmd)
            q=cmd[cmd.index('--query')+1]
            try:
                import jmespath
            except ImportError:
                pass  # Optional developer validation; end-user tests need stdlib only.
            else:
                jmespath.compile(q)
            if op=='get-caller-identity': data={'Account':'123456789012'}
            elif op=='describe-vpcs': data=[{'ID':'vpc-abcd','Default':False}]
            elif op=='list-services': data=['service-a']
            elif op=='describe-services': data={'services':[{'TaskDefinition':'task-a'}],'failures':[]}
            elif op=='describe-task-definition':
                self.assertNotIn('environment[].value',q)
                self.assertNotIn('secrets[].valueFrom',q)
                data={'TaskRole':'arn:aws:iam::123456789012:role/task-a','ExecutionRole':'arn:aws:iam::123456789012:role/exec'}
            elif op=='list-tasks': data=['task-'+str(i) for i in range(101)]
            elif op=='list-container-instances': data=['ci-a']
            elif op=='describe-load-balancers': data=[{'ARN':'lb-a'}]
            elif op=='describe-target-groups': data=[{'ARN':'tg-a'}]
            elif op=='list-buckets': data=['labseat-test']
            elif op=='list-queues': data=['https://sqs.example/queue']
            else: data=[]
            return subprocess.CompletedProcess(cmd,0,json.dumps(data),'')
        with patch.object(a1.subprocess,'run',side_effect=fake):
            a1.collect(self.c)
        batches=[x for x in commands if x[2]=='describe-tasks']
        self.assertEqual(len(batches),2)
        self.assertTrue(all(x['status']=='COLLECTED' for x in self.c.rows))
        for r in self.c.rows:
            self.assertTrue((self.c.dest/r['file']).is_file())
        self.assertEqual(json.loads((self.c.dest/'manifest.json').read_text())['status'],'NOT_REVIEWED')

if __name__=='__main__': unittest.main()
