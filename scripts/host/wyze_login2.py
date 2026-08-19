import hashlib
import json
import urllib.request
import urllib.error

EMAIL = "nickyg6667@gmail.com"
PASSWORD = "GoKB1aNZ!!"
KEY_ID = "0d3db228-ebc7-480c-925a-5ce47523d3aa"
API_KEY = "XpGNqBUxNMTQko5Ewu6tn830iNOj4EyGaaVViO6um47PK8UxGBfq3LJMMQf1"


def md5(s):
    return hashlib.md5(s.encode("ascii")).hexdigest()


h = md5(md5(md5(PASSWORD)))

url = "https://auth-prod.api.wyze.com/api/user/login"
payload = json.dumps({"email": EMAIL, "password": h}).encode("utf-8")

req = urllib.request.Request(
    url,
    data=payload,
    headers={
        "Content-Type": "application/json",
        "User-Agent": "docker-wyze-bridge/1.0.0",
        "apikey": API_KEY,
        "keyid": KEY_ID,
    },
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.loads(r.read().decode("utf-8"))
        print("HTTP", r.status)
        print("headers:", dict(r.headers))
        print("body:", json.dumps(body, indent=2))
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8")
    print("HTTP ERROR", e.code)
    print("headers:", dict(e.headers))
    print("body:", body)