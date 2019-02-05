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

def registration_complete(recipient):
    msg = new_message(recipient, "You're registered for The Borderland 2019!",
    '''
Dearest Borderling,

This is your confirmation! You've registered for the 2019 membership lottery!

The lottery runs from the 16th to the 22nd.

We'll send you another e-mail if you win. However it's recommended you check the website every day or two during the lottery since e-mail can be unreliable. You have two days to act when you get an invitation.

Don't forget to tell all your friends to attend the lottery! Everyone going to the Borderland must be registered in this system (there are two exceptions and you can read about them on the webpage).

You can change your answers up until the lottery starts at
    https://memberships.theborderland.se/

Love,
The Borderland Membership Team
    ''')
    send_message(msg)


def voucher_allocated(recipient):
    msg = new_message(recipient, "You're invited to The Borderland 2019!",
    '''
Dearest Borderling,

You're invited to get a membership for you and a friend for The Borderland 2019!

Please hurry, you only have two days!

Go here: https://memberships.theborderland.se/

Love,
The Borderland Membership Team
    ''')
    send_message(msg)

def order_complete(recipient):
    msg = new_message(recipient, "Your Borderland 2019 membership",
    '''
Dearest Borderling,

You did it! You're going to The Borderland! Have you started packing yet?

You'll receive your printable ticket in a separate e-mail, please bring it
together with ID to the port when you arrive.

You can view your receipt at https://memberships.theborderland.se/

Hugs,
The Borderland Membership Team
    ''')
    send_message(msg)

def gifted_ticket(recipient, sender):
    msg = new_message(recipient, "Someone gifted you a membership to The Borderland 2019!",
    '''
Lovely Borderling,

Someone going by the email {} gifted you a membership to The Borderland 2019!

That's it, you're all set! Start packing!

You'll receive your printable ticket in a separate e-mail, please bring it
together with ID to the port when you arrive.

You can view the receipt at https://memberships.theborderland.se/

Hugs,
The Borderland Membership Team
    '''.format(sender))
    send_message(msg)

def voucher_transfer(recipient, sender, expiration):
    msg = new_message(recipient, "You've been invited to The Borderland 2019!",
    '''
Dearest Borderling,

Someone with the email address {} has sent you an invitation to The Borderland 2019!

Go here to purchase your membership: https://memberships.theborderland.se

Hurry up, it expires {}!

Hugs,
The Borderland Membership Team
    '''.format(sender, expiration))
    send_message(msg)


