import os
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

# Load env vars first
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

from backend.agent.graph import analysis_graph, qa_graph
from backend.agent.state import AgentState
from backend.utils.pdf_parser import parse_pdf_bytes

app = FastAPI(title="ResearchBeacon API")

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class UrlRequest(BaseModel):
    url: str

class QARequest(BaseModel):
    paper_text: str
    question: str

# Endpoints
@app.post("/api/analyze/url")
async def analyze_url(req: UrlRequest):
    try:
        initial_state = AgentState(
            source_type="url",
            source_ref=req.url,
            paper_text="",
            paper_title="",
            paper_authors="",
            search_query="",
            summary="",
            key_findings="",
            methodology="",
            limitations_future="",
            related_papers=[],
            qa_history=[],
            error=None
        )
        
        result = analysis_graph.invoke(initial_state)
        
        if result.get("error") == "NOT_A_RESEARCH_PAPER":
            raise HTTPException(
                status_code=422,
                detail="This does not appear to be a research paper. Please upload or link to an academic paper."
            )
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyze/pdf")
async def analyze_pdf(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")
        
    try:
        contents = await file.read()
        extracted_text = parse_pdf_bytes(contents)
        
        initial_state = AgentState(
            source_type="pdf",
            source_ref=file.filename,
            paper_text=extracted_text,
            paper_title=file.filename,
            paper_authors="",
            search_query="",
            summary="",
            key_findings="",
            methodology="",
            limitations_future="",
            related_papers=[],
            qa_history=[],
            error=None
        )
        
        result = analysis_graph.invoke(initial_state)
        
        if result.get("error") == "NOT_A_RESEARCH_PAPER":
            raise HTTPException(
                status_code=422,
                detail="This does not appear to be a research paper. Please upload an academic paper."
            )
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/qa")
async def ask_question(req: QARequest):
    try:
        initial_state = AgentState(
            source_type="qa",
            source_ref="qa",
            paper_text=req.paper_text,
            paper_title="",
            paper_authors="",
            search_query="",
            summary="",
            key_findings="",
            methodology="",
            limitations_future="",
            related_papers=[],
            qa_history=[{"question": req.question, "answer": ""}],
            error=None
        )
        
        result = qa_graph.invoke(initial_state)
        answer = result["qa_history"][-1]["answer"]
        
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/debug")
async def debug_api_key():
    """Quick diagnostic: ping each model with a minimal request and report status."""
    import os
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.messages import HumanMessage

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"error": "GEMINI_API_KEY is not set in .env"}

    from backend.agent.nodes import GEMINI_MODEL_CHAIN, GROQ_MODEL_CHAIN
    results = {}
    
    # Try Groq models first
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        from langchain_groq import ChatGroq
        for model_name in GROQ_MODEL_CHAIN:
            try:
                model = ChatGroq(model=model_name, api_key=groq_key, temperature=0)
                resp = model.invoke([HumanMessage(content="Say 'ok' in one word.")])
                results[model_name] = {"status": "✓ OK", "response": str(resp.content)[:60]}
            except Exception as e:
                err = str(e)
                results[model_name] = {"status": "✗ ERROR", "error": err[:120]}
    
    # Try Gemini models
    if api_key:
        for model_name in GEMINI_MODEL_CHAIN:
            try:
                model = ChatGoogleGenerativeAI(model=model_name, api_key=api_key, temperature=0)
                resp = model.invoke([HumanMessage(content="Say 'ok' in one word.")])
                results[model_name] = {"status": "✓ OK", "response": str(resp.content)[:60]}
            except Exception as e:
                err = str(e)
                if "RESOURCE_EXHAUSTED" in err:
                    results[model_name] = {"status": "✗ QUOTA_EXHAUSTED", "error": err[:120]}
                elif "NOT_FOUND" in err:
                    results[model_name] = {"status": "✗ MODEL_NOT_FOUND", "error": err[:120]}
                elif "API_KEY_INVALID" in err or "API key not valid" in err:
                    results[model_name] = {"status": "✗ INVALID_API_KEY", "error": err[:120]}
                else:
                    results[model_name] = {"status": "✗ ERROR", "error": err[:120]}

    return {"api_key_prefix": api_key[:8] + "..." if api_key else "None", "models": results}

# Mount static files and frontend
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
