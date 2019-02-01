from flask import Flask, jsonify, request, send_file, g
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_oidc import OpenIDConnect
import os
import json
import logging
from logging.config import dictConfig
from flask.logging import default_handler
import sentry_sdk
from sentry_sdk import capture_exception

os.getenv("SENTRY_URL") and sentry_sdk.init(os.getenv("SENTRY_URL"))

app = Flask(__name__)

# Set up logging
logging.getLogger().addHandler(default_handler)
dictConfig({
    'version': 1,
    'formatters': {'default': {
        'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
    }},
    'handlers': {'wsgi': {
        'class': 'logging.StreamHandler',
        'stream': 'ext://flask.logging.wsgi_errors_stream',
        'formatter': 'default'
    }},
    'root': {
        'level': 'INFO',
        'handlers': ['wsgi']
    }
})

# OID secrets written just to be read again by OIDC_CLIENT_SECRETS below,
# there's probably a better way to get this into flask_oidc
with open("/tmp/client_secrets.json", "w") as f:
    json.dump({
        'web': {'auth_uri': 'https://account.theborderland.se/auth/realms/master/protocol/openid-connect/auth',
                'client_id': os.getenv("OID_ID") or 'memberships-backend',
                'client_secret': os.getenv("OID_SECRET"),
                'issuer': 'https://account.theborderland.se/auth/realms/master',
                'redirect_uris': ['https://account.theborderland.se/*'],
                'token_introspection_uri': 'https://account.theborderland.se/auth/realms/master/protocol/openid-connect/token/introspect',
                'token_uri': 'https://account.theborderland.se/auth/realms/master/protocol/openid-connect/token',
                'userinfo_uri': 'https://account.theborderland.se/auth/realms/master/protocol/openid-connect/userinfo'}
    }, f)

# Flask config
app.config.update({
    'SQLALCHEMY_DATABASE_URI': os.getenv("LOTTO_DB"), #or 'sqlite:///test.db'
    'SQLALCHEMY_TRACK_MODIFICATIONS': False,
    'OIDC_RESOURCE_SERVER_ONLY': True,
    'OIDC_CLIENT_SECRETS': '/tmp/client_secrets.json',
    'OIDC_ID_TOKEN_COOKIE_SECURE': False,
    'OIDC_REQUIRE_VERIFIED_EMAIL': False,
    'OIDC_USER_INFO_ENABLED': True,
    'OIDC_OPENID_REALM': 'memberships-backend',
    'OIDC_SCOPES': ['openid', 'email'],
    'OIDC_INTROSPECTION_AUTH_METHOD': 'client_secret_post'
})

# Magic value land! TODO make a config store. Some of this belongs in the
# Lottery class
host = "pretix.theborderland.se"
org = "borderland"
event = "test3"
expiration_delta = { "days": 2 }
item = 5
child_item = 6


oidc = OpenIDConnect(app)
db = SQLAlchemy(app)
# SQLAlchemy might throw an exception on a dropped idle collection, unhandled
# by flask even if sqlalchemy automatically reconnects. Send a ping to trigger
# reconnect before doing anything.
db.engine.pool._pre_ping = True # TODO look at SQLALCHEMY_POOL_RECYCLE as an alternative


# Get the current lottery, in a silly way
# TODO actually support multiple lotteries
def get_lottery():
    return Lottery.query.first()

# Assign vouchers as long as we can
def do_lottery():
    lottery = get_lottery()
    if lottery.lotteryRunning():
        while True:
            borderling = lottery.get_random_borderling()
            app.logger.info("Cron: drew {}".format(borderling))
            if borderling:
                if not borderling.isChild():
                    if not pretix.get_vouchers(borderling):
                        break
            else:
                break
    else:
        app.logger.info("Cron: Lottery not running")

# Yay circular imports!
from views import *
from models import *
import pretix

if __name__ == '__main__':
    if not Lottery.query.first():
        print("Creating test data")
        from test_data import db_test_data
        db_test_data()


    app.run(debug = True)
