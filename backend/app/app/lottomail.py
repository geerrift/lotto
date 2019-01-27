import os
import smtplib
from email.message import EmailMessage

#TODO
# pretty HTML multipart messages
# support multiple lotteries

def new_message(recipient, subject, body):
    msg = EmailMessage()
    msg.set_content(body)

    msg['Subject'] = subject
    msg['From'] = "Borderland Memberships <noreply@theborderland.se>"
    msg['To'] = recipient
    return msg

def send_message(msg):
    s = smtplib.SMTP(os.getenv("SMTP_HOST"))
    s.connect(os.getenv("SMTP_HOST"))
    s.starttls()
    s.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASS"))
    s.send_message(msg)
    s.quit()

def voucher_allocated(recipient):
    msg = new_message(recipient, "You're going to The Borderland 2019!",
    '''
pretty words go here
    ''')
    send_message(msg)

def order_complete(recipient):
    msg = new_message(recipient, "Your Borderland 2019 membership",
    '''
pretty words go here
    ''')
    send_message(msg)

def registration_complete(recipient):
    msg = new_message(recipient, "You're registered for The Borderland 2019!",
    '''
pretty words go here
    ''')
    send_message(msg)

def gifted_ticket(recipient, sender):
    msg = new_message(recipient, "Someone gifted you a membership to The Borderland 2019!",
    '''
pretty words go here {}
    '''.format(sender))
    send_message(msg)

def voucher_transfer(recipient, sender, expiration):
    msg = new_message(recipient, "You've been invited to The Borderland 2019!",
    '''
{} pretty words go here {}
    '''.format(sender, expiration))
    send_message(msg)


