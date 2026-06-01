# My Resume Generator — n8n Workflow

Ever wished you could just fill out a form and get a polished, PDF-ready resume without wrestling with Word templates or LaTeX? That's exactly what this workflow does. You type in your details, an AI writes the resume, converts it to LaTeX, and Overleaf compiles it into a clean PDF — all automatically.

---

## How It Works (The Big Picture)

The workflow splits into two parallel tracks the moment someone submits the form, then merges back together to produce the final PDF.

**Track 1 — The AI writing track:** Takes your raw input and turns it into a structured resume, then converts that into LaTeX code.

**Track 2 — The Overleaf authentication track:** Logs into Overleaf, grabs session cookies and a CSRF token, and gets a project ready to receive the LaTeX.

Once both tracks are done, the LaTeX gets uploaded to Overleaf, compiled, and the PDF is returned.

---

## Step-by-Step Breakdown

### 1. The Form (`On form submission`)
Everything starts with a simple web form hosted at the path `resume-form-webhook`. It collects four things:

- Full Name
- Email
- Work Experience (free-text area)
- Skills (free-text area)

When the user hits submit, the workflow kicks off simultaneously on both tracks.

---

### 2. AI Resume Writing (`Resume Generator`)
The form data gets handed to an AI agent running on a local **Ollama** model (`qwen3:4b`). The prompt instructs the model to act as a professional resume writer and generate a complete, well-structured resume — think summary, experience, skills, education, the works — in plain text format.

The system message specifically asks for ATS-optimized output, which matters a lot if the resume is going to be submitted to job portals.

---

### 3. LaTeX Conversion (`Resume Latex Convertor`)
Once the plain-text resume is ready, it gets passed to a second AI agent (same Ollama model). This one's job is purely technical — take the resume content and wrap it in proper **moderncv LaTeX** code using the `classic` style with a `blue` color theme.

The model is instructed to output *only* raw LaTeX, nothing else. No explanations, no markdown fences — just clean code that Overleaf can compile directly.

---

### 4. Preparing Form Data (`Code in JavaScript`)
Running in parallel with the AI track, this node cleans up and normalizes the raw form submission. It handles slight differences in how n8n surfaces the body fields (`body['Full Name']` vs just `'Full Name'`) and packages everything into a tidy object with a timestamp. This data is used downstream to name the Overleaf project.

---

### 5. Setting Overleaf Credentials (`Edit Fields3`)
This is where you configure your Overleaf account details. The node sets three values:

- `overleaf_email` — your Overleaf login email
- `overleaf_password` — your Overleaf password
- `project_name` — auto-generated as `"Resume - [Full Name]"` using the person's name from the form

**Note:** You'll need to swap in your real credentials here before running the workflow.

---

### 6. Encoding Auth (`Decode Cookie key`)
A small JavaScript node that encodes the credentials into base64 format for auth purposes, and prepares the data structure that the following HTTP requests will need. Nothing fancy — just gets things ready.

---

### 7. Logging Into Overleaf (`Connect Overleaf`)
An HTTP GET request hits the Overleaf login page (`https://www.overleaf.com/login`) and grabs the full response — including the raw HTML and response headers.

---

### 8. Pulling the CSRF Token (`Extract curl`)
Overleaf (like most web apps) protects its forms with a CSRF token. This node parses the HTML from the login page using regex to find the hidden `_csrf` input field, and also extracts the session cookie from the response headers.

Both the token and the cookie are saved for use in the next requests.

---

### 9. Creating the Overleaf Project (`Create Project and Paste Latex`)
With a valid session cookie and CSRF token in hand, a POST request goes to `https://www.overleaf.com/api/project` to create a new project. The project gets named after the person (e.g., "Resume - Jane Smith").

The response includes the new project's ID, which is needed for compilation.

---

### 10. Extracting the Project ID (`Extract`)
A quick cleanup node that digs the `project_id` out of Overleaf's API response (it could be under `project_id`, `_id`, or similar depending on the response shape) and makes it available for the next steps.

---

### 11. Compiling the LaTeX (`Project Compiler`)
A POST request to Overleaf's compile endpoint triggers the actual PDF build. It passes `check: silent` and `stopOnFirstError: false` so the compilation runs through even if there are minor warnings.

---

### 12. Downloading the PDF (`Generate Resume PDF`)
While the compiler runs, this node also attempts to fetch the compiled PDF directly from the Overleaf output URL. It uses the session cookie for authentication and returns the file as binary data.

---

### 13. Packaging the Result (`Rendered Resume PDF`)
The final node wraps everything up into a clean output object with:

- `success` — true/false based on compile status
- `status` — the raw status string from Overleaf
- `pdf_url` — where the PDF lives
- `project_id` — the Overleaf project reference
- `message` — a human-readable summary
- `timestamp` — when it was generated

---

## Prerequisites

Before running this, you'll need:

- **n8n** — self-hosted or cloud, your choice
- **Ollama** running locally with the `qwen3:4b` model pulled (`ollama pull qwen3:4b`)
- An **Overleaf account** (free tier works)
- The Ollama credentials configured in n8n under the name `Ollama account`

---

## Configuration

Open the **Edit Fields3** node and replace the placeholder values:

```
overleaf_email    →  your-actual-email@example.com
overleaf_password →  your-actual-password
```

That's the only required setup step.

---

## Limitations & Things to Know

- The workflow uses **web scraping / cookie-based auth** to interact with Overleaf, since there's no official public API for project creation. This approach works but can break if Overleaf updates their login flow or CSRF implementation.
- The AI model runs locally via Ollama — so the quality of the resume depends on how well `qwen3:4b` follows instructions. For better results, you can swap in a more capable model.
- The LaTeX template used is `moderncv` (classic, blue). If you want a different style, update the prompt in the **Resume Latex Convertor** node.
- The workflow is currently set to **inactive** — you'll need to activate it in n8n before the webhook will respond.

---

## Flow Diagram (Text Version)

```
Form Submission
     │
     ├──────────────────────────────────────┐
     ▼                                      ▼
Resume Generator (AI)              Code in JavaScript
     │                                      │
     ▼                                      ▼
Resume Latex Convertor             Edit Fields3
                                           │
                                           ▼
                                   Decode Cookie Key
                                           │
                                           ▼
                                   Connect Overleaf (GET login)
                                           │
                                           ▼
                                   Extract CSRF Token + Cookie
                                           │
                                           ▼
                                   Create Overleaf Project (POST)
                                           │
                             ┌─────────────┤
                             ▼             ▼
                     Generate PDF      Extract Project ID
                                           │
                                           ▼
                                   Project Compiler (POST compile)
                                           │
                                           ▼
                                   Rendered Resume PDF (final output)
```
