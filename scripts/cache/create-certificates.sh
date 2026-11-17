#!/usr/bin/env bash
set -euo pipefail
# Keep the CA key offline. Use the exact EC2 private DNS endpoint as the SAN.
endpoint=${1:?Usage: create-certificates.sh PRIVATE_DNS NEW_OUTPUT_DIRECTORY}
output_dir=${2:?Provide a new private output directory outside the repository}
[[ "$endpoint" =~ ^[A-Za-z0-9.-]+$ ]] || exit 1
[[ ! -e "$output_dir" ]] || exit 1
umask 077
mkdir -m 700 "$output_dir"
openssl req -x509 -newkey rsa:3072 -nodes -days 365 -keyout "$output_dir/ca.key" \
  -out "$output_dir/ca.pem" -subj /CN=LabSeat-Private-Redis-CA
openssl req -newkey rsa:3072 -nodes -keyout "$output_dir/server.key" \
  -out "$output_dir/server.csr" -subj "/CN=$endpoint"
printf 'subjectAltName=DNS:%s\nextendedKeyUsage=serverAuth\n' "$endpoint" >"$output_dir/extensions.cnf"
openssl x509 -req -in "$output_dir/server.csr" -CA "$output_dir/ca.pem" -CAkey "$output_dir/ca.key" \
  -CAcreateserial -out "$output_dir/server.pem" -days 90 -extfile "$output_dir/extensions.cnf"
openssl verify -CAfile "$output_dir/ca.pem" -verify_hostname "$endpoint" "$output_dir/server.pem"
