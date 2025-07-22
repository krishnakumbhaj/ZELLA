from gmail.auth import authenticate_gmail

def get_unread_emails(max_results=5, print_output=True):
    service = authenticate_gmail()

    results = service.users().messages().list(
        userId='me',
        labelIds=['INBOX', 'UNREAD'],
        maxResults=max_results
    ).execute()

    messages = results.get('messages', [])
    email_data = []

    if not messages:
        if print_output:
            print("📭 No unread messages found.")
        return []

    for msg in messages:
        msg_id = msg['id']
        msg_detail = service.users().messages().get(userId='me', id=msg_id).execute()

        headers = msg_detail['payload']['headers']
        subject = sender = None

        for header in headers:
            if header['name'] == 'Subject':
                subject = header['value']
            elif header['name'] == 'From':
                sender = header['value']

        snippet = msg_detail.get('snippet', '')

        email_data.append({
            'sender': sender or "Unknown",
            'subject': subject or "No Subject",
            'snippet': snippet or "No Preview Available"
        })

        service.users().messages().modify(
            userId='me',
            id=msg_id,
            body={'removeLabelIds': ['UNREAD']}
        ).execute()

    # Pretty print the emails
    if print_output:
        print("\n📬 Recent Unread Emails:\n" + "="*40)
        for i, email in enumerate(email_data, 1):
            print(f"\n📨 Email #{i}")
            print(f"{'-'*30}")
            print(f"📤 From    : {email['sender']}")
            print(f"📌 Subject : {email['subject']}")
            print(f"📝 Snippet : {email['snippet']}")
            print(f"{'-'*30}")

    return email_data
