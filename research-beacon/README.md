# ResearchBeacon

A LangGraph-powered agent that accepts research paper URLs or PDFs, performs multi-dimensional analysis, and presents results on a clean web interface hosted locally.

## Features
- **LangGraph Agent**: Orchestrates multiple analysis tasks using Gemini 2.0 Flash.
- **Tavily Search**: Finds related academic papers based on the analyzed paper's title.
- **FastAPI Backend**: Serves REST endpoints for URL parsing, PDF processing, and Question Answering.
- **Vanilla Frontend**: Beautiful single-page app with glassmorphism style and dynamic features.
- **Download as PDF**: Easily export the structured analysis.

## Setup Instructions

### 1. Prerequisites
- Python 3.10+
- Valid Google Gemini API Key
- Valid Tavily API Key

### 2. Install Dependencies
Create a virtual environment (optional but recommended) and install dependencies:

```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r backend/requirements.txt
```

### 3. Environment Variables
Add your API keys to the `backend/.env` file:
```
GEMINI_API_KEY=your_gemini_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
```

### 4. Run the Server
From the root of the project (where this README is), start the FastAPI server:

```bash
uvicorn backend.main:app --reload
```

### 5. Access the Application
Open your browser and navigate to: [http://localhost:8000](http://localhost:8000)
