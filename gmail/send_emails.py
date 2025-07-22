from email.mime.text import MIMEText
import base64

def create_message(to, subject, body):
    message = MIMEText(body)
    message['to'] = to
    message['subject'] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {'raw': raw}

def send_email(service, to, subject, body):
    message = create_message(to, subject, body)
    send_message = service.users().messages().send(userId="me", body=message).execute()
    print(f"📤 Email sent to {to}! ID: {send_message['id']}")
