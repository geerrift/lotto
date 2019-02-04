import os
from main import db, expiration_delta, host, org, event, item, app
from models import *
import requests
import random
import lottomail
from datetime import datetime,timedelta

pretix_token = os.getenv("PRETIX_TOKEN")

def generate_code():
    return  "".join(random.sample([ chr(c) for c in range(ord('A'), ord('Z')+1) ]
                                  + [ str(i) for i in range(1,9)], 25))

def get_vouchers(borderling):
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
        first = True
        for v in r.json():
            app.logger.info("Created voucher {}".format(v['code']))
            db.session.add(Voucher(
                borderling_id = borderling.id,
                code = v["code"],
                expires = valid_until,
                primary = first
            ))
            first = False
        db.session.commit()
        lottomail.voucher_allocated(borderling.email)
        return True
    else:
        print("Unable to create vouchers: {} {}".format(r.status_code, r.text))
        return False

def order_info(code):
    r = requests.get("https://{}/api/v1/organizers/{}/events/{}/orders/{}/".format(host, org, event, code),
                     headers = {
                      "Authorization": "Token {}".format(pretix_token)
                  })
    if r.status_code == 200:
        return r.json()
    app.logger.warn("Error getting pretix order info: {} {}".format(r.status_code, r.text))
    return None

def voucher_info(vid):
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


def update_order_name(a, b):
    app.logger.error("UNIMPLEMENTED update {} with {}".format(a, b))

