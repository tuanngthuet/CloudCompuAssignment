mock_provider "aws" {}
variables {
  expected_account_id = "000000000000" # MOCK_ONLY; never used by a deployment root.
  state_bucket_name   = "mock-only-tv1-state"
}
run "state_protection" {
  command = apply
  assert {
    condition     = aws_s3_bucket_versioning.state.versioning_configuration[0].status == "Enabled"
    error_message = "State versioning must be enabled."
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.state.block_public_acls && aws_s3_bucket_public_access_block.state.block_public_policy && aws_s3_bucket_public_access_block.state.ignore_public_acls && aws_s3_bucket_public_access_block.state.restrict_public_buckets
    error_message = "All four public access protections must be enabled."
  }
  assert {
    condition     = one(aws_s3_bucket_server_side_encryption_configuration.state.rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256" && !aws_s3_bucket.state.force_destroy
    error_message = "State must be encrypted and must not be force-destroyed."
  }
  assert {
    condition     = jsondecode(aws_s3_bucket_policy.tls.policy).Statement[0].Condition.Bool["aws:SecureTransport"] == "false"
    error_message = "Bucket must deny non-TLS access."
  }
}
