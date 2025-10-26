import os
import threading
import requests
from flask import Flask, request, jsonify, render_template
from github import Github
import google.generativeai as genai
from dotenv import load_dotenv


load_dotenv()

app = Flask(__name__)

# Configure API keys
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Ensure the GITHUB_PAT is available and initialize Github client
github_pat = os.getenv("GITHUB_PAT")
if not github_pat:
    print("Warning: GITHUB_PAT is not set. GitHub Webhook functionality will fail.")
    g = None # Set to None if PAT is missing
else:
    g = Github(github_pat)


# Create a Gemini model instance for code analysis
model = genai.GenerativeModel('gemini-2.5-flash')

def process_review(payload):
    """
    Contains the core logic for PyGithub and Gemini API calls, run in a background thread.
    This function processes the PR and posts review comments.
    """
    # Check if GitHub client is initialized
    if g is None:
        print("Error: Cannot process review. GITHUB_PAT is missing.")
        return

    if payload and payload.get('pull_request'):
        try:
            pr = payload.get('pull_request')
            repo_name = pr['base']['repo']['full_name']
            
            repo = g.get_repo(repo_name)
            pull = repo.get_pull(pr['number'])

            print(f"Starting review for PR #{pr['number']} in {repo_name}")

            for file in pull.get_files():
                # Fetch content of the file
                file_content_url = file.raw_url
                response = requests.get(file_content_url)
                
                if response.status_code != 200:
                    print(f"Skipping file {file.filename}: Could not fetch content.")
                    continue

                file_content = response.text

                prompt = f"""
                You are an intelligent code review bot. Analyze the following code focusing on security, efficiency, 
                readability, and potential bugs. Provide a concise, structured review.
                Code to review: ```{file_content}```
                """

                # Call the Gemini API
                gemini_response = model.generate_content(prompt)
                review_comment = gemini_response.text

                # Post the comment back to the Pull Request
                # Note: pull.create_issue_comment posts a general comment on the PR thread.
                # For inline comments, you would use pull.create_review_comment(body, commit_id, path, position).
                pull.create_issue_comment(f"**Code Review for `{file.filename}`**\n\n{review_comment}")
                print(f"Posted review for file: {file.filename}")

            print(f"Successfully posted final review for PR #{pr['number']}")

        except Exception as e:
            # Log any errors that happen in the background thread
            error_message = f"Background processing error for PR #{pr.get('number', 'N/A')}: {e}"
            print(error_message)


# This route displays the input form (The "page" you want)
@app.route('/', methods=['GET'])
def index():
    """Renders the main web page for manual code review."""
    return render_template('index.html') 


# This route receives the code and runs the Gemini review
@app.route('/review', methods=['POST'])
def website_review():
    """Handles manual code submission from the website and returns a review."""
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
        # Log the error on the server side
        print(f"Error during manual review: {e}")
        return jsonify({'review': f'An internal error occurred: {e}'})


@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Endpoint for GitHub webhooks. 
    Starts background processing immediately to avoid GitHub timeouts.
    """
    try:
        # Get the JSON payload from the request
        payload = request.get_json()
    except Exception as e:
        print(f"Webhook error: Invalid JSON payload - {e}")
        return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400

    # 1. Start the heavy work in a new thread
    # Only process 'opened', 'reopened', or 'synchronize' actions on a pull_request
    if payload and payload.get('pull_request') and payload.get('action') in ['opened', 'reopened', 'synchronize']:

        # Start a new thread to run the process_review function
        thread = threading.Thread(target=process_review, args=(payload,))
        thread.start()

        # 2. Return success immediately (within milliseconds) to GitHub
        print(f"Webhook received. Processing PR #{payload['pull_request']['number']} in background.")
        return jsonify({"status": "success", "message": "Processing started in background"}), 200

    # Ignore irrelevant events, but still return 200 to keep GitHub happy
    return jsonify({"status": "ignored", "message": "Event not relevant"}), 200

# We removed the 'if __name__ == '__main__': app.run(debug=True, port=5000)' block.
# Vercel will now automatically find and run the 'app' object.
