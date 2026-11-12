from pathlib import Path
import hcl2,re,ipaddress,json
r=Path(__file__).resolve().parents[2];resources={};outputs=set();count=0
for p in r.rglob('*'):
 if '.terraform' in p.parts or not p.is_file():continue
 if p.suffix=='.tf' or p.name.endswith('.tftest.hcl'):
  with p.open() as f:d=hcl2.load(f)
  count+=1
  if 'modules/network' in p.as_posix():
   for item in d.get('resource',[]):
    for typ,names in item.items():
     for name,body in names.items():resources[(typ.strip('"'),name.strip('"'))]=body
   for o in d.get('output',[]):outputs.update(k.strip('"') for k in o)
with (r/'infra/modules/network/main.tf').open() as f:d=hcl2.load(f)
s=d['locals'][0]['subnets']; assert len(s)==6
nets=[]
for k,v in s.items():
 idx=int(re.search(r', 8, (\d+)\)',v['cidr'])[1]);nets.append(ipaddress.ip_network(f'10.20.{idx}.0/24'))
assert len(set(nets))==6
for i,a in enumerate(nets):
 assert a.subnet_of(ipaddress.ip_network('10.20.0.0/16'))
 for b in nets[i+1:]:assert not a.overlaps(b)
assert sum(typ=='aws_nat_gateway' for typ,name in resources)==1
routes=[b for (t,n),b in resources.items() if t=='aws_route'];assert len(routes)==2
assert all('"db"' not in b['route_table_id'] for b in routes)
ing=[b for (t,n),b in resources.items() if t=='aws_vpc_security_group_ingress_rule'];assert len(ing)==3
assert {int(b['from_port']) for b in ing}=={80,8000,5432}
assert resources['aws_subnet','this']['map_public_ip_on_launch'] is False
expected={'vpc_id','public_subnet_ids','app_subnet_ids','db_subnet_ids','alb_sg_id','app_sg_id','db_sg_id','s3_endpoint_id'}
assert outputs==expected
for p in r.rglob('*.tf'):
 if '.terraform' in p.parts:continue
 text=p.read_text();assert 'terraform_remote_state' not in text
print(f'PASS: HCL parse of {count} Terraform/test files')
print('PASS: 6 non-overlapping /24 subnets within VPC /16')
print('PASS: exactly 1 NAT declaration; no declared DB default route')
print('PASS: ingress ports only 80/8000/5432; no SSH ingress')
print('PASS: public IP auto-assignment disabled; 8 exact contract output names')
print('PASS: no remote-state dependency')
print('These are source checks only; provider validation, mock execution and AWS runtime remain pending.')
