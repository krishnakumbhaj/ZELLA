import os
import re
import json
import pickle
import streamlit as st
from datetime import datetime
from dotenv import load_dotenv
import base64
from email.mime.text import MIMEText

# Google Auth imports
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser

# Load .env variables
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

# Gmail API scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 
          'https://www.googleapis.com/auth/gmail.send']

# File path for saving chat history
CHAT_HISTORY_FILE = "chat_history.json"

# Gmail Authentication Functions
def authenticate_gmail():
    """Authenticate and return Gmail service object"""
    creds = None
    
    # The file token.pickle stores the user's access and refresh tokens.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                st.warning(f"Token refresh failed: {e}")
                # Delete the invalid token file
                if os.path.exists('token.pickle'):
                    os.remove('token.pickle')
                creds = None
        
        if not creds:
            # Check if credentials.json exists
            if not os.path.exists('credentials.json'):
                raise FileNotFoundError(
                    "credentials.json not found. Please download it from Google Cloud Console."
                )
            
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            except Exception as e:
                raise Exception(f"OAuth flow failed: {e}")
        
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    return build('gmail', 'v1', credentials=creds)

def get_unread_emails(service, max_results=5):
    """Get unread emails from Gmail"""
    try:
        # Get unread messages
        results = service.users().messages().list(
            userId='me', 
            q='is:unread',
            maxResults=max_results
        ).execute()
        
        messages = results.get('messages', [])
        
        if not messages:
            return []
        
        email_list = []
        
        for message in messages:
            try:
                # Get message details
                msg = service.users().messages().get(
                    userId='me', 
                    id=message['id'],
                    format='full'
                ).execute()
                
                # Extract email data
                headers = msg['payload'].get('headers', [])
                
                # Get sender, subject, and date
                sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
                
                # Get email snippet
                snippet = msg.get('snippet', 'No preview available')
                
                email_list.append({
                    'sender': sender,
                    'subject': subject,
                    'date': date,
                    'snippet': snippet,
                    'id': message['id']
                })
                
            except Exception as e:
                st.warning(f"Error processing message: {e}")
                continue
        
        return email_list
        
    except HttpError as error:
        st.error(f"Gmail API error: {error}")
        return []
    except Exception as e:
        st.error(f"Error fetching emails: {e}")
        return []

def send_email_with_gmail(service, to_email, subject, body):
    """Send email using Gmail API"""
    try:
        # Create message
        message = MIMEText(body)
        message['to'] = to_email
        message['subject'] = subject
        
        # Encode message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        
        # Send email
        send_message = service.users().messages().send(
            userId='me',
            body={'raw': raw_message}
        ).execute()
        
        return f"Email sent successfully! Message ID: {send_message['id']}"
        
    except HttpError as error:
        return f"Gmail API error: {error}"
    except Exception as e:
        return f"Error sending email: {e}"

def test_gmail_connection(service):
    """Test Gmail API connection"""
    try:
        if service:
            # Try to get user profile
            profile = service.users().getProfile(userId='me').execute()
            return f"✅ Connected as: {profile.get('emailAddress')}"
        else:
            return "❌ Gmail service not initialized"
    except Exception as e:
        return f"❌ Connection test failed: {str(e)}"

