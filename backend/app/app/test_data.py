from main import *
from datetime import timezone, timedelta

event = "test3"
item = 5
child_item = 6


def db_test_data():
    tz = timezone(offset=timedelta(hours = 1))
    lottery = Lottery(
                         registration_start = datetime(2019,2,1,8,0,tzinfo=tz),
                         registration_end = datetime(2019,2,28,23,0,tzinfo=tz),
                         lottery_start = datetime(2019,2,1,20,0,tzinfo=tz),
                         lottery_end = datetime(2019,2,1,20,50,tzinfo=tz),
                         transfer_start = datetime(2019,1,29,17,0,tzinfo=tz),
                         transfer_end = datetime(2019,2,28,20,50,tzinfo=tz),
                         fcfs_voucher = "fcfs",
                         child_voucher = "child",
                         child_item = child_item,
                         ticket_item = item,
                         pretix_event_url = "https://pretix.theborderland.se/borderland/{}/".format(event))
    db.session.add(lottery)


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


if __name__ == '__main__':
    import sys
    print("Danger zone")
    sys.stdin.readline()
    db.drop_all()
    db.create_all()
    db_test_data()
