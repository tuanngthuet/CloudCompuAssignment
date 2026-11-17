packer {
  required_version = ">= 1.14.0"

  required_plugins {
    amazon = {
      source  = "github.com/hashicorp/amazon"
      version = "= 1.8.3"
    }
  }
}

variable "region" {
  type = string
}

variable "source_ami" {
  type = string
}

variable "build_subnet_id" {
  type = string
}

variable "build_security_group_id" {
  type = string
}

variable "build_instance_profile" {
  type = string
}

variable "manifest_path" {
  type = string
}

source "amazon-ebs" "cache" {
  region                      = var.region
  source_ami                  = var.source_ami
  instance_type               = "t3.small"
  subnet_id                   = var.build_subnet_id
  security_group_id           = var.build_security_group_id
  iam_instance_profile        = var.build_instance_profile
  associate_public_ip_address = false
  ssh_username                = "ec2-user"
  ssh_interface               = "session_manager"
  ssh_timeout                 = "10m"
  ssh_clear_authorized_keys   = true
  imds_support                = "v2.0"
  ami_name                    = "labseat-redis-7.4.12-${formatdate("YYYYMMDD-hhmmss", timestamp())}"
  ami_description             = "LabSeat Redis 7.4.12 TLS"

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  launch_block_device_mappings {
    device_name           = "/dev/xvda"
    volume_type           = "gp3"
    volume_size           = 20
    encrypted             = true
    delete_on_termination = true
  }

  tags = {
    Project      = "labseat"
    RedisVersion = "7.4.12"
    ImageMode    = "cache"
    BaseAMI      = var.source_ami
  }
}

build {
  sources = ["source.amazon-ebs.cache"]

  provisioner "shell" {
    inline = ["mkdir -m 700 /tmp/labseat-cache"]
  }
  provisioner "file" {
    source      = "${path.root}/"
    destination = "/tmp/labseat-cache/"
  }
  provisioner "shell" {
    script          = "${path.root}/install.sh"
    execute_command = "chmod +x '{{ .Path }}'; sudo '{{ .Path }}'"
  }

  post-processor "manifest" {
    output     = var.manifest_path
    strip_path = true
    custom_data = {
      redis_version = "7.4.12"
      source_sha256 = "56588ee1648539556f2b6cf4e873e3734afbbe40fa952fec2fcd6b6d7dae2924"
      source_ami    = var.source_ami
      region        = var.region
    }
  }
}
