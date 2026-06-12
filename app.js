// app.js - Preact Single Page Application for Bilingual Book Reader

import { h, render } from './libs/preact.mjs';
import { useState, useEffect, useRef, useMemo } from './libs/hooks.mjs';
import htm from './libs/htm.mjs';

// Initialize htm with Preact
const html = htm.bind(h);

// Default settings configuration
const DEFAULT_SETTINGS = {
  provider: 'openai',
  baseURL: 'https://api.openai.com/v1',
  apiKey: '',
  model: 'gpt-4o-mini',
};

function App() {
  // Sync initial navigation state from URL hash
  const getInitialRoute = () => {
    const hash = window.location.hash;
    if (!hash) return { book: null, page: 1 };
    const readMatch = hash.match(/^#\/read\/([^/]+)(?:\/page\/(\d+))?$/);
    if (readMatch) {
      const slug = readMatch[1];
      const pageNum = readMatch[2] ? parseInt(readMatch[2], 10) : 1;
      // BOOKS is a global defined in books.js
      const book = typeof BOOKS !== 'undefined' ? BOOKS.find(b => b.slug === slug) : null;
      if (book) {
        return { book, page: pageNum };
      }
    }
    return { book: null, page: 1 };
  };

  const initialRoute = getInitialRoute();

  // --- Navigation & Book State ---
  const [activeBook, setActiveBook] = useState(initialRoute.book);
  const [page, setPage] = useState(initialRoute.page);
  const [viewMode, setViewMode] = useState(() => {
    return localStorage.getItem('bilingual.reader.viewMode') || 'en';
  }); // 'en' | 'vi' | 'split'
  const [layoutMode, setLayoutMode] = useState(() => {
    return localStorage.getItem('bilingual.reader.layoutMode') || 'en-vi';
  });
  const [fullBookText, setFullBookText] = useState('');

  // --- Dynamic Dashboard Layout & Pagination State ---
  const getColsCount = () => {
    const width = window.innerWidth;
    if (width < 600) return 2;
    if (width < 1000) return 4;
    if (width < 1500) return 6;
    return 8;
  };
  const [cols, setCols] = useState(getColsCount);
  const [currentPage, setCurrentPage] = useState(1);

  useEffect(() => {
    const handleResize = () => {
      setCols(getColsCount());
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const sortedBooks = useMemo(() => {
    return typeof BOOKS !== 'undefined' ? [...BOOKS].reverse() : [];
  }, []);

  const pageSize = cols * 3;
  const totalPages = Math.ceil(sortedBooks.length / pageSize);
  const clampedPage = Math.min(currentPage, Math.max(1, totalPages));

  const paginatedBooks = useMemo(() => {
    const start = (clampedPage - 1) * pageSize;
    return sortedBooks.slice(start, start + pageSize);
  }, [sortedBooks, clampedPage, pageSize]);

  // --- UI Layout State ---
  const [chatOpen, setChatOpen] = useState(() => {
    return localStorage.getItem('bilingual.reader.chatOpen') === 'true';
  });
  const [settingsOpen, setSettingsOpen] = useState(false);

  // --- API & Settings State ---
  const [settings, setSettings] = useState(() => {
    // Load local CONFIG if available (defined in config.js)
    const localOpenAIKey = typeof CONFIG !== 'undefined' ? CONFIG.OPENAI_API_KEY : '';
    const localGeminiKey = typeof CONFIG !== 'undefined' ? CONFIG.GEMINI_API_KEY : '';

    // Load from LocalStorage
    const saved = localStorage.getItem('bilingual.reader.settings');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        // Ensure all required fields exist
        return { ...DEFAULT_SETTINGS, ...parsed };
      } catch (e) {
        console.warn('Failed to parse saved settings', e);
      }
    }

    // Default fallback prioritizing local environment keys
    if (localGeminiKey) {
      return {
        provider: 'gemini',
        baseURL: 'https://generativelanguage.googleapis.com/v1beta/openai',
        apiKey: localGeminiKey,
        model: 'gemini-1.5-flash',
      };
    } else if (localOpenAIKey) {
      return {
        provider: 'openai',
        baseURL: 'https://api.openai.com/v1',
        apiKey: localOpenAIKey,
        model: 'gpt-4o-mini',
      };
    }

    return DEFAULT_SETTINGS;
  });

  // Settings modal fields
  const [formProvider, setFormProvider] = useState(settings.provider);
  const [formBaseURL, setFormBaseURL] = useState(settings.baseURL);
  const [formApiKey, setFormApiKey] = useState(settings.apiKey);
  const [formModel, setFormModel] = useState(settings.model);
  const [formLayoutMode, setFormLayoutMode] = useState(layoutMode);

  const openSettings = () => {
    setFormProvider(settings.provider);
    setFormBaseURL(settings.baseURL);
    setFormApiKey(settings.apiKey);
    setFormModel(settings.model);
    setFormLayoutMode(layoutMode);
    setSettingsOpen(true);
  };

  // --- Chat State ---
  const [messages, setMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [chatPending, setChatPending] = useState(false);

  const messagesEndRef = useRef(null);
  const [popupConfig, setPopupConfig] = useState(null); // { type: 'alert' | 'confirm', title: string, message: string, onConfirm: () => void, onCancel?: () => void }
  const abortControllerRef = useRef(null);

  // --- Chat Resizing State & Event Handlers ---
  const [chatWidth, setChatWidth] = useState(() => {
    const saved = localStorage.getItem('bilingual.reader.chatWidth');
    return saved ? parseInt(saved, 10) : 400;
  });
  const [isResizing, setIsResizing] = useState(false);
  const isResizingRef = useRef(false);
  const resizingRafRef = useRef(null);

  // Sync layout state to LocalStorage
  useEffect(() => {
    localStorage.setItem('bilingual.reader.viewMode', viewMode);
  }, [viewMode]);

  useEffect(() => {
    localStorage.setItem('bilingual.reader.chatOpen', chatOpen);
  }, [chatOpen]);

  useEffect(() => {
    localStorage.setItem('bilingual.reader.chatWidth', chatWidth);
  }, [chatWidth]);

  const startResizing = (e) => {
    e.preventDefault();
    isResizingRef.current = true;
    setIsResizing(true);
    document.body.classList.add('is-resizing');
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', stopResizing);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  const handleMouseMove = (e) => {
    if (!isResizingRef.current) return;
    let newWidth = window.innerWidth - e.clientX;
    if (newWidth < 280) newWidth = 280;
    if (newWidth > 800) newWidth = 800;
    
    // Direct DOM styling updates for maximum performance
    const sidebar = document.querySelector('.chat-sidebar');
    if (sidebar) {
      sidebar.style.width = `${newWidth}px`;
    }

    if (resizingRafRef.current) {
      cancelAnimationFrame(resizingRafRef.current);
    }
    resizingRafRef.current = requestAnimationFrame(() => {
      scaleIframes();
    });
  };

  const stopResizing = () => {
    isResizingRef.current = false;
    setIsResizing(false);
    document.body.classList.remove('is-resizing');
    document.removeEventListener('mousemove', handleMouseMove);
    document.removeEventListener('mouseup', stopResizing);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';

    // Synchronize the final width to Preact state
    const sidebar = document.querySelector('.chat-sidebar');
    if (sidebar) {
      const finalWidth = parseInt(sidebar.style.width, 10);
      if (!isNaN(finalWidth)) {
        setChatWidth(finalWidth);
      }
    }
  };

  useEffect(() => {
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', stopResizing);
      if (resizingRafRef.current) {
        cancelAnimationFrame(resizingRafRef.current);
      }
    };
  }, []);

  // --- Dynamic scaling for iframes to fit standard A4 dimension ---
  const scaleIframes = () => {
    const wrappers = document.querySelectorAll('.iframe-wrapper');
    const panesContainer = document.querySelector('.reader-panes');
    const isVertical = panesContainer && (
      panesContainer.classList.contains('layout-en-over-vi') || 
      panesContainer.classList.contains('layout-vi-over-en')
    );

    wrappers.forEach(wrapper => {
      const iframe = wrapper.querySelector('.reader-iframe');
      if (!iframe) return;

      const containerWidth = wrapper.clientWidth;
      const containerHeight = wrapper.clientHeight;

      const targetWidth = 794;
      const targetHeight = 1123;
      const padding = 20;

      const availableWidth = Math.max(containerWidth - padding, 100);
      const availableHeight = Math.max(containerHeight - padding, 100);

      const scaleX = availableWidth / targetWidth;
      const scaleY = availableHeight / targetHeight;
      
      // If layout is vertical stack, scale to fit the width only and scroll vertically
      const scale = isVertical ? Math.min(scaleX, 1) : Math.min(scaleX, scaleY, 1);

      iframe.style.transform = `scale(${scale})`;
      iframe.style.width = `${targetWidth}px`;
      iframe.style.height = `${targetHeight}px`;
    });
  };

  // Trigger scale adjustment on layout updates
  useEffect(() => {
    const timer = setTimeout(scaleIframes, 50);
    return () => clearTimeout(timer);
  }, [viewMode, chatOpen, chatWidth, page, activeBook, layoutMode]);

  // Handle window resizing
  useEffect(() => {
    window.addEventListener('resize', scaleIframes);
    return () => window.removeEventListener('resize', scaleIframes);
  }, []);

  // Helper to save messages and handle state safely
  const saveChatHistory = (slug, msgs) => {
    if (!slug) return;
    const cleanMsgs = msgs.filter(m => !m.pending);
    if (cleanMsgs.length > 0) {
      const chatHistory = {
        messages: cleanMsgs,
        lastUpdated: Date.now()
      };
      localStorage.setItem(`bilingual.reader.chatHistory.${slug}`, JSON.stringify(chatHistory));
    } else {
      localStorage.removeItem(`bilingual.reader.chatHistory.${slug}`);
    }
  };

  const updateMessagesAndSave = (updater) => {
    setMessages(prev => {
      const next = typeof updater === 'function' ? updater(prev) : updater;
      saveChatHistory(activeBook?.slug, next);
      return next;
    });
  };

  // Register Service Worker on mount
  useEffect(() => {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('sw.js')
        .then(reg => {
          console.log('[App] Service Worker registered scope:', reg.scope);
        })
        .catch(err => {
          console.error('[App] Service Worker registration failed:', err);
        });
    }
  }, []);

  // Silent background prefetch for book pages when activeBook changes
  useEffect(() => {
    if (!activeBook) return;
    
    const prefetchBook = async () => {
      if (!('caches' in window)) return;
      try {
        const cache = await caches.open('bilingual-reader-books');
        
        // Cache book.html silently
        const bookHtmlUrl = `books/${activeBook.slug}/output/book.html`;
        cache.match(bookHtmlUrl).then(matched => {
          if (!matched) {
            fetch(bookHtmlUrl).then(res => {
              if (res.ok) cache.put(bookHtmlUrl, res);
            }).catch(() => {});
          }
        });

        // Prefetch pages silently
        for (let i = 1; i <= activeBook.pageCount; i++) {
          const pad = String(i).padStart(4, '0');
          const enUrl = `books/${activeBook.slug}/output/en/page_${pad}.html`;
          const viUrl = `books/${activeBook.slug}/output/vi/page_${pad}.html`;

          cache.match(enUrl).then(matched => {
            if (!matched) {
              fetch(enUrl).then(res => {
                if (res.ok) cache.put(enUrl, res);
              }).catch(() => {});
            }
          });

          cache.match(viUrl).then(matched => {
            if (!matched) {
              fetch(viUrl).then(res => {
                if (res.ok) cache.put(viUrl, res);
              }).catch(() => {});
            }
          });
        }
      } catch (e) {
        console.warn("[Cache] Silent background prefetch failed:", e);
      }
    };

    prefetchBook();
  }, [activeBook]);

  // Sync activeBook chat history on change
  useEffect(() => {
    if (activeBook) {
      const saved = localStorage.getItem(`bilingual.reader.chatHistory.${activeBook.slug}`);
      if (saved) {
        try {
          const parsed = JSON.parse(saved);
          setMessages(parsed.messages || []);
          return;
        } catch (e) {
          console.warn('[App] Failed to parse chat history:', e);
        }
      }
    }
    setMessages([]);
  }, [activeBook]);

  // Cleanup expired chat histories (TTL logic)
  useEffect(() => {
    const cleanupExpiredHistories = () => {
      const keys = Object.keys(localStorage);
      const now = Date.now();
      const expireDays = 7; // Hardcoded to 7 days
      
      const expireMs = expireDays * 24 * 60 * 60 * 1000;
      let count = 0;
      
      keys.forEach(key => {
        if (key.startsWith('bilingual.reader.chatHistory.')) {
          try {
            const saved = localStorage.getItem(key);
            if (saved) {
              const parsed = JSON.parse(saved);
              if (parsed.lastUpdated && (now - parsed.lastUpdated > expireMs)) {
                localStorage.removeItem(key);
                count++;
                console.log(`[TTL Cache] Cleaned up expired chat history for key: ${key}`);
              }
            }
          } catch (e) {
            localStorage.removeItem(key);
          }
        }
      });
      if (count > 0) {
        console.log(`[TTL Cache] Successfully cleaned up ${count} expired chat sessions.`);
      }
    };

    cleanupExpiredHistories();
  }, []);

  // Clear active chat
  const handleClearActiveChat = () => {
    setPopupConfig({
      type: 'confirm',
      title: 'Xác nhận xóa',
      message: 'Bạn có muốn xóa lịch sử chat của cuốn sách này?',
      onConfirm: () => {
        updateMessagesAndSave([]);
      }
    });
  };

  // Main window keyboard shortcut listeners
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Skip pagination if the user is typing in a form field
      if (document.activeElement && (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA')) {
        return;
      }

      if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
        e.preventDefault();
        setPage(p => Math.max(1, p - 1));
      } else if (e.key === 'ArrowRight' || e.key === 'PageDown') {
        e.preventDefault();
        setPage(p => Math.min(activeBook ? activeBook.pageCount : p, p + 1));
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeBook]);

  // Iframe content load handler
  const handleIframeLoad = (e) => {
    scaleIframes();
    try {
      const iframeWin = e.target.contentWindow;
      const doc = e.target.contentDocument || iframeWin.document;
      if (doc) {
        doc.documentElement.style.overflow = 'hidden';
        doc.body.style.overflow = 'hidden';

        // Hide internal pages redundant navigation controls
        const nav = doc.querySelector('.page-nav');
        if (nav) nav.style.display = 'none';

        // Listen for keys inside the iframe to slide pages
        doc.addEventListener('keydown', (event) => {
          if (event.key === 'ArrowLeft' || event.key === 'PageUp') {
            event.preventDefault();
            setPage(p => Math.max(1, p - 1));
          } else if (event.key === 'ArrowRight' || event.key === 'PageDown') {
            event.preventDefault();
            setPage(p => Math.min(activeBook ? activeBook.pageCount : p, p + 1));
          }
        });
      }
    } catch (err) {
      console.warn("Could not style loaded iframe content: ", err);
    }
  };

  // --- Router hash controller ---
  useEffect(() => {
    function handleHashChange() {
      const hash = window.location.hash;
      if (!hash || hash === '#/') {
        setActiveBook(null);
        setPage(1);
        return;
      }

      // Pattern: #/read/:slug or #/read/:slug/page/:num
      const readMatch = hash.match(/^#\/read\/([^/]+)(?:\/page\/(\d+))?$/);
      if (readMatch) {
        const slug = readMatch[1];
        const pageNum = readMatch[2] ? parseInt(readMatch[2], 10) : 1;

        // Find book in BOOKS array (defined in books.js)
        const book = BOOKS.find(b => b.slug === slug);
        if (book) {
          setActiveBook(book);
          setPage(pageNum);
        } else {
          // Fallback if book slug not found
          window.location.hash = '#/';
        }
      }
    }

    window.addEventListener('hashchange', handleHashChange);
    handleHashChange(); // Run once on load

    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  // Sync hash with active book / page changes
  useEffect(() => {
    if (activeBook) {
      window.location.hash = `#/read/${activeBook.slug}/page/${page}`;
    } else {
      window.location.hash = '#/';
    }
  }, [activeBook, page]);

  // Load full book text asynchronously for AI context
  useEffect(() => {
    if (!activeBook) {
      setFullBookText('');
      return;
    }

    setFullBookText('Loading book context...');
    fetch(`books/${activeBook.slug}/output/book.html`)
      .then(res => {
        if (!res.ok) throw new Error('Book HTML not found');
        return res.text();
      })
      .then(htmlContent => {
        const parser = new DOMParser();
        const doc = parser.parseFromString(htmlContent, 'text/html');
        // Extract clean text content from articles/sheets
        const text = doc.body.innerText || '';
        // Truncate if unreasonably massive, but standard LLM contexts support it.
        setFullBookText(text);
      })
      .catch(err => {
        console.error('Failed to pre-load full book context:', err);
        setFullBookText('Unable to load full book context.');
      });
  }, [activeBook]);

  // Scroll to bottom of chat
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'auto' });
    }
  }, [messages, chatPending]);

  // Handle setting provider autofills
  const onProviderChange = (e) => {
    const prov = e.target.value;
    setFormProvider(prov);
    if (prov === 'openai') {
      setFormBaseURL('https://api.openai.com/v1');
      setFormModel('gpt-4o-mini');
    } else if (prov === 'gemini') {
      setFormBaseURL('https://generativelanguage.googleapis.com/v1beta/openai');
      setFormModel('gemini-1.5-flash');
    }
  };

  const saveSettings = (e) => {
    e.preventDefault();
    const updated = {
      provider: formProvider,
      baseURL: formBaseURL,
      apiKey: formApiKey,
      model: formModel
    };
    setSettings(updated);
    localStorage.setItem('bilingual.reader.settings', JSON.stringify(updated));
    
    setLayoutMode(formLayoutMode);
    localStorage.setItem('bilingual.reader.layoutMode', formLayoutMode);
    
    setSettingsOpen(false);
  };

  // Extract text from the active iframe(s) DOM
  const getIframePageText = () => {
    let pageText = '';
    
    // Left pane (English)
    const enIframe = document.querySelector('.en-pane-iframe');
    if (enIframe && enIframe.contentDocument) {
      const txt = enIframe.contentDocument.body.innerText.trim();
      if (txt) {
        pageText += `=== ENGLISH PAGE ${page} ===\n${txt}\n\n`;
      }
    }

    // Right pane (Vietnamese)
    const viIframe = document.querySelector('.vi-pane-iframe');
    if (viIframe && viIframe.contentDocument) {
      const txt = viIframe.contentDocument.body.innerText.trim();
      if (txt) {
        pageText += `=== VIETNAMESE PAGE ${page} ===\n${txt}\n\n`;
      }
    }

    return pageText.trim();
  };

  // AI Chat submission handler
  const sendChatMessage = async (userInputText = null) => {
    const textToSend = userInputText || chatInput;
    if (!textToSend.trim() || chatPending) return;

    if (!settings.apiKey) {
      setPopupConfig({
        type: 'alert',
        title: 'Thiếu API Key',
        message: 'Vui lòng vào Settings cài đặt API Key để chat với trợ lý AI!',
        onConfirm: () => {
          openSettings();
        }
      });
      return;
    }

    // 1. Add user message
    const newUserMsg = { role: 'user', content: textToSend };
    updateMessagesAndSave(prev => [...prev, newUserMsg]);
    setChatInput('');
    setChatPending(true);

    // 2. Add empty pending bubble
    updateMessagesAndSave(prev => [...prev, { role: 'assistant', content: '', pending: true }]);

    // 3. Assemble prompt with extracted contexts
    const activePageText = getIframePageText();
    const cleanFullTextContext = fullBookText && fullBookText !== 'Loading book context...' && fullBookText !== 'Unable to load full book context.'
      ? fullBookText.slice(0, 150000) // Keep context under ~150k characters to prevent overflow
      : 'No global book context loaded.';

    const systemPrompt = `You are a helpful, expert AI Book Assistant. You are guiding the user who is reading the book "${activeBook.title}" by ${activeBook.author}.
The user is currently reading page ${page}.

CURRENT PAGE CONTEXT:
${activePageText}

FULL BOOK BACKGROUND (clean text sample):
${cleanFullTextContext}

Instructions:
1. Answer the user's questions accurately based on the current page and full book context provided.
2. If the user asks about something on this page, prioritize the CURRENT PAGE CONTEXT.
3. If they ask about overall book concepts, utilize the FULL BOOK BACKGROUND.
4. Keep your responses structured, clear, and scan-friendly (use short markdown paragraphs, lists, or bold highlights).
5. Please answer in Vietnamese (the user's language) unless they ask you to write or explain in English. Keep code snippets in their original programming language.
`;

    // Initialize AbortController
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    // 4. Dispatch completions fetch via local proxy /api/chat to bypass CORS
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        signal,
        body: JSON.stringify({
          baseURL: settings.baseURL,
          apiKey: settings.apiKey,
          model: settings.model,
          messages: [
            { role: 'system', content: systemPrompt },
            ...messages.filter(m => !m.pending).map(m => ({ role: m.role, content: m.content })),
            newUserMsg
          ],
          stream: true
        })
      });

      if (!response.ok) {
        throw new Error(`API Error: ${response.status} ${response.statusText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let assistantReply = '';
      let doneStreaming = false;
      let buffer = '';

      const processLine = (line) => {
        const cleanLine = line.trim();
        if (cleanLine === 'data: [DONE]') {
          doneStreaming = true;
          return;
        }
        if (!cleanLine) return;

        if (cleanLine.startsWith('data: ')) {
          try {
            const data = JSON.parse(cleanLine.slice(6));
            const deltaContent = data.choices?.[0]?.delta?.content || '';
            assistantReply += deltaContent;

            // Update the assistant bubble content in real-time
            updateMessagesAndSave(prev => {
              const copy = [...prev];
              let targetIdx = -1;
              for (let i = copy.length - 1; i >= 0; i--) {
                if (copy[i].role === 'assistant') {
                  targetIdx = i;
                  break;
                }
              }
              if (targetIdx !== -1) {
                copy[targetIdx] = {
                  role: 'assistant',
                  content: assistantReply,
                  pending: false
                };
              }
              return copy;
            });
          } catch (e) {
            // Ignore partial JSON parsing errors
          }
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          if (buffer) {
            processLine(buffer);
          }
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // Keep the last incomplete line in buffer

        for (const line of lines) {
          processLine(line);
          if (doneStreaming) break;
        }
        if (doneStreaming) {
          try { await reader.cancel(); } catch (e) {}
          break;
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        console.log('AI chat generation aborted by user.');
        updateMessagesAndSave(prev => {
          const copy = [...prev];
          let targetIdx = -1;
          for (let i = copy.length - 1; i >= 0; i--) {
            if (copy[i].role === 'assistant') {
              targetIdx = i;
              break;
            }
          }
          if (targetIdx !== -1) {
            copy[targetIdx] = {
              ...copy[targetIdx],
              content: copy[targetIdx].content ? copy[targetIdx].content : 'Yêu cầu đã bị hủy.',
              pending: false
            };
          }
          return copy;
        });
      } else {
        console.error('AI chat assistant error:', err);
        updateMessagesAndSave(prev => {
          const copy = [...prev];
          let targetIdx = -1;
          for (let i = copy.length - 1; i >= 0; i--) {
            if (copy[i].role === 'assistant') {
              targetIdx = i;
              break;
            }
          }
          if (targetIdx !== -1) {
            copy[targetIdx] = {
              role: 'assistant',
              content: `Xin lỗi, đã xảy ra lỗi khi kết nối với AI Model: ${err.message}. Vui lòng kiểm tra lại cấu hình API Key hoặc kết nối mạng trong phần Settings!`,
              pending: false
            };
          }
          return copy;
        });
      }
    } finally {
      abortControllerRef.current = null;
      setChatPending(false);
    }
  };

  const handleCancelChat = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setChatPending(false);
    updateMessagesAndSave(prev => {
      const copy = [...prev];
      let targetIdx = -1;
      for (let i = copy.length - 1; i >= 0; i--) {
        if (copy[i].role === 'assistant') {
          targetIdx = i;
          break;
        }
      }
      if (targetIdx !== -1 && copy[targetIdx].pending) {
        copy[targetIdx] = {
          ...copy[targetIdx],
          pending: false
        };
      }
      return copy;
    });
  };

  const handleQuickPrompt = (promptText) => {
    sendChatMessage(promptText);
  };

  // Helper to parse inline markdown elements: bold (**), italic (*), and inline code (`)
  const parseInlineFormatting = (text) => {
    const regex = /(\*\*.*?\*\*|\*.*?\*|`.*?`)/g;
    const parts = text.split(regex);
    return parts.map((part, idx) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return html`<strong key=${idx}>${part.slice(2, -2)}</strong>`;
      }
      if (part.startsWith('*') && part.endsWith('*')) {
        return html`<em key=${idx}>${part.slice(1, -1)}</em>`;
      }
      if (part.startsWith('`') && part.endsWith('`')) {
        return html`<code class="inline-code" key=${idx}>${part.slice(1, -1)}</code>`;
      }
      return part;
    });
  };

  // Formatting helper to render markdown elements in blocks
  const renderMessageContent = (content) => {
    const lines = content.split('\n');
    let inCodeBlock = false;
    let codeContent = [];
    const elements = [];
    let keyIdx = 0;
    
    let listItems = [];
    let listType = null; // 'ul' | 'ol'

    const flushList = () => {
      if (listItems.length > 0) {
        const itemElements = listItems.map((item, idx) => html`<li key=${idx}>${parseInlineFormatting(item)}</li>`);
        if (listType === 'ul') {
          elements.push(html`<ul key=${keyIdx++}>${itemElements}</ul>`);
        } else if (listType === 'ol') {
          elements.push(html`<ol key=${keyIdx++}>${itemElements}</ol>`);
        }
        listItems = [];
        listType = null;
      }
    };

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      if (line.trim().startsWith('```')) {
        flushList();
        if (inCodeBlock) {
          inCodeBlock = false;
          elements.push(html`<pre key=${keyIdx++}><code>${codeContent.join('\n')}</code></pre>`);
          codeContent = [];
        } else {
          inCodeBlock = true;
        }
        continue;
      }

      if (inCodeBlock) {
        codeContent.push(line);
        continue;
      }

      const trimmed = line.trim();
      if (!trimmed) {
        flushList();
        continue;
      }

      // Headers
      if (trimmed.startsWith('### ')) {
        flushList();
        elements.push(html`<h4 key=${keyIdx++}>${parseInlineFormatting(trimmed.slice(4))}</h4>`);
        continue;
      }
      if (trimmed.startsWith('## ')) {
        flushList();
        elements.push(html`<h3 key=${keyIdx++}>${parseInlineFormatting(trimmed.slice(3))}</h3>`);
        continue;
      }

      // Unordered list items starting with '*' or '-'
      const ulMatch = line.match(/^(\s*)([*+-])\s+(.*)$/);
      if (ulMatch) {
        if (listType !== 'ul') {
          flushList();
          listType = 'ul';
        }
        listItems.push(ulMatch[3]);
        continue;
      }

      // Ordered list items starting with numbers '1.', '2.', etc.
      const olMatch = line.match(/^(\s*)(\d+)\.\s+(.*)$/);
      if (olMatch) {
        if (listType !== 'ol') {
          flushList();
          listType = 'ol';
        }
        listItems.push(olMatch[3]);
        continue;
      }

      // Regular paragraph
      flushList();
      elements.push(html`<p key=${keyIdx++}>${parseInlineFormatting(line)}</p>`);
    }

    flushList();
    if (inCodeBlock && codeContent.length > 0) {
      elements.push(html`<pre key=${keyIdx++}><code>${codeContent.join('\n')}</code></pre>`);
    }

    return elements;
  };

  // --- Render Dashboard UI ---
  if (!activeBook) {
    return html`
      <div>
        <header>
          <div class="header-container">
            <h1>Bilingual Digital Library</h1>
            <button class="btn-action" onClick=${openSettings}>
              Settings ⚙️
            </button>
          </div>
        </header>

        <main class="dashboard-container">
          <div class="dashboard-title-section">
            <h2>Danh sách Tủ Sách Song Ngữ</h2>
            <span style="color: var(--text-muted); font-size: 14px;">Tổng cộng: ${BOOKS.length} cuốn</span>
          </div>

          <div class="books-grid">
            ${paginatedBooks.map(book => {
              const hasCover = !!book.cover;
              return html`
                <div class="book-card" key=${book.slug} onClick=${() => {
                  setActiveBook(book);
                  setPage(1);
                  setViewMode('en');
                }}>
                  <div class="book-card__cover-wrapper">
                    ${hasCover
                      ? html`<img class="book-card__cover-img" src=${book.cover} alt=${book.title} />`
                      : html`
                        <div class="book-card__cover-fallback">
                          <h4>${book.title}</h4>
                          <p>${book.author}</p>
                        </div>
                      `
                    }
                  </div>
                  <div class="book-card__content">
                    <h3 class="book-card__title">${book.title}</h3>
                    <div class="book-card__author">Tác giả: ${book.author}</div>
                    <p class="book-card__desc">${book.description}</p>
                    <div class="book-card__footer">
                      <span>📖 ${book.pageCount} trang</span>
                      <span class="book-card__badge">Bilingual</span>
                    </div>
                  </div>
                </div>
              `;
            })}
          </div>

          ${totalPages > 1 && html`
            <div class="pagination-container">
              <button class="nav-btn pagination-arrow" disabled=${clampedPage <= 1} onClick=${() => setCurrentPage(p => Math.max(1, p - 1))}>
                ◀
              </button>
              <span class="pagination-info">Trang ${clampedPage} / ${totalPages}</span>
              <button class="nav-btn pagination-arrow" disabled=${clampedPage >= totalPages} onClick=${() => setCurrentPage(p => Math.min(totalPages, p + 1))}>
                ▶
              </button>
            </div>
          `}
        </main>

        <footer>
          <p>© 2026 Bilingual Book Reader. Digital restoration crafted with ♥ by @thaonv795.</p>
        </footer>

        ${settingsOpen && renderSettingsModal()}
        ${popupConfig && renderPopupModal()}
      </div>
    `;
  }

  // --- Render Settings Modal ---
  function renderSettingsModal() {
    return html`
      <div class="modal-backdrop" onClick=${() => setSettingsOpen(false)}>
        <form class="modal-content" onSubmit=${saveSettings} onClick=${(e) => e.stopPropagation()}>
          <div class="modal-header">
            <h3>Cấu hình Trợ lý AI</h3>
            <button class="nav-btn" type="button" onClick=${() => setSettingsOpen(false)}>✕</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label class="form-label">API Provider</label>
              <select class="form-select" value=${formProvider} onChange=${onProviderChange}>
                <option value="openai">OpenAI (Official)</option>
                <option value="gemini">Google Gemini (OpenAI compat)</option>
                <option value="custom">Custom (Ollama / Local)</option>
              </select>
            </div>

            <div class="form-group">
              <label class="form-label">API Base URL</label>
              <input class="form-input" type="text" required value=${formBaseURL} onInput=${(e) => setFormBaseURL(e.target.value)} />
            </div>

            <div class="form-group">
              <label class="form-label">API Key</label>
              <input class="form-input" type="password" placeholder="Nhập API Key của bạn" value=${formApiKey} onInput=${(e) => setFormApiKey(e.target.value)} />
            </div>

            <div class="form-group">
              <label class="form-label">Model Name</label>
              <input class="form-input" type="text" required value=${formModel} onInput=${(e) => setFormModel(e.target.value)} />
            </div>

            <div class="form-group">
              <label class="form-label">Bố cục song ngữ</label>
              <div class="layout-options-grid">
                <div class=${`layout-option-card ${formLayoutMode === 'en-vi' ? 'active' : ''}`} onClick=${() => setFormLayoutMode('en-vi')} title="English - Tiếng Việt (Trái - Phải)">
                  <div class="layout-preview preview-en-vi">
                    <span class="preview-badge badge-en">EN</span>
                    <span class="preview-badge badge-vi">VI</span>
                  </div>
                </div>

                <div class=${`layout-option-card ${formLayoutMode === 'vi-en' ? 'active' : ''}`} onClick=${() => setFormLayoutMode('vi-en')} title="Tiếng Việt - English (Trái - Phải)">
                  <div class="layout-preview preview-vi-en">
                    <span class="preview-badge badge-vi">VI</span>
                    <span class="preview-badge badge-en">EN</span>
                  </div>
                </div>

                <div class=${`layout-option-card ${formLayoutMode === 'en-over-vi' ? 'active' : ''}`} onClick=${() => setFormLayoutMode('en-over-vi')} title="English / Tiếng Việt (Trên - Dưới)">
                  <div class="layout-preview preview-en-over-vi">
                    <span class="preview-badge badge-en">EN</span>
                    <span class="preview-badge badge-vi">VI</span>
                  </div>
                </div>

                <div class=${`layout-option-card ${formLayoutMode === 'vi-over-en' ? 'active' : ''}`} onClick=${() => setFormLayoutMode('vi-over-en')} title="Tiếng Việt / English (Trên - Dưới)">
                  <div class="layout-preview preview-vi-over-en">
                    <span class="preview-badge badge-vi">VI</span>
                    <span class="preview-badge badge-en">EN</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn-secondary" type="button" onClick=${() => setSettingsOpen(false)}>Hủy</button>
            <button class="btn-primary" type="submit">Lưu Cấu Hình</button>
          </div>
        </form>
      </div>
    `;
  }

  // --- Render Custom Alert/Confirm Popup ---
  function renderPopupModal() {
    if (!popupConfig) return null;

    const { type, title, message, onConfirm, onCancel } = popupConfig;

    const handleConfirmClick = () => {
      setPopupConfig(null);
      if (onConfirm) onConfirm();
    };

    const handleCancelClick = () => {
      setPopupConfig(null);
      if (onCancel) onCancel();
    };

    return html`
      <div class="modal-backdrop" onClick=${handleCancelClick}>
        <div class="modal-content" style="max-width: 400px; animation: modalIn 0.2s ease-out;" onClick=${(e) => e.stopPropagation()}>
          <div class="modal-header" style="padding: 16px 20px;">
            <h3>${title || (type === 'confirm' ? 'Xác nhận' : 'Thông báo')}</h3>
            <button class="nav-btn" type="button" onClick=${handleCancelClick}>✕</button>
          </div>
          <div class="modal-body" style="padding: 20px; font-size: 14px; line-height: 1.5; color: var(--text-color);">
            ${message}
          </div>
          <div class="modal-footer" style="padding: 12px 20px;">
            ${type === 'confirm' && html`
              <button class="btn-secondary" style="padding: 8px 16px; border-radius: 8px;" type="button" onClick=${handleCancelClick}>Hủy</button>
            `}
            <button class="btn-primary" style="padding: 8px 16px; border-radius: 8px;" type="button" onClick=${handleConfirmClick}>Đồng ý</button>
          </div>
        </div>
      </div>
    `;
  }

  // --- Render Reader UI ---
  const padPage = (num) => String(num).padStart(4, '0');
  
  const enPageUrl = `books/${activeBook.slug}/output/en/page_${padPage(page)}.html`;
  const viPageUrl = `books/${activeBook.slug}/output/vi/page_${padPage(page)}.html`;

  return html`
    <div class="reader-view">
      <div class="reader-topbar">
        <div class="reader-topbar__left">
          <button class="btn-action" onClick=${() => setActiveBook(null)}>
            🏠 Library
          </button>
          <span class="reader-topbar__title">${activeBook.title}</span>
        </div>

        <div class="reader-nav">
          <button class="nav-btn" disabled=${page <= 1} onClick=${() => setPage(p => Math.max(1, p - 1))}>
            ◀
          </button>
          <span class="page-indicator">
            Trang
            <input class="page-input" type="number" min="1" max=${activeBook.pageCount} value=${page} 
              onChange=${(e) => {
                let val = parseInt(e.target.value, 10);
                if (isNaN(val) || val < 1) val = 1;
                if (val > activeBook.pageCount) val = activeBook.pageCount;
                setPage(val);
              }}
            />
            / ${activeBook.pageCount}
          </span>
          <button class="nav-btn" disabled=${page >= activeBook.pageCount} onClick=${() => setPage(p => Math.min(activeBook.pageCount, p + 1))}>
            ▶
          </button>
        </div>

        <div class="reader-topbar__right">
          <div class="view-modes">
            <button class=${`mode-btn ${viewMode === 'en' ? 'active' : ''}`} onClick=${() => setViewMode('en')} title="Tiếng Anh (Bản gốc)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
              </svg>
              <span>EN</span>
            </button>
            <button class=${`mode-btn ${viewMode === 'vi' ? 'active' : ''}`} onClick=${() => setViewMode('vi')} title="Tiếng Việt (Bản dịch)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
              </svg>
              <span>VI</span>
            </button>
            <button class=${`mode-btn ${viewMode === 'split' ? 'active' : ''}`} onClick=${() => setViewMode('split')} title="Song ngữ song song">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                <line x1="12" y1="3" x2="12" y2="21"></line>
              </svg>
              <span>Song Ngữ</span>
            </button>
          </div>

          <button class=${`btn-icon ${chatOpen ? 'active' : ''}`} onClick=${() => setChatOpen(!chatOpen)} title="Trợ lý AI">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
              <circle cx="9" cy="10" r="1"></circle>
              <circle cx="15" cy="10" r="1"></circle>
              <path d="M9 15h6"></path>
            </svg>
          </button>
          
          <button class="btn-icon" onClick=${openSettings} title="Cấu hình API Key">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="3"></circle>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1-1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
            </svg>
          </button>
        </div>
      </div>

      <div class=${`reader-workspace ${chatOpen ? 'chat-open' : ''}`}>
        <div class=${`reader-panes layout-${layoutMode}`}>
          
          <!-- English Pane -->
          ${(viewMode === 'en' || viewMode === 'split') && html`
            <div class="reader-pane" id="en-pane">
              <span class="pane-label">EN</span>
              <div class="iframe-wrapper">
                <iframe class="reader-iframe en-pane-iframe" src=${enPageUrl} key=${`en-${page}`} onLoad=${handleIframeLoad} scrolling="no" />
              </div>
            </div>
          `}

          <!-- Vietnamese Pane -->
          ${(viewMode === 'vi' || viewMode === 'split') && html`
            <div class="reader-pane" id="vi-pane">
              <span class="pane-label">VI</span>
              <div class="iframe-wrapper">
                <iframe class="reader-iframe vi-pane-iframe" src=${viPageUrl} key=${`vi-${page}`} onLoad=${handleIframeLoad} scrolling="no" />
              </div>
            </div>
          `}
        </div>

        <!-- Chat Sidebar Drawer -->
        <div class=${`chat-sidebar ${isResizing ? 'is-resizing' : ''}`} style=${chatOpen ? { width: `${chatWidth}px` } : { width: '0px', borderLeft: 'none', overflow: 'hidden' }}>
          <!-- Resize Handle -->
          <div class="chat-resize-handle" onMouseDown=${startResizing}></div>

          <div class="chat-header">
            <span class="chat-header__title">
              🤖 Agent Assistant
              <span class="chat-header__badge">Context Active</span>
            </span>
            <div style="display: flex; gap: 8px; align-items: center;">
              ${messages.length > 0 && html`
                <button class="nav-btn reload-chat-btn" onClick=${handleClearActiveChat} title="Làm mới phiên chat">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M23 4v6h-6"></path>
                    <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
                  </svg>
                </button>
              `}
              <button class="nav-btn" onClick=${() => setChatOpen(false)}>✕</button>
            </div>
          </div>

          <!-- Messages scrollable area -->
          <div class="chat-messages">
            ${messages.map((msg, idx) => html`
              <div class=${`chat-bubble ${msg.role === 'user' ? 'bubble-user' : 'bubble-assistant'} ${msg.pending ? 'pending' : ''}`} key=${idx}>
                ${msg.pending 
                  ? html`
                    <div style="display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-muted);">
                      <span>Đang trả lời</span>
                      <div class="typing-indicator">
                        <span></span>
                        <span></span>
                        <span></span>
                      </div>
                    </div>
                  `
                  : renderMessageContent(msg.content)
                }
              </div>
            `)}
            <div ref=${messagesEndRef} />
          </div>

          <!-- Quick Actions Prompt Toolbar -->
          <div class="chat-quick-actions">
            <button class="quick-prompt-btn" onClick=${() => handleQuickPrompt('Tóm tắt ngắn gọn nội dung trang này.')}>
              📝 Tóm tắt trang
            </button>
            <button class="quick-prompt-btn" onClick=${() => handleQuickPrompt('Giải thích các thuật ngữ kỹ thuật xuất hiện ở trang này.')}>
              💡 Giải thích thuật ngữ
            </button>
            <button class="quick-prompt-btn" onClick=${() => handleQuickPrompt('Có những khái niệm quan trọng nào cần lưu ý ở chương này?')}>
              🔎 Điểm quan trọng
            </button>
          </div>

          <!-- Input Composer -->
          <div class="chat-composer">
            <div class="chat-composer-container">
              <textarea class="chat-input" 
                placeholder="Hỏi về trang này hoặc toàn bộ sách..." 
                value=${chatInput}
                onInput=${(e) => setChatInput(e.target.value)}
                onKeyDown=${(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendChatMessage();
                  }
                }}
              />
              <div class="chat-composer-actions">
                <span class="chat-char-counter">${chatInput.length} ký tự</span>
                ${chatPending 
                  ? html`
                    <button class="chat-send-btn chat-cancel-btn" onClick=${handleCancelChat} title="Hủy phản hồi">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="4" y="4" width="16" height="16" rx="2" ry="2" fill="currentColor"></rect>
                      </svg>
                    </button>
                  `
                  : html`
                    <button class="chat-send-btn" disabled=${!chatInput.trim()} onClick=${() => sendChatMessage()}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="22" y1="2" x2="11" y2="13"></line>
                        <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                      </svg>
                    </button>
                  `
                }
              </div>
            </div>
          </div>
        </div>
      </div>

      ${settingsOpen && renderSettingsModal()}
      ${popupConfig && renderPopupModal()}
    </div>
  `;
}

// Render the application to root body element
render(html`<${App} />`, document.body);
