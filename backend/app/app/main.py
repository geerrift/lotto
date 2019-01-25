from flask import Flask, jsonify, request, send_file, g
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.expression import func
from flask_oidc import OpenIDConnect
import requests
import os
import json
import logging
from logging.config import dictConfig
from flask.logging import default_handler
import sentry_sdk
from sentry_sdk import capture_exception

os.getenv("SENTRY_URL") and sentry_sdk.init(os.getenv("SENTRY_URL"))

import lottomail

# TODO actually support multiple lotteries

app = Flask(__name__)
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

# TODO config
pretix_token = os.getenv("PRETIX_TOKEN")
host = "pretix.theborderland.se"
org = "borderland"
event = "test"
item = 1
expiration_delta = { "days": 2 }

oidc = OpenIDConnect(app)
db = SQLAlchemy(app)
db.engine.pool._pre_ping = True # SQLALCHEMY_POOL_RECYCLE


class Lottery(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    questionsets = db.relationship('Questionset', backref='Lottery', lazy = True)
    borderlings = db.relationship('Borderling', backref='Lottery', lazy = True)
    registration_start = db.Column(db.DateTime)
    registration_end = db.Column(db.DateTime)
    lottery_start = db.Column(db.DateTime)
    lottery_end = db.Column(db.DateTime)
    transfer_start = db.Column(db.DateTime)
    transfer_end = db.Column(db.DateTime)
    fcfs_voucher = db.Column(db.String(500))
    child_voucher = db.Column(db.String(500))

    def __repr__(self):
        return '<Lottery %r>' % self.id

    def transferAllowed(self):
        return self.transfer_start < datetime.now() and self.transfer_end > datetime.now()

    def lotteryRunning(self):
        return self.lottery_start < datetime.now() and self.lottery_end > datetime.now()

    def registrationAllowed(self):
        return True # TODO FIXME testing
        return (self.registration_start < datetime.now() and
                self.registration_end > datetime.now()) and not self.lotteryRunning()

    def isFCFS(self):
        return self.lottery_end < datetime.now()

    def get_random_borderling(self):
        return Borderling.query.filter(Borderling.lottery_id == self.id,
                                       ~Borderling.vouchers.any() ).order_by(
                                           func.random()).first()

    def to_dict(self):
        return { "can_register": self.registrationAllowed(),
                 "can_transfer": self.transferAllowed(),
                 "questions": [ qs.id for qs in self.questionsets ]}

class Borderling(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lottery_id = db.Column(db.Integer, db.ForeignKey("lottery.id"))
    email = db.Column(db.String(120), unique=True, nullable=False)
    ticket = db.Column(db.String(120), unique=True)
    vouchers = db.relationship('Voucher', backref='Borderling', lazy = True)
    answers = db.relationship('Answer', backref='Borderling', lazy = True)
    admin = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return '<Borderling %r>' % self.email

    def isChild(self):
        q = Question.query.filter(Question.tag == "DOB").first()
        if not q:
            return False
        a = Answer.query.filter(Answer.borderling_id == self.id,
                                Answer.question.any(Question.id == q.id)).first()
        try:
            dob = datetime.strptime(a.text, "%Y-%m-%d") # TODO
        except:
            return False
        return dob > datetime.now()-timedelta(days = 13*365)

    def getVouchers(self):
        lottery_ = get_lottery() # TODO
        if self.isChild() and (lottery_.lotteryRunning() or lottery_.isFCFS()):
            return [ lottery_.child_voucher ]
        elif lottery_.isFCFS():
            return [ lottery_.fcfs_voucher ]
        else:
            return [ v.to_dict() for v in self.vouchers ]

    def isRegistered(self, lottery):
        return self in lottery.borderlings

    def to_dict(self, lottery):
        tickets = Voucher.query.filter(Voucher.borderling_id == self.id,
                                       Voucher.order == "").first()
        return { "registered": self.isRegistered(lottery),
                 "tickets": tickets and tickets.ticket_dict(),
                 "vouchers": self.getVouchers() }

class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(5000), unique=False, nullable=True)
    borderling_id = db.Column(db.Integer, db.ForeignKey("borderling.id"))
    question = db.relationship('Question', backref='Answer', lazy = True)
    selections = db.Column(db.String(5000), unique=False, nullable=True)

    def __repr__(self):
        return '<Answer: %r>' % self.text

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    set_id = db.Column(db.Integer, db.ForeignKey("questionset.id"))
    text = db.Column(db.String(5000), unique=False, nullable=True)
    type = db.Column(db.String(100), unique=False, nullable=True)
    answer_id = db.Column(db.Integer, db.ForeignKey("answer.id"))
    options = db.relationship('QuestionOption', backref='Question', lazy = True)
    tag = db.Column(db.String(100), unique=False, nullable=True)

    def __repr__(self):
        return '<Question: %r>' % self.text

    def get_selections(self, borderling):
        a = Answer.query.filter(Answer.borderling_id == borderling.id,
                                Answer.id == self.answer_id).first()
        if a and a.selections:
            return list(map(int, a.selections.split(",")))
        else:
            return []


    def get_answer(self, borderling):
        a = Answer.query.filter(Answer.borderling_id == borderling.id,
                                Answer.id == self.answer_id).first()
        if a:
            return a.text
        else:
            return ""

    def answer(self, u, v):
        prev = db.session.query(Answer).filter(Answer.id == self.answer_id, Answer.borderling_id == u.id).first()
        if type(v) != list:
            if prev:
                app.logger.info("User {}: Replacing {:s} with {:s}".format(u.id, prev.text, v))
                prev.text = v
            else:
                db.session.add(Answer(question = [self], borderling_id = u.id, text = v))
        else:
            v = ",".join(v)
            prev = db.session.query(Answer).filter(Answer.id == self.answer_id, Answer.borderling_id == u.id).first()
            if prev:
                app.logger.info("User {}: Replacing {:s} with {:s}".format(u.id, prev.text, v))
                prev.selections = v
            else:
                db.session.add(Answer(question = [self], borderling_id = u.id, selections = v))
        db.session.commit()

    def to_dict(self, borderling=None):
        return { "id": self.id,
                 "question": self.text,
                 "options": [ o.to_dict() for o in self.options ],
                 "answer": (borderling and
                   self.get_answer(borderling))
                 or "",
                 "type": self.type,
                 "selections": (borderling and self.get_selections(borderling)) or []}

class QuestionOption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id"))
    priority = db.Column(db.Integer)
    text = db.Column(db.String(1000), unique=False)

    def to_dict(self):
        return { "id": self.id,
                 "text" : self.text }

class Questionset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lottery_id = db.Column(db.Integer, db.ForeignKey("lottery.id"))
    priority = db.Column(db.Integer)
    name = db.Column(db.String(5000), unique=False, nullable=True)
    description = db.Column(db.String(5000), unique=False, nullable=True)
    questions = db.relationship('Question', backref = "Questionset", lazy = True)

    def __repl__(self):
        return '<Questionset: %r>' % self.name

    def to_dict(self, borderling=None):
        return { "id": self.id, "name": self.name,
                 "description": self.description,
                 "priority": self.priority,
                 "questions": [ q.to_dict(borderling) for q in self.questions ] }

class Voucher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(1000), unique=True, nullable=False)
    expires = db.Column(db.DateTime, unique=False, nullable=True)
    borderling_id = db.Column(db.Integer, db.ForeignKey("borderling.id"))
    gifted_to = db.Column(db.Integer)
    order = db.Column(db.String(1000), unique=True, nullable=True)

    def __repr__(self):
        return '<Voucher: %r>' % self.code

    def ticket_dict(self):
        # TODO pdf_url
        return { "order": self.order }

    def to_dict(self):
        return { "code": self.code, "expires": self.expires }

    def isTicket(self):
        if self.order:
            return True
        return False

    def transfer(self, origin, target):
        # not checking if transfers are allowed here because it's used by
        # gifting and webhooks
        if orgin.id != self.borderling_id:
            return False
        self.borderling_id = target.id
        self.gifted_to = None
        db.session.commit()
        return True

    def gift_to(self, origin, target):
        if orgin.id != self.borderling_id and not self.order:
            app.logger.warn("gift_to: {} tried to gift ticket to {}, but voucher is either not paid for, or is not owned by source".format(origin, target))
            return False
        if Voucher.query.filter(Voucher.borderling_id == target.id, Voucher.order.any()):
            app.logger.warn("gift_to: {} tried to gift ticket to {} who already has one".format(origin, target))
            # TODO return errors
            return False
        self.gifted_to = target.id
        db.session.commit()
        return True



