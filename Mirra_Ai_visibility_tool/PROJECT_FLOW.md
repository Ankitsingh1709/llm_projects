# AI Visibility Audit Tool - Complete System Flow

## 📋 Project Overview
The **AI Visibility Audit Tool** is a web-based application that measures how well AI systems (ChatGPT, Claude, Gemini, Ollama) can understand and describe your company. It runs completely offline using local Ollama models and provides actionable recommendations for improving your "AI visibility."

---

## 🎯 Core Concept

**What Problem Does It Solve?**
- Companies want to know: "How do AI systems perceive my brand?"
- AI systems are trained on public web data, so if your content isn't clear to AI, you're losing visibility
- This tool audits that gap and provides specific recommendations

**Evaluation Framework: 5 Scoring Criteria**
1. **Brand Clarity (20 points)** - Does AI mention the company name and know what it does?
2. **Product/Service Clarity (20 points)** - Can AI describe specific offerings?
3. **Content Depth (20 points)** - Are AI responses detailed enough (500+ characters)?
4. **Sentiment (20 points)** - Does AI use positive language about the brand?
5. **Competitive Awareness (20 points)** - Does AI know the competitors?

**Overall Score: 0-100**
- 80+: Strong AI Visibility 🟢
- 50-79: Moderate AI Visibility 🟡
- Below 50: Weak AI Visibility 🔴

---

## 🔄 Complete Data Flow

### **PHASE 1: User Input & Route Handling**

```
┌─────────────────────────────────────────┐
│ User opens index.html in browser        │
│ Enters: Company Name + Optional Website │
└─────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────┐
│ Clicks "Run Audit" button               │
│ → Calls JavaScript: runAudit()          │
│ → POST request to /audit endpoint       │
└─────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────┐
│ Backend: Flask receives POST at /audit  │
│ Extracts:                               │
│  - company (string)                     │
│  - website (string, optional)           │
└─────────────────────────────────────────┘
```

### **PHASE 2: Audit Type Detection**

```
┌─────────────────────────────────────────┐
│ Check if website has a path beyond root │
│ (e.g., "nike.com/running-shoes")       │
└─────────────────────────────────────────┘
         ↙              ↘
┌──────────────────┐  ┌─────────────────────┐
│ Has path?        │  │ No path (just       │
│ YES = PAGE AUDIT │  │ domain)?            │
│                  │  │ = BRAND AUDIT       │
└──────────────────┘  └─────────────────────┘
         ↓                      ↓
┌──────────────────┐  ┌─────────────────────┐
│ Fetch page       │  │ No specific page    │
│ content via      │  │ content needed      │
│ BeautifulSoup    │  │ (Skip to Phase 3)   │
└──────────────────┘  └─────────────────────┘
```

### **PHASE 3: Fresh Data Collection (Web Scraping)**

The system scrapes 3 sources to feed fresh, real-time data to the AI models:

**Source 1: Company Website (Via ScrapeGraphAI)**
```
┌────────────────────────────────────────────────────┐
│ ScrapeGraphAI with Ollama/Gemma3:4b               │
│ Query: Extract company mission, products, facts    │
│ → Intelligent AI-powered web scraping              │
│ → Returns: 1500 chars max                          │
└────────────────────────────────────────────────────┘
           ↓
┌────────────────────────────────────────────────────┐
│ Fallback: If ScrapeGraphAI fails                    │
│ → Use BeautifulSoup (basic HTML parsing)           │
│ → Extract clean text, remove scripts/styles        │
│ → Returns: 2000 chars max                          │
└────────────────────────────────────────────────────┘
```

