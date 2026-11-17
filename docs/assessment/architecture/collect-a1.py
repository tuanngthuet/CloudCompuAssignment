"""A1: read-only AWS metadata collection. Python 3.9+, AWS CLI v2, no pip.
Outputs stay under .local/assessment (private, ignored). No AWS writes.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ALLOWED = {
    'sts': {'get-caller-identity'},
    'ec2': {'describe-vpcs', 'describe-subnets', 'describe-route-tables',
            'describe-security-groups', 'describe-nat-gateways', 'describe-vpc-endpoints',
            'describe-internet-gateways', 'describe-instances', 'describe-network-acls'},
    'ecs': {'describe-clusters', 'list-services', 'describe-services', 'list-tasks',
            'describe-tasks', 'describe-task-definition', 'list-container-instances',
            'describe-container-instances'},
    'autoscaling': {'describe-auto-scaling-groups'},
    'application-autoscaling': {'describe-scalable-targets', 'describe-scaling-policies'},
    'elbv2': {'describe-load-balancers', 'describe-listeners', 'describe-target-groups', 'describe-target-health'},
    'rds': {'describe-db-instances'},
    'elasticache': {'describe-replication-groups', 'describe-cache-clusters'},
    's3api': {'list-buckets', 'get-bucket-location', 'get-bucket-versioning',
              'get-bucket-encryption', 'get-public-access-block', 'get-bucket-policy-status'},
    'cloudwatch': {'describe-alarms'},
    'logs': {'describe-log-groups'},
    'sqs': {'list-queues', 'get-queue-attributes'},
    'ssm': {'describe-parameters'},
    'iam': {'get-role', 'list-attached-role-policies', 'list-role-policies'},
}

def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()

class Collector:
    def __init__(self, args, dest):
        self.args, self.dest, self.rows = args, dest, []
    def call(self, name, service, action, query, *options):
        if action not in ALLOWED.get(service, set()) or not query:
            raise ValueError('Operation/query is not allowed')
        cmd = ['aws', service, action, *options, '--profile', self.args.profile,
               '--region', self.args.region, '--output', 'json', '--query', query,
               '--no-cli-pager', '--cli-connect-timeout', '10', '--cli-read-timeout', '30']
        row = {'name': name, 'started_at': utc(), 'command': cmd}
        env = dict(os.environ, AWS_PAGER='', AWS_CLI_AUTO_PROMPT='off', AWS_MAX_ATTEMPTS='2')
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                               errors='replace', timeout=180, env=env, shell=False)
            if p.returncode:
                # Do not retain arbitrary raw error text (may include identifiers).
                m = re.search(r'\(([A-Za-z0-9_.-]+)\)', p.stderr)
                raise RuntimeError(m.group(1) if m else 'CLI_ERROR_' + str(p.returncode))
            data = json.loads(p.stdout)
            failures = data.get('failures') if isinstance(data, dict) else None
            row['status'] = 'PARTIAL' if failures else 'COLLECTED'
            path = self.dest / (name + '.json')
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            row.update(file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        except (OSError, subprocess.TimeoutExpired, RuntimeError, json.JSONDecodeError) as exc:
            row.update(status='BLOCKED', error=str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__)
            data = None
        row['ended_at'] = utc()
        self.rows.append(row)
        print(name + ': ' + row['status'])
        self.save()
        return data
    def save(self):
        manifest = {'task_id': 'A1', 'run_id': self.dest.name, 'owner': 'Nguoi 1',
                    'region': self.args.region, 'source_commit': self.args.commit,
                    'status': 'NOT_REVIEWED', 'image_digest': 'See ecs-tasks files',
                    'schema_revision': 'NOT_VERIFIED: no DB connection in this collector',
                    'privacy': 'PRIVATE; selected metadata, not approved for public Git',
                    'checks': self.rows}
        (self.dest / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        lines = ['# A1 collection summary', '', 'Collection success is NOT acceptance PASS.', '',
                 '| Check | Status | Error |', '|---|---|---|']
        lines += [f"| {r['name']} | {r['status']} | {r.get('error', '')} |" for r in self.rows]
        (self.dest / 'summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def collect(c):
    a = c.args
    ident = c.call('identity', 'sts', 'get-caller-identity', '{Account:Account,Arn:Arn}')
    if not ident or ident.get('Account') != a.expected_account:
        raise RuntimeError('STOP: identity unavailable or account mismatch; no resource collection performed.')
    if a.vpc_id:
        vopts = ('--vpc-ids', a.vpc_id)
    else:
        vopts = ('--filters', 'Name=tag:Project,Values=labseat')
    vpcs = c.call('vpcs', 'ec2', 'describe-vpcs', 'Vpcs[].{ID:VpcId,CIDR:CidrBlock,CIDRs:CidrBlockAssociationSet[].CidrBlock,Default:IsDefault}', *vopts)
    if not vpcs or len(vpcs) != 1 or vpcs[0].get('Default'):
        raise RuntimeError('STOP: need exactly one non-default project VPC; review vpcs.json and pass --vpc-id.')
    vpc = vpcs[0]['ID']
    f = ('--filters', 'Name=vpc-id,Values=' + vpc)
    ec2 = [
        ('subnets','describe-subnets','Subnets[].{ID:SubnetId,AZ:AvailabilityZone,CIDR:CidrBlock,PublicIP:MapPublicIpOnLaunch}'),
        ('routes','describe-route-tables','RouteTables[].{ID:RouteTableId,Associations:Associations,Routes:Routes}'),
        ('security-groups','describe-security-groups','SecurityGroups[].{ID:GroupId,Name:GroupName,Ingress:IpPermissions,Egress:IpPermissionsEgress}'),
        ('nats','describe-nat-gateways','NatGateways[].{ID:NatGatewayId,Subnet:SubnetId,State:State,Type:ConnectivityType}'),
        ('endpoints','describe-vpc-endpoints','VpcEndpoints[].{ID:VpcEndpointId,Service:ServiceName,Type:VpcEndpointType,RouteTables:RouteTableIds,Subnets:SubnetIds,State:State}'),
        ('nacls','describe-network-acls','NetworkAcls[].{ID:NetworkAclId,Associations:Associations,Entries:Entries}'),
        ('instances','describe-instances','Reservations[].Instances[].{ID:InstanceId,Type:InstanceType,State:State.Name,AZ:Placement.AvailabilityZone,Subnet:SubnetId,SGs:SecurityGroups,Profile:IamInstanceProfile.Arn,Metadata:MetadataOptions}')]
    for name, op, q in ec2:
        options = ('--filter', f[1]) if op == 'describe-nat-gateways' else f
        c.call(name, 'ec2', op, q, *options)
    c.call('igws','ec2','describe-internet-gateways','InternetGateways[].{ID:InternetGatewayId,Attachments:Attachments}', '--filters', 'Name=attachment.vpc-id,Values=' + vpc)
    c.call('asg','autoscaling','describe-auto-scaling-groups', 'AutoScalingGroups[].{Name:AutoScalingGroupName,Min:MinSize,Max:MaxSize,Desired:DesiredCapacity,AZs:AvailabilityZones,Subnets:VPCZoneIdentifier,Instances:Instances,LaunchTemplate:LaunchTemplate,Suspended:SuspendedProcesses}', '--auto-scaling-group-names', a.cluster)
    c.call('ecs-cluster','ecs','describe-clusters','{clusters:clusters[].{Name:clusterName,Status:status,Running:runningTasksCount,Pending:pendingTasksCount,Instances:registeredContainerInstancesCount,Providers:capacityProviders},failures:failures}', '--clusters', a.cluster)
    ci = c.call('ecs-container-list','ecs','list-container-instances','containerInstanceArns','--cluster',a.cluster) or []
    for n in range(0,len(ci),100):
        c.call('ecs-container-'+str(n),'ecs','describe-container-instances','{instances:containerInstances[].{ARN:containerInstanceArn,EC2:ec2InstanceId,Status:status,Registered:registeredResources,Remaining:remainingResources,Running:runningTasksCount},failures:failures}', '--cluster',a.cluster,'--container-instances',*ci[n:n+100])
    services = c.call('ecs-service-list','ecs','list-services','serviceArns','--cluster',a.cluster) or []
    roles = set()
    for i, srv in enumerate(services):
        d = c.call('ecs-service-'+str(i),'ecs','describe-services','{services:services[].{Name:serviceName,Desired:desiredCount,Running:runningCount,Pending:pendingCount,TaskDefinition:taskDefinition,Network:networkConfiguration,LoadBalancers:loadBalancers,Deployments:deployments[].{Status:status,Rollout:rolloutState,TaskDefinition:taskDefinition,Desired:desiredCount,Running:runningCount}},failures:failures}', '--cluster',a.cluster,'--services',srv)
        for s in (d or {}).get('services',[]):
            td = c.call('ecs-definition-'+str(i),'ecs','describe-task-definition','taskDefinition.{ARN:taskDefinitionArn,TaskRole:taskRoleArn,ExecutionRole:executionRoleArn,Network:networkMode,CPU:cpu,Memory:memory,Containers:containerDefinitions[].{Name:name,Image:image,Ports:portMappings,SecretNames:secrets[].name,EnvironmentNames:environment[].name}}','--task-definition',s['TaskDefinition'])
            if td:
                roles.update(r for r in [td.get('TaskRole'),td.get('ExecutionRole')] if r)
    tasks = c.call('ecs-task-list','ecs','list-tasks','taskArns','--cluster',a.cluster) or []
    for n in range(0,len(tasks),100):
        c.call('ecs-tasks-'+str(n),'ecs','describe-tasks','{tasks:tasks[].{ARN:taskArn,Definition:taskDefinitionArn,AZ:availabilityZone,ContainerInstance:containerInstanceArn,Status:lastStatus,Health:healthStatus,Containers:containers[].{Name:name,Digest:imageDigest,Status:lastStatus},Attachments:attachments},failures:failures}', '--cluster',a.cluster,'--tasks',*tasks[n:n+100])
    for i, arn in enumerate(sorted(roles)):
        role = arn.rsplit('/',1)[-1]
        c.call('iam-role-'+str(i),'iam','get-role','Role.{Name:RoleName,ARN:Arn,Trust:AssumeRolePolicyDocument,Boundary:PermissionsBoundary}','--role-name',role)
        c.call('iam-attached-'+str(i),'iam','list-attached-role-policies','AttachedPolicies','--role-name',role)
        c.call('iam-inline-'+str(i),'iam','list-role-policies','PolicyNames','--role-name',role)
    for op in ['describe-scalable-targets','describe-scaling-policies']:
        q = 'ScalableTargets' if op.endswith('targets') else 'ScalingPolicies'
        c.call(op,'application-autoscaling',op,q,'--service-namespace','ecs')
    lbs = c.call('albs','elbv2','describe-load-balancers',f"LoadBalancers[?VpcId=='{vpc}'].{{ARN:LoadBalancerArn,Name:LoadBalancerName,Scheme:Scheme,Type:Type,AZs:AvailabilityZones,SGs:SecurityGroups,State:State}}") or []
    for i, lb in enumerate(lbs):
        c.call('listeners-'+str(i),'elbv2','describe-listeners','Listeners[].{Port:Port,Protocol:Protocol,Certificates:Certificates,Actions:DefaultActions,SslPolicy:SslPolicy}','--load-balancer-arn',lb['ARN'])
        tgs = c.call('targets-'+str(i),'elbv2','describe-target-groups','TargetGroups[].{ARN:TargetGroupArn,Port:Port,Protocol:Protocol,Type:TargetType,HealthPath:HealthCheckPath}', '--load-balancer-arn',lb['ARN']) or []
        for j,tg in enumerate(tgs):
            c.call(f'health-{i}-{j}','elbv2','describe-target-health','TargetHealthDescriptions','--target-group-arn',tg['ARN'])
    c.call('rds','rds','describe-db-instances',f"DBInstances[?DBSubnetGroup.VpcId=='{vpc}'].{{ID:DBInstanceIdentifier,Engine:Engine,Version:EngineVersion,Class:DBInstanceClass,Status:DBInstanceStatus,MultiAZ:MultiAZ,AZ:AvailabilityZone,SecondaryAZ:SecondaryAvailabilityZone,Public:PubliclyAccessible,Encrypted:StorageEncrypted,BackupDays:BackupRetentionPeriod,EarliestRestore:EarliestRestorableTime,LatestRestore:LatestRestorableTime,Subnets:DBSubnetGroup.Subnets,SGs:VpcSecurityGroups,Storage:AllocatedStorage}}")
    c.call('redis','elasticache','describe-replication-groups','ReplicationGroups[].{ID:ReplicationGroupId,Status:Status,Members:MemberClusters,Groups:NodeGroups,AutoFailover:AutomaticFailover,MultiAZ:MultiAZ,TLS:TransitEncryptionEnabled,Encrypted:AtRestEncryptionEnabled,Users:UserGroupIds,SnapshotDays:SnapshotRetentionLimit}')
    c.call('redis-nodes','elasticache','describe-cache-clusters','CacheClusters[].{ID:CacheClusterId,Engine:Engine,Version:EngineVersion,Type:CacheNodeType,AZ:PreferredAvailabilityZone,SubnetGroup:CacheSubnetGroupName,SGs:SecurityGroups,Status:CacheClusterStatus}')
    buckets = c.call('buckets','s3api','list-buckets',"Buckets[?starts_with(Name, 'labseat')].Name") or []
    for i,b in enumerate(buckets):
        for op,q in [('get-bucket-location','LocationConstraint'),('get-bucket-versioning','{Status:Status,MFADelete:MFADelete}'),('get-bucket-encryption','ServerSideEncryptionConfiguration'),('get-public-access-block','PublicAccessBlockConfiguration'),('get-bucket-policy-status','PolicyStatus')]:
            c.call(f's3-{i}-{op}','s3api',op,q,'--bucket',b,'--expected-bucket-owner',a.expected_account)
    c.call('alarms','cloudwatch','describe-alarms',"{MetricAlarms:MetricAlarms[?contains(AlarmName, 'labseat')].{Name:AlarmName,State:StateValue,Metric:MetricName,Namespace:Namespace,Dimensions:Dimensions,Actions:AlarmActions,Enabled:ActionsEnabled},CompositeAlarms:CompositeAlarms[?contains(AlarmName, 'labseat')].{Name:AlarmName,State:StateValue}}")
    c.call('logs','logs','describe-log-groups','logGroups[].{Name:logGroupName,Retention:retentionInDays,Bytes:storedBytes}','--log-group-name-prefix','/labseat')
    queues = c.call('queues','sqs','list-queues','QueueUrls','--queue-name-prefix','labseat') or []
    for i,url in enumerate(queues):
        c.call('queue-'+str(i),'sqs','get-queue-attributes','Attributes','--queue-url',url,'--attribute-names','QueueArn','VisibilityTimeout','MessageRetentionPeriod','RedrivePolicy','SqsManagedSseEnabled','ApproximateNumberOfMessages')
    c.call('ssm-metadata','ssm','describe-parameters','Parameters[].{Name:Name,Type:Type,Version:Version,Modified:LastModifiedDate}', '--parameter-filters','Key=Name,Option=BeginsWith,Values=/labseat/')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile',default='tv1')
    p.add_argument('--region',choices=['ap-southeast-2'],default='ap-southeast-2')
    p.add_argument('--expected-account',required=True)
    p.add_argument('--vpc-id',default='')
    p.add_argument('--cluster',default='labseat-lab')
    p.add_argument('--commit',default='UNKNOWN')
    a = p.parse_args()
    if not re.fullmatch(r'\d{12}',a.expected_account) or (a.vpc_id and not re.fullmatch(r'vpc-[0-9a-f]+',a.vpc_id)):
        p.error('Invalid account or VPC ID')
    root = Path(__file__).resolve().parents[3]
    if not (root / '.git').exists():
        p.error('Copy docs/ into the existing Git repository first.')
    ignored = subprocess.run(['git','-C',str(root),'check-ignore','-q','.local/assessment/check'], capture_output=True)
    if ignored.returncode != 0:
        p.error('.local/ is not ignored by Git; update repository from main first.')
    if a.commit == 'UNKNOWN':
        r = subprocess.run(['git','-C',str(root),'rev-parse','HEAD'],capture_output=True,text=True)
        if r.returncode == 0:
            a.commit = r.stdout.strip()
    dest = root / '.local' / 'assessment' / (dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-A1-' + os.urandom(3).hex())
    dest.mkdir(parents=True,exist_ok=False)
    c = Collector(a,dest)
    try:
        collect(c)
    except RuntimeError as exc:
        c.rows.append({'name':'preflight','status':'BLOCKED','error':str(exc)})
        print(str(exc))
    finally:
        c.save()
    print('Private output: ' + str(dest))
    print('Review summary.md first; never upload the entire private directory.')
    return 2 if any(r['status'] in ('BLOCKED','PARTIAL') for r in c.rows) else 0

if __name__ == '__main__':
    sys.exit(main())
