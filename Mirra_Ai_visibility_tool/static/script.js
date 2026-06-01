// Track selected model — default is 'all'
let selectedModel = 'all';
let selectedLanguage = 'en';

const LANGUAGE_UI = {
    en: {
        appTitle: '🔍 AI Visibility Audit Tool',
        subtitle: 'Find out how AI systems see your brand — and how to improve it.',
        companyPlaceholder: 'Company name e.g. Nike, Apple...',
        websitePlaceholder: 'e.g. nike.com or nike.com/running-shoes',
        runAudit: 'Run Audit',
        downloadPdf: 'Download PDF',
        inputHint: '💡 Enter just a domain for a brand audit — or a specific page URL for a page-level audit',
        loading: 'Querying local Ollama models... this may take a few seconds.',
        modelLabel: 'Run with:',
        languageLabel: 'Language:'
    },
    de: {
        appTitle: '🔍 KI-Sichtbarkeits-Audit',
        subtitle: 'Finden Sie heraus, wie KI-Systeme Ihre Marke sehen — und wie Sie sie verbessern.',
        companyPlaceholder: 'Firmenname z. B. Nike, Apple...',
        websitePlaceholder: 'z. B. nike.com oder nike.com/running-shoes',
        runAudit: 'Audit starten',
        downloadPdf: 'PDF herunterladen',
        inputHint: '💡 Geben Sie nur eine Domain für ein Marken-Audit ein — oder eine spezielle Seiten-URL für ein Seiten-Audit',
        loading: 'Lokale Ollama-Modelle werden abgefragt... das kann einige Sekunden dauern.',
        modelLabel: 'Ausführen mit:',
        languageLabel: 'Sprache:'
    },
    it: {
        appTitle: '🔍 Controllo visibilità AI',
        subtitle: 'Scopri come i sistemi AI vedono il tuo brand e come migliorarlo.',
        companyPlaceholder: 'Nome azienda es. Nike, Apple...',
        websitePlaceholder: 'es. nike.com o nike.com/running-shoes',
        runAudit: 'Esegui audit',
        downloadPdf: 'Scarica PDF',
        inputHint: '💡 Inserisci solo un dominio per un audit brand — o un URL specifico per un audit di pagina',
        loading: 'Interrogando i modelli Ollama locali... questo potrebbe richiedere qualche secondo.',
        modelLabel: 'Esegui con:',
        languageLabel: 'Lingua:'
    },
    ja: {
        appTitle: '🔍 AI可視化監査ツール',
        subtitle: 'AIシステムがあなたのブランドをどのように見ているか、そして改善方法を見つけます。',
        companyPlaceholder: '会社名 例: Nike, Apple...',
        websitePlaceholder: '例: nike.com または nike.com/running-shoes',
        runAudit: '監査を実行',
        downloadPdf: 'PDFをダウンロード',
        inputHint: '💡 ブランド監査にはドメインのみを入力してください。ページ監査には特定のページURLを入力してください。',
        loading: 'ローカルのOllamaモデルに問い合わせています... しばらくお待ちください。',
        modelLabel: '実行モデル:',
        languageLabel: '言語:'
    }
};

