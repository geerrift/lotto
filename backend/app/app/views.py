from main import app, db, oidc, jsonify, request, send_file, g, get_lottery, do_lottery
from models import *
import lottomail
import pretix
import json
import os

# Get or update users' registration status
@app.route('/api/registration', methods=['GET', 'POST'])
@oidc.accept_token(require_token=True)
def registration():
    u = get_or_create(Borderling, email=g.oidc_token_info['email'])
    lottery = get_lottery()
    if request.method == 'POST':
        if lottery.registrationAllowed():
            lottery.borderlings.append(u)
            db.session.commit()
            # TODO check if not already registered so we don't send additional
            # emails
            lottomail.registration_complete(u.email)
    return jsonify(u.to_dict(lottery))

# Get this lottery's current status
@app.route('/api/lottery')
@oidc.accept_token(require_token=True)
def lottery():
    return jsonify(get_lottery().to_dict())

# Get or submit questions
@app.route('/api/questions/<int:qs>',
           methods=['GET', 'POST'])
@oidc.accept_token(require_token=True)
def questionset(qs):
    u = get_or_create(Borderling, email=g.oidc_token_info['email'])
    if request.method == 'POST':
        #for k,v in request.get_json().items():
            #if not v:
            #    return jsonify({"result": False, "message": "Empty answer"}), 400
        for k,v in request.get_json().items():
            q = Question.query.filter_by(id=int(k)).first()
            q.answer(u, v)
            return jsonify({"result": True, "message": ""})
    return jsonify(Questionset.query.filter_by(id=qs).first().to_dict(u))

# Transfer a voucher ("invite") from one account's supplementary vouchers to
# anothers main
@app.route('/api/transfer', methods=['POST'])
@oidc.accept_token(require_token=True)
def transfer_voucher():
    u = get_or_create(Borderling, email=g.oidc_token_info['email'])
    if get_lottery().transferAllowed():
        r = request.get_json()
        voucher = Voucher.query.filter(Voucher.code == r['voucher']).first()
        dest = Borderling.query.filter(Borderling.email == r['email']).first()
        if voucher and dest:
            result = voucher.transfer(u, dest)
            app.logger.warn("transfer {}".format(result))
            if result:
                lottomail.voucher_transfer(dest.email, u.email, voucher.expires)
            else:
                return jsonify(u.to_dict(lottery)), 401
        else:
            app.logger.warn("transfer failed {} to {}".format(voucher, dest))
            return jsonify(u.to_dict(lottery)), 401
    return jsonify(u.to_dict(lottery))

# Mark a voucher as gifted, will do the actual transfer once it's been paid in
# the webhook
@app.route('/api/gift', methods=['POST'])
@oidc.accept_token(require_token=True)
def gift_voucher():
    u = get_or_create(Borderling, email=g.oidc_token_info['email'])
    r = request.get_json()
    voucher = Voucher.query.filter(Voucher.code == r['voucher']).first()
    dest = Borderling.query.filter(Borderling.email == r['email']).first()
    if voucher and dest and voucher.gift_to(u, dest):
        return jsonify({"result": True,
                        "url": "https://{}/{}/{}/redeem?voucher={}".format(host,org,event,voucher.code)
        }), 201
    return jsonify({"result": False}), 401

@app.route('/')
def route_root():
    index_path = os.path.join(app.static_folder, 'index.html')
    return send_file(index_path)

# Called by Pretix when an order has been paid, so we can do gifting and update the status.
# Here be dragons: a lot of this belongs in the model
@app.route('/_/webhooks/pretix', methods=['POST'])
def pretix_webhook():
    d = request.get_json()
    if d['action'] == "pretix.event.order.paid":
        #{"notification_id": 117, "organizer": "borderland", "event": "test", "code": "Z9M9V", "action": "pretix.event.order.paid"}
        orderinfo = pretix.order_info(d['code'])
        orderposition = orderinfo['positions'][0] # TODO assumes only one product, this assumption is prevalent
        pretix_voucher = pretix.voucher_info(orderposition['voucher'])
        app.logger.info("Webhook order.paid: {} for {}".format(d['code'], pretix_voucher))
        voucher = Voucher.query.filter(Voucher.code == pretix_voucher['code']).first()
        borderling = Borderling.query.filter(Borderling.id == voucher.borderling_id).first()
        if voucher:
            # update order info
            voucher.order = d['code']
            voucher.secret = orderinfo['secret']
            if voucher.gifted_to:
                recipient = Borderling.query.filter(Borderling.id == Voucher.gifted_to).first()
                if Voucher.query.filter(Voucher.borderling_id == recipient.id, Voucher.order != None):
                    app.logger.info("Webhook: transfering gifted voucher from {} to {}".format(borderling, recipient))
                    if voucher.move(borderling, recipient):
                        lottomail.gifted_ticket(recipient.email, borderling.email)
                        pretix.update_order_name(d['code'], borderling.pretix_name())
                else:
                    app.logger.error("Webhook: Order {} gifted to {} who already has ticket".format(d['code'], recipient))
            else:
                app.logger.info("Webhook: purchase completed for {}".format(borderling))
                lottomail.order_complete(borderling.email)
                pretix.update_order_name(d['code'], borderling.pretix_name())
        db.session.commit()
    return "k"


# Default catch-all
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

