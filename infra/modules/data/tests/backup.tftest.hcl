mock_provider "aws" {}
variables {
  project       = "labseat"
  environment   = "lab"
  db_subnet_ids = ["subnet-0123456789abcdef0", "subnet-0123456789abcdef1"]
  db_sg_id      = "sg-0123456789abcdef0"
  db_name       = "labseat"
  multi_az      = true
}
run "production_backup_default" {
  command = plan
  assert {
    condition     = aws_db_instance.app.backup_retention_period == 30 && aws_db_instance.app.multi_az && !aws_db_instance.app.publicly_accessible
    error_message = "The default must retain 30 days of backups on a private Multi-AZ database."
  }
}
run "short_backup_preserves_ha" {
  command = plan
  variables { backup_retention_days = 1 }
  assert {
    condition     = aws_db_instance.app.backup_retention_period == 1 && aws_db_instance.app.multi_az && aws_db_instance.app.deletion_protection && !aws_db_instance.app.publicly_accessible
    error_message = "Shorter retention must retain HA, deletion protection and private networking."
  }
}
run "reject_disabled_backups" {
  command = plan
  variables { backup_retention_days = 0 }
  expect_failures = [var.backup_retention_days]
}