const LANGUAGE_KEYWORDS = {
    en: {
        productWords: ['product', 'service', 'offer', 'provide', 'sell', 'platform', 'tool', 'software', 'app', 'solution'],
        positiveWords: ['trusted', 'reliable', 'popular', 'leading', 'reputable', 'well-known', 'established', 'successful'],
        negativeWords: ['scam', 'fraud', 'unreliable', 'controversial', 'complaints', 'issues', 'problems', 'avoid'],
        competitorWords: ['competitor', 'alternative', 'compared to', 'versus', 'vs', 'rival', 'competing', 'other options']
    },
    de: {
        productWords: ['produkt', 'dienstleistung', 'angebot', 'bietet', 'plattform', 'tool', 'software', 'app', 'lösung'],
        positiveWords: ['zuverlässig', 'vertrauenswürdig', 'beliebt', 'führend', 'renommiert', 'bekannt', 'etabliert', 'erfolgreich'],
        negativeWords: ['betrug', 'unzuverlässig', 'kontrovers', 'beschwerden', 'probleme', 'vermeiden', 'schlecht'],
        competitorWords: ['konkurrent', 'alternative', 'im vergleich', 'versus', 'vs', 'rivale', 'wettbewerb', 'andere optionen', 'mitbewerber']
    },
    it: {
        productWords: ['prodotto', 'servizio', 'offre', 'offerta', 'piattaforma', 'strumento', 'software', 'app', 'soluzione'],
        positiveWords: ['affidabile', 'fidato', 'popolare', 'leader', 'stimato', 'ben noto', 'stabile', 'di successo'],
        negativeWords: ['truffa', 'frode', 'inaffidabile', 'controverso', 'reclami', 'problemi', 'evitare'],
        competitorWords: ['concorrente', 'alternativa', 'rispetto a', 'versus', 'vs', 'rivale', 'competendo', 'altre opzioni']
    },
    ja: {
        productWords: ['製品', 'サービス', '提供', 'プラットフォーム', 'ツール', 'ソフトウェア', 'アプリ', 'ソリューション'],
        positiveWords: ['信頼', '信頼できる', '人気', 'リード', '評判', '確立', '成功'],
        negativeWords: ['詐欺', '信頼できない', '問題', '苦情', '避ける', '悪い', '不安'],
        competitorWords: ['競合', 'ライバル', '比較', '他社', '代替', '対抗']
    }
};

function applyLanguageUI(language) {
    const ui = LANGUAGE_UI[language] || LANGUAGE_UI.en;
    document.documentElement.lang = language;
    document.querySelector('header h1').textContent = ui.appTitle;
    document.querySelector('header p').textContent = ui.subtitle;
    document.getElementById('companyInput').placeholder = ui.companyPlaceholder;
    document.getElementById('websiteInput').placeholder = ui.websitePlaceholder;
    document.getElementById('auditBtn').textContent = ui.runAudit;
    document.getElementById('downloadPdfBtn').textContent = ui.downloadPdf;
    document.querySelector('.input-hint').textContent = ui.inputHint;
    document.getElementById('loading').querySelector('p').textContent = ui.loading;
    document.getElementById('modelLabel').textContent = ui.modelLabel;
    document.getElementById('languageLabel').textContent = ui.languageLabel;
}

async function runAudit() {
    const company = document.getElementById('companyInput').value.trim();
    const website = document.getElementById('websiteInput').value.trim();

    if (!company) {
        alert('Please enter a company name!');
        return;
    }

    // Show loading, hide results
    document.getElementById('loading').classList.remove('hidden');
    document.getElementById('results').classList.add('hidden');
    document.getElementById('auditBtn').disabled = true;

    try {
        document.getElementById('downloadPdfBtn').classList.add('hidden');
        document.getElementById('downloadPdfBtn').disabled = true;
        const response = await fetch('/audit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ company: company, website: website, selected_model: selectedModel, language: selectedLanguage })
        });

        const data = await response.json();
        displayResults(data);

    } catch (error) {
        alert('Something went wrong. Please try again.');
        console.error(error);
    } finally {
        document.getElementById('loading').classList.add('hidden');
        document.getElementById('auditBtn').disabled = false;
    }
}

