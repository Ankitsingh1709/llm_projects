# Mirra 🪞
### See Your Brand Through AI's Eyes

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat&logo=python)
![Flask](https://img.shields.io/badge/Flask-2.x-black?style=flat&logo=flask)
![Claude](https://img.shields.io/badge/Claude-Haiku-orange?style=flat)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o--mini-green?style=flat)
![Gemini](https://img.shields.io/badge/Gemini-2.0--Flash-blue?style=flat)
![Ollama](https://img.shields.io/badge/Ollama-Local-grey?style=flat)
![License](https://img.shields.io/badge/License-MIT-yellow?style=flat)

---

## 🔍 The Problem

Millions of users now skip Google entirely and ask AI assistants like ChatGPT, Claude, and Gemini directly about products and services. This creates three major problems for businesses:

- **Lost traffic** — users get answers from AI and never visit the company's website
- **No analytics** — companies cannot see how many people asked AI about them
- **No control** — no way to influence what AI says about your brand

**Mirra solves this.** It audits how AI systems perceive your brand, scores your visibility, and gives you a clear action plan to improve it.

---

## ✨ Features

- 🤖 **Multi-provider audit** — queries Claude, GPT-4o Mini, Gemini, and a local Ollama model simultaneously
- 📊 **AI Visibility Score** — rates your brand out of 100 with per-provider breakdowns
- 💡 **AEO/GEO Recommendations** — actionable steps to improve how AI talks about you
- 🌐 **RAG-powered scraping** — fetches fresh data from your website, Wikipedia, and Google News before querying AI
- 🧠 **ScrapeGraphAI integration** — uses AI to intelligently extract web content instead of brittle HTML parsing
- 📄 **Page-level audit** — audit a specific page (e.g. `nike.com/running-shoes`) not just the overall brand
- 🕒 **Scrape timestamp** — shows exactly when the data was collected so you know how fresh it is
- ⚠️ **Graceful error handling** — if one provider fails, the rest still run and scores adjust automatically

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML, CSS, Vanilla JavaScript |
| Backend | Python + Flask |
| AI Providers | Claude (Anthropic), OpenAI, Gemini (Google), Ollama (Local) |
| Web Scraping | ScrapeGraphAI + BeautifulSoup4 |
| Environment | python-dotenv |

---

## 📸 Demo

> Audit **Nike** — brand-level

```
Company: Nike
Website: nike.com

AI Visibility Score: 87 / 100  🟢 Strong AI Visibility

Claude:     92 / 100  ████████████████████
OpenAI:     88 / 100  ████████████████████
Gemini:     84 / 100  ███████████████████
Ollama:     82 / 100  ██████████████████
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com/) installed and running
- API keys for Anthropic, OpenAI, and Google Gemini

###  Run the app

Open your browser at **http://127.0.0.1:5000**

---

## 📦 Project Structure

```
mirra/
├── app.py                  ← Flask backend
├── requirements.txt        ← Python dependencies
├── .env                    ← API keys (apna use kro bhai)
├── .gitignore
├── templates/
│   └── index.html          ← Main webpage
└── static/
    ├── style.css           ← Styling
    └── script.js           ← Frontend logic
```

---


### working

In backedn it"s using SCRAPEGRAPHAI to fetch fresh content from the web.
Source 1 company website
Source 2 wikipedia
Source 3 google news but not with ScrapeGraphAI, instead with beautifulsoup4 as ScrapeGraphAI cannot bypass Google's bot detection.

- Different sets of question on bases of brand audit and page audit.
**Brand audit**
1. What is {company}?
2. What products or services does {company} offer?
3. Is {company} a trustworthy company?
4. What are people saying about {company}?
5. Who are {company}'s competitors?

**Page audit**
1. What is the main purpose of this page?
2. What products or services are being offered on this page?
3. Who is the target audience for this page?
4. What is missing that would make this page more informative and trustworthy?
5. How well is this page optimized for answering user questions directly?

## 📖 Key Concepts

**AEO (Answer Engine Optimization)**
Optimizing your content so AI answer engines give your brand as the answer when someone asks a relevant question.

**GEO (Generative Engine Optimization)**
Structuring your website content so generative AI models include your brand in their responses when relevant.

**RAG (Retrieval Augmented Generation)**
Fetching fresh web content first, then feeding it to AI as context so it answers based on live data — not just training data from months ago.

---

## 🗺️ Roadmap

- [x] Multi-provider AI audit
- [x] Scoring system with per-provider breakdown
- [x] AEO/GEO recommendations engine
- [x] Brand-level vs page-level audit
- [x] RAG with ScrapeGraphAI
- [x] Scrape timestamp
- [ ] Perplexity integration (real-time web search AI)
- [ ] Export audit report as PDF
- [ ] Historical score tracking over time
- [ ] Email alerts when AI sentiment changes

---

## ⚠️ Disclaimer

Mirra is intended for research and educational purposes. Web scraping should be used responsibly and in accordance with each website's terms of service.

---

## 👤 Author

Built by [Ankit Singh] as a portfolio project.

---

## 📄 License

MIT License — free to use, modify, and share.