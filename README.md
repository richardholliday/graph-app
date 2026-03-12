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

### AWS resources

| Resource | Name / ID |
|---|---|
| S3 bucket | `news-knowledge-graph` |
| CloudFront distribution | `E3TCZ7VBIYU9VB` |
| Lambda function | `graph-pipeline` |
| EventBridge rule | `graph-pipeline-hourly` |
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
├── requirements.txt    # Python dependencies
├── graph.json          # Latest graph data (generated)
├── version.json        # Build metadata (generated)
└── .github/
    └── workflows/
        └── deploy.yml  # S3 deploy on push to main
```
