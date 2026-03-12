Pull the latest CloudFront access logs for driftforge.cloud from S3, decompress them, and give me a visitor summary.

Run this command to fetch and parse the logs:
```
aws s3 sync s3://news-knowledge-graph-logs/cf-logs/ /tmp/cf-logs/ --quiet && gunzip -f /tmp/cf-logs/*.gz 2>/dev/null
```

Then analyse all log entries (lines not starting with #) and report:

1. **Total requests** — human visits vs bot/crawler traffic (identify bots by user agent strings containing "bot", "crawler", "spider", "checker", "curl", "python", etc.)
2. **Unique visitor IPs** — human only
3. **Top pages requested** — which URIs were hit most
4. **CloudFront edge locations** — which regions visitors are coming from (decode the edge codes: YUL=Montreal, YYZ=Toronto, JFK/EWR=New York, ORD=Chicago, IAD=Washington, ATL=Atlanta, DFW=Dallas, LAX=Los Angeles, SFO=San Francisco, LHR=London, CDG=Paris, AMS=Amsterdam, FRA=Frankfurt, SIN=Singapore, NRT=Tokyo, SYD=Sydney)
5. **Devices** — break down Mac, iPhone/iPad, Android, Windows, other from user agent
6. **Cache performance** — Hit vs Miss ratio from the x-edge-result-type field (column 14)
7. **Any errors** — 4xx or 5xx status codes

Present as a clean summary with highlights. Call out anything interesting or unexpected.