# Chat persistence functions
def load_chat_history():
    """Load chat history from JSON file"""
    try:
        if os.path.exists(CHAT_HISTORY_FILE):
            with open(CHAT_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        st.error(f"Error loading chat history: {e}")
    return {"sessions": []}

def save_chat_history(chat_data):
    """Save chat history to JSON file"""
    try:
        with open(CHAT_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(chat_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        st.error(f"Error saving chat history: {e}")

def create_new_session():
    """Create a new chat session"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "title": f"Chat - {timestamp}",
        "timestamp": timestamp,
        "messages": []
    }

def save_current_session():
    """Save current session to history"""
    if st.session_state.messages:
        chat_data = load_chat_history()
        
        # Update existing session or create new one
        session_exists = False
        for session in chat_data["sessions"]:
            if session["id"] == st.session_state.current_session_id:
                session["messages"] = st.session_state.messages
                session["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # Update title with first user message if available
                if st.session_state.messages and st.session_state.messages[0]["role"] == "user":
                    first_msg = st.session_state.messages[0]["content"][:30] + "..." if len(st.session_state.messages[0]["content"]) > 30 else st.session_state.messages[0]["content"]
                    session["title"] = first_msg
                session_exists = True
                break
        
        if not session_exists:
            new_session = create_new_session()
            new_session["id"] = st.session_state.current_session_id
            new_session["messages"] = st.session_state.messages
            if st.session_state.messages and st.session_state.messages[0]["role"] == "user":
                first_msg = st.session_state.messages[0]["content"][:30] + "..." if len(st.session_state.messages[0]["content"]) > 30 else st.session_state.messages[0]["content"]
                new_session["title"] = first_msg
            chat_data["sessions"].append(new_session)
        
        # Keep only last 20 sessions
        if len(chat_data["sessions"]) > 20:
            chat_data["sessions"] = chat_data["sessions"][-20:]
        
        save_chat_history(chat_data)

# Page configuration
st.set_page_config(
    page_title="ZELLA",
    page_icon="🤖",
    layout="wide"
)

# Initialize session state for Streamlit
if "messages" not in st.session_state:
    st.session_state.messages = []

if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = load_chat_history()

if "message_history" not in st.session_state:
    st.session_state.message_history = [
        SystemMessage(content="You are a formal, helpful assistant. Be polite, answer professionally, and remember user's name if they tell you.")
    ]

if "llm" not in st.session_state:
    if not api_key:
        st.error("❌ GOOGLE_API_KEY not found in environment variables!")
        st.stop()
    st.session_state.llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=api_key)

if "parser" not in st.session_state:
    st.session_state.parser = StrOutputParser()

# Gmail service initialization with better error handling
if "gmail_service" not in st.session_state:
    try:
        # Check for credentials file first
        if not os.path.exists('credentials.json'):
            st.error("❌ credentials.json file not found!")
            st.info("📝 **Setup Instructions:**")
            st.markdown("""
            1. Go to [Google Cloud Console](https://console.cloud.google.com/)
            2. Create a new project or select existing one
            3. Enable Gmail API
            4. Create OAuth 2.0 credentials (Desktop Application)
            5. Download the credentials.json file
            6. Place it in your app's root directory
            7. Restart the application
            """)
            st.session_state.gmail_service = None
        else:
            with st.spinner("🔐 Authenticating with Gmail..."):
                st.session_state.gmail_service = authenticate_gmail()
            st.success("✅ Gmail authentication successful!")
    except FileNotFoundError as e:
        st.error(f"❌ Missing credentials file: {e}")
        st.session_state.gmail_service = None
    except Exception as e:
        st.error(f"❌ Gmail authentication failed: {e}")
        st.info("💡 **Troubleshooting:**")
        st.markdown("""
        - Try deleting `token.pickle` file and restart
        - Ensure Gmail API is enabled in Google Cloud Console
        - Check if your email is added as a test user
        - Verify credentials.json is valid
        """)
        st.session_state.gmail_service = None

# Email approval session states
if "pending_email" not in st.session_state:
    st.session_state.pending_email = None

if "email_preview_mode" not in st.session_state:
    st.session_state.email_preview_mode = False

if "email_modifications" not in st.session_state:
    st.session_state.email_modifications = ""

# Enhanced email functions
def generate_email_with_ai(user_input):
    """Generate complete email content using AI based on user request"""
    try:
        # Create a comprehensive prompt for email generation
        email_generation_prompt = f"""
        Based on the user's request, generate a complete email with all necessary details.
        
        User request: "{user_input}"
        
        Please analyze the request and generate a professional email. Return ONLY a valid JSON object with these fields:
        {{
            "to": "recipient email address (extract from the request)",
            "subject": "appropriate email subject line",
            "body": "complete, well-formatted email body with proper greeting, content, and closing"
        }}
        
        Guidelines for email generation:
        1. Extract the recipient email address from the request
        2. Create an appropriate subject line based on the content
        3. Write a complete, professional email body including:
           - Proper greeting (Dear [Name]/Hello/Hi)
           - Main content based on user's request
           - Appropriate closing (Best regards, Thank you, etc.)
           - Professional tone unless specified otherwise
        4. Make the email complete and ready to send
        
        IMPORTANT: Return ONLY the JSON object with no additional text or formatting.
        """
        
        # Get AI response for email generation
        generation_response = st.session_state.llm.invoke([HumanMessage(content=email_generation_prompt)])
        generated_text = st.session_state.parser.invoke(generation_response)
        
        # Clean up the response - remove markdown formatting if present
        clean_text = generated_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()
        
        # Try to parse JSON from response
        try:
            # Look for JSON in the response
            json_start = clean_text.find('{')
            json_end = clean_text.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                json_str = clean_text[json_start:json_end]
                email_details = json.loads(json_str)
                
                # Validate that we have the required fields
                if not email_details.get('to'):
                    return None, "⚠️ Could not determine recipient email address. Please specify who should receive this email."
                
                if not email_details.get('subject'):
                    email_details['subject'] = "Message from ZELLA Assistant"  # Default subject
                
                if not email_details.get('body'):
                    return None, "⚠️ Could not generate email content. Please provide more details about what you want to say."
                
                return email_details, None
            else:
                # Try direct JSON parsing if no braces found in substring
                try:
                    email_details = json.loads(clean_text)
                    return email_details, None
                except:
                    return None, "Could not parse email response. Please try rephrasing your request."
        except json.JSONDecodeError as e:
            return None, f"Error processing email generation. Please try rephrasing your request."
    except Exception as e:
        return None, f"Error generating email: {str(e)}"

def is_email_request(text: str) -> bool:
    """Enhanced email request detection"""
    text_lower = text.lower()
    email_keywords = [
        "send email", "mail to", "write email", "send a mail", 
        "compose email", "email to", "send an email", "email",
        "write a mail", "compose a mail"
    ]
    
    # Check for keywords
    keyword_match = any(keyword in text_lower for keyword in email_keywords)
    
    # Check for email address pattern
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    has_email = bool(re.search(email_pattern, text))
    
    return keyword_match or (has_email and any(word in text_lower for word in ["send", "mail", "write"]))

def is_read_email_request(text: str) -> bool:
    text = re.sub(r"[^\w\s]", "", text.lower())
    keywords = [
        "read email", "show inbox", "unread emails", "recent emails",
        "check mail", "read my messages", "latest emails",
        "fetch emails", "list my emails", "show me emails", 
        "provide me the recent emails", "read my inbox"
    ]
    return any(k in text for k in keywords)

def is_email_modification_request(text: str) -> bool:
    """Check if user wants to modify the pending email"""
    modification_keywords = [
        "change", "modify", "edit", "update", "alter", "revise",
        "make it", "can you", "please change", "update the"
    ]
    return any(keyword in text.lower() for keyword in modification_keywords)

def update_history(role, content):
    if role == "user":
        st.session_state.message_history.append(HumanMessage(content=content))
    else:
        st.session_state.message_history.append(AIMessage(content=content))
    while len(st.session_state.message_history) > 8:
        st.session_state.message_history.pop(1)

def process_chatbot_input(user_input):
    """Process user input using the same logic as your original chatbot"""
    
    # Handle email sending with approval workflow
    if is_email_request(user_input) and not st.session_state.email_preview_mode:
        try:
            # Generate complete email using AI
            email_details, error = generate_email_with_ai(user_input)
            
            if error:
                return f"❌ {error}", "error"
            
            # Store pending email for approval
            st.session_state.pending_email = email_details
            st.session_state.email_preview_mode = True
            
            return email_details, "email_preview"
        except Exception as e:
            return f"❌ Email generation error: {str(e)}", "error"
    
    # Handle email modifications when in preview mode
    elif st.session_state.email_preview_mode and is_email_modification_request(user_input):
        try:
            # Use AI to modify the email based on user request
            modification_prompt = f"""
            Current email draft:
            To: {st.session_state.pending_email.get('to', '')}
            Subject: {st.session_state.pending_email.get('subject', '')}
            Body: {st.session_state.pending_email.get('body', '')}
            
            User modification request: "{user_input}"
            
            Please modify the email according to the user's request and return the complete updated email in JSON format:
            {{
                "to": "recipient email (keep same unless user wants to change)",
                "subject": "updated or original subject",
                "body": "complete updated email body with proper formatting, greeting, content, and closing"
            }}
            
            Guidelines for modifications:
            1. Keep the original structure unless specifically asked to change
            2. Maintain professional tone unless asked otherwise
            3. Make sure the email remains complete and well-formatted
            4. Apply the requested changes while keeping the email coherent
            5. Include proper greeting and closing in the body
            
            Return only the JSON object.
            """
            
            modification_response = st.session_state.llm.invoke([HumanMessage(content=modification_prompt)])
            modified_text = st.session_state.parser.invoke(modification_response)
            
            # Parse the modified email
            json_start = modified_text.find('{')
            json_end = modified_text.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                json_str = modified_text[json_start:json_end]
                modified_email = json.loads(json_str)
                st.session_state.pending_email = modified_email
                return modified_email, "email_preview"
            else:
                return "❌ Could not process modifications. Please try again with more specific instructions.", "error"
                
        except Exception as e:
            return f"❌ Modification error: {str(e)}", "error"

    # Handle email reading
    elif is_read_email_request(user_input):
        try:
            if not st.session_state.gmail_service:
                return "❌ Gmail service not available. Please check authentication.", "error"
            
            emails = get_unread_emails(st.session_state.gmail_service)
            if emails:
                return emails, "emails"
            else:
                return "📭 No unread emails found.", "info"
        except Exception as e:
            return f"❌ Error reading emails: {e}", "error"

    # Normal Gemini QA response
    else:
        update_history("user", user_input)
        try:
            raw_response = st.session_state.llm.invoke(st.session_state.message_history)
            parsed_answer = st.session_state.parser.invoke(raw_response)
            update_history("ai", parsed_answer)
            return f"ZELLA: {parsed_answer}", "ai"
        except Exception as e:
            error_msg = f"⚠️ ZELLA error: {e}"
            return error_msg, "error"

def send_approved_email():
    """Send the approved email"""
    try:
        if not st.session_state.gmail_service:
            return "❌ Gmail service not available. Please check authentication."
        
        if st.session_state.pending_email:
            result = send_email_with_gmail(
                st.session_state.gmail_service,
                st.session_state.pending_email['to'],
                st.session_state.pending_email['subject'],
                st.session_state.pending_email['body']
            )
            
            # Reset email preview mode
            st.session_state.pending_email = None
            st.session_state.email_preview_mode = False
            
            return f"✅ {result}"
        else:
            return "❌ No pending email to send."
    except Exception as e:
        return f"❌ Error sending email: {str(e)}"

def cancel_email():
    """Cancel the pending email"""
    st.session_state.pending_email = None
    st.session_state.email_preview_mode = False
    return "❌ Email cancelled."

def streamlit_chatbot():
    """Streamlit version of your chatbot function"""
    
    st.title("🤖 ZELLA")
    st.markdown("Ask anything, send emails, or read your inbox!")
    
    # Gmail Status Banner
    if st.session_state.gmail_service:
        with st.container():
            col1, col2 = st.columns([3, 1])
            with col1:
                st.success("🔗 Gmail Connected - Email features available!")
            with col2:
                if st.button("🧪 Test Connection"):
                    result = test_gmail_connection(st.session_state.gmail_service)
                    st.info(result)
    else:
        st.warning("⚠️ Gmail not connected - Email features disabled")
    
    # Email preview banner - ENHANCED VERSION
    if st.session_state.email_preview_mode and st.session_state.pending_email:
        # Create a very prominent alert
        st.error("🚨 EMAIL PREVIEW MODE - PLEASE REVIEW BEFORE SENDING! 🚨")
        
        # Create a container with colored background
        with st.container():
            st.markdown("### 📧 Email Ready for Review")
            
            # Create columns for better layout
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # Email details in an info box
                st.info(f"**📨 To:** {st.session_state.pending_email.get('to', 'Unknown')}")
                st.info(f"**📋 Subject:** {st.session_state.pending_email.get('subject', 'Unknown')}")
                
                # Email body in a text area
                st.markdown("**📄 Complete Email Message:**")
                email_body = st.session_state.pending_email.get('body', 'No content')
                
                st.text_area(
                    label="Email Content Preview:",
                    value=email_body,
                    height=200,
                    disabled=True,
                    key="email_preview_display"
                )
            
            with col2:
                st.markdown("### 🎯 Actions")
                
                # Send button - make it prominent
                if st.button("✅ **SEND EMAIL**", type="primary", use_container_width=True, key="send_email_btn"):
                    result = send_approved_email()
                    st.session_state.messages.append({"role": "assistant", "content": result})
                    save_current_session()
                    st.rerun()
                
                # Cancel button
                if st.button("❌ **CANCEL**", use_container_width=True, key="cancel_email_btn"):
                    result = cancel_email()
                    st.session_state.messages.append({"role": "assistant", "content": result})
                    save_current_session()
                    st.rerun()
                
                st.markdown("---")
                st.markdown("**💡 Need Changes?**")
                st.caption("Type modifications in the chat below")
                st.markdown("**Examples:**")
                st.caption("• 'Make it more formal'")
                st.caption("• 'Change the subject'")
                st.caption("• 'Add more details'")
        
        st.markdown("---")
    
    # Sidebar with chat history and controls
    with st.sidebar:
        st.header("💬 Chat History")
        
        # Gmail connection status in sidebar
        if st.session_state.gmail_service:
            st.success("✅ Gmail Connected")
        else:
            st.error("❌ Gmail Disconnected")
        
        # New Chat button
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("🆕 New Chat", use_container_width=True):
                # Save current session before creating new one
                save_current_session()
                # Reset for new chat
                st.session_state.messages = []
                st.session_state.current_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
                st.session_state.message_history = [
                    SystemMessage(content="You are a formal, helpful assistant. Be polite, answer professionally, and remember user's name if they tell you.")
                ]
                # Reset email states
                st.session_state.pending_email = None
                st.session_state.email_preview_mode = False
                st.rerun()
        
        with col2:
            if st.button("💾 Save Chat", use_container_width=True):
                save_current_session()
                st.success("Chat saved!")
                st.session_state.chat_history = load_chat_history()  # Refresh
        
        # Display saved chats
        st.subheader("📚 Saved Chats")
        
        # Refresh chat history
        current_chat_history = load_chat_history()
        
        if current_chat_history["sessions"]:
            # Sort by timestamp (newest first)
            sorted_sessions = sorted(current_chat_history["sessions"], key=lambda x: x["timestamp"], reverse=True)
            
            for session in sorted_sessions:
                # Create a container for each chat session
                with st.container():
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        # Chat title and timestamp
                        if st.button(
                            f"💬 {session['title']}",
                            key=f"load_{session['id']}",
                            help=f"Load chat from {session['timestamp']}",
                            use_container_width=True
                        ):
                            # Save current session first
                            save_current_session()
                            # Load selected session
                            st.session_state.messages = session["messages"]
                            st.session_state.current_session_id = session["id"]
                            # Reset email states when switching chats
                            st.session_state.pending_email = None
                            st.session_state.email_preview_mode = False
                            # Rebuild message history for AI context
                            st.session_state.message_history = [
                                SystemMessage(content="You are a formal, helpful assistant. Be polite, answer professionally, and remember user's name if they tell you.")
                            ]
                            for msg in session["messages"]:
                                if msg["role"] == "user":
                                    st.session_state.message_history.append(HumanMessage(content=msg["content"]))
                                elif msg["role"] == "assistant":
                                    st.session_state.message_history.append(AIMessage(content=msg["content"]))
                            st.rerun()
                    
                    with col2:
                        # Delete button
                        if st.button("🗑️", key=f"del_{session['id']}", help="Delete this chat"):
                            # Remove session from history
                            current_chat_history["sessions"] = [s for s in current_chat_history["sessions"] if s["id"] != session["id"]]
                            save_chat_history(current_chat_history)
                            st.session_state.chat_history = current_chat_history
                            st.rerun()
                    
                    # Show preview of first message
                    if session["messages"]:
                        first_msg = session["messages"][0]["content"]
                        preview = first_msg[:50] + "..." if len(first_msg) > 50 else first_msg
                        st.caption(f"🕒 {session['timestamp'][:16]} | {preview}")
                    
                    st.divider()
        else:
            st.info("No saved chats yet. Start chatting and save your conversations!")

    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input
    if prompt := st.chat_input("Type your message here... (or 'exit' to quit)"):
        
        # Handle exit command
        if prompt.lower() in ["exit", "quit"]:
            st.success("👋 Session ended! Refresh to start again.")
            st.stop()
        
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Process user input using your original chatbot logic
        with st.chat_message("assistant"):
            with st.spinner("Processing..."):
                response, response_type = process_chatbot_input(prompt)
            
            # Handle email preview
            if response_type == "email_preview" and isinstance(response, dict):
                success_msg = "✅ **Email Generated Successfully!** Please review the email preview above and click 'SEND EMAIL' when ready."
                st.markdown(success_msg)
                st.session_state.messages.append({"role": "assistant", "content": success_msg})
                # Force UI refresh to show preview
                st.rerun()
            
            # Handle email modification
            elif response_type == "email_preview" and st.session_state.email_preview_mode:
                modification_msg = "✅ **Email Updated!** Please review the changes in the preview above."
                st.markdown(modification_msg)
                st.session_state.messages.append({"role": "assistant", "content": modification_msg})
                # Force UI refresh to show updated preview
                st.rerun()
            
            # Special formatting for emails
            elif response_type == "emails" and isinstance(response, list):
                st.markdown("📬 **Recent Unread Emails:**")
                
                for i, email in enumerate(response, 1):
                    # Create an expandable card for each email
                    with st.expander(f"📨 Email #{i} - {email.get('subject', 'No Subject')}", expanded=False):
                        col1, col2 = st.columns([1, 3])
                        
                        with col1:
                            st.markdown("**👤 From:**")
                            st.markdown("**📅 Date:**")
                            st.markdown("**📋 Subject:**")
                            
                        with col2:
                            st.markdown(f"`{email.get('sender', 'Unknown')}`")
                            st.markdown(f"`{email.get('date', 'Unknown')}`")
                            st.markdown(f"`{email.get('subject', 'No Subject')}`")
                        
                        st.markdown("**📄 Preview:**")
                        snippet = email.get('snippet', 'No preview available')
                        st.markdown(f"_{snippet}_")
                
                # Summary at the bottom
                st.info(f"📊 Total unread emails: **{len(response)}**")
                
                # Save the formatted response for chat history
                formatted_response = f"📬 Displayed {len(response)} unread emails with detailed view"
                st.session_state.messages.append({"role": "assistant", "content": formatted_response})
            else:
                # Regular text response formatting
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
            
            # Auto-save after each interaction
            save_current_session()

    # Footer
    st.markdown("---")
    st.markdown("**🔧 Quick Actions:**")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("📧 Check Emails", use_container_width=True):
            if st.session_state.gmail_service:
                with st.spinner("Fetching emails..."):
                    emails = get_unread_emails(st.session_state.gmail_service)
                    if emails:
                        st.session_state.messages.append({"role": "user", "content": "Check my emails"})
                        formatted_response = f"📬 Found {len(emails)} unread emails"
                        st.session_state.messages.append({"role": "assistant", "content": formatted_response})
                        save_current_session()
                        st.rerun()
                    else:
                        st.info("📭 No unread emails found.")
            else:
                st.error("❌ Gmail not connected")
    
    with col2:
        if st.button("🆕 Quick Email", use_container_width=True):
            st.session_state.messages.append({"role": "user", "content": "Help me compose an email"})
            response = "📝 I'll help you compose an email! Please tell me:\n\n1. **Who** should receive it (email address)\n2. **What** is the subject\n3. **What** message you want to send\n\nYou can say something like: 'Send an email to john@example.com about the meeting tomorrow'"
            st.session_state.messages.append({"role": "assistant", "content": response})
            save_current_session()
            st.rerun()
    
    with col3:
        if st.button("🔄 Refresh Gmail", use_container_width=True):
            try:
                if os.path.exists('token.pickle'):
                    os.remove('token.pickle')
                    st.session_state.gmail_service = None
                    st.info("🔄 Gmail token refreshed. Please restart the app.")
                else:
                    st.info("ℹ️ No token file found to refresh.")
            except Exception as e:
                st.error(f"❌ Error refreshing token: {e}")
    
    with col4:
        if st.button("ℹ️ Help", use_container_width=True):
            help_text = """
            **🤖 ZELLA Help Guide**
            
            **📧 Email Commands:**
            - "Send email to john@example.com about meeting"
            - "Read my emails" or "Check inbox"
            - "Compose email to team about project update"
            
            **💬 Chat Features:**
            - Ask any question
            - Get help with tasks
            - Generate content
            
            **🔧 Setup Requirements:**
            - credentials.json from Google Cloud Console
            - Gmail API enabled
            - GOOGLE_API_KEY in .env file
            
            **🚨 Email Preview:**
            - All emails are previewed before sending
            - You can modify emails before sending
            - Use "Make it more formal" or "Change subject" to modify
            """
            st.session_state.messages.append({"role": "user", "content": "Show help"})
            st.session_state.messages.append({"role": "assistant", "content": help_text})
            save_current_session()
            st.rerun()

if __name__ == "__main__":
    streamlit_chatbot()
