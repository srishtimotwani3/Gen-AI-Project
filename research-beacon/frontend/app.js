document.addEventListener('DOMContentLoaded', () => {
    // UI Elements
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    const urlInput = document.getElementById('url-input');
    const analyzeUrlBtn = document.getElementById('analyze-url-btn');
    
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const fileInfo = document.getElementById('file-info');
    const fileNameDisplay = document.getElementById('file-name');
    const analyzePdfBtn = document.getElementById('analyze-pdf-btn');
    
    const loadingSection = document.getElementById('loading-section');
    const errorBanner = document.getElementById('error-message');
    const resultsSection = document.getElementById('results-section');
    const downloadPdfBtn = document.getElementById('download-pdf-btn');
    
    const qaInput = document.getElementById('qa-input');
    const qaSubmitBtn = document.getElementById('qa-submit-btn');
    const qaHistory = document.getElementById('qa-history');

    let currentFile = null;
    let extractedPaperText = ""; // Store for Q&A

    // Configure marked options for markdown rendering
    marked.setOptions({
        breaks: true,
        gfm: true
    });

    // Tab Switching
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // Remove active classes
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            
            // Add active to clicked
            btn.classList.add('active');
            document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
        });
    });

    // Drag and Drop Logic
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'), false);
    });

    dropZone.addEventListener('drop', handleDrop, false);
    fileInput.addEventListener('change', (e) => handleFiles(e.target.files), false);

    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFiles(files);
    }

    function handleFiles(files) {
        if (files.length > 0) {
            const file = files[0];
            if (file.type === 'application/pdf') {
                currentFile = file;
                dropZone.style.display = 'none';
                fileInfo.style.display = 'flex';
                fileNameDisplay.textContent = file.name;
            } else {
                showError("Please upload a valid PDF file.");
            }
        }
    }

    // Analysis Logic
    analyzeUrlBtn.addEventListener('click', async () => {
        const url = urlInput.value.trim();
        if (!url) {
            showError("Please enter a valid URL.");
            return;
        }
        
        startLoading();
        try {
            const response = await fetch('/api/analyze/url', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });
            await handleAnalysisResponse(response);
        } catch (err) {
            showError(err.message);
            stopLoading();
        }
    });

    analyzePdfBtn.addEventListener('click', async () => {
        if (!currentFile) return;
        
        startLoading();
        const formData = new FormData();
        formData.append('file', currentFile);
        
        try {
            const response = await fetch('/api/analyze/pdf', {
                method: 'POST',
                body: formData
            });
            await handleAnalysisResponse(response);
        } catch (err) {
            showError(err.message);
            stopLoading();
        }
    });

    async function handleAnalysisResponse(response) {
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Analysis failed");
        }
        
        const data = await response.json();
        
        // Store paper text for QA
        extractedPaperText = data.paper_text;
        
        // Render results
        document.getElementById('paper-title-display').textContent = data.paper_title || "Analysis Results";
        document.getElementById('res-summary').innerHTML = marked.parse(data.summary || "No summary available.");
        document.getElementById('res-key-findings').innerHTML = marked.parse(data.key_findings || "No key findings available.");
        document.getElementById('res-methodology').innerHTML = marked.parse(data.methodology || "No methodology available.");
        document.getElementById('res-limitations').innerHTML = marked.parse(data.limitations_future || "No limitations available.");
        
        // Render related papers
        const relatedList = document.getElementById('res-related-papers');
        relatedList.innerHTML = '';
        if (data.related_papers && data.related_papers.length > 0) {
            data.related_papers.forEach(paper => {
                const li = document.createElement('li');
                li.innerHTML = `
                    <a href="${paper.url}" target="_blank">${paper.title}</a>
                    <p>${paper.snippet}</p>
                `;
                relatedList.appendChild(li);
            });
        } else {
            relatedList.innerHTML = '<li>No related papers found.</li>';
        }
        
        stopLoading();
        resultsSection.style.display = 'block';
        
        // Smooth scroll to results
        resultsSection.scrollIntoView({ behavior: 'smooth' });
    }

    // QA Logic
    qaSubmitBtn.addEventListener('click', askQuestion);
    qaInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') askQuestion();
    });

    async function askQuestion() {
        const question = qaInput.value.trim();
        if (!question || !extractedPaperText) return;
        
        // Add user msg to UI
        addQAMessage(question, 'user');
        qaInput.value = '';
        qaSubmitBtn.disabled = true;
        
        try {
            const response = await fetch('/api/qa', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    paper_text: extractedPaperText,
                    question: question
                })
            });
            
            if (!response.ok) throw new Error("Failed to get answer");
            
            const data = await response.json();
            addQAMessage(marked.parseInline(data.answer), 'bot');
        } catch (err) {
            addQAMessage("Sorry, an error occurred while processing your question.", 'bot');
        } finally {
            qaSubmitBtn.disabled = false;
        }
    }

    function addQAMessage(text, sender) {
        const div = document.createElement('div');
        div.className = `qa-msg ${sender}`;
        div.innerHTML = text;
        qaHistory.appendChild(div);
        qaHistory.scrollTop = qaHistory.scrollHeight;
    }

    // PDF Download
    downloadPdfBtn.addEventListener('click', async () => {
        const element = document.getElementById('pdf-content-area');
        
        // Prevent PDF from cutting off by forcing single column
        element.classList.add('pdf-exporting');
        
        const opt = {
            margin: 0.5,
            filename: 'research-beacon-analysis.pdf',
            image: { type: 'jpeg', quality: 0.98 },
            html2canvas: { scale: 2, windowWidth: 900 },
            jsPDF: { unit: 'in', format: 'a4', orientation: 'portrait' }
        };
        
        await html2pdf().set(opt).from(element).save();
        
        element.classList.remove('pdf-exporting');
    });

    // Helpers
    function startLoading() {
        errorBanner.style.display = 'none';
        resultsSection.style.display = 'none';
        loadingSection.style.display = 'block';
        
        // Animate steps
        const steps = document.querySelectorAll('.step');
        let currentStep = 0;
        
        // Simple mock animation of steps progress
        window.loadingInterval = setInterval(() => {
            steps.forEach(s => s.classList.remove('active'));
            if (currentStep < steps.length) {
                steps[currentStep].classList.add('active');
                currentStep++;
            }
        }, 3000);
    }

    function stopLoading() {
        loadingSection.style.display = 'none';
        if (window.loadingInterval) clearInterval(window.loadingInterval);
    }

    function showError(msg) {
        errorBanner.textContent = msg;
        errorBanner.style.display = 'block';
        setTimeout(() => { errorBanner.style.display = 'none'; }, 5000);
    }
});
