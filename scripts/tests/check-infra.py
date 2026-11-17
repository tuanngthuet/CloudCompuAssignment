"""Validate and mock-test all owner modules with isolated Terraform metadata, never AWS apply."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--terraform', default='terraform')
    args = parser.parse_args()
    subprocess.run([args.terraform, 'fmt', '-check', '-recursive', 'infra'], cwd=ROOT, check=True)
    modules = ['modules/network','modules/compute','modules/observability','modules/data','modules/iam',
               'modules/cache','modules/messaging','modules/managed_cache','bootstrap/state','bootstrap/network-stack','integration']
    with tempfile.TemporaryDirectory(prefix='labseat-provider-cache-') as cache:
        for module in modules:
            with tempfile.TemporaryDirectory(prefix='labseat-tf-check-') as data:
                env = {**os.environ, 'TF_DATA_DIR':data, 'TF_PLUGIN_CACHE_DIR':os.environ.get('TF_PLUGIN_CACHE_DIR',cache)}
                base = [args.terraform, '-chdir='+str(ROOT/'infra'/module)]
                for command in [('init','-backend=false','-input=false','-lockfile=readonly'), ('validate','-no-color')]:
                    subprocess.run(base+list(command), env=env, check=True)
                if (ROOT/'infra'/module/'tests').exists():
                    subprocess.run(base+['test','-no-color'], env=env, check=True)
    print('PASS: validation and mocked tests. AWS integration remains a separate gate.')


if __name__ == '__main__':
    main()
