import hashlib
import json
import urllib.request
import urllib.error

EMAIL = "nickgelinas@rocketmail.com"
PASSWORD = "GoKB1aNZ!!"
KEY_ID = "d7252c82-4b87-4191-a40c-5bbd8773d715"
API_KEY = "stmvWEG7CVwget6YXw3Qo65OmrSYHKDUJXlWOQ1eetsXhmNEb1DW4H5hDQpi"


def md5(s):
    return hashlib.md5(s.encode("ascii")).hexdigest()


h = md5(md5(md5(PASSWORD)))
print("password:", repr(PASSWORD))
print("len:", len(PASSWORD))
print("hash:", h, "expected already-seen: 0378e9a21e94da0448fc1a8bc8b7b759")

url = "https://auth-prod.api.wyze.com/api/user/login"
payload = json.dumps(
    {
        "email": EMAIL,
        "password": h,
        "phone_id": "0d3db228-ebc7-480c-925a-5ce47523d3aa",
        "verification_code": "",
    }
).encode("utf-8")

req = urllib.request.Request(
    url,
    data=payload,
    headers={
        "Content-Type": "application/json",
        "User-Agent": "wyze_ios_3.1.48",
        "keyid": KEY_ID,
        "apikey": API_KEY,
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