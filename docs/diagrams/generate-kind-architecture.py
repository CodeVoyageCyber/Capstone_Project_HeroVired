"""Render the sprint-mapped KinD target architecture as editable SVG (stdlib only)."""
from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parent
C = {1: '#2563eb', 2: '#07856f', 3: '#c06a13', 4: '#7c3aed', 5: '#d23869', 6: '#087d9e'}
s = ['''<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1530" viewBox="0 0 1920 1530" role="img" aria-labelledby="title desc">
<title id="title">KinD architecture — Kubernetes health checker and auto-healing, Sprints 1–6</title>
<desc id="desc">Target architecture inside Docker Desktop: a three-node KinD cluster with GratitudeApp, a health checker and healing controller, Prometheus, Grafana, Alertmanager and external Slack. Sprint 1 is documented, not verified as deployed. Later capabilities are planned and drawn with dashed borders.</desc>
<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4" orient="auto-start-reverse"><path d="M0 0 L8 4 L0 8 Z" fill="#52627a"/></marker></defs>
<rect width="1920" height="1530" fill="#f7f9fc"/>
<style>text{font-family:Helvetica,Arial,sans-serif;fill:#182b46}.title{font-size:34px;font-weight:700}.sub{font-size:20px;fill:#52627a}.section{font-size:23px;font-weight:700}.node{font-size:23px;font-weight:700}.body{font-size:19px;fill:#41536d}.small{font-size:17px;fill:#52627a}.badge{font-size:16px;font-weight:700;fill:white}.edge{fill:none;stroke:#52627a;stroke-width:2;marker-end:url(#arrow)}.edgeplan{fill:none;stroke:#52627a;stroke-width:2;stroke-dasharray:7 5;marker-end:url(#arrow)}</style>''']


def text(x,y,value,cls='body'):
    s.append(f'<text x="{x}" y="{y}" class="{cls}">{escape(value)}</text>')


def rect(x,y,w,h,fill='#fff',stroke='#d6dfeb',dash=False,r=12):
    d=' stroke-dasharray="8 6"' if dash else ''
    s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="1.6"{d}/>')


def badge(x,y,n):
    rect(x,y,43,26,C[n],C[n],r=6)
    text(x+9,y+19,f'S{n}','badge')


def card(x,y,w,h,title,lines,sprints,planned=False):
    rect(x,y,w,h,'#fff','#9aadc4' if planned else '#bbcadd',planned)
    for i,n in enumerate(sprints): badge(x+w-15-49*(len(sprints)-i),y+15,n)
    text(x+20,y+36,title,'node')
    for i,line in enumerate(lines): text(x+20,y+69+i*26,line)


def edge(points,planned=False):
    cls='edgeplan' if planned else 'edge'
    dash = ' stroke-dasharray="7 5"' if planned else ''
    s.append(f'<path class="{cls}" d="{points}" fill="none" stroke="#52627a" stroke-width="2" marker-end="url(#arrow)"{dash}/>')


text(50,58,'GratitudeApp · Kubernetes health checker & auto-healing','title')
text(50,93,'KinD target architecture  /  grouped by responsibility, mapped to the six project sprints','sub')
legend=[('Foundation',1),('Health & rules',2),('Pod recovery',3),('Scale & balance',4),('Notifications',5),('Dashboard & handover',6)]
x=50
for label,n in legend:
    badge(x,115,n);text(x+53,135,label,'small');x += [230,255,240,270,250,300][n-1]
