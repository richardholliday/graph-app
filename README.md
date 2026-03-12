# News Knowledge Graph

A live 3D knowledge graph built from today's news. Entities (people, organisations, countries, events, concepts) and their relationships are extracted from RSS feeds by Claude and visualised as an interactive 3D force graph.

Live at: **https://driftforge.cloud**

---

## How it works

### Data pipeline

1. `pipeline.py` fetches headlines from BBC, NPR, and The Guardian RSS feeds
2. The articles are sent to Claude Opus (via the Anthropic API) which extracts entities and relationships as structured JSON
3. The result is written to `graph.json` and uploaded to S3

The pipeline runs automatically every hour via AWS Lambda + EventBridge. It can also be run locally:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python3 pipeline.py
```

### Frontend

`index.html` is a single-file app with no build step. It fetches `graph.json` on load and renders it using [3d-force-graph](https://github.com/vasturiano/3d-force-graph) (Three.js/WebGL).

Features:
- 3D force-directed graph with physics simulation
- Node size scales quadratically with connection count
- Labels positioned away from neighbouring nodes
- Entity type filters (person, organisation, country, event, concept)
- Sentiment link colouring (hostile / cooperative / neutral)
- Community detection via label propagation
- Search with zoom-to-match
- Side panel with node details and connections
- Auto-refresh every 5 minutes if new data is available
- Mobile-optimised with touch controls

---

## AWS architecture

```
EventBridge (hourly cron)
    └── Lambda (graph-pipeline)
            ├── Fetches RSS feeds
            ├── Calls Anthropic API
            └── Uploads graph.json → S3 (news-knowledge-graph)

S3 (news-knowledge-graph)
    ├── index.html        (static site)
    ├── graph.json        (data, TTL 1 hour in CloudFront)
    └── version.json      (build metadata, no-cache)

CloudFront (E3TCZ7VBIYU9VB)
    └── driftforge.cloud  (Route 53 → ACM certificate)
```

### Visitor analytics

CloudFront access logging is enabled. Logs are written as gzipped TSV files to the `news-knowledge-graph-logs` S3 bucket under `cf-logs/`. A second Lambda (`cf_log_shipper`) is triggered by S3 on each new log file and:

1. Parses the gzipped CloudFront W3C log format
2. Enriches each event with a `city` field decoded from the CloudFront edge location code
3. Classifies requests as bot or human based on user-agent strings
4. Ships structured JSON events to CloudWatch Logs (`/driftforge/cloudfront`), batched per log file into individual log streams
5. Checks each new human IP against a known-IP list stored at `s3://news-knowledge-graph-logs/known-ips.json`
6. Publishes an SNS alert for any IP not seen before (new visitor notification)

Logs are retained for 90 days in CloudWatch. The known-IP list is updated in S3 after each run.

```
S3 (news-knowledge-graph-logs)
    ├── cf-logs/          ← CloudFront access logs (gzipped TSV)
    └── known-ips.json    ← Seen human IPs (for new visitor alerts)

Lambda (cf_log_shipper)
    ├── Triggered by: S3 PutObject on cf-logs/
    ├── Writes to:    CloudWatch Logs /driftforge/cloudfront
    └── Alerts via:   SNS topic driftforge-alerts → email
```

### AWS resources

| Resource | Name / ID |
|---|---|
| S3 bucket (site) | `news-knowledge-graph` |
| S3 bucket (logs) | `news-knowledge-graph-logs` |
| CloudFront distribution | `E3TCZ7VBIYU9VB` |
| Lambda function (pipeline) | `graph-pipeline` |
| Lambda function (log shipper) | `cf_log_shipper` |
| EventBridge rule | `graph-pipeline-hourly` |
| CloudWatch log group | `/driftforge/cloudfront` |
| SNS topic | `driftforge-alerts` |
| IAM role (Lambda) | `graph-pipeline-lambda-role` |
| IAM user (deploy) | `graph-app-deploy` |
| Domain | `driftforge.cloud` (Route 53) |

---

## CI/CD

Pushing to `main` triggers the **Deploy to S3** GitHub Actions workflow which:
1. Generates `version.json` from the current git tag (`git describe --tags`)
2. Uploads `index.html` and `version.json` to S3
3. Invalidates the CloudFront cache for those files

Required GitHub secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`

---

## Local development

```bash
# Serve locally
python3 -m http.server 8080 --bind 0.0.0.0

# Open in browser
open http://localhost:8080
```

`graph.json` must exist locally (run `pipeline.py` first, or copy from S3).

---

## Project structure

```
graph-app/
├── index.html          # Single-file frontend
├── pipeline.py         # Data pipeline (RSS → Claude → S3)
├── cf_log_shipper.py   # Lambda: CloudFront logs → CloudWatch + SNS alerts
├── requirements.txt    # Python dependencies
├── graph.json          # Latest graph data (generated)
├── version.json        # Build metadata (generated)
└── .github/
    └── workflows/
        └── deploy.yml  # S3 deploy on push to main
```