def get_or_create(model, **kwargs):
    try:
        return db.session.query(model).filter_by(**kwargs).one()
    except NoResultFound:
        created = model(**kwargs)
        #try: TODO
        db.session.add(created)
        db.session.commit()
        return created
        #except IntegrityError:
        #    db.session.rollback()
        #    return db.session.query(model).filter_by(**kwargs).one()

@app.route('/api/registration', methods=['GET', 'POST'])
@oidc.accept_token(require_token=True)
def registration():
    u = get_or_create(Borderling, email=g.oidc_token_info['email'])
    lottery = get_lottery()
    if request.method == 'POST':
        if lottery.registrationAllowed():
            lottery.borderlings.append(u)
            db.session.commit()
            lottomail.registration_complete(u.email)
    return jsonify(u.to_dict(lottery))

@app.route('/api/lottery')
@oidc.accept_token(require_token=True)
def lottery():
    return jsonify(get_lottery().to_dict())

@app.route('/api/questions/<int:qs>',
           methods=['GET', 'POST'])
@oidc.accept_token(require_token=True)
def questionset(qs):
    u = get_or_create(Borderling, email=g.oidc_token_info['email'])
    if request.method == 'POST':
        for k,v in request.get_json().items():
            q = Question.query.filter_by(id=int(k)).first()
            q.answer(u, v)
    return jsonify(Questionset.query.filter_by(id=qs).first().to_dict(u))

