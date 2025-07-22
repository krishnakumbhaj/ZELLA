from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from dotenv import load_dotenv
import os
import json
import re

load_dotenv()

llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash")

prompt = PromptTemplate.from_template("""
You are a helpful email writing assistant.

Given this instruction: "{user_prompt}", generate a professional subject and email body.

Respond only in this JSON format (no extra words or code blocks):
{{
    "subject": "<your subject>",
    "body": "<your full email body>"
}}
""")

chain = prompt | llm | StrOutputParser()

def extract_json(text: str) -> str:
    # This removes markdown-style ```json blocks if present
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    return text.strip()

def generate_email(prompt_text: str):
    result = chain.invoke({"user_prompt": prompt_text})
    
    # Clean and extract actual JSON string
    cleaned_result = extract_json(result)
    
    try:
        return json.loads(cleaned_result)
    except json.JSONDecodeError as e:
        print("⚠️ Failed to parse JSON from LLM output:")
        print(cleaned_result)
        raise e
