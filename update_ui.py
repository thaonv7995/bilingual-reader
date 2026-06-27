import re

with open('application/backend/books_cli/templates/index.html', 'r') as f:
    html = f.read()

css_old = r"""        \.books-grid \{
            display: grid;
            grid-template-columns: repeat\(auto-fill, minmax\(280px, 1fr\)\);
            gap: 1\.5rem;
        \}

        \.book-card \{
            background: var\(--bg-surface\);
            border: 1px solid var\(--border-subtle\);
            border-radius: var\(--radius-lg\);
            overflow: hidden;
            transition: all 0\.3s cubic-bezier\(0\.4, 0, 0\.2, 1\);
            cursor: pointer;
            position: relative;
            display: flex;
            flex-direction: column;
        \}

        \.book-card:hover \{
            transform: translateY\(-4px\);
            border-color: rgba\(59, 130, 246, 0\.4\);
            box-shadow: var\(--shadow-glow\);
        \}

        \.book-cover-wrapper \{
            position: relative;
            width: 100%;
            padding-top: 140%; /\* 1:1\.4 aspect ratio for book covers \*/
            background: #1e293b;
            overflow: hidden;
        \}

        \.book-cover-canvas \{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: cover;
            transition: transform 0\.5s ease;
        \}
        
        \.book-card:hover \.book-cover-canvas \{
            transform: scale\(1\.05\);
        \}

        \.book-cover-placeholder \{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient\(135deg, #1e293b 0%, #0f172a 100%\);
            color: var\(--border-hover\);
        \}

        \.book-info \{
            padding: 1\.25rem;
            flex: 1;
            display: flex;
            flex-direction: column;
        \}

        \.book-title \{
            font-size: 1\.1rem;
            font-weight: 600;
            margin-bottom: 0\.5rem;
            line-height: 1\.3;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            word-break: break-word;
        \}

        \.book-meta \{
            color: var\(--text-secondary\);
            font-size: 0\.875rem;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0\.5rem;
        \}

        \.badge \{
            padding: 0\.25rem 0\.6rem;
            border-radius: 99px;
            font-size: 0\.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0\.05em;
        \}
        \.badge-ready \{ background: rgba\(59, 130, 246, 0\.1\); color: #60a5fa; border: 1px solid rgba\(59, 130, 246, 0\.2\); \}
        \.badge-processing \{ background: rgba\(245, 158, 11, 0\.1\); color: #fbbf24; border: 1px solid rgba\(245, 158, 11, 0\.2\); \}
        \.badge-success \{ background: rgba\(16, 185, 129, 0\.1\); color: #34d399; border: 1px solid rgba\(16, 185, 129, 0\.2\); \}
        \.badge-failed \{ background: rgba\(239, 68, 68, 0\.1\); color: #f87171; border: 1px solid rgba\(239, 68, 68, 0\.2\); \}

        \.book-actions \{
            margin-top: auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-top: 1rem;
            border-top: 1px solid var\(--border-subtle\);
        \}

        \.book-actions-icons \{
            display: flex;
            gap: 0\.25rem;
        \}"""

css_new = """        .books-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
            gap: 2.5rem 1.5rem;
        }

        .book-card {
            background: transparent;
            border: none;
            cursor: pointer;
            position: relative;
            display: flex;
            flex-direction: column;
        }

        .book-cover-wrapper {
            position: relative;
            width: 100%;
            padding-top: 140%; /* 1:1.4 aspect ratio for book covers */
            background: #1e293b;
            border-radius: var(--radius-md);
            overflow: hidden;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.3s ease;
            border: 1px solid var(--border-subtle);
        }

        .book-card:hover .book-cover-wrapper {
            transform: translateY(-8px);
            box-shadow: 0 16px 24px rgba(0,0,0,0.5), 0 0 15px rgba(59, 130, 246, 0.2);
            border-color: rgba(59, 130, 246, 0.4);
        }

        .book-cover-canvas {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: cover;
            transition: transform 0.5s ease;
        }

        .book-card:hover .book-cover-canvas {
            transform: scale(1.05);
        }

        .book-cover-placeholder {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            color: var(--border-hover);
        }

        .book-hover-actions {
            position: absolute;
            bottom: 0;
            left: 0;
            width: 100%;
            padding: 1rem 0.5rem 0.5rem;
            background: linear-gradient(to top, rgba(0,0,0,0.9) 0%, transparent 100%);
            display: flex;
            justify-content: flex-end;
            gap: 0.25rem;
            opacity: 0;
            transition: opacity 0.2s ease;
            z-index: 10;
        }

        .book-card:hover .book-hover-actions {
            opacity: 1;
        }

        .book-hover-actions .btn-icon {
            background: rgba(255,255,255,0.1);
            backdrop-filter: blur(4px);
            color: #fff;
            padding: 0.4rem;
        }
        
        .book-hover-actions .btn-icon:hover {
            background: rgba(255,255,255,0.2);
        }

        .badge-floating {
            position: absolute;
            top: 0.5rem;
            right: 0.5rem;
            z-index: 10;
            box-shadow: 0 2px 5px rgba(0,0,0,0.5);
            backdrop-filter: blur(4px);
        }

        .book-info {
            padding: 0.75rem 0.25rem 0;
            flex: 1;
            display: flex;
            flex-direction: column;
        }

        .book-title {
            font-size: 0.95rem;
            font-weight: 600;
            margin-bottom: 0.25rem;
            line-height: 1.3;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            word-break: break-word;
            color: var(--text-primary);
            transition: color 0.2s;
        }

        .book-card:hover .book-title {
            color: var(--accent-primary);
        }

        .book-meta {
            color: var(--text-secondary);
            font-size: 0.75rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .badge {
            padding: 0.25rem 0.5rem;
            border-radius: 99px;
            font-size: 0.7rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .badge-ready { background: rgba(59, 130, 246, 0.15); color: #93c5fd; border: 1px solid rgba(59, 130, 246, 0.3); }
        .badge-processing { background: rgba(245, 158, 11, 0.15); color: #fcd34d; border: 1px solid rgba(245, 158, 11, 0.3); }
        .badge-success { background: rgba(16, 185, 129, 0.15); color: #6ee7b7; border: 1px solid rgba(16, 185, 129, 0.3); }
        .badge-failed { background: rgba(239, 68, 68, 0.15); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.3); }"""

