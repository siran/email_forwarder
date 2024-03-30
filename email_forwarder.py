import json
import boto3
import traceback
from email import message_from_bytes
from email.utils import parseaddr

# Configuration variables
s3 = boto3.client('s3')
ses = boto3.client('ses', region_name='us-east-1')
bucket_name = 'your-email-bucket-name'  # Specify your S3 bucket name here

managed_domains = [
    'preferredframe.com',
    'wildnloyal.com',
    'cinemestizo.com',
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
    recipients = receipt['recipients']

    # The key in S3 is derived from the SES messageId, prefixed with "incoming/"
    key = f"incoming/{messageId}"

    process_ses_s3(bucket_name, key, recipients)

def process_ses_s3(bucket, key, recipients):
    obj = s3.get_object(Bucket=bucket, Key=key)
    email_body = obj['Body'].read()

    msg = message_from_bytes(email_body)

    # Apply forwarding rules for each recipient
    for recipient in recipients:
        forwarding_to, _, _ = apply_forwarding_rules(recipient)
        if forwarding_to:
            send_response_email(msg, {
                'to_addresses': list(forwarding_to),
            }, recipient.split('@')[-1])

def apply_forwarding_rules(recipient):
    rules = get_rules()
    forwarding_to = set()

    domain = recipient.split('@')[-1]
    if domain in managed_domains:
        for rule, forward_emails in rules.items():
            if rule in recipient or rule.split('@')[-1] == domain:
                forwarding_to.update(forward_emails)
                break
        else:
            forwarding_to.update(rules.get('_catch_all_', []))

    return forwarding_to, set(), set()

def send_response_email(original_msg, params, original_recipient_domain):
    sender_name, sender_email = parseaddr(original_msg['From'])
    original_to_name, original_to_address = parseaddr(original_msg['To'])

    ses_from_address = f"{sender_name} ({sender_email}) <fwdr@{original_recipient_domain}>"

    # Sending the email as is
    ses.send_raw_email(
        Source=ses_from_address,
        Destinations=params.get('to_addresses', []),
        RawMessage={'Data': original_msg.as_string()}
    )

print('Function setup complete.')
