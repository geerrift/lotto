from main import *
from datetime import timezone, timedelta

event = "test3"
item = 5
child_item = 6


def db_test_data():
    tz = timezone(offset=timedelta(hours = 1))
    lottery = Lottery(
                         registration_start = datetime(2019,2,3,8,0,tzinfo=tz),
                         registration_end = datetime(2019,2,5,23,0,tzinfo=tz),
                         lottery_start = datetime(2019,2,3,17,0,tzinfo=tz),
                         lottery_end = datetime(2019,2,3,17,30,tzinfo=tz),
                         transfer_start = datetime(2019,1,3,17,0,tzinfo=tz),
                         transfer_end = datetime(2019,2,28,20,50,tzinfo=tz),
                         fcfs_voucher = "FCFS",
                         child_voucher = "",
                         child_item = child_item,
                         ticket_item = item,
                         pretix_event_url = "https://pretix.theborderland.se/borderland/{}/".format(event))
    db.session.add(lottery)


    db.session.commit()
    personal_qs = Questionset(lottery_id = lottery.id, priority=10, name="Personal questions",description='''
    To make the lottery fair we need to check your ID when you arrive at the port. Please fill out the following like it appears on an official document.

    Kids under 13 get in for free with a member guardian, if you plan on bringing kids please indicate how many.
    ''')

    demographic_qs = Questionset(lottery_id = lottery.id, priority=30, name="Demographic questions",
                                 description='''
                                 We'd also like to know a few things about the people attending.
''')

    volunteer_qs = Questionset(lottery_id = lottery.id, priority=20, name="Voluteer questions",
                               description='''
The Borderland is built on co-creation and a community that takes care of each other.

Most of what happens at The Borderland is organised in a decentralised fashion by camps, but there are certain infrastructual and civic reponsibilities the needs to be in place. 
''')

    db.session.add(personal_qs)
    db.session.add(volunteer_qs)
    db.session.add(demographic_qs)
    db.session.commit()
    q1 = Question(set_id = personal_qs.id, text="Your name as it appears on official documents", type = "text", tag="realname",
                  tooltip = "Firstname Lastname")
    q2 = Question(set_id = personal_qs.id, text="Your date of birth", type = "date", tag="DOB",
                  tooltip = "dd/mm/yyyy")

    q3 = Question(set_id = personal_qs.id, text="If you're bringing children under 13, how many?", type = "number", tag="children")
    db.session.add(q1)
    db.session.add(q2)
    db.session.add(q3)

    db.session.add(Question(set_id = volunteer_qs.id,
                            type = "multiple",
                            text = '''
Please indicate if you'd like to be contacted about taking on responsibilities in any of these teams. No experience is neccessary, and first timers are especially encouraged to participate!
                           ''',
                            options = [
                                QuestionOption(text = "Clown Police", tooltip = "Patrol the event and watch for safety issues."),
                                QuestionOption(text = "Sanctuary", tooltip = "First aid and psychological well-being"),
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
                            text = "In which country do you presently live?",
                            options = [ QuestionOption(text = c['Name'])
                                        for c in json.load(open("./countries.json")) ]))
    db.session.add(Question(set_id = demographic_qs.id,
                            type = "number",
                            text = "How many Burn-like events have you been to before (The Borderland, Burning Man, Nowhere, ...)?"))
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
