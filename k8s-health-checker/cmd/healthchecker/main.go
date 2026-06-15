// Command healthchecker is the entrypoint for the Kubernetes Cluster
// Health Checker and Auto-Healing tool.
//
// In Sprint 1 this binary only verifies that the Kubernetes API
// connection works correctly by listing cluster nodes and pods.
// Later sprints will add the monitoring, self-healing, alerting,
// and dashboard functionality.
package main

import (
	"context"
	"fmt"
	"log"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	"github.com/yourusername/k8s-health-checker/internal/k8sclient"
)

func main() {
	clientset, err := k8sclient.NewClient()
	if err != nil {
		log.Fatalf("error creating Kubernetes client: %v", err)
	}

	ctx := context.Background()

	nodes, err := clientset.CoreV1().Nodes().List(ctx, metav1.ListOptions{})
	if err != nil {
		log.Fatalf("error listing nodes: %v", err)
	}
	fmt.Printf("Connected to cluster. Found %d node(s):\n", len(nodes.Items))
	for _, n := range nodes.Items {
		fmt.Printf("  - %s\n", n.Name)
	}

	pods, err := clientset.CoreV1().Pods("").List(ctx, metav1.ListOptions{})
	if err != nil {
		log.Fatalf("error listing pods: %v", err)
	}
	fmt.Printf("Found %d pod(s) across all namespaces\n", len(pods.Items))
}