// ─────────────────────────────────────────────────────────────────────────────.
// It counts the actual number of valid (non-error) responses dynamically.
// This means the score stays accurate whether you have 4 providers or 5.
// ─────────────────────────────────────────────────────────────────────────────
function scoreCompany(results) {
    let total = 0;
    let count = 0;  // counts only successful (non-error) responses
    let flags = [];

    // We'll also collect breakdowns per parameter so suggestions can estimate impact
    const breakdownTotals = { companyMention: 0, products: 0, length: 0, sentiment: 0, competitive: 0 };
    let breakdownCount = 0;

    results.results.forEach(item => {
        Object.values(item.responses).forEach(response => {
            if (!response.startsWith('Error')) {
                const { score, flags: responseFlags, breakdown } = scoreModel(results.company, response, results.language || 'en');
                total += score;
                count++;                    // only count successes
                flags.push(...responseFlags);
                // accumulate breakdown raw points (0-20/10 as defined in scoreModel)
                if (breakdown) {
                    breakdownTotals.companyMention += breakdown.companyMention.points;
                    breakdownTotals.products += breakdown.products.points;
                    breakdownTotals.length += breakdown.length.points;
                    breakdownTotals.sentiment += breakdown.sentiment.points;
                    breakdownTotals.competitive += breakdown.competitive.points;
                    breakdownCount++;
                }
            } else {
                flags.push('response_error');
            }
        });
    });

    // Avoid dividing by zero if all providers errored
    const score = count === 0 ? 0 : Math.min(100, Math.round(total / count));

    // Compute average breakdown percentages (out of their max possible points)
    const breakdownAverages = breakdownCount === 0 ? {
        companyMention: 0,
        products: 0,
        length: 0,
        sentiment: 0,
        competitive: 0
    } : {
        companyMention: Math.round((breakdownTotals.companyMention / (breakdownCount * 20)) * 100),
        products: Math.round((breakdownTotals.products / (breakdownCount * 20)) * 100),
        length: Math.round((breakdownTotals.length / (breakdownCount * 20)) * 100),
        sentiment: Math.round((breakdownTotals.sentiment / (breakdownCount * 20)) * 100),
        competitive: Math.round((breakdownTotals.competitive / (breakdownCount * 20)) * 100)
    };

    return { score, flags: [...new Set(flags)], breakdownAverages };
}

function scoreModel(company, response, language = 'en') {
    const companyLower = company.toLowerCase();
    const r = response.toLowerCase();
    const keywords = LANGUAGE_KEYWORDS[language] || LANGUAGE_KEYWORDS.en;
    let score = 0;
    let flags = [];

    const breakdown = {
        companyMention: { present: false, points: 0, max: 20 },
        products: { present: false, points: 0, max: 20 },
        length: { present: false, points: 0, max: 20 },
        sentiment: { present: false, points: 0, max: 20 },
        competitive: { present: false, points: 0, max: 20 }
    };

    // 1. Brand clarity
    if (r.includes(companyLower)) {
        breakdown.companyMention.present = true;
        breakdown.companyMention.points = 20;
        score += 20;
    } else flags.push('not_mentioned');

    // 2. Product/service clarity — needs 2+ matches for full points
    const productMatches = keywords.productWords.filter(w => r.includes(w)).length;
    if (productMatches >= 2) {
        breakdown.products.present = true;
        breakdown.products.points = 20;
        score += 20;
    } else if (productMatches === 1) {
        breakdown.products.points = 10;
        score += 10;
        flags.push('no_products');
    } else {
        flags.push('no_products');
    }

    // 3. Content depth
    if (r.length > 500) {
        breakdown.length.present = true;
        breakdown.length.points = 20;
        score += 20;
    } else if (r.length > 200) {
        breakdown.length.points = 10;
        score += 10;
        flags.push('too_vague');
    } else {
        flags.push('too_vague');
    }

    // 4. Sentiment
    const hasPositive = keywords.positiveWords.some(w => r.includes(w));
    const hasNegative = keywords.negativeWords.some(w => r.includes(w));

    if (hasPositive && !hasNegative) {
        breakdown.sentiment.present = true;
        breakdown.sentiment.points = 20;
        score += 20;
    } else if (hasNegative) {
        flags.push('negative_sentiment');
    } else {
        breakdown.sentiment.points = 10;
        score += 10;
    }

    // 5. Competitive awareness
    const competitorMatches = keywords.competitorWords.filter(w => r.includes(w)).length;
    if (competitorMatches >= 2) {
        breakdown.competitive.present = true;
        breakdown.competitive.points = 20;
        score += 20;
    } else if (competitorMatches === 1) {
        breakdown.competitive.points = 10;
        score += 10;
        flags.push('no_competitors');
    } else {
        flags.push('no_competitors');
    }

    return {
        score: Math.min(100, score),
        flags: [...new Set(flags)],
        breakdown
    };
}

