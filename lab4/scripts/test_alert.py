"""User-invoked channel setup test; this is not scheduled drift evidence."""
import json
import os

from cloudlayer.observability import secret_value
from monitoring.alerts import deliver
from src import config

if __name__ == "__main__":
    config.load()
    webhook = secret_value(os.environ["VAULT_URL"], os.environ["ALERT_SECRET_NAME"])
    result = deliver(webhook, "ITCS355 Lab 4: channel setup test succeeded. This is not a scheduled drift alert.")
    print(json.dumps(result, indent=2))
