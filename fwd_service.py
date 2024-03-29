import os
import json
import boto3
import urllib.parse
import traceback
from email import policy
from email.parser import BytesParser
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr, getaddresses

print('3')

s3 = boto3.client('s3')
ses = boto3.client('ses', region_name='us-east-1')

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

    original_recipient_domain = get_original_domain(msg)
    if original_recipient_domain not in managed_domains:
        print('Skipping since not in managed domains')
        return  # Skip non-managed domains

    forwarding_to, forwarding_cc = apply_forwarding_rules(msg)

    # Extract additional recipients from the 'To' field
    to_addresses = getaddresses(msg.get_all('to', []))
    cc_addresses = getaddresses(msg.get_all('cc', []))

    # Combine the forwarding addresses with the addresses in the 'To' field
    forwarding_to.update(address[1] for address in to_addresses)
    forwarding_cc.update(address[1] for address in cc_addresses)

    send_response_email(msg, {
        'to_addresses': list(forwarding_to),
        'cc_addresses': list(forwarding_cc),
    }, original_recipient_domain=original_recipient_domain)



def apply_forwarding_rules(msg):
    rules = get_rules()
    forwarding_to = set()
    forwarding_cc = set()
    catch_all = rules.get('_catch_all_', 'anmichel@gmail.com')

    # Split handling of 'To' and 'Cc' to properly fill forwarding_cc
    to_addresses = getaddresses(msg.get_all('to', []))
    cc_addresses = getaddresses(msg.get_all('cc', []))

    print(to_addresses, cc_addresses)

    def apply_rules(addresses):
        # Process addressess according to get_rules()
        forwarding = set()
        for name, email in addresses:
            email_domain = email.split('@')[-1]
            if email_domain not in managed_domains:
                print('Skipping since not in managed domains')
                continue # Skip non-managed domains
            for rule, forward_email_list in rules.items():
                type(email)
                print(f'match {rule} in {email}?')
                if rule in email:
                    forwarding.update(forward_email_list)
                    break
            else:
                    forwarding.update(rules.get('_catch_all_'))

        return forwarding

    forwarding_to = apply_rules(to_addresses)
    forwarding_cc = apply_rules(cc_addresses)

    return forwarding_to, forwarding_cc

def get_original_domain(msg):
    # Default to a known domain if needed
    recipient_address = parseaddr(msg['To'])[1]
    return recipient_address.split('@')[-1]

def send_response_email(original_msg, params, original_recipient_domain):
    sender_name, sender_email = parseaddr(original_msg['From'])
    original_to_name, original_to_address = parseaddr(original_msg['To'])

    # Define the sender information for the SES address
    ses_from_address = f"{sender_name} ({sender_email}) <fwdr@{original_recipient_domain}>"

    # Print original message details
    print("Original FROM:", original_msg['From'])
    print("Original TO:", original_msg['To'])
    print("Original SUBJECT:", original_msg['Subject'])

    # Create a new MIME message
    forward_msg = MIMEMultipart('mixed')
    forward_msg['Subject'] = original_msg['Subject']
    forward_msg['From'] = ses_from_address
    forward_msg['To'] = ', '.join(params.get('to_addresses', []))
    forward_msg['Cc'] = ', '.join(params.get('cc_addresses', []))
    forward_msg['Reply-To'] = sender_email
    forward_msg['In-Reply-To'] = original_msg['Message-ID']
    forward_msg['References'] = original_msg['Message-ID']

    # Create a new MIME message part for the forwarded email body
    forward_body = MIMEMultipart('alternative')

    # Define the original sender indication
    original_sender_name = sender_name if sender_name else sender_email
    original_sender_indication = f"--- {original_sender_name} wrote: ---\n"

    # Define the original sender indication with <p> tags for HTML version
    original_sender_indication_html = f"<p>{original_sender_indication}</p>\n"

    # Attach the original sender indication to both plain text and HTML parts
    for content_type, indication in [('plain', original_sender_indication), ('html', original_sender_indication_html)]:
        forward_body.attach(MIMEText(indication, content_type))

    # Add the original message as a MIME message part
    forward_body.attach(original_msg)

    # Attach the forward body to the main message
    forward_msg.attach(forward_body)

    # Print forwarded message details
    print("Forwarded FROM:", ses_from_address)
    print("Forwarded TO:", ', '.join(params.get('to_addresses', [])))
    print("Forwarded SUBJECT:", original_msg['Subject'])

    # Send the email
    ses.send_raw_email(
        Source=ses_from_address,
        Destinations=params.get('to_addresses', []) + params.get('cc_addresses', []) + params.get('bcc_addresses', []),
        RawMessage={'Data': forward_msg.as_string()}
    )
