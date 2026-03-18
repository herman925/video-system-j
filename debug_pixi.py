import requests
import time

try:
    print('Requesting...')
    r = requests.get('http://127.0.0.1:8766/')
    print(r.status_code)
except Exception as e:
    print(e)