**Source 2: Wikipedia (Via ScrapeGraphAI)**
```
┌────────────────────────────────────────────────────┐
│ Check if Wikipedia page exists                     │
│ (look for "noarticletext" div)                    │
└────────────────────────────────────────────────────┘
         ↙                        ↘
┌──────────────┐        ┌──────────────────────┐
│ Page exists? │        │ Page not found?      │
│ YES → Query  │        │ SKIP Wikipedia       │
└──────────────┘        └──────────────────────┘
         ↓
┌────────────────────────────────────────────────────┐
│ Verify first paragraph mentions business terms:   │
│ "company", "platform", "startup", "founded" etc   │
└────────────────────────────────────────────────────┘
         ↙                        ↘
┌──────────────┐        ┌──────────────────────┐
│ Business     │        │ Not a business       │
│ relevant?    │        │ page? SKIP           │
│ YES → Query  │        └──────────────────────┘
└──────────────┘
         ↓
┌────────────────────────────────────────────────────┐
│ ScrapeGraphAI Query:                               │
│ "Extract founding year, HQ, products,             │
│  milestones, controversies"                        │
│ → Returns: 1500 chars max                          │
└────────────────────────────────────────────────────┘
```

**Source 3: Google News (Via BeautifulSoup)**
```
┌────────────────────────────────────────────────────┐
│ Google News blocks AI scrapers, so use             │
│ BeautifulSoup for basic extraction                 │
│ → Search: news.google.com/?q=[company]             │
│ → Extract first 5 articles                         │
│ → Returns: 500 chars max per article               │
└────────────────────────────────────────────────────┘
```

**Result: Fresh Context String**
```
Combined output (max ~6000 chars):
"COMPANY WEBSITE CONTENT: ...
WIKIPEDIA: ...
RECENT NEWS: ..."
```

### **PHASE 4: Query Generation**

Based on audit type, generate 5 contextual questions:

**For BRAND AUDIT:**
```
Query 1: "What is [Company]?"
Query 2: "What products or services does [Company] offer?"
Query 3: "Is [Company] a trustworthy company?"
Query 4: "What are people saying about [Company]?"
Query 5: "Who are [Company]'s competitors?"
```

**For PAGE AUDIT (specific URL provided):**
```
Query 1: "What is the main purpose of this page?"
Query 2: "What products/services are offered on this page?"
Query 3: "Who is the target audience for this page?"
Query 4: "What is missing that would make it more trustworthy?"
Query 5: "How well is this page optimized for direct answers?"
```

Each query includes:
- **display**: User-friendly question shown in results
- **prompt**: Full AI prompt including fresh web context

### **PHASE 5: AI Model Querying (Local Ollama)**

```
┌──────────────────────────────────────────────────┐
│ For each of 5 queries:                           │
│ Call 4 local Ollama models simultaneously        │
└──────────────────────────────────────────────────┘

Query → ┌─ Qwen 2.5 7B   (Best reasoner, replaces Claude)
        ├─ Llama 3.2 3B   (Meta's local model)
        ├─ Qwen3 4B       (Lightweight local model)
        └─ Gemma 3 4B    (General purpose)

Each model:
1. Receives same prompt with fresh context
2. Generates response (max 300 tokens)
3. Returns response or error message
```

**Helper Function: query_ollama()**
```python
def query_ollama(model_key, prompt):
    1. Look up model name from MODELS dict
    2. Connect to localhost:11434/v1 (Ollama server)
    3. Send prompt with temperature=0 (deterministic)
    4. Collect response or catch error
    5. Return as string
```

### **PHASE 6: Scoring (Frontend JavaScript)**

**Per-Response Scoring: scoreModel()**

For each AI response, check:

