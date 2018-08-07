#!/usr/bin/env python3
# # -*- coding: utf-8 -*-

"""
drem - date reminder & mail notifier

# e.g. cron job every day at 0000
# crontab -e
0 0 * * * /path/to/script/drem.py > /dev/null 2>&1

"""
# TODO
#  - Prettify HTML email (CSS styled table or something?)

# Imports
import os
import datetime
import base64
import prettytable
import sendgrid
from sendgrid.helpers.mail import *

from azure.cosmosdb.table.tableservice import TableService
from azure.cosmosdb.table.models import Entity

# Capture environment variables
try:
    azure_storage_account_name = os.environ["AZURE_STORAGE_ACCOUNT"]
    azure_storage_account_key = os.environ["AZURE_STORAGE_ACCOUNT_KEY"]
    sendgrid_api_key = os.environ["SENDGRID_API_KEY"]
except:
    print("\nError! Set environment variables: AZURE_STORAGE_ACCOUNT, AZURE_STORAGE_ACCOUNT_KEY, SENDGRID_API_KEY\n")
    exit()

mail_subject = '[drem] Date Reminders'
mail_prefix = ''
mail_suffix = '\n\nUpdates or additions? Just reply back to this email to let me know.\n\nThis program has been migrated to Microsoft Azure Tables & Functions. Sorry for the service interruption ;)'

def mail(mail_sender,mail_receiver,subject,text,html):
    sg = sendgrid.SendGridAPIClient(apikey=os.environ.get('SENDGRID_API_KEY'))
    from_email = Email(mail_sender)
    to_email = Email(mail_receiver)
    subject = subject
    content = Content("text/plain", text)
    content = Content("text/html", html)
    mail = Mail(from_email, subject, to_email, content)
    response = sg.client.mail.send.post(request_body=mail.get())

def calculate_age(born):
    """Calculate the number of years since an event occurred"""
    today = datetime.date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))

def calculate_days_till_next(original_date):
    """Calculate the number of days until the next anniversary of an event"""
    now = datetime.datetime.now()
    delta1 = datetime.datetime(now.year, original_date.month, original_date.day) - now
    delta2 = datetime.datetime(now.year+1, original_date.month, original_date.day) - now
    #days = max(delta1, delta2).total_seconds() / 60 /60 /24
    if delta1.days <= 0:
        return delta2.days+1
    else:
        return delta1.days+1

# Generate/format txt and html pretty tables
pt_bdays = prettytable.PrettyTable(["DaysTillNextBirthDay", "Name", "CurrentAge", "BirthDate", "DeathDate"])
pt_annivs = prettytable.PrettyTable(["DaysTillNextAnniv", "Spouse1", "Spouse2", "YearsMarried", "AnnivDate"])

# Open Azure Table
table_service = TableService(account_name=azure_storage_account_name, account_key=azure_storage_account_key)

# mail_receiver = ['sean@scummins.com'] # dev override
mail_sender='sean@scummins.com'
mail_receiver=['sean@scummins.com']

# Process birthdays
birthday_entities = table_service.query_entities('birthdays', filter="PartitionKey eq 'Birthdays'")
bdaylist = []

for birthday_ent in birthday_entities:
    birthdayDate = datetime.datetime.strptime(birthday_ent.BirthDate, '%m/%d/%Y').date()
    name = birthday_ent.Name
    currentAge = calculate_age(birthdayDate)
    daysTillNextBirthDay = calculate_days_till_next(birthdayDate)
    try:
        deathDate = datetime.datetime.strptime(birthday_ent.DeathDate, '%m/%d/%Y').date()
    except:
        deathDate = None

    bdaylist.append([daysTillNextBirthDay,name,currentAge,birthdayDate,deathDate])

# Flag flips to true if there's a birthday today
birthdays_today = False
subj_override = ''
alert_messages = ''
for row in bdaylist:
    # Build Prettytable
    pt_bdays.add_row(row)

    # Alert code (look for upcoming birthdays)
    if row[0] < 1:
        birthdays_today = True

        name = row[1]
        age = row[2]
        age += 1
        alert_msg = "! Upcoming birthday: %s will be %d" % (name, age)
        print(alert_msg)

        if subj_override == '':
            subj_override = '[drem] Today: %s(%d)' % (name, age)
        else:
            subj_override += ', %s(%d)' % (name, age)

        # TODO: mail_prefix and mail_suffix
        mail_prefix += alert_msg

# Format prettytable
pt_bdays.align = "l"
pt_bdays.float_format = "4.0"
pt_bdays.get_string(attributes = {"class": "csstable"})
pt_bdays.format = True
pt_bdays.sortby = "DaysTillNextBirthDay"


### Anniversaries
anniv_entities = table_service.query_entities('anniversaries', filter="PartitionKey eq 'Anniversaries'")
annivlist = []

for anniv_ent in anniv_entities:
    annivDate = datetime.datetime.strptime(anniv_ent.AnnivDate, '%m/%d/%Y')
    spouse1 = anniv_ent.Spouse1
    spouse2 = anniv_ent.Spouse2
    currentAge = calculate_age(annivDate)
    daysTillNextAnniv = calculate_days_till_next(annivDate)

    annivlist.append([daysTillNextAnniv,spouse1,spouse2,currentAge,annivDate.date()])

# Flag flips to true if there's an anniv today
anniv_today = False

for row in annivlist:
    # Build Prettytable
    pt_annivs.add_row(row)

    # Alert code (look for upcoming annivs)
    if row[0] < 0:
        anniv_today = True

        spouse1 = row[1]
        spouse2 = row[2]
        years_married = row[3]
        years_married += 1
        alert_msg = "! Upcoming anniversary: %s & %s married %d years" % (spouse1, spouse2, years_married)
        print(alert_msg)

        if subj_override == '':
            subj_override = '[drem] Today: %s & %s(%d)' % (spouse1, spouse2, years_married)
        else:
            subj_override += ', %s & %s(%d)' % (spouse1, spouse2, years_married)

        # TODO: mail_prefix and mail_suffix
        mail_prefix += alert_msg

# Format prettytable
pt_annivs.align = "l"
pt_annivs.float_format = "4.0"
pt_annivs.get_string(attributes = {"class": "csstable"})
pt_annivs.format = True
pt_annivs.sortby = "DaysTillNextAnniv"


text = pt_bdays.get_string() + "\n" + pt_annivs.get_string()
html = "<html><head></head><body> "+ pt_bdays.get_html_string() + "</p><p>" + pt_annivs.get_html_string() + "</p></div></body></html>"

# Print results to screen
print(pt_bdays)
print(pt_annivs)


# Send summary email
# Only send if it's a Sunday or if there are birthdays/annivs today
dayofweek = datetime.datetime.today().weekday()

dayofweek = 6  # DEV OVERRIDE

if dayofweek == 6 or birthdays_today == True or anniv_today == True:
    if subj_override != '':
        subject = subj_override
    else:
        subject = mail_subject

    mail(mail_sender,mail_receiver,subject,text,html)
