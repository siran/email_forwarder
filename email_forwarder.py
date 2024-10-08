import json
import boto3
import traceback
import re
from email import message_from_bytes
from email.utils import parseaddr
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.header import Header
from email import encoders
from email.mime.text import MIMEText
from email.encoders import encode_7or8bit


# Configuration variables
s3 = boto3.client('s3')
ses = boto3.client('ses', region_name='us-east-1')
bucket_name = 'preferredframe.com'  # Adjust with your actual bucket name

default_catch_all_email = ["anmichel@gmail.com"]

managed_domains = [
    'preferredframe.com',
    'wildnloyal.com',
    'cinemestizo.com',
    'eserviciosat.com',
    'eduweb.com',
]

def get_rules():
    return {
        # 'shashi@preferredframe.com': ['sskuwar@gmail.com'],
        'felix@preferredframe.com': ['konefka@gmail.com'], # chief?
        'jorge@preferredframe.com': ['bricenojlx@gmail.com'], # chief of endogenous development
        'nathan@preferredframe.com': ['n.rapport@gmail.com'], # chief of research and technology
        'cecilia@preferredframe.com': ['cecilia.rojas.rojas@gmail.com'], # chief of marketing
        'juan@preferredframe.com': ['juanfermin1@gmail.com'], # chief of media producing

        'jose@cinemestizo.com': ['jocalejandro@gmail.com'],
        'dani@cinemestizo.com': ['danielruiz2000@gmail.com'],

        'an@': ['anmichel@gmail.com'],

        '@preferredframe.com': ['anmichel@gmail.com'],
        '@wildnloyal.com': ['anmichel@gmail.com'],
        '@cinemestizo.com': ['anmichel@gmail.com', 'danielruiz2000@gmail.com', 'jocalejandro@gmail.com'],
        '_catch_all_': ['anmichel@gmail.com'],
    }

def process_event(event, context=None):
    print(json.dumps(event))
    try:
        if 'ses' in event['Records'][0]:
            process_ses_event(event['Records'][0]['ses'])
    except Exception as e:
        print(f'Error processing event: {str(e)}')
        traceback.print_exc()

def process_ses_event(ses_event):
    mail = ses_event['mail']
    messageId = mail['messageId']
    receipt = ses_event['receipt']
    intended_recipients = receipt['recipients']

    key = f"incoming/{messageId}"
    process_ses_s3(bucket_name, key, intended_recipients)

def process_ses_s3(bucket, key, intended_recipients):
    obj = s3.get_object(Bucket=bucket, Key=key)
    email_body = obj['Body'].read()
    msg = message_from_bytes(email_body)

    for intended_recipient in intended_recipients:
        forwarding_addresses = apply_forwarding_rules(intended_recipient)
        print(f"Forwarding {intended_recipients} to {forwarding_addresses}")
        send_response_email(msg, forwarding_addresses, intended_recipient)

def apply_forwarding_rules(intended_recipient):
    rules = get_rules()
    forwarding_addresses = set()

    for rule, emails in rules.items():
        if rule == intended_recipient:
            forwarding_addresses.update(emails)
            break
        elif rule in intended_recipient:
            forwarding_addresses.update(emails)
            break
    else:
        forwarding_addresses.update(rules.get('_catch_all_', default_catch_all_email))

    return forwarding_addresses

def send_response_email(original_msg, forwarding_addresses, intended_recipient):
    sender_name, sender_email = parseaddr(original_msg['From'])
    print(sender_email)
    sender_preat, sender_postat = sender_email.split("@")
    ses_from_address = f"{sender_name} <{sender_preat}.at.{sender_postat}+To+{intended_recipient}>"

    # Create a new MIME message
    forward_msg = MIMEMultipart('mixed')
    forward_msg['Subject'] = original_msg['Subject']
    forward_msg['From'] = ses_from_address
    forward_msg['To'] = ', '.join(forwarding_addresses)
    forward_msg['Reply-To'] = original_msg['Reply-To'] if 'Reply-To' in original_msg else sender_email
    forward_msg['In-Reply-To'] = original_msg['Message-ID']
    forward_msg['References'] = original_msg['Message-ID']

    # Create a new MIME message part for the forwarded email body
    forward_body = MIMEMultipart('alternative')

    # Define the original sender indication with <p> tags for HTML version
    original_sender_name = sender_name if sender_name else sender_email
    original_sender_indication_html = f"<p>--- Forwarded message from {original_sender_name} ---</p>\n"

    # Attach the original sender indication to HTML part
    forward_body.attach(MIMEText(original_sender_indication_html, 'html'))

    # Attach the original message as a part
    forward_msg.attach(original_msg)

    # Print forwarded message details
    print("Forwarded FROM:", ses_from_address)
    print("Forwarded TO:", ', '.join(forwarding_addresses))
    print("Forwarded SUBJECT:", original_msg['Subject'])
    print("Forwarded REPLY-TO:", forward_msg['Reply-To'])
    print("Oringinal REPLY-TO:", original_msg['Reply-To'])

    # Send the email using SES
    ses.send_raw_email(
        Source=ses_from_address,
        Destinations=list(forwarding_addresses),
        RawMessage={'Data': forward_msg.as_string()}
    )