```
1. BRAND CLARITY (20 pts)
   ✓ Response contains company name (case-insensitive)
   → Award 20 pts
   ✗ Company name missing
   → Award 0 pts, add flag "not_mentioned"

2. PRODUCT CLARITY (20 pts)
   ✓ 2+ product words found (product, service, offer, provide, tool, etc)
   → Award 20 pts
   ✓ 1 product word found
   → Award 10 pts
   ✗ No product words
   → Award 0 pts, add flag "no_products"

3. CONTENT DEPTH (20 pts)
   ✓ Response > 500 characters
   → Award 20 pts
   ✓ Response 200-500 characters
   → Award 10 pts
   ✗ Response < 200 characters
   → Award 0 pts, add flag "too_vague"

4. SENTIMENT (20 pts)
   ✓ Contains positive words (trusted, reliable, leading, etc)
     AND no negative words (scam, fraud, unreliable, etc)
   → Award 20 pts
   ✓ No sentiment indicators
   → Award 10 pts
   ✗ Contains negative words
   → Award 0 pts, add flag "negative_sentiment"

5. COMPETITIVE AWARENESS (20 pts)
   ✓ 2+ competitor words (competitor, alternative, versus, rival, etc)
   → Award 20 pts
   ✓ 1 competitor word
   → Award 10 pts
   ✗ No competitor words
   → Award 0 pts, add flag "no_competitors"
```

**Overall Score Calculation: scoreCompany()**
```
1. For each of 4 models × 5 queries = 20 responses
2. Skip error responses
3. Score each non-error response
4. Average all valid scores
5. Cap at 100, round to nearest integer
6. Collect all flags (unique)
7. Calculate breakdown averages (0-100%)
```

### **PHASE 7: Result Display**

**Score Card Section:**
- Overall score (0-100) with color coding
- Label (Strong/Moderate/Weak AI Visibility)
- Audit type badge (Brand or Page)
- Warnings if fetch failed or no fresh data
- Timestamp of scrape
- Collapsible source inspector

**Score Breakdown Section:**
- 5 metrics, each showing % of responses that passed
- Tooltips explaining what each metric means

**Model Scores Section:**
- Per-model average scores displayed as bars
- Partial note if model had some errors

**Per-Query Results Section:**
- 5 query blocks, each showing:
  - Question displayed to user
  - Responses from all 4 models
  - Error indicators if model failed

**Suggestions Section:**
- 3-4 high/medium priority fixes
- 3 best practice recommendations
- Each includes estimated impact on score

### **PHASE 8: Advanced Features**

**PDF Export**
- Captures results div
- Uses html2pdf.js library
- Filename: `{company}-AI-Visibility-Audit.pdf`

**Recommendations Endpoint**
- If score < 100, fetch additional AI recommendations
- Sends score, flags, and sample responses to Qwen 2.5 7B (`qwen7b`)
- Returns personalized action plan
- Updates suggestions section

---

## 📊 Data Structure Summary

### Request/Response Flow

**POST /audit**
```json
REQUEST:
{
  "company": "Apple",
  "website": "apple.com/products"
}

RESPONSE:
{
  "company": "Apple",
  "results": [
    {
      "query": "What is Apple?",
      "responses": {
        "gemma": "Apple is a technology...",
        "qwen7b": "Apple Inc. is a...",
        "llama": "Apple is known for...",
        "qwen3": "Apple makes..."
      }
    },
    ...
  ],
  "website": "apple.com/products",
  "audit_type": "page",
  "fetch_error": false,
  "sources": ["Company website", "Wikipedia"],
  "has_fresh_data": true,
  "scraped_at": "May 27, 2026 at 03:45 PM",
  "source_previews": {
    "website": { "label": "Company Website (apple.com)", "content": "..." },
    "wikipedia": { "label": "Wikipedia", "content": "..." }
  }
}
```

**POST /recommendations**
```json
REQUEST:
{
  "company": "Apple",
  "website": "apple.com",
  "score": 75,
  "flags": ["too_vague", "no_competitors"],
  "ai_responses": "Sample responses from the audit..."
}

RESPONSE:
{
  "recommendations": "Based on your score of 75..."
}
```

---

