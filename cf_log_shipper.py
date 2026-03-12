"""
cf_log_shipper.py
Triggered by S3 when CloudFront writes a new log file.
Parses the gzipped TSV and ships structured JSON events to CloudWatch Logs.
"""

import boto3
import gzip
import json
from datetime import datetime, timezone
from urllib.parse import unquote_plus

s3_client   = boto3.client('s3')
logs_client = boto3.client('logs')

LOG_GROUP = '/driftforge/cloudfront'

BOT_PATTERNS = [
    'bot', 'crawler', 'spider', 'checker', 'curl', 'python',
    'wget', 'scrapy', 'headless', 'phantomjs', 'selenium',
]

# CloudFront W3C extended log format — column positions
COL = {
    'date': 0, 'time': 1, 'edge': 2, 'bytes_sent': 3, 'client_ip': 4,
    'method': 5, 'host': 6, 'uri': 7, 'status': 8, 'referer': 9,
    'user_agent': 10, 'query': 11, 'cookie': 12, 'result_type': 13,
    'protocol': 16, 'bytes_recv': 17, 'time_taken': 18,
}


def is_bot(ua: str) -> bool:
    ua_lower = ua.lower()
    return any(p in ua_lower for p in BOT_PATTERNS)


def parse_line(line: str) -> dict | None:
    if line.startswith('#') or not line.strip():
        return None
    parts = line.strip().split('\t')
    if len(parts) <= max(COL.values()):
        return None
    try:
        ua = unquote_plus(parts[COL['user_agent']]) if parts[COL['user_agent']] != '-' else '-'
        return {
            'timestamp':   f"{parts[COL['date']]}T{parts[COL['time']]}Z",
            'edge':        parts[COL['edge']],
            'client_ip':   parts[COL['client_ip']],
            'method':      parts[COL['method']],
            'uri':         parts[COL['uri']],
            'status':      int(parts[COL['status']]),
            'result_type': parts[COL['result_type']],
            'time_taken':  float(parts[COL['time_taken']]) if parts[COL['time_taken']] != '-' else 0,
            'bytes_sent':  int(parts[COL['bytes_sent']]) if parts[COL['bytes_sent']] != '-' else 0,
            'user_agent':  ua,
            'is_bot':      is_bot(ua),
            'referer':     parts[COL['referer']] if parts[COL['referer']] != '-' else None,
        }
    except (IndexError, ValueError) as e:
        print(f"Skipping malformed line: {e}")
        return None


def ensure_log_group():
    try:
        logs_client.create_log_group(logGroupName=LOG_GROUP)
        logs_client.put_retention_policy(logGroupName=LOG_GROUP, retentionInDays=90)
        print(f"Created log group {LOG_GROUP}")
    except logs_client.exceptions.ResourceAlreadyExistsException:
        pass


def ship_events(log_stream: str, events: list[dict]):
    try:
        logs_client.create_log_stream(logGroupName=LOG_GROUP, logStreamName=log_stream)
    except logs_client.exceptions.ResourceAlreadyExistsException:
        pass

    # CloudWatch requires events sorted by timestamp
    events.sort(key=lambda e: e['timestamp'])

    cw_events = []
    for entry in events:
        ts_ms = int(
            datetime.strptime(entry['timestamp'], '%Y-%m-%dT%H:%M:%SZ')
            .replace(tzinfo=timezone.utc)
            .timestamp() * 1000
        )
        cw_events.append({'timestamp': ts_ms, 'message': json.dumps(entry)})

    # CloudWatch limit: 10,000 events or 1MB per batch
    for i in range(0, len(cw_events), 10_000):
        logs_client.put_log_events(
            logGroupName=LOG_GROUP,
            logStreamName=log_stream,
            logEvents=cw_events[i:i + 10_000],
        )

    human  = sum(1 for e in events if not e['is_bot'])
    bots   = len(events) - human
    print(f"Shipped {len(events)} events ({human} human, {bots} bot) → {log_stream}")


def lambda_handler(event, context):
    ensure_log_group()

    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key    = unquote_plus(record['s3']['object']['key'])

        print(f"Processing s3://{bucket}/{key}")

        obj     = s3_client.get_object(Bucket=bucket, Key=key)
        content = gzip.decompress(obj['Body'].read()).decode('utf-8')

        entries = [parse_line(l) for l in content.splitlines()]
        entries = [e for e in entries if e]

        if not entries:
            print("No valid entries found")
            continue

        log_stream = key.replace('/', '_').replace('.gz', '')
        ship_events(log_stream, entries)

    return {'statusCode': 200, 'body': 'Done'}
