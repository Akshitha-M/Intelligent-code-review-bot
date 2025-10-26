import os
import threading
import requests
from flask import Flask, request, jsonify, render_template
from github import Github
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure API keys
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
g = Github(os.getenv("GITHUB_PAT"))

# Create a Gemini model instance for code analysis
model = genai.GenerativeModel('gemini-2.5-flash')

def process_review(payload):
    """Contains the core logic for PyGithub and Gemini API calls."""
    # This function takes the full payload and processes it
    if payload and payload.get('pull_request'):
        try:
            pr = payload.get('pull_request')
            repo_name = pr['base']['repo']['full_name']

            # --- PyGithub initialization (ensure this is outside the webhook route or handled robustly) ---
            # Assuming g and model are initialized globally or passed in if preferred.
            # For this example, let's assume 'g' and 'model' are initialized globally/accessible.

            repo = g.get_repo(repo_name)
            pull = repo.get_pull(pr['number'])

            for file in pull.get_files():
                # Your existing code to fetch content, call Gemini, and post the comment
                file_content_url = file.raw_url
                response = requests.get(file_content_url)
                file_content = response.text

                prompt = f"""
                You are an intelligent code review bot... 
                Code to review: ```{file_content}```
                """

                gemini_response = model.generate_content(prompt)
                review_comment = gemini_response.text

                pull.create_issue_comment(f"**Code Review for `{file.filename}`**\n\n{review_comment}")

            print(f"Successfully posted review for PR #{pr['number']}")

        except Exception as e:
            # Log any errors that happen in the background thread
            error_message = f"Background processing error: {e}"
            print(error_message)
# This route displays the input form (The "page" you want)
@app.route('/', methods=['GET'])
def index():
    return render_template('index.html') 

# This route receives the code and runs the Gemini review
@app.route('/review', methods=['POST'])
def website_review():
    # Get the code pasted by the user from the form data
    pasted_code = request.form.get('code_input') 

    if not pasted_code:
        return jsonify({'review': 'Please paste code to review.'})

    try:
        # Create the code review prompt
        prompt = f"""
        You are an intelligent code review bot. Provide a structured review for the following code, focusing on quality, efficiency, and common bugs.
        Code to review: ```{pasted_code}```
        """

        # Call the Gemini API (using the globally defined 'model')
        gemini_response = model.generate_content(prompt)
        review_comment = gemini_response.text

        # Return the review text to the website via JSON
        return jsonify({'review': review_comment})

    except Exception as e:
        return jsonify({'review': f'An internal error occurred: {e}'})

# ... (Your existing @app.route('/webhook') code follows here) ...

@app.route('/webhook', methods=['POST'])
def webhook():
    """Endpoint for GitHub webhooks. Starts background processing immediately."""
    try:
        payload = request.get_json()
    except Exception:
        return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400

    # 1. Start the heavy work in a new thread
    if payload and payload.get('pull_request') and payload.get('action') in ['opened', 'reopened', 'synchronize']:

        # Start a new thread to run the process_review function
        thread = threading.Thread(target=process_review, args=(payload,))
        thread.start()

        # 2. Return success immediately (within milliseconds)
        return jsonify({"status": "success", "message": "Processing started in background"}), 200

    # Ignore irrelevant events, but still return 200
    return jsonify({"status": "ignored", "message": "Event not relevant"}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)