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
item = 5
child_item = 6
expiration_delta = { "days": 2 }


oidc = OpenIDConnect(app)
db = SQLAlchemy(app)
# SQLAlchemy might throw an exception on a dropped idle collection, unhandled
# by flask even if sqlalchemy automatically reconnects. Send a ping to trigger
# reconnect before doing anything.
db.engine.pool._pre_ping = True # TODO look at SQLALCHEMY_POOL_RECYCLE as an alternative


# Get the current lottery, in a silly way
# TODO actually support multiple lotteries
def get_lottery():
    return get_or_create(Lottery,
                         registration_start = datetime(2019,1,1,12,0),
                         registration_end = datetime(2019,2,1,12,0),
                         lottery_start = datetime(2019,1,1,12,0),
                         lottery_end = datetime(2019,2,1,12,0),
                         transfer_start = datetime(2019,1,1,12,0),
                         transfer_end = datetime(2019,2,1,12,0),
                         fcfs_voucher = "fcfs",
                         child_voucher = "child",
                         child_item = "item_{}=1".format(child_item),
                         ticket_item = "item_{}=1".format(item),
                         pretix_event_url = "https://pretix.theborderland.se/borderland/{}/".format(event))

# Assign vouchers as long as we can
def do_lottery():
    lottery = get_lottery()
    if lottery.lotteryRunning():
        while True:
            borderling = lottery.get_random_borderling()
            app.logger.info("Cron: drew {}".format(borderling))
            if borderling:
                if not borderling.isChild():
                    if not pretix_get_vouchers(borderling):
                        break
            else:
                break
    else:
        app.logger.info("Cron: Lottery not running")

def db_test_data():
    lottery = get_lottery()
    db.session.commit()
    personal_qs = Questionset(lottery_id = lottery.id, priority=10, name="Personal questions",description='''To make the lottery fair we need to check your ID when you arrive at the port. Please fill out the following like it appears on an official document.

    This information is deleted after the event, but we might summarise ages for demographic purposes.
    ''')

    demographic_qs = Questionset(lottery_id = lottery.id, priority=30, name="Demographic questions",
                                 description="Questions just so we know a bit about how's coming. Anonymised etc")
    volunteer_qs = Questionset(lottery_id = lottery.id, priority=20, name="Voluteer questions",
                               description='''
The Borderland is built on co-creation and a community that takes care of each other.

Would you like to be contacted by someone about signing up for one of these civic responsibility roles?
''')
    db.session.add(personal_qs)
    db.session.add(volunteer_qs)
    db.session.add(demographic_qs)
    db.session.commit()
    q1 = Question(set_id = personal_qs.id, text="Your name as it appears on official documents", type = "text")
    q2 = Question(set_id = personal_qs.id, text="Your date of birth", type = "date", tag="DOB")
    db.session.add(q1)
    db.session.add(q2)

    db.session.add(Question(set_id = volunteer_qs.id,
                            type = "multiple",
                            text = '''If you'd like to be part of one of the civic responsibility teams, please let us know by ticking off your preferred area(s) in the options below. Note that this is not binding, and that you only agree to be contacted with the option to participate.

You do not need prior experience, and if this is your first Borderland, you are highly encouraged to participate!
                           ''',
                            options = [
                                QuestionOption(text = "Clown Police"),
                                QuestionOption(text = "Sanctuary (first aid and psychological well being)"),
                                QuestionOption(text = "Electrical Power"),
                                QuestionOption(text = "Drinking Water and Greywater"),
                                QuestionOption(text = "Swimming Safety"),
                                QuestionOption(text = "Communal Spaces"),
                                QuestionOption(text = "Communications")
                            ]))
    db.session.add(Question(set_id = volunteer_qs.id,
                            type = "multiple",
                            text = '''
Please let us know if you have any special skills or relevant experience and would like to help out within one (or more) of the following areas:
                            ''',
                            options = [
                                QuestionOption(text = "First aid or other medical experience"),
                                QuestionOption(text = "Psychological Welfare"),
                                QuestionOption(text = "Conflict Resolution"),
                                QuestionOption(text = "Power or other Infrastructure"),
                                QuestionOption(text = "Safety and Risk Assessment"),
                                QuestionOption(text = "Bureaucracy related to this kind of event")
                            ]))

    db.session.add(Question(set_id = demographic_qs.id,
                            type = "datalist",
                            text = "Where in the world are you from?",
                            options = [ QuestionOption(text = c['Name'])
                                        for c in json.load(open("./countries.json")) ]))
    db.session.add(Question(set_id = demographic_qs.id,
                            type = "number",
                            text = "How many Burn-like events have you been to before (The Borderland, Burning Man, Nowhere, Burning Møn, ...)?"))
    db.session.add(Question(set_id = demographic_qs.id,
                            type = "number",
                            text = "Of those, how many times have you attended The Borderland?"))
    db.session.commit()

#db.drop_all()
db.create_all()

# Yay circular imports!
from views import *
from models import *


if not Lottery.query.first():
    print("Creating test data")
    db_test_data()

if __name__ == '__main__':
    app.run(debug = True)
