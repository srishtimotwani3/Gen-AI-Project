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
            summary="",
            key_findings="",
            methodology="",
            limitations_future="",
            related_papers=[],
            qa_history=[],
            error=None
        )
        
        result = analysis_graph.invoke(initial_state)
        
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
            
        return result
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
            summary="",
            key_findings="",
            methodology="",
            limitations_future="",
            related_papers=[],
            qa_history=[],
            error=None
        )
        
        result = analysis_graph.invoke(initial_state)
        
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
            
        return result
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

# Mount static files and frontend
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