function getSuggestions(flags, modelScores, company, breakdownAverages, baseScore) {
    const suggestions = [];

    function estimateUplift(paramMaxPoints) {
        const approx = {
            companyMention: Math.round((breakdownAverages.companyMention / 100) * 20),
            products: Math.round((breakdownAverages.products / 100) * 20),
            length: Math.round((breakdownAverages.length / 100) * 10)
        };

        let potentialGainRaw = 0;
        if (paramMaxPoints.companyMention) potentialGainRaw += (paramMaxPoints.companyMention - approx.companyMention);
        if (paramMaxPoints.products) potentialGainRaw += (paramMaxPoints.products - approx.products);
        if (paramMaxPoints.length) potentialGainRaw += (paramMaxPoints.length - approx.length);

        const potentialGainScore = Math.round((potentialGainRaw / 50) * 100);
        const newScore = Math.min(100, baseScore + potentialGainScore);
        const absoluteIncrease = Math.max(0, newScore - baseScore);
        const percentIncrease = baseScore === 0 ? absoluteIncrease * 2 : Math.round((absoluteIncrease / baseScore) * 100);

        return { absoluteIncrease, percentIncrease, newScore };
    }

    const brandFocus = breakdownAverages.companyMention;
    const productFocus = breakdownAverages.products;
    const contentFocus = breakdownAverages.length;

    if (brandFocus < 100) {
        const uplift = estimateUplift({ companyMention: 20, products: 0, length: 0 });
        suggestions.push({
            priority: '🔴 High Priority',
            title: 'Make your brand identity explicit for AI',
            detail: `Your current score shows brand recognition is only ${brandFocus}% across responses. Improve the clarity of your About and homepage content so AI can consistently associate the brand name with what you do.`,
            geo_tip: '💡 GEO Tip: Add a clear mission statement and an entity-focused About page. Use the brand name within the first 50 words and repeat it naturally in headings and product descriptions.',
            impact: uplift
        });
    }

    if (productFocus < 100) {
        const uplift = estimateUplift({ companyMention: 0, products: 20, length: 0 });
        suggestions.push({
            priority: '🔴 High Priority',
            title: 'Describe your products or services more precisely',
            detail: `AI responses are only ${productFocus}% strong at identifying products or services. Add dedicated, crawlable descriptions for each product or service and include structured markup where possible.`,
            geo_tip: '💡 GEO Tip: Use Schema.org Product or Service markup and clear product headings. AI thrives on explicit product/service language, so avoid vague marketing phrases.',
            impact: uplift
        });
    }

    if (contentFocus < 100) {
        const uplift = estimateUplift({ companyMention: 0, products: 0, length: 10 });
        suggestions.push({
            priority: '🟡 Medium Priority',
            title: 'Expand your content so AI has enough context',
            detail: `Your content depth score is ${contentFocus}%. Longer, more direct content helps AI understand your business and produce richer answers. Add FAQs, use cases, and concise explanations on core pages.`,
            geo_tip: '💡 AEO Tip: Structure your pages with clear Q&A sections, summaries, and short answer blocks. AI answer engines prefer content that can be extracted as a direct response.',
            impact: uplift
        });
    }

    if (flags.includes('negative_sentiment')) {
        const uplift = estimateUplift({ companyMention: 5, products: 5, length: 5 });
        suggestions.push({
            priority: '🔴 High Priority',
            title: 'Improve the tone and authority of your brand coverage',
            detail: 'Some AI responses may reflect negative or uncertain sentiment. Build more positive, authoritative content and third-party coverage to shift the overall message AI sees.',
            geo_tip: '💡 AEO Tip: Publish case studies, customer testimonials, and press mentions to create a stronger positive narrative for AI models.',
            impact: uplift
        });
    }

    suggestions.push({
        priority: '🔵 Best Practice',
        title: 'Build topical authority in your niche',
        detail: 'AI systems favor brands that are clearly an authority on a specific topic. Create a content cluster around your core topic — a main pillar page and multiple supporting articles that all link together. This signals to AI that you are an expert in your space.',
        geo_tip: '💡 GEO Tip: Pick 3-5 core topics directly related to your business and publish at least 5 pieces of content on each. Consistency and depth matter more than volume.'
    });

    suggestions.push({
        priority: '🔵 Best Practice',
        title: 'Optimize for direct answer extraction',
        detail: 'AI answer engines are designed to extract concise answers from web content. Structure your key pages so the most important information appears in the first 2-3 sentences. Use clear headings, short paragraphs, and bullet points.',
        geo_tip: '💡 AEO Tip: Add an FAQ section to your homepage and product pages. Write questions exactly as a user would ask them to an AI — "What is [Company]?," "How does [Product] work?," "Who is [Product] best for?" — and answer them directly below each question.'
    });

    suggestions.push({
        priority: '🔵 Best Practice',
        title: 'Get cited by sources AI trusts',
        detail: 'AI models are heavily influenced by content from Wikipedia, major news outlets, industry publications, and authoritative blogs. A single mention in a trusted source is worth more than dozens of mentions on unknown websites.',
        geo_tip: '💡 GEO Tip: Target HARO (Help a Reporter Out) and similar platforms to get quoted in news articles. Submit your company to relevant industry directories and association websites. These citations build the kind of authority AI systems recognize.'
    });

    return suggestions;
}

