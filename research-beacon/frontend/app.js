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
                const safeSnippet = marked.parse(paper.snippet || '');
                const safeUrl = encodeURI(paper.url || '#');
                li.innerHTML = `
                    <a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${safeTitle}</a>
                    ${safeSnippet}
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

    // ── PDF Download — clean text-based via jsPDF ────
    downloadPdfBtn.addEventListener('click', () => {
        // jsPDF UMD exports as window.jspdf.jsPDF
        const { jsPDF } = window.jspdf;
        const doc = new jsPDF({ unit: 'mm', format: 'a4', orientation: 'portrait' });

        const PAGE_W  = doc.internal.pageSize.getWidth();   // 210
        const PAGE_H  = doc.internal.pageSize.getHeight();  // 297
        const ML = 18, MR = 18, MT = 20, MB = 20;
        const CW = PAGE_W - ML - MR;   // content width
        let y = MT;

        // ── Colour palette ────────────────────────────
        const C = {
            accent:  [45,  104,  255], // Brilliant Blue
            title:   [15,  23,  42], // Deep Slate
            heading: [25,  60,  150], // Navy Blue
            sub:     [71,  85,  105], // Slate-500
            body:    [30,  41,  59], // Slate-800
            muted:   [100, 116, 139], // Slate-400
            divider: [226, 232, 240], // Light gray
            link:    [37,  99,  235], // Blue
        };
        const rgb  = (c) => doc.setTextColor(c[0], c[1], c[2]);
        const drgb = (c) => doc.setDrawColor(c[0], c[1], c[2]);
        const frgb = (c) => doc.setFillColor(c[0], c[1], c[2]);

        // ── Helpers ───────────────────────────────────
        // Line height in mm for a given font-size in pt
        const lhMm = (ptSize, factor = 1.4) => ptSize * 0.3528 * factor;

        function newPageIfNeeded(spaceNeeded = 10) {
            if (y + spaceNeeded > PAGE_H - MB) {
                doc.addPage();
                y = MT;
            }
        }

        function hRule(color = C.divider, weight = 0.25) {
            newPageIfNeeded(5);
            drgb(color);
            doc.setLineWidth(weight);
            doc.line(ML, y, PAGE_W - MR, y);
            y += 4;
        }

        // Render wrapped text block; returns height used
        function textBlock(text, ptSize, color, opts = {}) {
            const { bold = false, indent = 0, leading = 1.4, maxW } = opts;
            doc.setFontSize(ptSize);
            doc.setFont('helvetica', bold ? 'bold' : 'normal');
            rgb(color);
            const w     = (maxW !== undefined ? maxW : CW) - indent;
            const lines = doc.splitTextToSize(text, w);
            const lh    = lhMm(ptSize, leading);
            newPageIfNeeded(lh * lines.length + 2);
            doc.text(lines, ML + indent, y, { lineHeightFactor: leading });
            y += lh * lines.length;
            return lh * lines.length;
        }

        // ── Header bar ────────────────────────────────
        doc.setFontSize(10);
        doc.setFont('helvetica', 'bold');
        rgb(C.accent);
        doc.text('ResearchBeacon', ML, y);
        doc.setFont('helvetica', 'normal');
        doc.setFontSize(9);
        rgb(C.muted);
        const dateStr = new Date().toLocaleDateString('en-US', {
            year: 'numeric', month: 'long', day: 'numeric'
        });
        doc.text(dateStr, PAGE_W - MR, y, { align: 'right' });
        y += 5;
        hRule(C.accent, 0.5);
        y += 8; // Extra space so title doesn't hit the blue line

        // Paper title
        doc.setFontSize(22); // Slightly larger title
        doc.setFont('helvetica', 'bold');
        rgb(C.title);
        const titleWrapped = doc.splitTextToSize(currentPaperTitle, CW);
        newPageIfNeeded(lhMm(22, 1.4) * titleWrapped.length + 8);
        doc.text(titleWrapped, ML, y, { lineHeightFactor: 1.4 });
        y += lhMm(22, 1.4) * titleWrapped.length + 4; // Space below title

        // Authors
        if (currentAuthors && currentAuthors !== 'Authors not listed') {
            doc.setFontSize(11);
            doc.setFont('helvetica', 'normal'); 
            rgb(C.muted);
            const cleanAuthors = currentAuthors.replace(/\s{2,}/g, ' ').trim();
            const authWrapped = doc.splitTextToSize(cleanAuthors, CW);
            newPageIfNeeded(lhMm(11, 1.5) * authWrapped.length + 6);
            doc.text(authWrapped, ML, y, { lineHeightFactor: 1.5 });
            y += lhMm(11, 1.5) * authWrapped.length + 5;
        }
        y += 3;
        hRule();

        // ── Section renderer ──────────────────────────
        // Section labels — ASCII only (no emojis; jsPDF helvetica can't render them)
        const SECTION_LABELS = {
            summary:            'Summary',
            key_findings:       'Key Findings & Contributions',
            methodology:        'Methodology',
            limitations_future: 'Limitations & Future Work',
        };

        function renderSection(label, markdownText, isLast = false) {
            if (!markdownText || !markdownText.trim()) return;
            newPageIfNeeded(20);
            y += 5;

            // Section heading accent bar
            frgb(C.accent);
            doc.rect(ML, y - 4, 3, 6, 'F');

            doc.setFontSize(13);
            doc.setFont('helvetica', 'bold');
            rgb(C.heading);
            doc.text(label.toUpperCase(), ML + 5, y);
            y += 4;

            const lines = markdownText.split('\n');
            for (const rawLine of lines) {
                const line = rawLine.trimEnd();
                if (!line.trim()) { y += 2; continue; }

                if (line.startsWith('### ')) {
                    // Sub-heading
                    newPageIfNeeded(12);
                    y += 3;
                    const subText = line.replace(/^###\s*/, '').trim();
                    const clean   = stripInlineMarkdown(subText).toUpperCase();
                    doc.setFontSize(9);
                    doc.setFont('helvetica', 'bold');
                    rgb(C.sub);
                    const subWrapped = doc.splitTextToSize(clean, CW);
                    doc.text(subWrapped, ML, y, { lineHeightFactor: 1.5 });
                    y += lhMm(9, 1.5) * subWrapped.length + 1.5;

                } else if (line.startsWith('## ') || line.startsWith('# ')) {
                    newPageIfNeeded(12);
                    y += 2.5;
                    const subText = line.replace(/^#{1,2}\s*/, '').trim();
                    textBlock(stripInlineMarkdown(subText), 11, C.sub, { bold: true });
                    y += 1.5;

                } else if (/^[-*]\s+/.test(line)) {
                    // Bullet point
                    const bulletText = line.replace(/^[-*]\s+/, '').trim();
                    const clean = stripInlineMarkdown(bulletText);
                    const ptSize = 10;
                    const lh = lhMm(ptSize, 1.4); // slightly larger line height for readability
                    const bulletW = CW - 7;
                    
                    // CRITICAL: Set font BEFORE splitting so measurements are accurate
                    doc.setFontSize(ptSize);
                    doc.setFont('helvetica', 'normal');
                    
                    const bLines = doc.splitTextToSize(clean, bulletW);
                    newPageIfNeeded(lh * bLines.length + 3);

                    // Bullet dot
                    doc.setFontSize(14);
                    doc.setFont('helvetica', 'normal');
                    rgb(C.accent);
                    doc.text('\u2022', ML + 1, y);   // Unicode bullet (safe in jsPDF)

                    // Bullet text
                    doc.setFontSize(ptSize);
                    doc.setFont('helvetica', 'normal');
                    rgb(C.body);
                    doc.text(bLines, ML + 7, y, { lineHeightFactor: 1.4 });
                    y += lh * bLines.length + 1.5;

                } else {
                    // Paragraph
                    const clean = stripInlineMarkdown(line.trim());
                    if (clean) textBlock(clean, 10, C.body, { leading: 1.4 });
                    y += 1;
                }
            }
            y += 4;
            if (!isLast) hRule(C.divider, 0.25);
        }

        // ── Related papers renderer ───────────────────
        function renderRelatedPapers(papers) {
            if (!papers || papers.length === 0) return;
            newPageIfNeeded(20);
            y += 5;

            frgb(C.accent);
            doc.rect(ML, y - 4, 3, 6, 'F');
            doc.setFontSize(13);
            doc.setFont('helvetica', 'bold');
            rgb(C.heading);
            doc.text('RELATED PAPERS', ML + 5, y);
            y += 8; // Increased spacing to prevent overlap with section header

            papers.forEach((paper, idx) => {
                newPageIfNeeded(25);
                // Title
                const titleText = `${idx + 1}.  ${paper.title || 'Untitled'}`;
                doc.setFontSize(10.5);
                doc.setFont('helvetica', 'bold');
                rgb(C.link);
                const tLines = doc.splitTextToSize(titleText, CW);
                doc.text(tLines, ML, y, { lineHeightFactor: 1.4 });
                y += lhMm(10.5, 1.4) * tLines.length + 2;

                // Snippet
                if (paper.snippet) {
                    doc.setFontSize(9.5);
                    doc.setFont('helvetica', 'normal');
                    rgb(C.body);
                    const cleanSnippet = stripInlineMarkdown(paper.snippet);
                    const sLines = doc.splitTextToSize(cleanSnippet, CW - 4);
                    doc.text(sLines, ML + 4, y, { lineHeightFactor: 1.45 });
                    y += lhMm(9.5, 1.45) * sLines.length + 2;
                }

                // URL
                if (paper.url) {
                    doc.setFontSize(8);
                    doc.setFont('helvetica', 'normal');
                    rgb(C.muted);
                    const urlText = paper.url.length > 90
                        ? paper.url.slice(0, 87) + '...'
                        : paper.url;
                    const uLines = doc.splitTextToSize(urlText, CW - 4);
                    doc.text(uLines, ML + 4, y, { lineHeightFactor: 1.3 });
                    y += lhMm(8, 1.3) * uLines.length + 3;
                }

                // Divider between papers
                if (idx < papers.length - 1) {
                    y += 3; // Minimal gap before divider
                    drgb(C.divider);
                    doc.setLineWidth(0.2);
                    doc.line(ML + 4, y, PAGE_W - MR, y);
                    y += 5; // Space after divider
                }
            });
        }

        // ── Render all sections ───────────────────────
        const sectionsToRender = [
            { label: SECTION_LABELS.summary, text: rawSections.summary },
            { label: SECTION_LABELS.key_findings, text: rawSections.key_findings },
            { label: SECTION_LABELS.methodology, text: rawSections.methodology },
            { label: SECTION_LABELS.limitations_future, text: rawSections.limitations_future }
        ].filter(s => s.text && s.text.trim());

        sectionsToRender.forEach((s, idx) => {
            const isLastSection = (idx === sectionsToRender.length - 1) && (!rawSections.related_papers || rawSections.related_papers.length === 0);
            renderSection(s.label, s.text, isLastSection);
        });

        renderRelatedPapers(rawSections.related_papers);

        // ── Page footers ──────────────────────────────
        const totalPages = doc.getNumberOfPages();
        for (let i = 1; i <= totalPages; i++) {
            doc.setPage(i);
            drgb(C.divider);
            doc.setLineWidth(0.2);
            doc.line(ML, PAGE_H - MB + 4, PAGE_W - MR, PAGE_H - MB + 4);
            doc.setFontSize(7.5);
            doc.setFont('helvetica', 'normal');
            rgb(C.muted);
            doc.text(
                `ResearchBeacon  \u00B7  Page ${i} of ${totalPages}`,
                PAGE_W / 2, PAGE_H - MB + 9, { align: 'center' }
            );
        }

        const safeName = (currentPaperTitle || 'analysis')
            .slice(0, 40)
            .replace(/[^a-z0-9\s-]/gi, '')
            .trim()
            .replace(/\s+/g, '-')
            .toLowerCase();
        doc.save(`researchbeacon-${safeName}.pdf`);
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
    }

    function escapeHtml(text) {
        const el = document.createElement('div');
        el.appendChild(document.createTextNode(String(text)));
        return el.innerHTML;
    }
});
