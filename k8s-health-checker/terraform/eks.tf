# EKS cluster with a single managed node group.
# Cost-conscious defaults: t3.medium x2, single NAT gateway (see vpc.tf),
# and public+private endpoint access so kubectl works from your machine
# without extra bastion/VPN setup.

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = var.cluster_version

  cluster_endpoint_public_access = true

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  enable_cluster_creator_admin_permissions = true

  eks_managed_node_groups = {
    default = {
      instance_types = [var.node_instance_type]
      ami_type       = "AL2_x86_64"

      min_size     = var.node_min_size
      max_size     = var.node_max_size
      desired_size = var.node_desired_size

      disk_size = var.node_disk_size

      labels = {
        role = "health-checker-worker"
      }

      tags = {
        Project = "k8s-health-checker"
      }
    }
  }

  tags = {
    Project = "k8s-health-checker"
  }
}