function formatResponse(text) {
    return text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/^[\*\•]\s+/gm, '• ')
        .replace(/\n{2,}/g, '</p><p>')
        .replace(/\n/g, '<br>')
        .replace(/^(.+)$/m, '<p>$1</p>');
}

function buildSourcesDropdown(sourcePreviews) {
    if (!sourcePreviews || Object.keys(sourcePreviews).length === 0) {
        return `<div class="sources-dropdown">
            <div class="sources-header">📁 Data Sources Used — click to inspect what AI was fed ▼</div>
            <div class="sources-content" style="display:none">
                <p style="color:#888;">⚠️ No sources were scraped for this audit.</p>
            </div>
        </div>`;
    }

    let items = '';
    const icons = { website: '🌐', wikipedia: '📖', news: '📰' };

    for (const [key, src] of Object.entries(sourcePreviews)) {
        const icon = icons[key] || '📄';
        const content = src.content || 'No preview available.';
        const status = content && content !== 'NA'
            ? `<p style="font-size:0.85em; color:#555;">${content}</p>`
            : `<p style="color:#e55;">❌ Not found or skipped for this audit.</p>`;
        items += `<div style="margin-bottom:12px; text-align:center;">
            <strong>${icon} ${src.label}</strong>${status}
        </div>`;
    }

    return `<div class="sources-dropdown">
        <div class="sources-header" onclick="
            var c = this.nextElementSibling;
            c.style.display = c.style.display === 'none' ? 'block' : 'none';
        " style="cursor:pointer;">
            📁 Data Sources Used — click to inspect what AI was fed ▼
        </div>
        <div class="sources-content" style="display:none">
            ${items}
        </div>
    </div>`;
}

function toggleSources(btn) {
    const content = btn.nextElementSibling;
    content.classList.toggle('hidden');
    btn.textContent = content.classList.contains('hidden')
        ? '📂 Data Sources Used — click to inspect what AI was fed ▼'
        : '📂 Data Sources Used — click to collapse ▲';
}