@app.route('/api/transfer', methods=['POST'])
@oidc.accept_token(require_token=True)
def transfer_voucher():
    if get_lottery().transferAllowed():
        u = get_or_create(Borderling, email=g.oidc_token_info['email'])
        r = request.get_json()
        voucher = Voucher.query.filter(Voucher.code == r.voucher).first()
        dest = Borderling.query.filter(Borderling.email == r.email).first()
        if voucher and to:
            result = voucher.transfer(u, dest)
            if result:
                lottomail.voucher_transfer(dest, u, voucher.expires)
            return jsonify({"result": result})
    return jsonify({"result": False})

@app.route('/api/gift', methods=['POST'])
@oidc.accept_token(require_token=True)
def gift_voucher():
    u = get_or_create(Borderling, email=g.oidc_token_info['email'])
    r = request.get_json()
    voucher = Voucher.query.filter(Voucher.code == r.voucher).first()
    dest = Borderling.query.filter(Borderling.email == r.email).first()
    if voucher and to:
        return jsonify({"result": voucher.gift_to(u, dest)})
    return jsonify({"result": False})

@app.route('/')
def route_root():
    index_path = os.path.join(app.static_folder, 'index.html')
    return send_file(index_path)

# Internal stuff
@app.route('/_/cron')
def periodic():
    do_lottery()
    return "k"

@app.route('/_/webhooks/pretix')
def pretix_webhook():
    d = request.get_json()
    if d.action == "pretix.event.order.paid":
        #{"notification_id": 117, "organizer": "borderland", "event": "test", "code": "Z9M9V", "action": "pretix.event.order.paid"}
        orderposition = pretix_order_info(d.code).positions[0] # TODO
        pretix_voucher = pretix_voucher_info(orderposition.voucher)
        voucher = Voucher.query.filter(Voucher.code == pretix_voucher.code)
        borderling = Borderling.query.filter(Borderling.id == voucher.borderling_id).first()
        # TODO update download link
        if not voucher.order:
            voucher.order = d.code # update order info
            if voucher.gifted_to:
                sender = Borderling.query.filter(Borderling.id == voucher.borderling_id).first()
                recipient = Borderling.query.filter(Borderling.id == voucher.gifted_to).first()
                if Voucher.query.filter(Voucher.borderling_id == target.id, ~Voucher.order.any()):
                    voucher.transfer(sender, recipient)
                    lottomail.gifted_ticket(recipient, sender)
                else:
                    app.logger.error("Webhook: Order {} gifted to {} who already has ticket".format(d.code, target))
            else:
                lottomail.order_complete(borderling.email)
        db.session.commit()
        pretix_update_order_name(d.code, borderling.pretix_name())
    return "k"


