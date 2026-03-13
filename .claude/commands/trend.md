Query CloudWatch Logs to show unique human visitors per day for driftforge.cloud.

Run the following:

```bash
QUERY_ID=$(aws logs start-query \
  --log-group-name '/driftforge/cloudfront' \
  --start-time $(date -v-30d +%s) \
  --end-time $(date +%s) \
  --query-string '
fields @timestamp, client_ip, is_bot, city, uri
| filter is_bot = 0 and city not in ["Toronto", "Chicago"] and uri = "/graph.json"
| stats count_distinct(client_ip) as visitors by datefloor(@timestamp, 1d) as day
| sort day asc
' --output text)

sleep 6

aws logs get-query-results --query-id $QUERY_ID --output json
```

Parse the JSON results and present a clean day-by-day table:

- Date (formatted as e.g. "Thu 12 Mar")
- Unique human visitors (IPs that loaded /graph.json — i.e. fully loaded the app)
- A simple ASCII bar chart scaled to the max day

Exclude Toronto and Chicago (that's the developer and a known friend).

Note the total, the peak day, and any obvious trend (growing, flat, fading).