## 🛠️ Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | HTML5 | Structure |
| | CSS3 | Styling (responsive design) |
| | Vanilla JavaScript | Interactivity & API calls |
| **Backend** | Flask | Web framework |
| | Python 3.x | Core logic |
| **Web Scraping** | ScrapeGraphAI | AI-powered extraction |
| | BeautifulSoup4 | HTML parsing (fallback) |
| | Requests | HTTP calls |
| **AI Models** | Ollama (Local) | Model serving |
| | Qwen 2.5 7B | Best reasoning |
| | Llama 3.2 3B | Meta's local model |
| | Qwen3 4B | Lightweight local model |
| | Gemma 3 4B | General purpose |
| **LLM Integration** | LangChain | AI framework |
| | OpenAI API (mocked) | Ollama compatibility |

---

## 🔐 Security & Privacy

✅ **Completely Offline**
- No data sent to external APIs
- All processing happens locally
- Only reads public web content

✅ **No Data Storage**
- No database
- Results exist only in user's browser
- PDF export is client-side only

⚠️ **Web Scraping**
- Respects robots.txt implicitly (uses standard User-Agent)
- Google News blocking is handled gracefully
- Wikipedia verification prevents scraping non-business pages

---

## 🚀 Key Features

### 1. **Dual Audit Modes**
- **Brand Audit**: How does AI describe your company overall?
- **Page Audit**: How well does AI understand a specific page?

### 2. **Fresh Web Context**
- Scrapes real-time data from website, Wikipedia, news
- Prevents AI from relying only on training data
- Shows sources used for transparency

### 3. **Multi-Model Comparison**
- 4 different AI models for diversity of perspective
- Identifies which models understand your company best
- Highlights if some models fail (partial score)

### 4. **Intelligent Scoring**
- 5 specific criteria aligned with SEO/GEO best practices
- Per-query and per-model breakdowns
- Actionable suggestions based on specific gaps

### 5. **AEO/GEO Guidance**
- Recommendations tailored to audit results
- Explains why score is low
- Provides specific action items with estimated impact
- Best practices for AI visibility

### 6. **PDF Export**
- Download audit results
- Share with team or stakeholders
- Includes all analysis and recommendations

---

## 📝 Example Audit Flow

**Input:**
- Company: "Notion"
- Website: "notion.so"

**Step 1: Type Detection**
- No path in URL → Brand audit

**Step 2: Data Scraping**
- Website: Fetches Notion's homepage features
- Wikipedia: Finds founding info, funding, products
- News: Fetches recent articles about Notion

**Step 3: Questions Generated**
1. What is Notion?
2. What products does Notion offer?
3. Is Notion trustworthy?
4. What are people saying about Notion?
5. Who are Notion's competitors?

**Step 4: Model Responses**
- Each model answers all 5 questions
- Total: 20 responses collected

**Step 5: Scoring**
- Gemma 3 4B avg: 85/100 (strong)
- Qwen 2.5 7B avg: 78/100 (good)
- Llama 3.2 3B avg: 72/100 (moderate)
- Qwen3 4B avg: 81/100 (strong)
- **Overall: 79/100** (Moderate AI Visibility)

**Step 6: Flags Identified**
- "no_competitors" (mentioned 2x)
- "too_vague" (mentioned 1x)

**Step 7: Recommendations**
- **High Priority**: Explain Notion's competitors (Confluence, Obsidian, etc)
- **High Priority**: Expand content depth with use cases
- **Best Practice**: Add FAQ section
- **Best Practice**: Get cited by tech news outlets

---

## 💡 The "Why" Behind Each Component

| Component | Why It Exists |
|-----------|---------------|
| **ScrapeGraphAI** | Intelligent extraction beats regex/CSS selectors |
| **Multiple Models** | No single model is perfect; comparison is valuable |
| **5 Scoring Criteria** | Proven factors for AI discoverability |
| **Fresh Context** | AI needs current data, not just training data |
| **Source Transparency** | Users should know what fed the AI |
| **Recommendations** | Scores are useless without actionable next steps |
| **Local Ollama** | Privacy + cost (no API bills) |
| **Page vs Brand** | Different contexts need different questions |