text(50,178,'STATUS: Sprint 1 guide authored; deployment unverified. Sprints 2–6 are planned capabilities.','sub')
# Entry points.
card(90,205,500,110,'Developer / application user',['Docker build + kind load; kubectl + Helm'],[1])
card(1260,205,550,110,'Operator / project reviewer',['localhost API :8000 · Grafana :3000'],[1,6])
# Boundaries.
rect(40,335,1840,1000,'#eef3f9','#879fbf',r=18)
text(65,369,'LOCAL MACHINE  /  Docker Desktop Linux VM','section')
text(65,398,'1 control-plane + 2 worker containers · shared laptop CPU and memory','body')
rect(70,420,1780,875,'#fff','#4b8ccf',dash=True,r=14)
text(95,455,'KinD cluster: gratitude','section')
text(420,454,'Local networking + standard StorageClass + namespace isolation','body')
badge(1775,433,1)
# Cluster-scoped API.
rect(650,475,570,74,'#eaf1ff','#99b5dd')
text(673,506,'Kubernetes API + built-in controllers','node')
text(673,533,'RBAC · scheduler · Deployment / ReplicaSet recovery','small')
# Namespace panels.
rect(95,575,505,650,'#f3f7fc','#d4e0ee')
rect(650,575,570,650,'#f5f7fb','#d4e0ee')
rect(1270,475,550,750,'#f2f8fa','#d4e0ee')
text(115,610,'APPLICATION  /  namespace: gratitude','section')
text(670,610,'AUTOMATION  /  health-system','section')
text(1290,510,'OBSERVABILITY  /  monitoring','section')
card(115,635,465,95,'React frontend',['nginx :80 · Service port :3000'],[1])
card(115,775,465,145,'Application services',['API gateway + server-main + files API','Entries, moods, stats: REST / gRPC','Local Docker builds to KinD image store'],[1])
card(115,965,465,95,'PostgreSQL',['Local PVC · journal, moods and stats'],[1])
card(115,1090,465,110,'Complete application access',['Shared /api routing + local S3 backend','Optional OpenAI integration: external'],[6],True)
card(670,635,530,145,'FastAPI health checker',['S1: read-only Kubernetes API polling','S2: readiness, conditions, resource checks','/healthz · /readyz · /api/* · /metrics'],[1,2])
card(670,830,530,145,'Opt-in healing controller',['Owned pods only · grace + cooldown','Recover failed / stuck / crashing pods','Scoped write RBAC added in Sprint 3'],[3],True)
card(670,1025,530,95,'Durable healing audit',['Action, reason, time and outcome'],[3],True)
card(670,1140,530,65,'Metrics Server / HPA / placement',[],[4],True)
# Monitoring cards.
card(1290,550,510,145,'Prometheus',['S1: scrape discovery + local TSDB PVC','S2: thresholds + custom alert rules','ServiceMonitor: /metrics'],[1,2])
card(1290,740,510,110,'Cluster exporters',['kube-state-metrics + kubelet/cAdvisor','Node/pod state · CPU · memory'],[1,2])
card(1290,895,510,125,'Grafana',['S1: install + Explore','S2: initial panels · S6: final dashboard','Health, resource trends, healing counters'],[1,2,6])
card(1290,1065,510,135,'Alertmanager',['S1: installed by monitoring chart','S5: severity routes + Slack receiver','S3 audit to S5 healing notifications'],[1,5])
# Connections in open lanes; meanings kept beside their source.
edge('M340 315 L50 315 L50 680 L115 680')
text(104,555,'S1: local build / deploy / port-forward','small')
edge('M1535 315 L1835 315 L1835 958 L1800 958')
text(1445,340,'UI access','small')
edge('M347 730 L347 775',True)
text(370,759,'API routing: S6', 'small')
# Shared frontend API routing is planned, hence the dashed edge.
edge('M347 920 L347 965');text(369,951,'SQL / gRPC','small')
edge('M670 662 L625 662 L625 510 L650 510');text(670,567,'S1: read nodes, pods, services and deployments','small')
edge('M1200 878 L1240 878 L1240 520 L1220 520',True)
text(700,808,'S3: delete eligible pod through API','small')
edge('M935 975 L935 1025',True)
text(954,1005,'append audit','small')
edge('M1290 645 L1200 645')
text(1218,723,'scrape','small')
edge('M1545 740 L1545 695');text(1562,726,'pull','small')
edge('M1800 955 L1810 955 L1810 615 L1800 615')
edge('M1290 675 L1255 675 L1255 1135 L1290 1135',True)
text(1290,1048,'S2 alerts to S5 delivery','small')
# HPA platform scope, separate from Python control loop.
text(95,1264,'S4 platform: Metrics Server to HPA to replicas; topology spread balances placement across workers.','body')
text(95,1317,'LOCAL STORAGE: PostgreSQL, Prometheus, Grafana + planned audit PVCs; survives pod restart, not cluster deletion.','body')
# Outside the Docker boundary.
card(90,1370,665,100,'Local operator exercises',['S3 chaos tests · S4 load / worker-capacity simulation'],[3,4],True)
card(1260,1370,550,100,'Slack  /  external notification destination',['Webhook stored in Kubernetes Secret · delivery tests'],[5],True)
edge('M1545 1200 L1545 1370',True)
text(1565,1357,'HTTPS webhook','small')
text(800,1403,'Solid card: Sprint 1 baseline', 'small')
text(800,1434,'Dashed card / flow: planned extension', 'small')
text(50,1503,'No EKS / ECR / AWS FIS required. KinD has fixed Docker nodes; S4 capacity simulation does not provision real machines.','small')
s.append('</svg>')
(OUT/'kind-architecture.svg').write_text('\n'.join(s))
print(OUT/'kind-architecture.svg')
