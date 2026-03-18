"""
News → Knowledge Graph pipeline.

Fetches headlines from RSS feeds, sends them to Claude to extract entities
and relationships, then writes a graph.json file for the D3 visualiser.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python pipeline.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import boto3
import feedparser
from anthropic import Anthropic

S3_BUCKET       = os.environ.get("S3_BUCKET", "news-knowledge-graph")
S3_KEY          = "graph.json"
S3_LOGS_BUCKET  = "news-knowledge-graph-logs"
TRAFFIC_KEY     = "last-traffic.json"
IDLE_SKIP_HOURS = 3    # skip if no traffic within this window
MAX_STALE_HOURS = 8    # always refresh if graph is older than this

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

RSS_FEEDS = [
    "http://feeds.bbci.co.uk/news/world/rss.xml",
    "https://feeds.npr.org/1001/rss.xml",
    "https://www.theguardian.com/world/rss",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://rss.dw.com/rdf/rss-en-world",
    "https://www.france24.com/en/rss",
]

MAX_ARTICLES_PER_FEED = 4  # sample evenly across feeds

# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_articles(max_per_feed: int = MAX_ARTICLES_PER_FEED) -> list[dict]:
    articles: list[dict] = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            count = 0
            for entry in feed.entries:
                if count >= max_per_feed:
                    break
                title = entry.get("title", "").strip()
                summary = entry.get("summary", "").strip()
                if title:
                    articles.append({
                        "title": title,
                        "summary": summary,
                        "link": entry.get("link", ""),
                    })
                    count += 1
            print(f"  {feed_url}: {len(feed.entries)} entries, took {count}")
        except Exception as exc:
            print(f"  Warning: could not fetch {feed_url}: {exc}", file=sys.stderr)
    return articles


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert geopolitical analyst building a knowledge graph from today's news.

Extract entities and relationships that reveal meaningful connections, cause-and-effect chains,
and patterns across world events. Prioritise entities that appear across multiple articles —
these are the high-influence nodes.

Entity types (use exactly these strings):
  person | organisation | country | event | concept

Relationship types (use exactly these strings):
  causes | caused_by | involves | opposes | supports | allies_with | threatens |
  located_in | responds_to | impacts | negotiates_with | accuses | sanctions

Rules:
- Entity IDs must be lowercase and hyphen-separated (e.g. "united-nations", "xi-jinping")
- Every relationship source and target MUST reference an ID that exists in your entities list
- Aim for 15–30 entities and 20–40 relationships
- Prefer depth (chains of causation) over breadth

Respond with ONLY a JSON object in this exact format, no other text:
{
  "entities": [{"id": "...", "label": "...", "type": "...", "description": "..."}],
  "relationships": [{"source": "...", "target": "...", "type": "...", "description": "..."}]
}"""


def extract_graph(articles: list[dict]) -> dict:
    client = Anthropic()

    articles_text = "\n\n".join(
        f"ARTICLE {i + 1}: {a['title']}\n{a['summary']}"
        for i, a in enumerate(articles)
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"Extract a knowledge graph from these {len(articles)} news articles.\n\n"
                f"{articles_text}"
            ),
        }],
    )

    text = response.content[0].text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


# ---------------------------------------------------------------------------
# Build final graph (validate + clean)
# ---------------------------------------------------------------------------

def build_graph(extraction: dict) -> dict:
    node_ids = {e["id"] for e in extraction["entities"]}

    nodes = [
        {
            "id": e["id"],
            "label": e["label"],
            "type": e["type"],
            "description": e["description"],
        }
        for e in extraction["entities"]
    ]

    links = []
    skipped = 0
    for rel in extraction["relationships"]:
        if rel["source"] not in node_ids or rel["target"] not in node_ids:
            skipped += 1
            continue
        if rel["source"] == rel["target"]:
            continue
        links.append({
            "source": rel["source"],
            "target": rel["target"],
            "type": rel["type"],
            "description": rel["description"],
        })

    if skipped:
        print(f"  Skipped {skipped} relationships with unknown entity references")

    return {"nodes": nodes, "links": links}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Fetching news articles...")
    articles = fetch_articles()
    print(f"Fetched {len(articles)} articles\n")

    print("Extracting graph with Claude Sonnet 4.6...")
    extraction = extract_graph(articles)
    print(f"  Entities: {len(extraction['entities'])}")
    print(f"  Relationships: {len(extraction['relationships'])}\n")

    graph = build_graph(extraction)
    graph["generated_at"] = datetime.now(timezone.utc).isoformat()
    print(f"Graph: {len(graph['nodes'])} nodes, {len(graph['links'])} links")

    graph_json = json.dumps(graph, indent=2)

    # Write locally if not running in Lambda
    if not os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        with open("graph.json", "w") as f:
            f.write(graph_json)
        print("Saved → graph.json")

    # Always upload to S3
    s3 = boto3.client("s3")
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=S3_KEY,
        Body=graph_json,
        ContentType="application/json",
        CacheControl="no-cache, no-store, must-revalidate",
    )
    print(f"Uploaded → s3://{S3_BUCKET}/{S3_KEY}")


def should_skip_due_to_idle() -> bool:
    """Return True if there's been no traffic recently AND the graph is fresh enough."""
    now = datetime.now(timezone.utc)
    s3 = boto3.client('s3')

    # Check last traffic timestamp
    try:
        obj = s3.get_object(Bucket=S3_LOGS_BUCKET, Key=TRAFFIC_KEY)
        data = json.loads(obj['Body'].read())
        last_traffic = datetime.fromisoformat(data['last_traffic'].replace('Z', '+00:00'))
        hours_since_traffic = (now - last_traffic).total_seconds() / 3600
    except Exception:
        # No traffic file yet — don't skip
        return False

    if hours_since_traffic < IDLE_SKIP_HOURS:
        return False  # recent traffic, run normally

    # No recent traffic — check how stale the graph is
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=S3_KEY)
        graph = json.loads(obj['Body'].read())
        generated = datetime.fromisoformat(graph['generated_at'].replace('Z', '+00:00'))
        hours_since_update = (now - generated).total_seconds() / 3600
    except Exception:
        return False  # can't read graph, run to be safe

    if hours_since_update >= MAX_STALE_HOURS:
        print(f"No traffic for {hours_since_traffic:.1f}h but graph is {hours_since_update:.1f}h old — refreshing")
        return False

    print(f"No traffic for {hours_since_traffic:.1f}h, graph is {hours_since_update:.1f}h old — skipping")
    return True


def lambda_handler(event, context):
    # Quiet hours: midnight–6am EST (UTC-5) — skip to control costs
    utc_hour = datetime.now(timezone.utc).hour
    est_hour = (utc_hour - 5) % 24
    if 0 <= est_hour < 6:
        print(f"Quiet hours ({est_hour:02d}:xx EST) — skipping run")
        return {"statusCode": 200, "body": "Skipped (quiet hours)"}
    if should_skip_due_to_idle():
        return {"statusCode": 200, "body": "Skipped (idle — no recent traffic)"}

    try:
        main()
        return {"statusCode": 200, "body": "Graph updated"}
    except Exception as e:
        # Leave existing graph.json in S3 untouched — site keeps serving last good data
        print(f"Pipeline failed, preserving last good graph.json: {e}", file=sys.stderr)
        return {"statusCode": 500, "body": f"Pipeline failed: {e}"}


if __name__ == "__main__":
    main()
