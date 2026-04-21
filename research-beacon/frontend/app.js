document.addEventListener('DOMContentLoaded', () => {
    // UI Elements
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    const urlInput = document.getElementById('url-input');
    const analyzeUrlBtn = document.getElementById('analyze-url-btn');
    
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const fileNameDisplay = document.getElementById('file-name');
    const analyzePdfBtn = document.getElementById('analyze-pdf-btn');
    const removePdfBtn = document.getElementById('remove-pdf-btn');
    const pdfSelectedRow = document.getElementById('pdf-selected-row');
    
    const loadingSection = document.getElementById('loading-section');
    const errorBanner = document.getElementById('error-message');
    const resultsSection = document.getElementById('results-section');
    const downloadPdfBtn = document.getElementById('download-pdf-btn');
    
    const qaInput = document.getElementById('qa-input');
    const qaSubmitBtn = document.getElementById('qa-submit-btn');
    const qaHistory = document.getElementById('qa-history');

    let currentFile = null;
    let extractedPaperText = "";
    let currentPaperTitle = "";
    let currentAuthors = "";

    // Store raw text for PDF generation
    let rawSections = {};

    // Configure marked for clean markdown rendering
    marked.setOptions({
        breaks: true,
        gfm: true,
        headerIds: false,
        mangle: false
    });

    // ── Tab Switching ────────────────────────────────
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
        });
    });

    // ── Drag and Drop ────────────────────────────────
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(e => {
        dropZone.addEventListener(e, () => dropZone.classList.add('dragover'), false);
    });
    ['dragleave', 'drop'].forEach(e => {
        dropZone.addEventListener(e, () => dropZone.classList.remove('dragover'), false);
    });

    dropZone.addEventListener('drop', handleDrop, false);
    fileInput.addEventListener('change', (e) => handleFiles(e.target.files), false);

    function handleDrop(e) { handleFiles(e.dataTransfer.files); }

    function handleFiles(files) {
        if (files.length > 0) {
            const file = files[0];
            if (file.type === 'application/pdf') {
                currentFile = file;
                dropZone.style.display = 'none';
                pdfSelectedRow.style.display = 'flex';
                fileNameDisplay.textContent = file.name;
            } else {
                showError("Please upload a valid PDF file.");
            }
        }
    }

    // ── Remove PDF ────────────────────────────────────
    removePdfBtn.addEventListener('click', () => {
        currentFile = null;
        fileInput.value = '';
        pdfSelectedRow.style.display = 'none';
        dropZone.style.display = 'block';
        fileNameDisplay.textContent = '';
    });

    // ── Analysis Triggers ────────────────────────────
    analyzeUrlBtn.addEventListener('click', async () => {
        const url = urlInput.value.trim();
        if (!url) { showError("Please enter a valid URL."); return; }
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

    // ── Render Results ───────────────────────────────
    async function handleAnalysisResponse(response) {
        if (!response.ok) {
            const err = await response.json();
            const msg = err.detail || "Analysis failed";
            // Special friendly message for non-research-paper
            if (response.status === 422) {
                showNotResearchPaperError(msg);
            } else {
                throw new Error(msg);
            }
            stopLoading();
            return;
        }

        const data = await response.json();

        extractedPaperText = data.paper_text;
        currentPaperTitle = data.paper_title || "Analysis Results";
        currentAuthors = data.paper_authors || "";

        // Store raw for PDF
        rawSections = {
            summary: data.summary || "",
            key_findings: data.key_findings || "",
            methodology: data.methodology || "",
            limitations_future: data.limitations_future || "",
            related_papers: data.related_papers || []
        };

        // Render title
        document.getElementById('paper-title-display').textContent = currentPaperTitle;

        // Render authors
        const authorsEl = document.getElementById('paper-authors-display');
        if (currentAuthors && currentAuthors !== "Authors not listed") {
            authorsEl.textContent = currentAuthors;
            authorsEl.style.display = 'block';
        } else {
            authorsEl.style.display = 'none';
        }

        // Parse and render markdown
        document.getElementById('res-summary').innerHTML      = marked.parse(data.summary || "No summary available.");
        document.getElementById('res-key-findings').innerHTML = marked.parse(data.key_findings || "No key findings available.");
        document.getElementById('res-methodology').innerHTML  = marked.parse(data.methodology || "No methodology available.");
        document.getElementById('res-limitations').innerHTML  = marked.parse(data.limitations_future || "No limitations available.");

        // Render related papers
        const relatedList = document.getElementById('res-related-papers');
        relatedList.innerHTML = '';
        if (data.related_papers && data.related_papers.length > 0) {
            data.related_papers.forEach(paper => {
                const li = document.createElement('li');
                const safeTitle = escapeHtml(paper.title);
                const safeSnippet = escapeHtml(paper.snippet || '');
                const safeUrl = encodeURI(paper.url || '#');
                li.innerHTML = `
                    <a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${safeTitle}</a>
                    <p>${safeSnippet}</p>
                `;
                relatedList.appendChild(li);
            });
        } else {
            relatedList.innerHTML = '<li>No related papers found.</li>';
        }

        stopLoading();
        resultsSection.style.display = 'block';
        resultsSection.scrollIntoView({ behavior: 'smooth' });
    }

    // ── QA Logic ─────────────────────────────────────
    qaSubmitBtn.addEventListener('click', askQuestion);
    qaInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') askQuestion(); });

    async function askQuestion() {
        const question = qaInput.value.trim();
        if (!question || !extractedPaperText) return;

        addQAMessage(escapeHtml(question), 'user');
        qaInput.value = '';
        qaSubmitBtn.disabled = true;

        try {
            const response = await fetch('/api/qa', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ paper_text: extractedPaperText, question })
            });
            if (!response.ok) throw new Error("Failed to get answer");
            const data = await response.json();
            addQAMessage(marked.parse(data.answer), 'bot');
        } catch (err) {
            addQAMessage("Sorry, an error occurred while processing your question.", 'bot');
        } finally {
            qaSubmitBtn.disabled = false;
        }
    }

    function addQAMessage(html, sender) {
        const div = document.createElement('div');
        div.className = `qa-msg ${sender}`;
        div.innerHTML = html;
        qaHistory.appendChild(div);
        qaHistory.scrollTop = qaHistory.scrollHeight;
    }

    // ── PDF Download — text-based via jsPDF ──────────
    downloadPdfBtn.addEventListener('click', () => {
        // jsPDF is bundled inside html2pdf as window.jspdf
        const { jsPDF } = window.jspdf;
        const doc = new jsPDF({ unit: 'mm', format: 'a4', orientation: 'portrait' });

        const PAGE_W = doc.internal.pageSize.getWidth();
        const PAGE_H = doc.internal.pageSize.getHeight();
        const MARGIN_L = 20;
        const MARGIN_R = 20;
        const MARGIN_T = 22;
        const MARGIN_B = 22;
        const CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R;
        let y = MARGIN_T;

        // Color palette
        const COLORS = {
            accent:     [37,  99,  235],  // blue
            title:      [15,  23,  42],   // near black
            heading:    [37,  99,  235],  // blue for section h3
            subheading: [71,  85,  105],  // slate-600 for ### subs
            body:       [30,  41,  59],   // slate-800
            muted:      [100, 116, 139],  // slate-500
            divider:    [226, 232, 240],  // slate-200
            link:       [37,  99,  235],
        };

        function setColor(rgb) { doc.setTextColor(rgb[0], rgb[1], rgb[2]); }
        function setDrawColor(rgb) { doc.setDrawColor(rgb[0], rgb[1], rgb[2]); }

        function checkPage(needed = 8) {
            if (y + needed > PAGE_H - MARGIN_B) {
                doc.addPage();
                y = MARGIN_T;
            }
        }

        function drawHRule(color = COLORS.divider) {
            checkPage(4);
            setDrawColor(color);
            doc.setLineWidth(0.3);
            doc.line(MARGIN_L, y, PAGE_W - MARGIN_R, y);
            y += 4;
        }

        function addWrappedText(text, fontSize, color, opts = {}) {
            const { bold = false, indent = 0, lineHeightFactor = 1.5, maxWidth } = opts;
            doc.setFontSize(fontSize);
            setColor(color);
            doc.setFont('helvetica', bold ? 'bold' : 'normal');
            const mw = maxWidth || (CONTENT_W - indent);
            const lines = doc.splitTextToSize(text, mw);
            const lineH = fontSize * 0.3528 * lineHeightFactor; // pt to mm approx
            checkPage(lineH * lines.length + 2);
            doc.text(lines, MARGIN_L + indent, y);
            y += lineH * lines.length;
            return lineH * lines.length;
        }

        // ── Cover block ──────────────────────────────
        // ResearchBeacon brand line
        doc.setFontSize(10);
        doc.setFont('helvetica', 'bold');
        setColor(COLORS.accent);
        doc.text('ResearchBeacon', MARGIN_L, y);
        doc.setFont('helvetica', 'normal');
        setColor(COLORS.muted);
        doc.setFontSize(9);
        const dateStr = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
        doc.text(dateStr, PAGE_W - MARGIN_R, y, { align: 'right' });
        y += 6;
        drawHRule(COLORS.accent);
        y += 2;

        // Paper title
        doc.setFontSize(17);
        doc.setFont('helvetica', 'bold');
        setColor(COLORS.title);
        const titleLines = doc.splitTextToSize(currentPaperTitle, CONTENT_W);
        doc.text(titleLines, MARGIN_L, y);
        y += titleLines.length * 7 + 2;

        // Authors
        if (currentAuthors && currentAuthors !== "Authors not listed") {
            doc.setFontSize(9.5);
            doc.setFont('helvetica', 'normal');
            setColor(COLORS.muted);
            const authLines = doc.splitTextToSize(currentAuthors, CONTENT_W);
            doc.text(authLines, MARGIN_L, y);
            y += authLines.length * 4.5 + 3;
        }
        y += 4;
        drawHRule();

        // ── Render a section ─────────────────────────
        function renderSection(icon, label, markdownText) {
            checkPage(14);
            y += 3;

            // Section heading
            doc.setFontSize(12);
            doc.setFont('helvetica', 'bold');
            setColor(COLORS.heading);
            doc.text(`${icon}  ${label}`, MARGIN_L, y);
            y += 2;
            drawHRule();

            // Parse the markdown text line by line
            const lines = markdownText.split('\n');
            for (const rawLine of lines) {
                const line = rawLine.trimEnd();
                if (!line.trim()) { y += 2; continue; }

                if (line.startsWith('### ')) {
                    // Sub-heading
                    checkPage(8);
                    y += 2;
                    const sub = line.replace(/^###\s*/, '').trim();
                    doc.setFontSize(9);
                    doc.setFont('helvetica', 'bold');
                    setColor(COLORS.subheading);
                    const subLines = doc.splitTextToSize(sub.toUpperCase(), CONTENT_W);
                    doc.text(subLines, MARGIN_L, y);
                    y += subLines.length * 4 + 1;

                } else if (line.startsWith('## ')) {
                    checkPage(8);
                    y += 2;
                    const sub = line.replace(/^##\s*/, '').trim();
                    addWrappedText(sub, 10, COLORS.subheading, { bold: true });
                    y += 1;

                } else if (line.match(/^[-*]\s+/)) {
                    // Bullet point
                    checkPage(6);
                    const bulletText = line.replace(/^[-*]\s+/, '').trim();
                    // Strip markdown inline (bold, italic, code, HTML tags)
                    const clean = stripInlineMarkdown(bulletText);
                    // Bullet dot
                    doc.setFontSize(10);
                    doc.setFont('helvetica', 'normal');
                    setColor(COLORS.accent);
                    doc.text('•', MARGIN_L + 1, y);
                    // Bullet text
                    setColor(COLORS.body);
                    const bLines = doc.splitTextToSize(clean, CONTENT_W - 8);
                    const lineH = 10 * 0.3528 * 1.5;
                    checkPage(lineH * bLines.length + 1);
                    doc.text(bLines, MARGIN_L + 6, y);
                    y += lineH * bLines.length + 0.5;

                } else {
                    // Regular paragraph text
                    const clean = stripInlineMarkdown(line.trim());
                    if (clean) {
                        addWrappedText(clean, 10, COLORS.body, { lineHeightFactor: 1.5 });
                        y += 0.5;
                    }
                }
            }
            y += 4;
        }

        // ── Related Papers section ───────────────────
        function renderRelatedPapers(papers) {
            if (!papers || papers.length === 0) return;
            checkPage(14);
            y += 3;
            doc.setFontSize(12);
            doc.setFont('helvetica', 'bold');
            setColor(COLORS.heading);
            doc.text('🔗  Related Papers', MARGIN_L, y);
            y += 2;
            drawHRule();

            papers.forEach((paper, idx) => {
                checkPage(16);
                // Title as link-styled text
                doc.setFontSize(10);
                doc.setFont('helvetica', 'bold');
                setColor(COLORS.link);
                const titleLines = doc.splitTextToSize(`${idx + 1}. ${paper.title}`, CONTENT_W);
                doc.text(titleLines, MARGIN_L, y);
                y += titleLines.length * 4.5 + 1;

                // Snippet
                if (paper.snippet) {
                    doc.setFontSize(9);
                    doc.setFont('helvetica', 'normal');
                    setColor(COLORS.muted);
                    const snippetLines = doc.splitTextToSize(paper.snippet, CONTENT_W - 4);
                    checkPage(snippetLines.length * 4 + 2);
                    doc.text(snippetLines, MARGIN_L + 2, y);
                    y += snippetLines.length * 4 + 1;
                }

                // URL in tiny muted text
                if (paper.url) {
                    doc.setFontSize(7.5);
                    setColor(COLORS.muted);
                    const urlTrunc = paper.url.length > 80 ? paper.url.slice(0, 77) + '...' : paper.url;
                    doc.text(urlTrunc, MARGIN_L + 2, y);
                    y += 4;
                }

                if (idx < papers.length - 1) {
                    setDrawColor(COLORS.divider);
                    doc.setLineWidth(0.2);
                    doc.line(MARGIN_L, y, PAGE_W - MARGIN_R, y);
                    y += 3;
                }
            });
        }

        // ── Render all sections ──────────────────────
        renderSection('📋', 'Summary', rawSections.summary);
        renderSection('🔑', 'Key Findings & Contributions', rawSections.key_findings);
        renderSection('🔬', 'Methodology', rawSections.methodology);
        renderSection('⚠', 'Limitations & Future Work', rawSections.limitations_future);
        renderRelatedPapers(rawSections.related_papers);

        // ── Footer on every page ─────────────────────
        const totalPages = doc.getNumberOfPages();
        for (let i = 1; i <= totalPages; i++) {
            doc.setPage(i);
            doc.setFontSize(7.5);
            doc.setFont('helvetica', 'normal');
            setColor(COLORS.muted);
            doc.text(`ResearchBeacon  ·  Page ${i} of ${totalPages}`, PAGE_W / 2, PAGE_H - 10, { align: 'center' });
        }

        doc.save('researchbeacon-analysis.pdf');
    });

    // ── Strip inline markdown for plain text PDF ─────
    function stripInlineMarkdown(text) {
        return text
            .replace(/\*\*(.+?)\*\*/g, '$1')  // **bold**
            .replace(/\*(.+?)\*/g, '$1')        // *italic*
            .replace(/_(.+?)_/g, '$1')          // _italic_
            .replace(/`(.+?)`/g, '$1')          // `code`
            .replace(/<\/?[a-z][^>]*>/gi, '')   // HTML tags
            .replace(/&amp;/g, '&')
            .replace(/&lt;/g, '<')
            .replace(/&gt;/g, '>')
            .trim();
    }

    // ── Helpers ───────────────────────────────────────
    function startLoading() {
        errorBanner.style.display = 'none';
        resultsSection.style.display = 'none';
        loadingSection.style.display = 'block';

        const steps = document.querySelectorAll('.step');
        let i = 0;
        steps.forEach(s => s.classList.remove('active'));

        window.loadingInterval = setInterval(() => {
            steps.forEach(s => s.classList.remove('active'));
            if (i < steps.length) { steps[i].classList.add('active'); i++; }
        }, 3000);
    }

    function stopLoading() {
        loadingSection.style.display = 'none';
        if (window.loadingInterval) clearInterval(window.loadingInterval);
    }

    function showError(msg) {
        errorBanner.textContent = msg;
        errorBanner.style.display = 'block';
        setTimeout(() => { errorBanner.style.display = 'none'; }, 6000);
    }

    function showNotResearchPaperError(msg) {
        errorBanner.innerHTML = `
            <div style="font-size:1.6rem;margin-bottom:0.4rem;">🔍</div>
            <strong>Oops! This doesn't look like a research paper.</strong><br>
            <span style="font-weight:400;font-size:0.9rem;">${escapeHtml(msg)}</span>
        `;
        errorBanner.style.display = 'block';
        setTimeout(() => { errorBanner.style.display = 'none'; }, 8000);
    }

    function escapeHtml(text) {
        const el = document.createElement('div');
        el.appendChild(document.createTextNode(String(text)));
        return el.innerHTML;
    }
});
