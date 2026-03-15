Query CloudWatch Logs to show About modal and button click engagement for driftforge.cloud.

Run the following two queries (start both, then fetch results):

```bash
# About opens
Q1=$(aws logs start-query \
  --log-group-name '/driftforge/cloudfront' \
  --start-time $(date -v-30d +%s) \
  --end-time $(date +%s) \
  --query-string '
fields @timestamp, client_ip, city, uri
| filter uri in ["/t/about-open", "/t/about-linkedin", "/t/about-github"]
| stats count() as clicks by uri, datefloor(@timestamp, 1d) as day
| sort day asc
' --output text)

sleep 6

aws logs get-query-results --query-id $Q1 --output json
```

Parse and present:
- Total clicks per button (about-open, about-linkedin, about-github)
- Day-by-day breakdown
- Which cities are engaging

Note the conversion rate: about-open → linkedin clicks, about-open → github clicks.