html = re.sub(css_old, css_new, html, count=1)

js_old = r"""                    html \+= `
                        <div class="book-card" onclick="openDetail\('\$\{b\.slug\}', '\$\{b\.title\.replace\(/'/g, "\\\\'"\)\}'\)">
                            <div class="book-cover-wrapper">
                                <canvas id="cvs-\$\{b\.slug\}" class="book-cover-canvas"></canvas>
                                <div class="book-cover-placeholder" style="display:none;"><i data-lucide="book" style="width:48px;height:48px;"></i></div>
                            </div>
                            <div class="book-info">
                                <div class="book-title">\$\{b\.title\}</div>
                                <div class="book-meta">
                                    <span>\$\{b\.page_count\} Pages</span> • \$\{badge\}
                                </div>
                                <div class="book-actions">
                                    <span style="font-size:0\.8rem; color:var\(--text-muted\);">\$\{b\.page_pdf_done\} split</span>
                                    <div class="book-actions-icons">
                                        <button class="btn-icon" onclick="event\.stopPropagation\(\); openEdit\('\$\{b\.slug\}', '\$\{b\.title\.replace\(/'/g, "\\\\'"\)\}'\)"><i data-lucide="edit-2" style="width:16px;height:16px;"></i></button>
                                        <button class="btn-icon" onclick="event\.stopPropagation\(\); deleteBook\('\$\{b\.slug\}'\)"><i data-lucide="trash-2" style="width:16px;height:16px;color:var\(--accent-danger\);"></i></button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;"""

js_new = """                    // Modify badge to include badge-floating
                    badge = badge.replace('class="badge ', 'class="badge badge-floating ');
                    html += `
                        <div class="book-card" onclick="openDetail('${b.slug}', '${b.title.replace(/'/g, "\\'")}')">
                            <div class="book-cover-wrapper">
                                ${badge}
                                <canvas id="cvs-${b.slug}" class="book-cover-canvas"></canvas>
                                <div class="book-cover-placeholder" style="display:none;"><i data-lucide="book" style="width:48px;height:48px;"></i></div>
                                <div class="book-hover-actions">
                                    <button class="btn-icon" title="Edit Book" onclick="event.stopPropagation(); openEdit('${b.slug}', '${b.title.replace(/'/g, "\\'")}')"><i data-lucide="edit-2" style="width:16px;height:16px;"></i></button>
                                    <button class="btn-icon" title="Delete Book" onclick="event.stopPropagation(); deleteBook('${b.slug}')"><i data-lucide="trash-2" style="width:16px;height:16px;color:#fca5a5;"></i></button>
                                </div>
                            </div>
                            <div class="book-info">
                                <div class="book-title" title="${b.title.replace(/"/g, '&quot;')}">${b.title}</div>
                                <div class="book-meta">
                                    <span>${b.page_count} Pages</span>
                                    <span>${b.page_pdf_done} split</span>
                                </div>
                            </div>
                        </div>
                    `;"""

html = re.sub(js_old, js_new, html, count=1)

with open('application/backend/books_cli/templates/index.html', 'w') as f:
    f.write(html)

print("Updated index.html successfully.")
