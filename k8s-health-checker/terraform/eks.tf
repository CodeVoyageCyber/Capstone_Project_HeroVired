# EKS cluster with a single managed node group, OIDC provider (for
# IRSA, used later by files-service / FIS chaos service accounts),
# and the EBS CSI driver addon (required by GratitudeApp's gp3
# StorageClass + Postgres PVC).
#
# Cost-conscious defaults: t3.medium x2, single NAT gateway (see
# vpc.tf), and public+private endpoint access so kubectl works from
# your machine without extra bastion/VPN setup.

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = var.cluster_version

  cluster_endpoint_public_access = true

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  enable_cluster_creator_admin_permissions = true

  # OIDC provider is required for IRSA: used by the EBS CSI driver
  # addon below, and later by files-service-sa (S3) and the FIS
  # chaos service account.
  enable_irsa = true

  cluster_addons = {
    coredns    = {}
    kube-proxy = {}
    vpc-cni    = {}

    aws-ebs-csi-driver = {
      service_account_role_arn = module.ebs_csi_irsa_role.iam_role_arn
    }
  }

  eks_managed_node_groups = {
    default = {
      instance_types = [var.node_instance_type]
      ami_type       = "AL2_x86_64"

      min_size     = var.node_min_size
      max_size     = var.node_max_size
      desired_size = var.node_desired_size

      disk_size = var.node_disk_size

      labels = {
        role = "gratitude-health-worker"
      }

      tags = {
        Project = "gratitude-health-checker"
      }
    }
  }

  tags = {
    Project = "gratitude-health-checker"
  }
}

# IAM role for the EBS CSI driver, bound via IRSA to the
# aws-ebs-csi-driver addon's service account.
module "ebs_csi_irsa_role" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.39"

  role_name             = "${var.cluster_name}-ebs-csi"
  attach_ebs_csi_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:ebs-csi-controller-sa"]
    }
  }

  tags = {
    Project = "gratitude-health-checker"
  }
}
