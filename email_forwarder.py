import json
import boto3
import traceback
from email import message_from_bytes
from email.utils import parseaddr
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.header import Header
from email import encoders

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
        'an@': ['anmichel@gmail.com'],
        'dani@': ['danielruiz2000@gmail.com'],
        '@preferredframe.com': ['anmichel@gmail.com'],
        '@wildnloyal.com': ['anmichel@gmail.com'],
        '@cinemestizo.com': ['anmichel@gmail.com', 'danielruiz2000@gmail.com'],
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
        if rule in intended_recipient:
            forwarding_addresses.update(emails)
            break
    else:
        forwarding_addresses.add(rules.get('_catch_all_', default_catch_all_email))

    return forwarding_addresses

def send_response_email(original_msg, forwarding_addresses, intended_recipient):
    # Use a verified email address as the sender
    verified_sender_email = "verified@example.com"  # Replace with your verified sender email address

    # Create a new MIMEMultipart message to wrap the original message as an attachment
    new_msg = MIMEMultipart()
    new_msg['Subject'] = f"Fwd: {original_msg['Subject']}"
    new_msg['From'] = verified_sender_email
    new_msg['To'] = ', '.join(list(forwarding_addresses))  # Join multiple addresses with a comma

    # Attach the original message as an application/octet-stream MIME part
    part = MIMEApplication(original_msg.as_string())
    part.add_header('Content-Disposition', 'attachment', filename="forwarded_message.eml")
    new_msg.attach(part)

    # Convert the new message to a string
    email_string = new_msg.as_string()

    ses.send_raw_email(
        Source=verified_sender_email,
        Destinations=list(forwarding_addresses),
        RawMessage={'Data': email_string}
    )
