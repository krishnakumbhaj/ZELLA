from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.runnables import RunnableLambda
from langchain_google_genai import ChatGoogleGenerativeAI
from tools.send_email_tool import send_email_tool
from agent.reply_generator import generate_email
from langchain import hub


import json
import re

# Extract email using regex
def extract_email(text):
    match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    return match.group() if match else None

# Tool wrapper to call Gemini + Gmail
# Tool wrapper to call Gemini + Gmail
def send_email_with_ai(user_input: str) -> str:
    recipient = extract_email(user_input)
    if not recipient:
        return "❌ Could not find an email address."

    result = generate_email(user_input)  # already a dict

    try:
        # ✅ No need to use json.loads here
        subject = result.get("subject")
        body = result.get("body")

        return send_email_tool.run({
    "to": recipient,
    "subject": subject,
    "body": body
    })

    except Exception as e:
        return f"⚠️ Failed to generate or send email: {str(e)}"

# LangChain agent setup
llm = ChatGoogleGenerativeAI(model="gemini-pro")
tools = [send_email_tool]

# 👇 Use default prompt
prompt = hub.pull("hwchase17/react")

agent = create_tool_calling_agent(llm=llm, tools=tools, prompt=prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
