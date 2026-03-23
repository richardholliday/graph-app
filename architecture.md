# Architecture

```mermaid
flowchart TD
    subgraph Sources
        RSS[RSS Feeds\nBBC · NPR · Guardian\nAl Jazeera · DW · France24]
        Claude[Claude Sonnet 4.6\nAPI]
    end

    subgraph Pipeline ["Lambda: graph-pipeline"]
        PL[pipeline.py\nFetch → Extract → Build]
    end

    subgraph Schedule ["EventBridge"]
        E1[Every 90 min\nwhen traffic detected]
        E2[Daily 6am EST\nforced run]
    end

    subgraph Storage ["S3"]
        S3Main[news-knowledge-graph\ngraph.json · index.html · assets]
        S3Logs[news-knowledge-graph-logs\nlast-traffic.json · known-ips.json\nCloudFront raw logs]
    end

    subgraph Delivery ["CloudFront CDN"]
        CF[driftforge.cloud\nEdge cache]
    end

    subgraph LogPipeline ["Lambda: cf-log-shipper"]
        LS[cf_log_shipper.py\nParse · Filter bots · Ship]
    end

    subgraph Observability ["Observability"]
        CW[CloudWatch Logs\n/driftforge/cloudfront]
        CWA[CloudWatch Alarm\nLambda errors]
    end

    subgraph Alerts ["SNS Topics"]
        SNS1[graph-pipeline-alerts\nrh@richardholliday.com]
        SNS2[driftforge-alerts\nNew visitor emails]
    end

    Browser((Browser))

    E1 -->|invoke| PL
    E2 -->|invoke| PL
    PL -->|fetch headlines| RSS
    PL -->|extract entities & relationships| Claude
    PL -->|write graph.json| S3Main
    PL -->|on failure| SNS1
    CWA -->|on Lambda error| SNS1

    S3Main -->|serve static files| CF
    CF -->|write access logs| S3Logs
    S3Logs -->|S3 trigger| LS
    LS -->|structured JSON events| CW
    LS -->|new human IP| SNS2
    LS -->|update last-traffic.json| S3Logs

    S3Logs -->|last-traffic.json| PL
    CF -->|requests| Browser
    Browser -->|beacon /t/...| CF
```
