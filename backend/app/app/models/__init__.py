
from datetime import datetime, timedelta
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.expression import func
from main import app, db, get_lottery, host, org, event

def get_or_create(model, **kwargs):
    try:
        return db.session.query(model).filter_by(**kwargs).one()
    except NoResultFound:
        created = model(**kwargs)
        try: # This catches a some things it shouldn't, like an out of sync schema
            app.logger.info("Creating: {}".format(created))
            db.session.add(created)
            db.session.commit()
            return created
        except IntegrityError:
            app.logger.info("Integrity error {}".format(created))
            db.session.rollback()
            return db.session.query(model).filter_by(**kwargs).one()



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
    child_item = db.Column(db.Integer)
    ticket_item = db.Column(db.Integer)
    pretix_event_url = db.Column(db.String(500))
    message = db.Column(db.String(5000))

    def __repr__(self):
        return '<Lottery %r>' % self.id

    def transferAllowed(self):
        return self.transfer_start < datetime.utcnow() and self.transfer_end > datetime.utcnow()

    def lotteryRunning(self):
        return self.lottery_start < datetime.utcnow() and self.lottery_end > datetime.utcnow()

    def registrationAllowed(self):
        return (self.registration_start < datetime.utcnow() and
                self.registration_end > datetime.utcnow()) and not self.lotteryRunning()

    def isFCFS(self):
        return self.fcfs_voucher and self.lottery_end < datetime.utcnow()

    def get_random_borderling(self):
        return Borderling.query.filter(Borderling.lottery_id == self.id,
                                       ~Borderling.vouchers.any() ).order_by(
                                           func.random()).first()

    def to_dict(self):
        return { "can_register": self.registrationAllowed(),
                 "can_transfer": self.transferAllowed(),
                 "child_item": "item_{}=1".format(self.child_item),
                 "fcfs_voucher": self.isFCFS() and self.fcfs_voucher,
                 "ticket_item": "item_{}=1".format(self.ticket_item),
                 "pretix_event_url": self.pretix_event_url,
                 "message": self.message,
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
        return dob > datetime.utcnow()-timedelta(days = 13*365)

    def getVouchers(self):
        lottery_ = get_lottery()
#        vouchers = [ v.to_dict() for v in self.vouchers ]
        return [ v.to_dict() for v in Voucher.query.filter(Voucher.borderling_id == self.id, Voucher.expires > datetime.utcnow()).order_by(Voucher.order, Voucher.primary.desc(),Voucher.id.desc()).all() ]
#        if vouchers:
#            return vouchers
#        else:
#            if self.isChild() and (lottery_.lotteryRunning() or lottery_.isFCFS()):
#                return [ { "code": lottery_.child_voucher,
#                        "expires": lottery_.transfer_end.isoformat()+"+01:00" # TODO timezones
#                } ]
#            elif lottery_.isFCFS():
#                return [ { "code": lottery_.fcfs_voucher, "expires": lottery_.transfer_end.isoformat()+"+01:00" } ]
#            else:
#                return []

    def isRegistered(self, lottery):
        return self in get_lottery().borderlings

    def pretix_name(self):
        return "" # TODO realname and DOB

    def to_dict(self, lottery):
        tickets = Voucher.query.filter(Voucher.borderling_id == self.id,
                                       Voucher.order != None).first()
        return { "registered": self.isRegistered(lottery),
                 "tickets": tickets and tickets.ticket_dict(),
                 "email": self.email,
                 "child_voucher": self.isChild() and lottery.child_voucher,
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
    tooltip = db.Column(db.String(5000), unique=False, nullable=True)
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
                app.logger.info("User {} question {}: Replacing {} with {}".format(u, prev, prev.text, v))
                prev.text = v
            else:
                db.session.add(Answer(question = [self], borderling_id = u.id, text = v))
        else:
            v = ",".join(v)
            prev = db.session.query(Answer).filter(Answer.id == self.answer_id, Answer.borderling_id == u.id).first()
            if prev:
                app.logger.info("User {}: Replacing {} with {}".format(u.id, prev.text, v))
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
                 or (self.tag == "children" and "0") # hacken, mixen, pulverizen
                 or "",
                 "type": self.type,
                 "tooltip": self.tooltip,
                 "selections": (borderling and self.get_selections(borderling)) or []}

class QuestionOption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id"))
    priority = db.Column(db.Integer)
    text = db.Column(db.String(1000), unique=False)
    tooltip = db.Column(db.String(5000), unique=False, nullable=True)

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
    secret = db.Column(db.String(1000), unique=True, nullable=True)
    primary = db.Column(db.Boolean, default = False)

    def __repr__(self):
        return '<Voucher: %r>' % self.code

    def ticket_dict(self):
        return { "order": self.order
                 , "url": "https://{}/{}/{}/order/{}/{}".format(host,org,event,self.order,self.secret) }

    def to_dict(self):
        return { "code": self.code, "expires": self.expires.isoformat()+"+01:00",
                 "primary": self.primary }

    def isTicket(self):
        if self.order:
            return True
        return False

    def transfer(self, origin, target):
        # not checking if transfers are allowed here because it's used by
        # gifting and webhooks
        if origin.id != self.borderling_id:
            app.logger.warn("Attempt to transfer ticket {} from {} to {}, but not owned by {}".format(self, origin, target, self.borderling_id))
            return False
        if self.primary:
            app.logger.error("Attempt to transfer primary voucher: {}".format(self))
            return False
        if target.vouchers and target.vouchers[0].order:
                app.logger.error("Attempt to transfer but target already has paid vouchers: {}".format(self))
                return False
        if target.vouchers and target.vouchers[0].expires > datetime.utcnow():
            app.logger.error("Attempt to transfer but target already has valid voucher: {}".format(self))
            return False
        self.primary = True
        self.borderling_id = target.id
        self.gifted_to = None
        db.session.commit()
        app.logger.warn("Transfered ticket {} from {} to {}".format(self, origin, target))
        return True

    def gift_to(self, origin, target):
        if origin.id != self.borderling_id and not self.order:
            app.logger.warn("gift_to: {} tried to gift ticket to {}, but voucher is either not paid for, or is not owned by source".format(origin, target))
            return False
        if Voucher.query.filter(Voucher.borderling_id == target.id, Voucher.order != None).first():
            app.logger.warn("gift_to: {} tried to gift ticket to {} who already has one".format(origin, target))
            # TODO return error text
            return False
        self.gifted_to = target.id
        db.session.commit()
        return True