# Everything not declared before (not a Flask route / API endpoint)...
@app.route('/<path:path>')
def route_frontend(path):
    # ...could be a static file needed by the front end that
    # doesn't use the `static` path (like in `<script src="bundle.js">`)
    file_path = os.path.join(app.static_folder, path)
    if os.path.isfile(file_path):
        return send_file(file_path)
    # ...or should be handled by the SPA's "router" in front end
    else:
        index_path = os.path.join(app.static_folder, 'index.html')
        return send_file(index_path)

def do_lottery():
    lottery = get_lottery()
    if lottery.lotteryRunning():
        while True:
            borderling = lottery.get_random_borderling()
            if borderling:
                if not borderling.isChild():
                    if not pretix_get_vouchers(borderling):
                        break
            else:
                break

def generate_code():
    return  "".join(random.sample([ chr(c) for c in range(ord('A'), ord('Z')+1) ]
                                  + [ str(i) for i in range(1,9)], 25))

def pretix_get_vouchers():
    valid_until = datetime.now()+timedelta(**expiration_delta)

    r = requests.post("https://{}/api/v1/organizers/{}/events/{}/vouchers/batch_create/".format(host, org, event),
                  headers = {
                      "Authorization": "Token {}".format(pretix_token)
                  },
                  json = [
                      {
                          "code": generate_code(),
                          "max_usages": 1,
                          "valid_until": str(valid_until),
                          "block_quota": "true",
                          "item": item,

                          "allow_ignore_quota": "false",
                          "price_mode": "none",
                          "value": "0",
                          "variation": None,
                          "quota": None,
                          "tag": "lottery",
                          "comment": "",
                          "subevent": None
                      },
                      {
                          "code": generate_code(),
                          "max_usages": 1,
                          "valid_until": str(valid_until),
                          "block_quota": "true",
                          "item": item,

                          "allow_ignore_quota": "false",
                          "price_mode": "none",
                          "value": "0",
                          "variation": None,
                          "quota": None,
                          "tag": "lottery",
                          "comment": "",
                          "subevent": None
                      }
                  ])

    if r.status_code == 201:
        for v in r.json():
            db.session.add(Voucher(
                borderling_id = borderling.id,
                code = v["code"],
                expires = valid_until
            ))
        db.session.commit()
        lottomail.voucher_allocated(borderling.email)
        return True
    else:
        print("Unable to create vouchers: {} {}".format(r.status_code, r.text))
        return False

def pretix_order_info(code):
    r = requests.get("https://{}/api/v1/organizers/{}/events/{}/orders/{}/".format(host, org, event, code),
                     headers = {
                      "Authorization": "Token {}".format(pretix_token)
                  })
    if r.status_code == 200:
        return r.json()
    app.logger.warn("Error getting pretix order info: {} {}".format(r.status_code, r.text))
    return None

def pretix_voucher_info(vid):
    r = requests.get("https://{}/api/v1/organizers/{}/events/{}/vouchers/{}/".format(host, org, event, vid),
                     headers = {
                      "Authorization": "Token {}".format(pretix_token)
                  })
    if r.status_code == 200:
        return r.json()
    # {
    #   "id": 1,
    #   "code": "43K6LKM37FBVR2YG",
    #   "max_usages": 1,
    #   "redeemed": 0,
    #   "valid_until": null,
    #   "block_quota": false,
    #   "allow_ignore_quota": false,
    #   "price_mode": "set",
    #   "value": "12.00",
    #   "item": 1,
    #   "variation": null,
    #   "quota": null,
    #   "tag": "testvoucher",
    #   "comment": "",
    #   "subevent": null
    # }
    app.logger.warn("Error getting pretix voucher info: {} {}".format(r.status_code, r.text))
    return None


def pretix_update_order_name(a, b):
    app.logger.warn("UNIMPLEMENTED update {} with {}".format(a, b))

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

def get_lottery():
    return get_or_create(Lottery,
                         registration_start = datetime(2019,1,1,12,0),
                         registration_end = datetime(2019,2,1,12,0),
                         lottery_start = datetime(2019,1,1,12,0),
                         lottery_end = datetime(2019,2,1,12,0),
                         transfer_start = datetime(2019,1,1,12,0),
                         transfer_end = datetime(2019,2,1,12,0),
                         fcfs_voucher = "fcfs",
                         child_voucher = "child")

#db.drop_all()
db.create_all()

if not Lottery.query.first():
    print("Creating test data")
    db_test_data()

if __name__ == '__main__':
    app.run(debug = True)
