import os
import json
import boto3
import urllib.parse
import traceback
from email import policy
from email.parser import BytesParser
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.utils import parseaddr, getaddresses

s3 = boto3.client('s3')
ses = boto3.client('ses', region_name='us-east-1')

def get_rules():
    return {
        'an@': ['anmichel@gmail.com'],
        'dani@': ['danielruiz2000@gmail.com'],
        '@preferredframe.com': ['anmichel@gmail.com'],
        '@wildnloyal.com': ['anmichel@gmail.com'],
        '@cinemestizo.com': ['anmichel@gmail.com', 'danielruiz2000@gmail.com']
    }

def process_event(event, context=None):
    print(json.dumps(event))
    try:
        records = event['Records']
        s3_event = records[0]['s3']
        process_s3_event(s3_event)
    except Exception as e:
        print(f'Error processing event: {str(e)}')
        traceback.print_exc()

def process_s3_event(s3_event):
    bucket = s3_event['bucket']['name']
    key = urllib.parse.unquote_plus(s3_event['object']['key'], encoding='utf-8')
    local_filename = os.path.join('/tmp', os.path.basename(key))
    s3.download_file(bucket, key, local_filename)

    with open(local_filename, 'rb') as file:
        msg = BytesParser(policy=policy.default).parse(file)

    rules = get_rules()

    def extract_addresses(address_field):
        return getaddresses(msg.get_all(address_field, []))

    def update_forwarding_lists(address_list, forwarding_list):
        for name, email in address_list:
            domain = email.split('@')[-1]
            for rule, forwards in rules.items():
                if email.startswith(rule) or ('@' + domain) == rule:
                    forwarding_list.update(forwards)

    forwarding_to = set()
    forwarding_cc = set()
    forwarding_bcc = set()

    addresses_list = [
        extract_addresses('to'),
        extract_addresses('cc'),
        extract_addresses('bcc')
    ]
    forwarding_lists = [forwarding_to, forwarding_cc, forwarding_bcc]

    for i, addresses in enumerate(addresses_list):
        update_forwarding_lists(addresses, forwarding_lists[i])

    if not any([forwarding_to, forwarding_cc, forwarding_bcc]):
        print("No forwarding rules matched.")
        return

    send_response_email({
        'to_addresses': list(forwarding_to),
        'cc_addresses': list(forwarding_cc),
        'bcc_addresses': list(forwarding_bcc),
        'reply_to_addresses': [parseaddr(msg['From'])[1]],
        'subject': msg['Subject'],
        'original_msg': msg,
        'message_id': msg['Message-ID'],
    })

def send_response_email(params):
    ses_from_address = "forwarder@preferredframe.com"
    to_addresses = params['to_addresses']
    cc_addresses = params.get('cc_addresses', [])
    bcc_addresses = params.get('bcc_addresses', [])
    reply_to_addresses = params['reply_to_addresses']
    subject = params['subject']
    original_msg = params['original_msg']
    message_id = params['message_id']

    # Create a new MIME message
    forward_msg = MIMEMultipart('mixed')
    forward_msg['Subject'] = f"Fwd: {subject}"
    forward_msg['From'] = ses_from_address
    forward_msg['To'] = ', '.join(to_addresses)
    if cc_addresses:
        forward_msg['Cc'] = ', '.join(cc_addresses)
    forward_msg['Reply-To'] = ', '.join(reply_to_addresses)
    forward_msg['In-Reply-To'] = message_id
    forward_msg['References'] = message_id

    # Create a new MIME message part for the forwarded email body
    forward_body = MIMEMultipart('alternative')

    # Add the original message as a MIME message part
    forward_body.attach(original_msg)

    # Attach the forward body to the main message
    forward_msg.attach(forward_body)

    # Send the email
    ses.send_raw_email(
        Source=ses_from_address,
        Destinations=to_addresses + cc_addresses + bcc_addresses,
        RawMessage={'Data': forward_msg.as_string()}
    )
