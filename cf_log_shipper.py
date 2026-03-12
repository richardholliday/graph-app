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
sns_client  = boto3.client('sns')

LOG_GROUP    = '/driftforge/cloudfront'
KNOWN_IPS_BUCKET = 'news-knowledge-graph-logs'
KNOWN_IPS_KEY    = 'known-ips.json'
SNS_TOPIC_ARN    = 'arn:aws:sns:us-east-1:597062269817:driftforge-alerts'

EDGE_CITIES = {
    # North America
    'ATL': 'Atlanta', 'BOS': 'Boston', 'CMH': 'Columbus', 'DEN': 'Denver',
    'DFW': 'Dallas', 'DTW': 'Detroit', 'EWR': 'Newark', 'HIO': 'Portland',
    'IAD': 'Washington DC', 'IAH': 'Houston', 'JFK': 'New York', 'LAX': 'Los Angeles',
    'LAS': 'Las Vegas', 'MCI': 'Kansas City', 'MIA': 'Miami', 'MSP': 'Minneapolis',
    'MSY': 'New Orleans', 'ORD': 'Chicago', 'PDX': 'Portland', 'PHX': 'Phoenix',
    'SDF': 'Louisville', 'SEA': 'Seattle', 'SFO': 'San Francisco', 'SJC': 'San Jose',
    'SLC': 'Salt Lake City', 'STL': 'St. Louis', 'YTO': 'Toronto', 'YUL': 'Montreal',
    'YVR': 'Vancouver', 'YYC': 'Calgary', 'YYZ': 'Toronto',
    # Europe
    'AMS': 'Amsterdam', 'ARN': 'Stockholm', 'ATH': 'Athens', 'BCN': 'Barcelona',
    'BEG': 'Belgrade', 'BER': 'Berlin', 'BRU': 'Brussels', 'BUD': 'Budapest',
    'CPH': 'Copenhagen', 'DUB': 'Dublin', 'DUS': 'Düsseldorf', 'EDI': 'Edinburgh',
    'FCO': 'Rome', 'FRA': 'Frankfurt', 'GVA': 'Geneva', 'HAM': 'Hamburg',
    'HEL': 'Helsinki', 'IST': 'Istanbul', 'LHR': 'London', 'LIS': 'Lisbon',
    'MAD': 'Madrid', 'MAN': 'Manchester', 'MRS': 'Marseille', 'MXP': 'Milan',
    'OSL': 'Oslo', 'OTP': 'Bucharest', 'PRG': 'Prague', 'SOF': 'Sofia',
    'TXL': 'Berlin', 'VIE': 'Vienna', 'WAW': 'Warsaw', 'ZAG': 'Zagreb',
    'ZRH': 'Zurich', 'CDG': 'Paris',
    # Asia Pacific
    'BKK': 'Bangkok', 'BLR': 'Bangalore', 'BOM': 'Mumbai', 'CCU': 'Kolkata',
    'CGK': 'Jakarta', 'CMB': 'Colombo', 'DEL': 'Delhi', 'HAN': 'Hanoi',
    'HKG': 'Hong Kong', 'HYD': 'Hyderabad', 'ICN': 'Seoul', 'KIX': 'Osaka',
    'KUL': 'Kuala Lumpur', 'MAA': 'Chennai', 'MNL': 'Manila', 'NRT': 'Tokyo',
    'PER': 'Perth', 'PNQ': 'Pune', 'SEL': 'Seoul', 'SGN': 'Ho Chi Minh City',
    'SIN': 'Singapore', 'SYD': 'Sydney', 'TPE': 'Taipei', 'MEL': 'Melbourne',
    'AKL': 'Auckland',
    # Middle East & Africa
    'BAH': 'Bahrain', 'CAI': 'Cairo', 'CPT': 'Cape Town', 'DME': 'Moscow',
    'DXB': 'Dubai', 'JNB': 'Johannesburg', 'LOS': 'Lagos', 'TLV': 'Tel Aviv',
    # South America
    'BOG': 'Bogotá', 'EZE': 'Buenos Aires', 'GRU': 'São Paulo',
    'LIM': 'Lima', 'SCL': 'Santiago',
}


def edge_to_city(edge: str) -> str:
    code = edge[:3].upper()
    return EDGE_CITIES.get(code, code)


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
            'city':        edge_to_city(parts[COL['edge']]),
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


def load_known_ips() -> set:
    try:
        obj = s3_client.get_object(Bucket=KNOWN_IPS_BUCKET, Key=KNOWN_IPS_KEY)
        return set(json.loads(obj['Body'].read()))
    except s3_client.exceptions.NoSuchKey:
        return set()


def save_known_ips(ips: set):
    s3_client.put_object(
        Bucket=KNOWN_IPS_BUCKET,
        Key=KNOWN_IPS_KEY,
        Body=json.dumps(sorted(ips)),
        ContentType='application/json',
    )


def alert_new_ip(ip: str, city: str, ua: str):
    sns_client.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject=f'New visitor — driftforge.cloud',
        Message=f'New IP address seen on driftforge.cloud\n\nIP:       {ip}\nLocation: {city}\nDevice:   {ua[:120]}',
    )
    print(f"Alert sent for new IP: {ip} ({city})")


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
    known_ips = load_known_ips()
    new_ips_found = False

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

        # Check for new human IPs
        for entry in entries:
            if entry['is_bot']:
                continue
            ip = entry['client_ip']
            if ip not in known_ips:
                known_ips.add(ip)
                new_ips_found = True
                alert_new_ip(ip, entry['city'], entry['user_agent'])

        log_stream = key.replace('/', '_').replace('.gz', '')
        ship_events(log_stream, entries)

    if new_ips_found:
        save_known_ips(known_ips)

    return {'statusCode': 200, 'body': 'Done'}
