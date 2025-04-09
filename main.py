from fastapi import FastAPI, Query
import google.generativeai as genai
from playwright.sync_api import sync_playwright
from langdetect import detect
import json
import time

# Configure Gemini API key
genai.configure(api_key="AIzaSyCtbjyQjRa7OmSt1YJDvqKat25f19OiFMk")

app = FastAPI()

# Tidio live chat URL
TIDIO_CHAT_URL = "https://www.tidio.com/panel/inbox/conversations/unassigned/"

# Scrape website data
def scrape_website(url="https://mufasatoursandtravels.com/"):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        page.wait_for_selector("body")
        page_content = page.inner_text("body")
        with open("website_data.json", "w", encoding="utf-8") as f:
            json.dump({"content": page_content}, f, indent=4)
        browser.close()
        return page_content

# Load cached data or scrape
def load_data():
    try:
        with open("website_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("content", "")
    except FileNotFoundError:
        return scrape_website()

# Send message to Tidio live chat with error handling
def send_message_to_tidio(message: str):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(TIDIO_CHAT_URL)
            page.wait_for_selector("textarea", timeout=10000)  # Wait for 10 seconds for the textarea to appear
            page.fill("textarea", message)
            time.sleep(2)
            page.keyboard.press("Enter")
            time.sleep(2)
            browser.close()
    except Exception as e:
        print(f"Error sending message to Tidio: {e}")
        return False
    return True

# Detect if escalation to human is needed
def needs_human_agent(question: str, answer: str) -> bool:
    low_confidence_phrases = [
        "I can't", "I do not", "I am unable", "I don't have information",
        "I cannot", "I am just an AI", "I don't know", "I only provide information",
        "I'm not sure", "I apologize", "Unfortunately, I cannot"
    ]
    trigger_keywords = ["complaints", "refunds", "booking issue", "flight problem", "support", "human agent", "live agent"]
    return any(phrase in answer.lower() for phrase in low_confidence_phrases) or any(keyword in question.lower() for keyword in trigger_keywords)

# Ask question with language awareness
def ask_question(question: str):
    data = load_data()

    try:
        detected_language = detect(question)
    except:
        detected_language = "en"

    # Format the instruction only if it's not English
    language_instruction = f"Respond ONLY in {detected_language}." if detected_language != "en" else "Respond in English."

    prompt = f"""
You are a helpful AI assistant that answers questions based ONLY on the content of the website below.

{language_instruction}

Website Content:
{data}

User's Question: {question}

Answer:
"""

    model = genai.GenerativeModel("gemini-1.5-pro")
    response = model.generate_content(prompt)
    answer = response.text.strip()

    if needs_human_agent(question, answer):
        send_message_to_tidio(f"User asked: '{question}'\nBot could not answer.")
        return {
            "message": "I am unable to answer this question right now, but don't worry, we are connecting you to a live agent. They will assist you shortly.",
            "status": "transferred_to_human"
        }

    return {"question": question, "answer": answer}

# API endpoint
@app.get("/ask")
def get_answer(question: str = Query(..., title="Question", description="Ask a question about the website")):
    if any(keyword in question.lower() for keyword in ["transfer to human agent", "talk to a person", "speak to support"]):
        message_sent = send_message_to_tidio(f"User requested a human agent for: '{question}'")
        
        # Reassurance message if live agent request is successful
        if message_sent:
            return {
                "message": "Please hold on, we're connecting you to a live agent. You will be assisted shortly.",
                "status": "transferred_to_human"
            }
        else:
            return {
                "message": "Sorry, there was an issue connecting to a live agent. Please try again later.",
                "status": "error"
            }

    return ask_question(question)