function displayResults(data) {
    const { score, flags, breakdownAverages } = scoreCompany(data);

    // Score card
    let colorClass = score >= 80 ? 'score-green' : score >= 50 ? 'score-orange' : 'score-red';
    let label = score >= 80 ? '🟢 Strong AI Visibility' : score >= 50 ? '🟡 Moderate AI Visibility' : '🔴 Weak AI Visibility';

    const tooltips = {
        companyMention: "Did AI recognize the company name and know what it does?",
        products: "Could AI describe specific products or services the company offers?",
        length: "Were AI responses detailed enough to be useful — not just 1-2 sentences?",
        sentiment: "Did AI use positive, confident language about the brand?",
        competitive: "Did AI know who the main competitors are in this space?"
    };

    const driverLabels = {
        companyMention: "Brand Clarity",
        products: "Product/Service Clarity",
        length: "Content Depth",
        sentiment: "Sentiment",
        competitive: "Competitive Awareness"
    };

    const breakdownHtml = `
        <div class="score-breakdown-card">
            <h3>📌 Score Drivers</h3>
            <div class="breakdown-row">
                ${Object.keys(driverLabels).map(key => `
                <div class="breakdown-item">
                    <strong>
                        ${driverLabels[key]}
                        <span class="tooltip-icon" title="${tooltips[key]}">ℹ️</span>
                    </strong>
                    <p>${breakdownAverages[key] ?? 0}% of AI responses passed this check.</p>
                </div>`).join('')}
            </div>
        </div>
    `;

    // ─────────────────────────────────────────────────────────────────────────
    // FIX: Safely build the website URL — don't double-add "https://" if the
    // user already typed it. Also handles http:// correctly.
    // ─────────────────────────────────────────────────────────────────────────
    // FIX: Safely build the website URL — don't double-add "https://" if the
    // user already typed it. Also handles http:// correctly.
    // ─────────────────────────────────────────────────────────────────────────
    const websiteHref = data.website
        ? (data.website.startsWith('http') ? data.website : 'https://' + data.website)
        : '';

    // ─────────────────────────────────────────────────────────────────────────
    // Provider display names — matched to the model keys in app.py MODELS dict
    const providerNames = {
        gemma:  '🤖 Gemma 3 4B (Local)',
        qwen7b: '🟣 Qwen 2.5 7B (Local)',
        llama:  '🟠 Llama 3.2 3B (Local)',
        qwen3:  '🟢 Qwen3 4B (Local)',
    };

    let modelTotals = {};
    let allFlags = [];

    data.results.forEach(item => {
        for (const [provider, response] of Object.entries(item.responses)) {
            if (modelTotals[provider] === undefined) modelTotals[provider] = [];
            if (response.startsWith('Error')) {
                modelTotals[provider].push('error');
            } else {
                const { score: modelScore, flags: responseFlags } = scoreModel(data.company, response);
                modelTotals[provider].push(modelScore);
                allFlags.push(...responseFlags);
            }
        }
    });

    // Calculate per-model average — skip errors
    let modelScores = {};
    let allScores = [];
    for (const [provider, scores] of Object.entries(modelTotals)) {
        const validScores = scores.filter(s => s !== 'error');
        const hasError = scores.some(s => s === 'error');
        const allErrors = scores.every(s => s === 'error');

        if (allErrors) {
            modelScores[provider] = 'error';
        } else if (validScores.length > 0) {
            const avg = Math.round(validScores.reduce((a, b) => a + b, 0) / validScores.length);
            modelScores[provider] = hasError ? { score: avg, partial: true } : avg;
            allScores.push(avg);
        }
    }

    document.getElementById('scoreCard').innerHTML = `
        <h2>Audit Results for <strong>${data.company}</strong></h2>
        ${data.website ? `<p style="color:#888; margin-top:4px;">🌐 <a href="${websiteHref}" target="_blank">${data.website}</a></p>` : ''}
        <div class="score-number ${colorClass}">${score}</div>
        <div class="score-label ${colorClass}">${label}</div>
        <p style="color:#888; margin-top:8px;">Score out of 100 based on ${allScores.length} of ${Object.keys(modelTotals).length} AI provider responses${allScores.length < Object.keys(modelTotals).length ? ' ⚠️ <span style="color:#f59e0b;">Some providers failed — score may not be fully reliable</span>' : ''}</p>
        <div style="margin-top:10px;">
            ${data.audit_type === 'page'
                ? '<span class="audit-type-badge badge-page">📄 Page-Level Audit</span>'
                : '<span class="audit-type-badge badge-brand">🏢 Brand-Level Audit</span>'}
        </div>
        ${data.fetch_error ? '<div class="fetch-error">⚠️ Could not fetch the page content — falling back to brand-level audit instead.</div>' : ''}
        ${data.has_fresh_data
            ? `<div class="fresh-data-badge">🌐 Enriched with fresh web data from: ${data.sources.join(', ')}</div>`
            : '<div class="stale-data-badge">⚠️ No fresh web data found — results based on AI training data only</div>'}
        ${data.scraped_at
            ? `<div class="scraped-at-badge">🕒 Data scraped on: <strong>${data.scraped_at}</strong></div>`
            : ''}
        ${buildSourcesDropdown(data.source_previews)}
    `;

    let modelScoreHTML = `<div class="query-block"><h3>📊 Model Scores</h3>`;
    for (const [provider, scoreData] of Object.entries(modelScores)) {
        if (scoreData === 'error') {
            modelScoreHTML += `
                <div class="model-score-row">
                    <span class="model-score-label">${providerNames[provider] || provider}</span>
                    <div class="model-score-bar-wrap">
                        <div class="model-score-bar" style="width: 100%; background: #e5e7eb;"></div>
                    </div>
                    <span class="model-score-number model-error">⚠️ Error</span>
                </div>`;
            continue;
        }

        const isPartial = typeof scoreData === 'object' && scoreData.partial;
        const scoreValue = isPartial ? scoreData.score : scoreData;
        const barColor = scoreValue >= 80 ? '#22c55e' : scoreValue >= 50 ? '#f59e0b' : '#ef4444';
        const partialNote = isPartial ? ' <span class="partial-note">(partial)</span>' : '';

        modelScoreHTML += `
            <div class="model-score-row">
                <span class="model-score-label">${providerNames[provider] || provider}</span>
                <div class="model-score-bar-wrap">
                    <div class="model-score-bar" style="width: ${scoreValue}%; background: ${barColor};"></div>
                </div>
                <span class="model-score-number" style="color: ${barColor};">${scoreValue}/100${partialNote}</span>
            </div>`;
    }
    modelScoreHTML += `</div>`;

    // Query results
    let html = modelScoreHTML + breakdownHtml;
    data.results.forEach(item => {
        html += `<div class="query-block">
            <h3>❓ ${item.query}</h3>`;

        for (const [provider, response] of Object.entries(item.responses)) {
            const isError = response.startsWith('Error');
            html += `<div class="provider-response ${isError ? 'provider-error' : ''}">
                <div class="provider-name">${providerNames[provider] || provider}</div>
                <p>${isError ? "⚠️ Couldn't retrieve response from this provider." : formatResponse(response)}</p>
            </div>`;
        }
        html += `</div>`;
    });

    // Suggestions
    const suggestions = getSuggestions(flags, modelScores, data.company, breakdownAverages, score);
    if (suggestions.length > 0) {
        html += `<div class="suggestions-card">
            <h3>💡 AEO & GEO Improvement Recommendations</h3>
            <p class="suggestions-intro">Based on how AI systems responded to queries about <strong>${data.company}</strong>, here are specific steps to improve your AI visibility:</p>`;
        suggestions.forEach(s => {
            html += `<div class="suggestion-item">
                <div class="suggestion-priority">${s.priority}</div>
                <strong>${s.title}</strong>
                <p>${s.detail}</p>
                <div class="geo-tip">${s.geo_tip}</div>`;
            if (s.impact) {
                html += `<div class="suggestion-impact">Estimated impact: +${s.impact.absoluteIncrease} points (${s.impact.percentIncrease}% increase) → New score: ${s.impact.newScore}</div>`;
            }
            html += `</div>`;
        });
        html += `</div>`;
    }

    document.getElementById('resultsContent').innerHTML = html;
    document.getElementById('results').classList.remove('hidden');
    const downloadButton = document.getElementById('downloadPdfBtn');
    downloadButton.classList.remove('hidden');
    downloadButton.disabled = false;

    if (score < 100) {
        fetchRecommendations(data);
    }
}

