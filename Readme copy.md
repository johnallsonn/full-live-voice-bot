# ResearchQuest AI Chatbot

Multimodal research assistant for PDFs and DOCX papers. Extracts text, tables, images (with captions/OCR/formula signals), classifies intent, and generates context-aware answers, summaries, visual plans, and downloads.

---

## 📂 Project Structure

```
.
├── streamlit_app.py          # Streamlit web UI (chat, previews, downloads)
├── app.py                    # CLI chat entry point
├── utils/
|   ├── __init__.py
│   ├── chatbot_backend.py    # Intent routing + handlers + OpenAI client
│   ├── document_processor.py # PDF/DOCX ingest, tables/images, captions/OCR
│   ├── download_handlers.py  # Manages downloads of excel, csv, markdown, png etc
│   ├── pdf_processor.py      # Low-level PDF text/table/image extraction
│   ├── image_analyzer.py     # OCR + formula/diagram detection
│   ├── agents.py             # Visualization, download, display, source-link helpers
│   └── features_handlers.py  # External tool shortcuts (Anushram suite)
├── requirements.txt
├── data/temp_images/         # Extracted figure snapshots
└── Research/                 # Legacy artifacts and exports
```

---

## 🚀 Key Features

- **Document ingest:** Upload or load PDF/DOCX; extracts cleaned text, numbered tables, images, captions, and basic metadata.
- **Intent-aware routing:** LLM classifier directs queries to `doc_qa`, `summary`, `table_lookup`, `table_create`, `image_explain`, `visualize`, `download`, `display`, `source_links`, or external tool intents.
- **Table & image reasoning:** Table selection/explanation, custom table creation, figure selection + caption-aware explanations with OCR/formula hints.
- **Visualization planner:** Returns lightweight JSON specs (Vega-Lite style) for charts/plots and exposes a download of the plan.
- **Download helpers:** Suggests CSV/XLSX/Markdown/Docx/PNG exports with preview content and download buttons.
- **External integrations:** One-click handoff to Anushram tools (Idea Generator, Paper Quality Check, Citation Generator, DOI Finder, Literature Review, Thesis Writer).
- **Streaming responses:** Summaries, QA, and explanations stream chunk-by-chunk for responsiveness.

---

## 🛠️ Setup & Installation

### 1. **Prerequisites**
- Python **3.9+**
- **Tesseract OCR** (optional; enhances OCR beyond EasyOCR)
- **OpenAI API Key**

---

### 2. **Environment Setup (Windows)**

```bash
# Create a virtual environment
python -m venv venv

# Activate the virtual environment
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. **Configuration**

Create a .env file inside the root directory:

```
env

OPENAI_API_KEY=sk-your-api-key-here
```

---

## ▶️ How to Run

### Option 1: Web Interface (Recommended)

Launch the Streamlit UI:

```bash
streamlit run streamlit_app.py
```

### Option 2: Terminal Mode (Legacy)

Runs the text-only CLI version:

```bash
python app.py
```

1) Upload a PDF/DOCX in the Streamlit sidebar and click **Process Document**.  
2) Review extracted stats (word/table/image counts).  
3) Ask questions or commands (e.g., “summarize section 2”, “explain table 3”, “create a comparison table”, “plan a bar chart”, “download as csv”).  
4) For figures, the bot picks the best match and explains with stored captions/OCR cues.  
5) Use download buttons for generated tables/specs; follow external links for Anushram tools when suggested.

---

## 📋 Requirements Reference

| Purpose | Packages |
| --- | --- |
| UI | streamlit |
| LLM | openai |
| PDF extraction | pdfplumber, pymupdf, PyPDF2 |
| Image/OCR | easyocr, opencv-python |
| Config | python-dotenv |
| Configuration | python-dotenv |