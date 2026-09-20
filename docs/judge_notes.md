ADARSH DIVANKAR

* **Solve a Practical, Everyday Problem:** He regularly showcases projects that address tangible needs. Instead of highly abstract technical concepts, focus on tools for things like travel planning, local business discovery, market research, healthcare access, or job matching.  
* **Build an AI Agent in Python:** Given his background, a submission built in Python that utilizes AI agents to autonomously fetch and process data will resonate strongly.  
* **Implement His Specific Technical Tips (Token Efficiency):** You will stand out if you apply the exact SerpApi optimizations he posts about. For instance, he recently recommended using `output=md` to pass search results as Markdown (which is more token-efficient for LLMs) and utilizing the `json_restrictor` parameter to keep agent inputs focused on only the necessary fields.  
* **Ship a Complete, Working Prototype:** He values shipping fast, noting in a recent post that he launched a mini e-commerce platform in under a month. He even mentioned that "vibe-coded submissions are welcome too," which suggests he cares more about a functional, creative, and usable prototype than a perfectly engineered but incomplete backend.

PRANAV KAFLE

Since Pranav Kafle comes from a deep Customer Success background but possesses serious technical chops, his perspective as a judge will be uniquely focused on **practical utility, developer experience, and no-nonsense execution.**&nbsp;

**tegrate via MCP:** Use the Model Context Protocol (MCP) for your AI agent. He personally wrote 53,000+ lines of code for SerpApi's MCP server, so this will immediately catch his eye.

**Pitch with Zero Buzzwords:** Be brutally direct in your presentation. Explain exactly what it does, who it helps, and how the data flows without any marketing fluff.

**Results Over Activity:** Do not over-engineer a complex theory. Build a straightforward pipeline that successfully executes a task from start to finish.

**Focus on Business Value & Clean Code:** Ensure your tool solves a painful, tedious workflow for the end-user and that your code handles the API JSON responses cleanly.

&nbsp;

TOMUS MURUA

**Focus on Context Engineering:** Prioritize how you filter, curate, and structure data fed to the LLM over just writing a clever prompt. Demonstrate how your system prevents "context poisoning" (hallucinations from bad data).

**Implement Advanced RAG:** Build a robust Retrieval-Augmented Generation (RAG) architecture using hybrid or semantic search to ground your AI agent in facts.

**Output Data in Markdown:** When pulling real-time internet data (like with SerpApi), return the results in **Markdown** instead of JSON. He specifically advocates for this because it halves token usage and reduces noise.

**Utilize Model Context Protocol (MCP):** Use MCP to standardize how your AI agent accesses tools, search APIs, or internal datasets.

**Build a Practical UI:** Do not just submit a command-line script. Deliver a tangible, working user interface (like a Streamlit dashboard, a Discord bot, or a chat app) that effectively visualizes the data.

&nbsp;

## Josef Strzibny

* **Tech Stack Preference (Ruby & Elixir):** He is a veteran Ruby and Elixir contractor and a [Ruby Developer Advocate at SerpApi](https://www.linkedin.com/in/strzibny/?utm_source=gemini). While any language works, using Ruby on Rails or Phoenix (Elixir) will directly align with his background.

&nbsp;

* **Simple, Self-Hosted Deployment:** Author of *Deployment from Scratch* and *Kamal Handbook*. He values clean, transparent infrastructure on basic VPS instances using Docker or **Kamal**, strongly preferring this over complex, black-box managed cloud platforms.  
  &nbsp;  
* **Data Security & Environment Hygiene:** He actively highlights security pitfalls in modern AI tooling, particularly improper logging or plaintext leaks of .env files and session transcripts. Keep API keys secure, configure clean environment handling, and avoid leaking secrets in logs.  
  &nbsp;  
* **Solid Scraping & Data Extraction Fundamentals:** He writes technical guides on web scraping for SerpApi. He values resilient network handling (timeouts, retries, rate limits) and using lightweight parsing methods instead of unnecessary, heavy headless browsers.  
  &nbsp;  
* **Open-Source & Usability:** Actively ships open-source projects (such as SerpTrail). Ensure your hackathon repository is public, cleanly structured, and includes a comprehensive README with straightforward setup and deployment instructions.

&nbsp;

&nbsp;