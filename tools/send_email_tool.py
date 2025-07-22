from langchain_core.tools import tool
from gmail.send_emails import send_email
from gmail.auth import authenticate_gmail

@tool
def send_email_tool(to: str, subject: str, body: str) -> str:
    """
    Sends an email using Gmail API.
    Args:
        to: Recipient email
        subject: Email subject
        body: Email body
    Returns:
        A success message with email ID.
    """
    service = authenticate_gmail()
    send_email(service, to, subject, body)
    return f"✅ Email sent to {to} \n subject '{subject}'\n Email body: {body}..."  # Show first 50 chars of body
