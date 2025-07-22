🔢	📄 File	📂 Location	📌 Purpose
1	requirements.txt	root	List all dependencies
2	.env	root	Store Gemini API key
3	auth.py	gmail/	Google OAuth login to Gmail
4	read_emails.py	gmail/	Read recent Gmail messages
5	send_emails.py	gmail/	Send or reply to emails
6	reply_generator.py	agent/	Generate AI replies using LangChain + Gemini
7	main.py	root	Glue logic to run the full flow