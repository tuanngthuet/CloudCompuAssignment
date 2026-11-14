"""Read runtime settings and replace this process with the release entry point."""

import json
import os
import subprocess
import sys


PARAMETER_PREFIX = "/labseat/lab/"
RUNTIME_PARAMETERS = ("DATABASE_URL", "S3_BUCKET")
OPTIONAL_PARAMETERS = ("S3_PREFIX",)


def release_settings():
    names = [PARAMETER_PREFIX + key for key in RUNTIME_PARAMETERS + OPTIONAL_PARAMETERS]
    response = subprocess.run(
        [
            "aws", "ssm", "get-parameters", "--region", os.environ["AWS_REGION"],
            "--with-decryption", "--output", "json", "--no-cli-pager", "--names", *names,
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    parameters = {
        item["Name"].removeprefix(PARAMETER_PREFIX): item
        for item in json.loads(response.stdout)["Parameters"]
        if item["Name"] in names
    }
    missing = [name for name in RUNTIME_PARAMETERS if not parameters.get(name, {}).get("Value")]
    if missing:
        raise RuntimeError("Required Parameter Store keys missing: " + ", ".join(missing))
    if parameters["DATABASE_URL"]["Type"] != "SecureString":
        raise RuntimeError("DATABASE_URL must be a SecureString")
    return {
        "APP_ENV": "lab",
        "STORAGE_BACKEND": "s3",
        "DATABASE_URL": parameters["DATABASE_URL"]["Value"],
        "S3_BUCKET": parameters["S3_BUCKET"]["Value"],
        "S3_PREFIX": parameters.get("S3_PREFIX", {}).get("Value", ""),
    }


def main():
    mode = os.environ.get("LABSEAT_IMAGE_MODE")
    environment = {**os.environ, "PORT": "8000", "HOST": "0.0.0.0"}
    if mode == "release":
        try:
            environment.update(release_settings())
        except RuntimeError as error:
            print(f"LabSeat startup: {error}", file=sys.stderr)
            return 1
        except (subprocess.SubprocessError, OSError, ValueError, KeyError, TypeError):
            print("LabSeat startup: could not read runtime settings from Parameter Store.", file=sys.stderr)
            return 1
    elif mode == "fixture":
        environment.update(APP_ENV="fixture", STORAGE_BACKEND="local")
    else:
        print("LabSeat startup: invalid image mode.", file=sys.stderr)
        return 1

    os.execve("/usr/bin/bash", ["bash", "/opt/labseat/app/start.sh"], environment)


if __name__ == "__main__":
    sys.exit(main())
