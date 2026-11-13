output "vpc_id" {
  value = aws_vpc.this.id
}
output "public_subnet_ids" {
  value = [aws_subnet.this["public_a"].id, aws_subnet.this["public_b"].id]
}
output "app_subnet_ids" {
  value = [aws_subnet.this["app_a"].id, aws_subnet.this["app_b"].id]
}
output "db_subnet_ids" {
  value = [aws_subnet.this["db_a"].id, aws_subnet.this["db_b"].id]
}
output "alb_sg_id" {
  value = aws_security_group.tier["alb"].id
}
output "app_sg_id" {
  value = aws_security_group.tier["app"].id
}
output "db_sg_id" {
  value = aws_security_group.tier["db"].id
}
output "s3_endpoint_id" {
  value = aws_vpc_endpoint.s3.id
}
