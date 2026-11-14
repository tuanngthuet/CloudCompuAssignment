"""Validate a prepared application bundle and build its AMI with Packer."""

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


TEMPLATE = Path(__file__).resolve().with_name("labseat.pkr.hcl")
EXCLUDED = {".git", "__pycache__", ".pytest_cache", ".venv"}


def package_files(source, target, mode):
    if target.is_relative_to(source):
        raise ValueError("Bundle source cannot contain the staging directory.")
    for filename in ("start.sh", "requirements.lock"):
        if not (source / filename).is_file():
            raise ValueError(f"Bundle root must contain {filename}.")
    if (source / "FIXTURE_ONLY").is_file() != (mode == "fixture"):
        raise ValueError("Bundle marker does not match the selected image mode.")

    for folder, directories, filenames in os.walk(source):
        path = Path(folder)
        directories[:] = [name for name in directories if name not in EXCLUDED]
        filenames = [name for name in filenames if name not in EXCLUDED]
        destination = target / path.relative_to(source)
        destination.mkdir(parents=True, exist_ok=True)
        for name in directories + filenames:
            entry = path / name
            if entry.is_symlink():
                raise ValueError(f"Bundle contains a symlink: {entry.relative_to(source)}")
            if name in {".aws", ".ssh"} or (name.startswith(".env") and name != ".env.example"):
                raise ValueError(f"Remove runtime credentials from the bundle: {entry.relative_to(source)}")
        for name in filenames:
            shutil.copyfile(path / name, destination / name)

    start_script = target / "start.sh"
    start_script.write_bytes(start_script.read_bytes().replace(b"\r\n", b"\n"))


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-bundle", action="store_true", help="Check and stage files locally only.")
    parser.add_argument("--app-dir", required=True, type=Path)
    parser.add_argument("--app-version", required=True)
    parser.add_argument("--mode", choices=("release", "fixture"), default="release")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--source-ami")
    parser.add_argument("--build-subnet-id")
    parser.add_argument("--build-security-group-id")
    parser.add_argument("--build-instance-profile")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}", args.app_version):
        parser.error("--app-version must be an AMI-safe version of up to 80 characters.")
    if not args.check_bundle:
        for option, pattern in {
            "region": r"[a-z]{2}(?:-[a-z0-9]+)+-\d+",
            "source_ami": r"ami-[0-9a-f]{8}(?:[0-9a-f]{9})?",
            "build_subnet_id": r"subnet-[0-9a-f]{8}(?:[0-9a-f]{9})?",
            "build_security_group_id": r"sg-[0-9a-f]{8}(?:[0-9a-f]{9})?",
            "build_instance_profile": r"[\w+=,.@-]{1,128}",
        }.items():
            if not re.fullmatch(pattern, getattr(args, option) or "", flags=re.ASCII):
                parser.error(f"Provide a valid --{option.replace('_', '-')} for a build.")
        if args.manifest is None:
            parser.error("--manifest is required for a build.")
    return args


def main():
    args = arguments()
    try:
        with TemporaryDirectory(prefix="labseat-ami-") as staging:
            package_files(args.app_dir.resolve(), Path(staging), args.mode)
            if args.check_bundle:
                print(f"Bundle checks passed ({args.mode}).")
                return 0

            manifest = args.manifest.resolve()
            manifest.parent.mkdir(parents=True, exist_ok=True)
            settings = {
                "app_dir": Path(staging).as_posix(),
                "app_version": args.app_version,
                "image_mode": args.mode,
                "region": args.region,
                "source_ami": args.source_ami,
                "build_subnet_id": args.build_subnet_id,
                "build_security_group_id": args.build_security_group_id,
                "build_instance_profile": args.build_instance_profile,
                "manifest_path": manifest.as_posix(),
            }
            variables = [f"-var={key}={value}" for key, value in settings.items()]
            subprocess.run(["packer", "validate", *variables, str(TEMPLATE)], check=True)
            subprocess.run(["packer", "build", *variables, str(TEMPLATE)], check=True)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"LabSeat AMI: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
