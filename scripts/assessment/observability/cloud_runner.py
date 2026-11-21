"""Run k6 on an isolated Fargate task; target only the approved AWS LABSEAT site."""
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tarfile
import time
from urllib.request import urlopen

import boto3
from botocore.config import Config


def utc():
    return datetime.now(timezone.utc).isoformat()


def metadata():
    with urlopen(os.environ['ECS_CONTAINER_METADATA_URI_V4']+'/task',timeout=5) as response:
        return json.load(response)


def rolling_5xx_exceeded(windows, latest):
    buckets=[windows.get(slot,[0,0]) for slot in range(latest-11,latest+1)]
    total=sum(x[0] for x in buckets)
    return total>0 and sum(x[1] for x in buckets)/total>0.05


def main():
    os.umask(0o077)
    phase=os.environ['ASSESSMENT_PHASE']
    allowed={'preflight','baseline','platform','admission20','admission50','scaling60','scaling100','scaling150','scaling200','recovery'}
    if phase not in allowed:raise ValueError('Unexpected phase')
    root=Path('/tmp/labseat-load');root.mkdir(exist_ok=False)
    out=root/'output';out.mkdir()
    bucket=os.environ['S3_BUCKET'];prefix=os.getenv('S3_PREFIX','').strip('/')
    key=lambda value:'/'.join(filter(None,(prefix,value)))
    session=boto3.Session(region_name='ap-southeast-2')
    store=session.client('s3',config=Config(connect_timeout=5,read_timeout=60,retries={'mode':'standard','max_attempts':3}))
    bundle=root/'bundle.tar.gz'
    store.download_file(bucket,key(os.environ['ASSESSMENT_BUNDLE_KEY']),str(bundle))
    if hashlib.sha256(bundle.read_bytes()).hexdigest()!=os.environ['ASSESSMENT_BUNDLE_SHA256']:
        raise RuntimeError('Bundle hash mismatch')
    inputs=root/'inputs';inputs.mkdir()
    with tarfile.open(bundle) as archive:archive.extractall(inputs,filter='data')
    files=json.loads((inputs/'hashes.json').read_text())
    for name,digest in files.items():
        if hashlib.sha256((inputs/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Input hash mismatch')
    binary=inputs/'k6';binary.chmod(0o700)
    info={'phase':phase,'started_at_utc':utc(),'base_url':'https://labseat.id.vn','input_hashes':files,'result':'NOT_RUN'}
    process=None
    def terminate(_signum,_frame):
        if process and process.poll() is None:process.terminate()
        raise InterruptedError('Operator stopped load')
    signal.signal(signal.SIGTERM,terminate)
    try:
        task=metadata();clock=task.get('ClockDrift',{})
        info.update(launch_type=task.get('LaunchType'),clock=clock,task_arn=task.get('TaskARN'),limits=task.get('Limits'))
        if task.get('LaunchType')!='FARGATE' or task.get('ContainerInstanceARN'):
            raise RuntimeError('Load runner must be outside the application EC2 ASG')
        if clock.get('ClockSynchronizationStatus')!='SYNCHRONIZED' or float(clock.get('ClockErrorBound',1e9))>100:
            raise RuntimeError('Fargate clock not synchronized within 100ms bound')
        info['k6_version']=subprocess.check_output([str(binary),'version'],text=True).strip()
        with urlopen(info['base_url']+'/readyz',timeout=15) as response:
            if response.status!=200:raise RuntimeError('App not ready')
        manifest=json.loads((inputs/'manifest.json').read_text())
        env=dict(os.environ,BASE_URL=info['base_url'],SESSION_ID=manifest['load_session'],SESSIONS_FILE=str(inputs/'sessions.json'),SESSION_EXPIRES_AT=manifest['sessions_expire_at'])
        if phase=='preflight':
            info['result']='PASS';return
        if phase=='baseline':script='catalogue.js';env['VUS']='5'
        elif phase=='platform':script='platform.js'
        elif phase.startswith('admission'):
            script='booking.js';env.update(VUS=phase.removeprefix('admission'),DURATION='5m',REQUIRE_QUEUE_ENABLED='1')
        elif phase.startswith('scaling'):
            script='ecs-scaling.js';env.update(VUS=phase.removeprefix('scaling'),HOLD_MINUTES='15',PAUSE_SECONDS='0.25')
        else:script=None
        console=(out/'console.private.log').open('w')
        if script:
            command=[str(binary),'run','--out','json='+str(out/'metrics.ndjson'),'--summary-export='+str(out/'summary.json'),str(inputs/script)]
            process=subprocess.Popen(command,env=env,stdout=console,stderr=subprocess.STDOUT)
        started=time.monotonic();deadline=started+(40*60 if script else 30*60)
        next_log=started;offset=0;windows={};stop_reason=None
        with (out/'runner.csv').open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=['at_utc','elapsed_seconds','clock_error_bound_ms','clock_status','memory_bytes','cpu_usage_usec','k6_running'])
            writer.writeheader()
            while (not process or process.poll() is None) and time.monotonic()<deadline:
                task=metadata();clock=task.get('ClockDrift',{})
                memory_path=Path('/sys/fs/cgroup/memory.current');cpu_path=Path('/sys/fs/cgroup/cpu.stat')
                memory=memory_path.read_text().strip() if memory_path.exists() else ''
                cpu=dict(line.split() for line in cpu_path.read_text().splitlines()).get('usage_usec','') if cpu_path.exists() else ''
                # Fargate can expose cgroup v1; retain missing values if neither exists.
                if not memory:
                    legacy=Path('/sys/fs/cgroup/memory/memory.usage_in_bytes')
                    if legacy.exists():memory=legacy.read_text().strip()
                if not cpu:
                    legacy=Path('/sys/fs/cgroup/cpuacct/cpuacct.usage')
                    if legacy.exists():cpu=str(int(legacy.read_text().strip())//1000)
                writer.writerow(dict(at_utc=utc(),elapsed_seconds=round(time.monotonic()-started,2),clock_error_bound_ms=clock.get('ClockErrorBound'),clock_status=clock.get('ClockSynchronizationStatus'),memory_bytes=memory,cpu_usage_usec=cpu,k6_running=bool(process and process.poll() is None)));stream.flush()
                raw=out/'metrics.ndjson'
                if raw.exists():
                    with raw.open() as metrics:
                        metrics.seek(offset)
                        while True:
                            line=metrics.readline()
                            if not line:break
                            try:point=json.loads(line)
                            except json.JSONDecodeError:break
                            if point.get('type')=='Point' and point.get('metric')=='http_reqs':
                                value=point['data'];stamp=datetime.fromisoformat(value['time'].replace('Z','+00:00')).timestamp();slot=int(stamp//10)
                                counts=windows.setdefault(slot,[0,0]);counts[0]+=value['value'];counts[1]+=value['value'] if str(value.get('tags',{}).get('status','')).startswith('5') else 0
                            offset=metrics.tell()
                    latest=int(datetime.now(timezone.utc).timestamp()//10)-1
                    if time.monotonic()-started>=120 and rolling_5xx_exceeded(windows,latest):
                        stop_reason='5xx above 5 percent over the rolling two-minute window'
                if clock.get('ClockSynchronizationStatus')!='SYNCHRONIZED':stop_reason='Clock synchronization lost'
                if stop_reason:
                    if process:process.terminate()
                    break
                if time.monotonic()>=next_log:
                    print(json.dumps({'phase':phase,'at_utc':utc(),'elapsed_seconds':int(time.monotonic()-started),'state':'RUNNING'}),flush=True);next_log+=30
                time.sleep(10)
        if process:
            if process.poll() is None:
                process.terminate();stop_reason=stop_reason or 'Maximum phase runtime exceeded'
            try:code=process.wait(timeout=30)
            except subprocess.TimeoutExpired:process.kill();code=process.wait()
            info['k6_exit_code']=code
            info['result']='PASS' if code==0 and not stop_reason else 'FAIL'
        else:info['result']='OBSERVED'
        if stop_reason:info['stop_reason']=stop_reason
        console.close()
    except Exception as exc:
        info.update(result='FAIL',error_type=type(exc).__name__,error=str(exc))
        raise
    finally:
        if process and process.poll() is None:process.terminate();process.wait(timeout=30)
        info['finished_at_utc']=utc();(out/'run.json').write_text(json.dumps(info,indent=2))
        artifact=root/'result.tar.gz'
        with tarfile.open(artifact,'w:gz') as archive:
            for path in out.iterdir():archive.add(path,arcname=path.name)
        output_key=os.environ['ASSESSMENT_RESULT_KEY']
        store.upload_file(str(artifact),bucket,key(output_key),ExtraArgs={'ServerSideEncryption':'AES256'})
        print('C3_RESULT='+json.dumps({'phase':phase,'result':info['result'],'output_key':output_key,'finished_at_utc':info['finished_at_utc']}),flush=True)


if __name__=='__main__':main()
