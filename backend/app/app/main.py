# TODO
# create db if empty - for test
# children
# Transfers
# Pretix integration
# Logging
# Emails
# question ordering?
# refactor - model, etc
# pre-login front page

from flask import Flask, jsonify, request, send_file, g
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.exc import IntegrityError
from flask_oidc import OpenIDConnect
import os
import json

app = Flask(__name__)
oidc = OpenIDConnect(app)
db = SQLAlchemy(app)
db.engine.pool._pre_ping = True # SQLALCHEMY_POOL_RECYCLE

with open("/tmp/client_secrets.json") as f:
    json.dump({
        
    }, f)

app.config.update({
    'SQLALCHEMY_DATABASE_URI' = os.getenv("LOTTO_DB"), #or 'sqlite:///test.db'
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
    fcfs_voucher = (db.String(500))
    child_voucher = (db.String(500))

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

    def to_dict(self):
        return { "can_register": self.registrationAllowed(),
                 "can_transfer": self.transferAllowed(),
                 "questions": [ qs.id for qs in Questionset.query.filter_by(lottery_id=self.id).all() ]}

class Borderling(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lottery_id = db.Column(db.Integer, db.ForeignKey("lottery.id"))
    email = db.Column(db.String(120), unique=True, nullable=False)
    ticket = db.Column(db.String(120), unique=True)
    vouchers = db.relationship('Voucher', backref='borderling', lazy = True)
    answers = db.relationship('Answer', backref='Borderling', lazy = True)
    admin = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return '<Borderling %r>' % self.email

    #def isChild
    # TODO child or FCFS
    def getVouchers(self):
        return [ v.to_dict() for v in self.vouchers ]

    def isRegistered(self, lottery):
        return self in get_lottery().borderlings

    def to_dict(self, lottery):
        return { "registered": self.isRegistered(lottery),
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
        if type(v) != list:
            prev_a = db.session.query(Answer).filter(Answer.id == self.answer_id, Answer.borderling_id == u.id).first()
            if prev_a:
                print("replaced previous text {:s} with {:s}".format(prev_a.text, v))
                prev_a.text = v
            else:
                db.session.add(Answer(question = [self], borderling_id = u.id, text = v))
        else:
            v = ",".join(v)
            prev_a = db.session.query(Answer).filter(Answer.id == self.answer_id, Answer.borderling_id == u.id).first()
            if prev_a:
                print("replaced previous selection {:s} with {:s}".format(prev_a.selections, v))
                prev_a.selections = v
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

    def __repr__(self):
        return '<Voucher: %r>' % self.code

    def to_dict(self):
        return { "code": self.code, "expires": self.expires }
    #def transfer -- check owner


def get_or_create(model,
                      **kwargs):
    try:
        return db.session.query(model).filter_by(**kwargs).one()
    except NoResultFound:
        created = model(**kwargs)
        try:
            db.session.add(created)
            db.session.commit()
            return created
        except IntegrityError:
            db.session.rollback()
            return db.session.query(model).filter_by(**kwargs).one()

@app.route('/api/registration', methods=['GET', 'POST'])
@oidc.accept_token(require_token=True)
def registration():
    u = get_or_create(Borderling, email=g.oidc_token_info['email'])
    lottery = get_lottery()
    if request.method == 'POST':
        if lottery.registrationAllowed():
            lottery.borderlings.append(u)
            db.session.commit()
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


@app.route('/')
def route_root():
    index_path = os.path.join(app.static_folder, 'index.html')
    return send_file(index_path)

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

def db_test_data():
    lottery = get_lottery()
    borderling_a = Borderling(email="a")
    db.session.add(borderling_a)
    db.session.commit()
    personal_qs = Questionset(lottery_id = lottery.id, priority=10, name="Personal questions",description="Tell me about your mother")
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
    q2 = Question(set_id = personal_qs.id, text="Your date of birth", type = "date")
    db.session.add(q1)
    db.session.add(q2)

    # Here’s a page that gives an overview of what you could help out with: http://wiki.theborderland.se/Civics TODO
    db.session.add(Question(set_id = volunteer_qs.id,
                            type = "multiple",
                            text = '''If you'd like to be part of one of the civic responsibility teams, please let us know by ticking off your preferred area(s) in the options below. Note that this is not binding, and that you only agree to be contacted with the option to participate.

You do not need prior experience, and if this is your first Borderland, you are highly encouraged to participate!
                           ''',
                            options = [
                                QuestionOption(text = "Clown Police"),
                                QuestionOption(text = "Sanctuary (first aid and psychological well being)")
                                QuestionOption(text = "Electrical Power")
                                QuestionOption(text = "Drinking Water and Greywater")
                                QuestionOption(text = "Swimming Safety")
                                QuestionOption(text = "Communal Spaces")
                                QuestionOption(text = "Communications")
                            ]))
    db.session.add(Question(set_id = volunteer_qs.id,
                            type = "multiple",
                            text = '''
Please let us know if you have any special skills or relevant experience and would like to help out within one (or more) of the following areas:
                            ''',
                            options = [
                                QuestionOption(text = "First aid or other medical experience"),
                                QuestionOption(text = "Psychological Welfare")
                                QuestionOption(text = "Conflict Resolution")
                                QuestionOption(text = "Power or other Infrastructure")
                                QuestionOption(text = "Safety and Risk Assessment")
                                QuestionOption(text = "Bureaucracy related to this kind of event")
                            ]))

    db.session.add(Question(set_id = demographic_qs.id,
                            type = "datalist",
                            text = "Where in the world are you from?",
                            options = [ QuestionOption(text = c['Name'])
                                        for c in json.load(open("countries.json")) ]))
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
                                transfer_end = datetime(2019,2,1,12,0))
#db.drop_all()
db.create_all()
db_test_data()

if __name__ == '__main__':
    app.run(debug = True)
