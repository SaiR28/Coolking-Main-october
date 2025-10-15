import requests
import json

url = "https://coolkingengineering.in/api/data"

headers = {
    "Content-Type": "application/json",
    "X-API-Key": "Cool2814"   # must match Flask exactly
}

data = {
    "esp32_mac": "28:9F:BD:BB:40:24:BC:6",
    "readings": [
        {"sensor_id": "28:9F:BD:BB:40:24:BC:6", "temperature": 25.5}
    ]
}

response = requests.post(url, headers=headers, json=data)
print(response.status_code)
print(response.json())
