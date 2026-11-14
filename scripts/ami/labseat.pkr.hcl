packer {
  required_version = ">= 1.13.0"

  required_plugins {
    amazon = {
      source  = "github.com/hashicorp/amazon"
      version = "= 1.8.3"
    }
  }
}

variable "app_dir" {
  type = string
}

variable "app_version" {
  type = string
}

variable "image_mode" {
  type = string
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

source "amazon-ebs" "labseat" {
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
  ami_name                    = "labseat-${var.image_mode}-${var.app_version}-${formatdate("YYYYMMDD-hhmmss", timestamp())}"
  ami_description             = "LabSeat ${var.image_mode} ${var.app_version}"

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
    Project    = "labseat"
    AppVersion = var.app_version
    ImageMode  = var.image_mode
    BaseAMI    = var.source_ami
  }
}

build {
  sources = ["source.amazon-ebs.labseat"]

  provisioner "shell" {
    inline = ["mkdir -m 700 /tmp/labseat-app /tmp/labseat-deploy"]
  }

  provisioner "file" {
    source      = "${var.app_dir}/"
    destination = "/tmp/labseat-app/"
  }

  provisioner "file" {
    source      = "${path.root}/../../deploy/"
    destination = "/tmp/labseat-deploy/"
  }

  provisioner "shell" {
    script          = "${path.root}/install-runtime.sh"
    execute_command = "chmod +x '{{ .Path }}'; sudo env {{ .Vars }} '{{ .Path }}'"
    env = {
      APP_VERSION        = var.app_version
      AWS_REGION         = var.region
      LABSEAT_IMAGE_MODE = var.image_mode
    }
  }

  post-processor "manifest" {
    output     = var.manifest_path
    strip_path = true
    custom_data = {
      app_version = var.app_version
      image_mode  = var.image_mode
      source_ami  = var.source_ami
      region      = var.region
    }
  }
}