async function fetchRecommendations(data) {
    // Collect a sample of AI responses as text to send to Ollama
    let aiResponsesSample = '';
    data.results.forEach(item => {
        aiResponsesSample += `Q: ${item.query}\n`;
        Object.entries(item.responses).forEach(([provider, response]) => {
            if (!response.startsWith('Error')) {
                aiResponsesSample += `${provider}: ${response.substring(0, 200)}\n`;
            }
        });
        aiResponsesSample += '\n';
    });

    const { score, flags, breakdownAverages } = scoreCompany(data);

    // Show a loading state in the suggestions section
    const suggestionsEl = document.querySelector('.suggestions-card');
    if (suggestionsEl) {
        suggestionsEl.innerHTML = `<h3>💡 AEO & GEO Improvement Recommendations</h3><p>🤖 Analyzing with local AI...</p>`;
    }

    try {
        const response = await fetch('/recommendations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                company: data.company,
                website: data.website || '',
                score: score,
                flags: flags,
                ai_responses: aiResponsesSample,
                language: data.language || selectedLanguage
            })
        });

        const result = await response.json();

        if (suggestionsEl && result.recommendations) {
            suggestionsEl.innerHTML = `
                <h3>💡 AEO & GEO Improvement Recommendations</h3>
                <p class="suggestions-intro">Analysis by local AI based on what the audit actually found:</p>
                <div class="suggestion-item">
                    ${formatResponse(result.recommendations)}
                </div>`;
        }
    } catch (error) {
        if (suggestionsEl) {
            suggestionsEl.innerHTML = `<h3>💡 Recommendations</h3><p>⚠️ Could not generate recommendations.</p>`;
        }
    }
}

function downloadPDF() {
    const resultsEl = document.getElementById('results');
    const company = document.getElementById('companyInput').value.trim() || 'AI-visibility-audit';
    const safeCompany = company.replace(/[^a-zA-Z0-9-_]/g, '_');
    const opt = {
        margin: 0.4,
        filename: `${safeCompany}-AI-Visibility-Audit.pdf`,
        image: { type: 'jpeg', quality: 0.98 },
        html2canvas: { scale: 2, useCORS: true },
        jsPDF: { unit: 'in', format: 'letter', orientation: 'portrait' }
    };

    if (typeof html2pdf === 'undefined') {
        alert('PDF export is unavailable because html2pdf.js could not be loaded.');
        return;
    }

    html2pdf().set(opt).from(resultsEl).save();
}

// Allow pressing Enter to trigger audit
// and wire model selector buttons
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.model-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.model-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            selectedModel = btn.dataset.model;
        });
    });

    const languageSelect = document.getElementById('languageSelect');
    if (languageSelect) {
        languageSelect.addEventListener('change', (e) => {
            selectedLanguage = e.target.value;
            applyLanguageUI(selectedLanguage);
        });
        applyLanguageUI(selectedLanguage);
    }

    document.getElementById('companyInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') runAudit();
    });
});