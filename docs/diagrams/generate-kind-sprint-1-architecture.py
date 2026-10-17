"""Generate the Sprint 1-only local architecture; no deployed status is implied."""
from html import escape
from pathlib import Path

s = ['''<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1120" viewBox="0 0 1920 1120" role="img" aria-labelledby="title desc">
<title id="title">Sprint 1 — KinD foundation and read-only monitoring</title>
<desc id="desc">Local Docker builds load images into a three-node KinD cluster. GratitudeApp, the read-only health checker and the monitoring stack occupy separate namespaces. Prometheus scrapes metrics and Grafana queries Prometheus. Access uses localhost port-forwards.</desc>
<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4" orient="auto-start-reverse"><path d="M0 0 L8 4 L0 8 Z" fill="#52627a"/></marker></defs>
<style>text{font-family:Helvetica,Arial,sans-serif;fill:#182b46}.title{font-size:34px;font-weight:700}.section{font-size:23px;font-weight:700}.node{font-size:23px;font-weight:700}.body{font-size:20px;fill:#41536d}.small{font-size:18px;fill:#52627a}</style>
<rect width="1920" height="1120" fill="#f7f9fc"/>
''']


def text(x,y,label,cls='body'):
    s.append(f'<text x="{x}" y="{y}" class="{cls}">{escape(label)}</text>')


def rect(x,y,w,h,fill='#fff',stroke='#c3d1e2',dash=False):
    d = ' stroke-dasharray="8 6"' if dash else ''
    s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="1.6"{d}/>')


def card(x,y,w,h,title,lines):
    rect(x,y,w,h)
    text(x+20,y+34,title,'node')
    for i,line in enumerate(lines): text(x+20,y+67+i*27,line)


def edge(path):
    s.append(f'<path d="{path}" fill="none" stroke="#52627a" stroke-width="2" marker-end="url(#arrow)"/>')


text(45,54,'Sprint 1 · KinD foundation and read-only monitoring','title')
text(45,89,'Implementation target for the local walkthrough · attach your own validation screenshots to the guide')
card(90,120,760,115,'Developer workstation',['Docker build + kind load docker-image · kubectl + Helm','localhost port-forward: API :8000 · Prometheus :9090 · Grafana :3000'])
card(1020,120,810,115,'Sprint 1 scope',['Cluster access · application baseline · read-only API · metrics discovery','Diagram shows the intended result; execution and evidence are pending.'])
rect(40,270,1840,775,'#eef3f9','#879fbf')
text(65,307,'Docker Desktop Linux VM · shared laptop compute and disk','section')
rect(70,330,1780,660,'#fff','#4b8ccf',True)
text(95,366,'KinD cluster: gratitude · 1 control-plane + 2 worker containers','section')
rect(650,395,560,85,'#eaf1ff','#99b5dd')
text(670,430,'Kubernetes API + built-in controllers','node')
text(670,459,'ServiceAccount authentication · read-only observer RBAC','small')
rect(100,510,490,425,'#f3f7fc')
rect(650,510,560,425,'#f5f7fb')
rect(1270,395,550,540,'#f2f8fa')
text(120,549,'namespace: gratitude','section')
text(670,549,'namespace: health-system','section')
text(1290,434,'namespace: monitoring','section')
card(120,580,450,140,'GratitudeApp',['9 services · local Docker images','React/nginx + REST/gRPC backends','Journal validation via API gateway'])
card(120,775,450,120,'PostgreSQL',['Local standard PVC','Application data + initialization SQL'])
card(670,580,520,160,'FastAPI health checker',['Read nodes, pods, services, deployments','Cached snapshot · polling every 15 seconds','/healthz · /readyz · /api/* · /metrics'])
card(670,805,520,90,'Service: healthchecker',['Named http port :8000 · ServiceMonitor target'])
card(1290,470,510,120,'Prometheus',['ServiceMonitor discovery · /metrics scrapes','Local TSDB PVC · cluster metrics'])
card(1290,645,510,105,'Cluster metrics sources',['kube-state-metrics + kubelet/cAdvisor'])
card(1290,805,510,90,'Grafana',['Prometheus data source · Explore · local PVC'])
edge('M470 235 L470 253 L50 253 L50 650 L120 650')
text(105,390,'Build images; load and apply resources','small')
edge('M1190 615 L1235 615 L1235 437 L1210 437')
text(675,570,'Read-only Kubernetes API calls','small')
edge('M1290 530 L1255 530 L1255 850 L1190 850')
text(675,780,'Prometheus pulls metrics through Service discovery','small')
edge('M1545 645 L1545 590')
text(1565,626,'scrape','small')
edge('M1800 850 L1810 850 L1810 530 L1800 530')
edge('M345 720 L345 775')
text(365,756,'SQL','small')
text(105,973,'Monitoring chart also installs Prometheus Operator and Alertmanager; no custom alert routing is configured in Sprint 1.','body')
text(65,1024,'Local PVCs survive pod recreation; deleting the KinD cluster removes its local data.','body')
text(45,1085,'Access: localhost port-forwards. Frontend assets and backend API are tested separately; shared browser /api routing is outside this baseline.','small')
s.append('</svg>')
p = Path(__file__).resolve().with_name('kind-sprint-1-architecture.svg')
p.write_text('\n'.join(s))
print(p)
