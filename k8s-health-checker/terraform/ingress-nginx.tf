# ingress-nginx controller, required by GratitudeApp's
# k8s/ingress-service.yml (ingressClassName: nginx).
#
# Installed via Helm/Terraform so the whole stack comes up with one
# `terraform apply`. Uses a Network Load Balancer (NLB) via the
# annotation below, which is the standard cost-effective choice on
# EKS for a single ingress controller.

resource "helm_release" "ingress_nginx" {
  count = var.enable_ingress_nginx ? 1 : 0

  name             = "ingress-nginx"
  repository       = "https://kubernetes.github.io/ingress-nginx"
  chart            = "ingress-nginx"
  namespace        = "ingress-nginx"
  create_namespace = true

  set {
    name  = "controller.service.type"
    value = "LoadBalancer"
  }

  set {
    name  = "controller.service.annotations.service\\.beta\\.kubernetes\\.io/aws-load-balancer-type"
    value = "nlb"
  }

  set {
    name  = "controller.resources.requests.cpu"
    value = "100m"
  }

  set {
    name  = "controller.resources.requests.memory"
    value = "128Mi"
  }

  depends_on = [module.eks]
}
