import os
import re
import json
import streamlit as st
from datetime import datetime
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser

from agent.email_agent import send_email_with_ai
from gmail.auth import authenticate_gmail
from gmail.read_emails import get_unread_emails

# Load .env variables
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

# File path for saving chat history
CHAT_HISTORY_FILE = "chat_history.json"

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
    page_title="Vecna Assistant",
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
    st.session_state.llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=api_key)

if "parser" not in st.session_state:
    st.session_state.parser = StrOutputParser()

if "gmail_service" not in st.session_state:
    try:
        st.session_state.gmail_service = authenticate_gmail()
    except Exception as e:
        st.error(f"Gmail authentication failed: {e}")
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
            "to": "recipient email address (extract or ask for clarification if missing)",
            "subject": "appropriate email subject line",
            "body": "complete, well-formatted email body with proper greeting, content, and closing"
        }}
        
        Guidelines for email generation:
        1. If recipient is not clear, use "RECIPIENT_NEEDED" as placeholder
        2. Create an appropriate subject line based on the content
        3. Write a complete, professional email body including:
           - Proper greeting (Dear [Name]/Hello/Hi)
           - Main content based on user's request
           - Appropriate closing (Best regards, Thank you, etc.)
           - Professional tone unless specified otherwise
        4. If the request lacks specific details, create reasonable content while keeping it professional
        5. Make the email complete and ready to send
        
        Return only the JSON object, no additional text.
        """
        
        # Get AI response for email generation
        generation_response = st.session_state.llm.invoke([HumanMessage(content=email_generation_prompt)])
        generated_text = st.session_state.parser.invoke(generation_response)
        
        # Try to parse JSON from response
        try:
            # Look for JSON in the response
            json_start = generated_text.find('{')
            json_end = generated_text.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                json_str = generated_text[json_start:json_end]
                email_details = json.loads(json_str)
                
                # Validate that we have the required fields
                if not email_details.get('to') or email_details.get('to') == 'RECIPIENT_NEEDED':
                    return None, "⚠️ Please specify the recipient email address. Who should receive this email?"
                
                if not email_details.get('subject'):
                    return None, "⚠️ Could not generate appropriate subject. Please specify the email subject."
                
                if not email_details.get('body'):
                    return None, "⚠️ Could not generate email content. Please provide more details about what you want to say."
                
                return email_details, None
            else:
                return None, "Could not generate email. Please provide more specific details about the recipient, subject, and what you want to communicate."
        except json.JSONDecodeError as e:
            return None, f"Error processing email generation. Please try rephrasing your request. Details: {str(e)}"
    except Exception as e:
        return None, f"Error generating email: {str(e)}"

def is_email_request(text: str) -> bool:
    keywords = ["send email", "mail to", "write email", "send a mail", "compose email", "email to"]
    return any(k in text.lower() for k in keywords)

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

    # Handle email reading (same logic as your chatbot)
    if is_read_email_request(user_input):
        try:
            emails = get_unread_emails()
            if emails:
                return emails, "emails"  # Return raw email data for special formatting
            else:
                return "📭 No unread emails found.", "info"
        except Exception as e:
            return f"❌ Error reading emails: {e}", "error"

    # Normal Gemini QA response (same logic as your chatbot)
    update_history("user", user_input)
    try:
        raw_response = st.session_state.llm.invoke(st.session_state.message_history)
        parsed_answer = st.session_state.parser.invoke(raw_response)
        update_history("ai", parsed_answer)
        return f"Vecna: {parsed_answer}", "ai"
    except Exception as e:
        error_msg = f"⚠️ Vecna error: {e}"
        return error_msg, "error"

def send_approved_email():
    """Send the approved email"""
    try:
        if st.session_state.pending_email:
            # Format the email request for the existing send_email_with_ai function
            email_request = f"Send email to {st.session_state.pending_email['to']} with subject '{st.session_state.pending_email['subject']}' and message: {st.session_state.pending_email['body']}"
            result = send_email_with_ai(email_request)
            
            # Reset email preview mode
            st.session_state.pending_email = None
            st.session_state.email_preview_mode = False
            
            return f"✅ Email sent successfully! {result}"
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
    
    st.title("Vecna")
    st.markdown("Ask anything, send emails, or read your inbox!")
    
    # Email preview banner - MOVED TO TOP AND MADE MORE PROMINENT
    if st.session_state.email_preview_mode and st.session_state.pending_email:
        # Create a prominent warning/info section
        st.warning("📧 **EMAIL PREVIEW MODE** - Please review the email below before sending!")
        
        # Create a well-defined container for email preview
        with st.container():
            st.markdown("### 📧 Email Preview")
            
            # Create a nice bordered section for email details
            with st.expander("📨 **Email Details** (Click to expand/collapse)", expanded=True):
                
                # Recipient
                st.markdown("**📨 To:**")
                st.info(st.session_state.pending_email.get('to', 'Not specified'))
                
                # Subject  
                st.markdown("**📋 Subject:**")
                st.info(st.session_state.pending_email.get('subject', 'Not specified'))
                
                # Email body
                st.markdown("**📄 Complete Email Message:**")
                email_body = st.session_state.pending_email.get('body', 'Not specified')
                
                # Display email body in a nice text area
                st.text_area(
                    label="Email Content:",
                    value=email_body, 
                    height=250, 
                    disabled=True,
                    help="This is the complete email that will be sent including greeting, message, and closing",
                    key="email_body_preview"
                )
                
            # Action buttons - make them more prominent
            st.markdown("### 🎯 Actions")
            col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
            
            with col1:
                if st.button("✅ **SEND EMAIL**", type="primary", use_container_width=True):
                    result = send_approved_email()
                    st.session_state.messages.append({"role": "assistant", "content": result})
                    save_current_session()
                    st.rerun()
            
            with col2:
                if st.button("❌ **CANCEL**", use_container_width=True):
                    result = cancel_email()
                    st.session_state.messages.append({"role": "assistant", "content": result})
                    save_current_session()
                    st.rerun()
            
            with col3:
                st.markdown("**💡 Need Changes?**")
                st.caption("Type modifications in chat below")
            
            with col4:
                st.markdown("**📝 Examples:**")
                st.caption("'Make it more formal', 'Change subject', 'Add more details'")
        
        st.markdown("---")
    
    # Sidebar with chat history and controls
    with st.sidebar:
        st.header("💬 Chat History")
        
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
        
        # Download chat history
        st.markdown("---")
        st.header("📥 Export")
        if st.button("📄 Download All Chats"):
            chat_data = load_chat_history()
            st.download_button(
                label="💾 Download JSON",
                data=json.dumps(chat_data, indent=2, ensure_ascii=False),
                file_name=f"vecna_chat_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )

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
            
            # Handle email preview - SIMPLIFIED MESSAGE
            if response_type == "email_preview" and isinstance(response, dict):
                success_msg = "✅ **Email Generated Successfully!** Please review the email preview above and click 'SEND EMAIL' when ready."
                st.markdown(success_msg)
                st.session_state.messages.append({"role": "assistant", "content": success_msg})
            
            # Handle email modification - SIMPLIFIED MESSAGE  
            elif response_type == "email_preview" and st.session_state.email_preview_mode:
                modification_msg = "✅ **Email Updated!** Please review the changes in the preview above."
                st.markdown(modification_msg)
                st.session_state.messages.append({"role": "assistant", "content": modification_msg})
            
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
    

if __name__ == "__main__":
    # Check if running in Streamlit
    try:
        # This will work when running with streamlit run main.py
        streamlit_chatbot()
    except:
        # Fallback to original chatbot for terminal use
        from bot.chatbot import chatbot
        chatbot()