import json
import boto3
import traceback
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
        forwarding_addresses.update(rules.get('_catch_all_', default_catch_all_email))

    return forwarding_addresses

def send_response_email(original_msg, forwarding_addresses, intended_recipient):
    sender_name, sender_email = parseaddr(original_msg['From'])
    recipient_domain = intended_recipient.split('@')[-1]
    ses_from_address = f"{sender_name} ({sender_email}) <fwdr@{recipient_domain}>"

    # Log the forwarding details
    print(f"Original FROM: {original_msg['From']}")
    print(f"Original TO: {original_msg['To']}")
    print(f"Original SUBJECT: {original_msg['Subject']}")
    print(f"Forwarding to addresses: {', '.join(forwarding_addresses)}")
    print(f"Intended recipient domain: {recipient_domain}")

    # Simplified content creation with minimal HTML formatting
    forwarding_note = f"Forwarded message from {sender_name} ({sender_email}) for {intended_recipient}:"
    print("--- Forward section ---")
    print(forwarding_note)

    # For HTML, simply wrap the note in <p> tags
    html_content = f"<p>{forwarding_note}</p>"

    # Create the new forwarding email as a mixed MIME message
    forward_msg = MIMEMultipart('mixed')
    forward_msg['Subject'] = f"Fwd: {original_msg['Subject']}"
    forward_msg['From'] = ses_from_address
    forward_msg['To'] = ', '.join(forwarding_addresses)

    # Attach both plain text and HTML parts within an 'alternative' MIME part
    msg_body = MIMEMultipart('alternative')
    text_part = MIMEText(forwarding_note, 'plain')
    html_part = MIMEText(html_content, 'html')

    msg_body.attach(text_part)
    msg_body.attach(html_part)
    forward_msg.attach(msg_body)

    # Correctly attaching the original email
    original_email_part = MIMEApplication(original_msg.as_string(), 'rfc822; name="original_message.eml"')
    encode_7or8bit(original_email_part)
    original_email_part.add_header('Content-Disposition', 'attachment; filename="original_message.eml"')
    forward_msg.attach(original_email_part)

    ses.send_raw_email(
        Source=ses_from_address,
        Destinations=list(forwarding_addresses),
        RawMessage={"Data": forward_msg.as_string()}
    )
