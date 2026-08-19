#!/bin/python3
import os
from wyze_sdk import Client
from wyze_sdk.errors import WyzeApiError

# Authenticate dynamically using credentials + API keys
try:
    response = Client().login(
        email=os.environ['WYZE_EMAIL'],
        password=os.environ['WYZE_PASSWORD'],
        key_id=os.environ['WYZE_KEY_ID'],
        api_key=os.environ['WYZE_API_KEY']
    )
    
    # Extract the short-lived access token from the login response
    access_token = response['access_token']
    client = Client(token=access_token)

    # Control the plug
    plug = client.plugs.info(device_mac='D03F271583AE')
    client.plugs.turn_off(device_model=plug.product.model, device_mac=plug.mac)
    print("Plug turned off successfully.")

except WyzeApiError as e:
    print(f"Wyze API Error: {e}")
