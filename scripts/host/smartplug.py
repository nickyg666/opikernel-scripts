import hashlib
import json
import argparse
import sys

import requests
from wyze_sdk import Client

EMAIL = "nickgelinas@rocketmail.com"
PASSWORD = "GoKB1aNZ!!"
KEY_ID = "d7252c82-4b87-4191-a40c-5bbd8773d715"
API_KEY = "stmvWEG7CVwget6YXw3Qo65OmrSYHKDUJXlWOQ1eetsXhmNEb1DW4H5hDQpi"

AUTH_API = "https://auth-prod.api.wyze.com/api/user/login"
DEVICE_API = "https://api.wyzecam.com/app/v2/home_page/get_object_list"


def md5(s):
    return hashlib.md5(s.encode("ascii")).hexdigest()


def login():
    """Login via raw request; return (access_token, refresh_token, user_id)."""
    phone_id = "0d3db228-ebc7-480c-925a-5ce47523d3aa"
    h = md5(md5(md5(PASSWORD)))
    payload = json.dumps(
        {"email": EMAIL, "password": h, "phone_id": phone_id, "verification_code": ""}
    ).encode("utf-8")
    req = requests.post(
        AUTH_API,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "wyze_ios_3.1.48",
            "keyid": KEY_ID,
            "apikey": API_KEY,
        },
        timeout=30,
    )
    req.raise_for_status()
    body = req.json()
    return body["access_token"], body["refresh_token"], body["user_id"]


def list_devices(token):
    """List all devices on the account."""
    client = Client(token=token)
    return client.devices_list()


def toggle(client, mac, product_model, state):
    if state is True:
        resp = client.plugs.turn_on(device_mac=mac, device_model=product_model)
    else:
        resp = client.plugs.turn_off(device_mac=mac, device_model=product_model)
    return resp


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list all devices")
    on = sub.add_parser("on", help="turn plug on")
    on.add_argument("mac")
    on.add_argument("--model", required=True)
    off = sub.add_parser("off", help="turn plug off")
    off.add_argument("mac")
    off.add_argument("--model", required=True)
    args = ap.parse_args()

    token, _refresh, user_id = login()
    print(f"login ok, user_id={user_id}")
    client = Client(token=token)

    if args.cmd == "list":
        for d in client.devices_list():
            online = getattr(d, "is_online", "?")
            try:
                model = d.product.model
            except Exception:
                model = "?"
            print(f"{d.mac}  model={model}  online={online}  name={d.nickname}")
    elif args.cmd in ("on", "off"):
        state = args.cmd == "on"
        resp = toggle(client, args.mac, args.model, state)
        print(f"toggle {args.cmd}: {resp}")


if __name__ == "__main__":
    main()