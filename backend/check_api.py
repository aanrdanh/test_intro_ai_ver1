import json
import urllib.request

url = 'http://127.0.0.1:8000/api/path'
request_data = {
    'start_station': 'Schwedenplatz',
    'end_station': 'Museumsquartier'
}

req = urllib.request.Request(
    url,
    data=json.dumps(request_data).encode('utf-8'),
    headers={'Content-Type': 'application/json'},
    method='POST'
)

with urllib.request.urlopen(req) as resp:
    print('Status:', resp.status)
    print('Response:')
    print(resp.read().decode('utf-8'))
