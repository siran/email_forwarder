import unittest
from unittest.mock import patch
from fwd_service import apply_forwarding_rules, get_original_domain, send_response_email
from email.message import EmailMessage

class EmailForwardingTestCase(unittest.TestCase):

    def create_email_message(self, to_addresses=None, cc_addresses=None, bcc_addresses=None, from_address='Original Sender <original@sender.com>', subject='Test Email', body='This is a test.'):
        to_addresses = to_addresses if to_addresses else []
        cc_addresses = cc_addresses if cc_addresses else []
        bcc_addresses = bcc_addresses if bcc_addresses else []
        msg = EmailMessage()
        msg['To'] = ', '.join(to_addresses)
        msg['Cc'] = ', '.join(cc_addresses)
        msg['Bcc'] = ', '.join(bcc_addresses)
        msg['From'] = from_address
        msg['Subject'] = subject
        msg.set_content(body)
        return msg

    def test_apply_forwarding_rules_to_addresses(self):
        """Test forwarding logic for 'To' addresses across managed and non-managed domains."""
        msg = self.create_email_message(
            to_addresses=['an@preferredframe.com', 'unknown@example.com'],
            cc_addresses=['dani@wildnloyal.com'],
            bcc_addresses=['user@cinemestizo.com', 'external@nonmanaged.com']
        )
        to, cc, bcc = apply_forwarding_rules(msg)
        self.assertIn('anmichel@gmail.com', to)
        self.assertIn('anmichel@gmail.com', cc)
        self.assertIn('anmichel@gmail.com', bcc)
        self.assertIn('danielruiz2000@gmail.com', bcc)

    def test_skipping_non_managed_domains(self):
        """Ensure emails from non-managed domains are skipped."""
        msg = self.create_email_message(to_addresses=['user@nonmanaged.com'])
        to, cc, bcc = apply_forwarding_rules(msg)
        self.assertEqual(len(to), 0)
        self.assertEqual(len(cc), 0)
        self.assertEqual(len(bcc), 0)

    @patch('email_forwarder.ses.send_raw_email')
    def test_send_response_email(self, mock_send_raw_email):
        """Mock SES sending to verify correct recipients are passed for managed domains."""
        msg = self.create_email_message(to_addresses=['to@preferredframe.com'])
        send_response_email(msg, {'to_addresses': ['anmichel@gmail.com'], 'cc_addresses': [], 'bcc_addresses': []}, 'preferredframe.com')
        mock_send_raw_email.assert_called()
        args, kwargs = mock_send_raw_email.call_args
        self.assertIn('anmichel@gmail.com', kwargs['Destinations'])

    @patch('email_forwarder.ses.send_raw_email')
    def test_from_address_format(self, mock_send_raw_email):
        """Test the 'From' address formatting in the forwarded email by mocking send_raw_email."""
        mock_send_raw_email.return_value = {'MessageId': 'fake-id'}
        original_msg = self.create_email_message(
            to_addresses=['recipient@preferredframe.com'],
            from_address='Original Sender <original@sender.com>',
            subject='Hello',
            body='Test message'
        )

        send_response_email(original_msg, {
            'to_addresses': ['recipient@preferredframe.com'],
            'cc_addresses': [],
            'bcc_addresses': []
        }, original_recipient_domain='preferredframe.com')

        args, kwargs = mock_send_raw_email.call_args
        expected_from_format = 'Original Sender (original@sender.com) <fwdr@preferredframe.com>'
        self.assertIn(expected_from_format, kwargs['Source'], f"From address format is incorrect. Expected {expected_from_format}, got {kwargs['Source']}")

    def test_handling_mixed_domains_in_recipients(self):
        """Test emails with a mix of managed and non-managed domains across 'To', 'Cc', and 'Bcc'."""
        msg = self.create_email_message(
            to_addresses=['managed@preferredframe.com', 'unmanaged@example.com'],
            cc_addresses=['managedcc@wildnloyal.com', 'unmanagedcc@example.com'],
            bcc_addresses=['managedbcc@cinemestizo.com', 'unmanagedbcc@example.com']
        )
        to, cc, bcc = apply_forwarding_rules(msg)
        self.assertTrue('anmichel@gmail.com' in to or 'danielruiz2000@gmail.com' in to)
        self.assertTrue('anmichel@gmail.com' in cc)
        self.assertTrue('anmichel@gmail.com' in bcc or 'danielruiz2000@gmail.com' in bcc)

if __name__ == '__main__':
    unittest.main()
