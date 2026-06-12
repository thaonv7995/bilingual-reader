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

const HIGHLIGHT_COLORS = [
  { id: 'yellow', value: '#fde68a', label: 'Vàng' },
  { id: 'blue', value: '#93c5fd', label: 'Xanh' },
  { id: 'pink', value: '#f9a8d4', label: 'Hồng' },
  { id: 'green', value: '#86efac', label: 'Xanh lá' },
];

const PARAGRAPH_SELECTOR = 'p, .chapter-start, .no-indent, h1, h2, h3, li';

let highlightAppContext = null;

function getSavedProgress(slug) {
  try {
    const saved = localStorage.getItem(`bilingual.reader.progress.${slug}`);
    if (saved) return JSON.parse(saved);
  } catch (e) {}
  return null;
}

function getRelativeTime(timestamp) {
  const now = Date.now();
  const diffMs = now - timestamp;
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return 'Vừa xong';
  if (diffMins < 60) return `${diffMins} phút trước`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours} giờ trước`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 30) return `${diffDays} ngày trước`;
  const diffMonths = Math.floor(diffDays / 30);
  return `${diffMonths} tháng trước`;
}

function generateHighlightId() {
  return `hl-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`;
}

function loadHighlights(slug) {
  try {
    const saved = localStorage.getItem(`bilingual.reader.highlights.${slug}`);
    if (saved) {
      const parsed = JSON.parse(saved);
      return parsed.highlights || [];
    }
  } catch (e) {}
  return [];
}

function saveHighlights(slug, highlights) {
  localStorage.setItem(`bilingual.reader.highlights.${slug}`, JSON.stringify({ highlights }));
}

function getInitialRoute() {
  const hash = window.location.hash;
  if (!hash) return { book: null, page: 1, viewMode: null };
  const readMatch = hash.match(/^#\/read\/([^/]+)(?:\/page\/(\d+))?$/);
  if (readMatch) {
    const slug = readMatch[1];
    const savedProgress = getSavedProgress(slug);
    const pageNum = readMatch[2]
      ? parseInt(readMatch[2], 10)
      : (savedProgress?.page || 1);
    const book = typeof BOOKS !== 'undefined' ? BOOKS.find(b => b.slug === slug) : null;
    if (book) {
      return {
        book,
        page: pageNum,
        viewMode: savedProgress?.viewMode || null,
      };
    }
  }
  return { book: null, page: 1, viewMode: null };
}

function App() {
  const initialRoute = getInitialRoute();

  // --- Navigation & Book State ---
  const [activeBook, setActiveBook] = useState(initialRoute.book);
  const [page, setPage] = useState(initialRoute.page);
  const [viewMode, setViewMode] = useState(() => {
    if (initialRoute.viewMode) return initialRoute.viewMode;
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
    if (width < 1000) return 3;
    return 4;
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
  const [highlightsPanelOpen, setHighlightsPanelOpen] = useState(false);
  const [bookHighlights, setBookHighlights] = useState([]);

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

  // --- Auto-save Reading Progress ---
  useEffect(() => {
    if (activeBook && page > 0) {
      const progressData = {
        page,
        viewMode,
        lastRead: Date.now()
      };
      localStorage.setItem(`bilingual.reader.progress.${activeBook.slug}`, JSON.stringify(progressData));
    }
  }, [activeBook, page, viewMode]);

  useEffect(() => {
    if (activeBook) {
      setBookHighlights(loadHighlights(activeBook.slug));
    } else {
      setBookHighlights([]);
      removeAllReaderHighlightUI();
      setHighlightsPanelOpen(false);
    }
  }, [activeBook]);

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

  // Clear sentence highlights when clicking outside of the iframes
  useEffect(() => {
    const handleParentClick = (e) => {
      if (!e.target.closest('.reader-iframe')) {
        clearAllHighlights();
        removeAllReaderHighlightUI();
      }
    };
    window.addEventListener('click', handleParentClick);
    return () => window.removeEventListener('click', handleParentClick);
  }, []);

  // Synchronize scrolling between English and Vietnamese wrappers (esp. in stacked layouts)
  useEffect(() => {
    const enWrapper = document.querySelector('#en-pane .iframe-wrapper');
    const viWrapper = document.querySelector('#vi-pane .iframe-wrapper');
    if (!enWrapper || !viWrapper) return;

    let isSyncingEnScroll = false;
    let isSyncingViScroll = false;

    const handleEnScroll = () => {
      if (!isSyncingEnScroll) {
        isSyncingViScroll = true;
        viWrapper.scrollTop = enWrapper.scrollTop;
        viWrapper.scrollLeft = enWrapper.scrollLeft;
        setTimeout(() => { isSyncingViScroll = false; }, 20);
      }
    };

    const handleViScroll = () => {
      if (!isSyncingViScroll) {
        isSyncingEnScroll = true;
        enWrapper.scrollTop = viWrapper.scrollTop;
        enWrapper.scrollLeft = viWrapper.scrollLeft;
        setTimeout(() => { isSyncingEnScroll = false; }, 20);
      }
    };

    enWrapper.addEventListener('scroll', handleEnScroll);
    viWrapper.addEventListener('scroll', handleViScroll);

    return () => {
      enWrapper.removeEventListener('scroll', handleEnScroll);
      viWrapper.removeEventListener('scroll', handleViScroll);
    };
  }, [layoutMode, viewMode, page]);

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
      const iframeEl = e.target;
      const iframeWin = iframeEl.contentWindow;
      const doc = iframeEl.contentDocument || iframeWin.document;
      if (doc) {
        doc.documentElement.style.overflow = 'hidden';
        doc.body.style.overflow = 'hidden';

        // Hide internal pages redundant navigation controls
        const nav = doc.querySelector('.page-nav');
        if (nav) nav.style.display = 'none';

        const isEnglish = iframeEl.classList.contains('en-pane-iframe');
        const lang = isEnglish ? 'en' : 'vi';
        injectHighlightCSS(doc, isEnglish);

        // Segment sentences in the document
        segmentDocSentences(doc);

        if (activeBook) {
          applyStoredHighlights(doc, activeBook.slug, page, lang);
        }

        // Register highlighting listeners inside the iframe
        registerIframeHighlightListeners(iframeWin, doc, iframeEl, lang);

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

  const createHighlight = (selectionInfo, lang, color, note = '') => {
    if (!activeBook || !selectionInfo) return;
    const highlight = {
      id: generateHighlightId(),
      page,
      lang,
      color,
      text: selectionInfo.text,
      startOffset: selectionInfo.startOffset,
      endOffset: selectionInfo.endOffset,
      paragraphIndex: selectionInfo.paragraphIndex,
      note: note || '',
      createdAt: Date.now(),
    };
    const next = [...bookHighlights, highlight];
    saveHighlights(activeBook.slug, next);
    setBookHighlights(next);
    reapplyHighlightsInIframes(activeBook.slug, page, lang);
    document.querySelectorAll('.reader-iframe').forEach(iframe => {
      iframe.contentWindow?.getSelection()?.removeAllRanges();
    });
    removeAllReaderHighlightUI();
    return highlight;
  };

  const updateHighlight = (id, updates) => {
    if (!activeBook) return;
    const next = bookHighlights.map(h => h.id === id ? { ...h, ...updates } : h);
    saveHighlights(activeBook.slug, next);
    setBookHighlights(next);
    const target = next.find(h => h.id === id);
    if (target) {
      reapplyHighlightsInIframes(activeBook.slug, target.page, target.lang);
    }
    removeAllReaderHighlightUI();
  };

  const deleteHighlight = (id) => {
    if (!activeBook) return;
    const target = bookHighlights.find(h => h.id === id);
    const next = bookHighlights.filter(h => h.id !== id);
    saveHighlights(activeBook.slug, next);
    setBookHighlights(next);
    if (target) {
      reapplyHighlightsInIframes(activeBook.slug, target.page, target.lang);
    }
    removeAllReaderHighlightUI();
  };

  useEffect(() => {
    if (!activeBook) {
      highlightAppContext = null;
      return;
    }
    highlightAppContext = {
      slug: activeBook.slug,
      page,
      setBookHighlights,
      createHighlight,
      updateHighlight,
      deleteHighlight,
    };
    return () => {
      highlightAppContext = null;
    };
  }, [activeBook, page, bookHighlights]);

  const jumpToHighlight = (highlight) => {
    if (!highlight || !activeBook) return;
    removeAllReaderHighlightUI();
    setPage(highlight.page);
    setTimeout(() => {
      const iframe = document.querySelector(highlight.lang === 'en' ? '.en-pane-iframe' : '.vi-pane-iframe');
      if (iframe && iframe.contentDocument) {
        const mark = iframe.contentDocument.querySelector(`mark.reader-highlight[data-highlight-id="${highlight.id}"]`);
        if (mark) {
          mark.scrollIntoView({ behavior: 'smooth', block: 'center' });
          mark.classList.add('reader-highlight--pulse');
          setTimeout(() => mark.classList.remove('reader-highlight--pulse'), 1200);
        }
      }
    }, 350);
  };

  const groupedHighlights = useMemo(() => {
    const groups = {};
    bookHighlights.forEach(h => {
      if (!groups[h.page]) groups[h.page] = [];
      groups[h.page].push(h);
    });
    return Object.keys(groups)
      .map(Number)
      .sort((a, b) => a - b)
      .map(pageNum => ({
        page: pageNum,
        items: groups[pageNum].sort((a, b) => a.createdAt - b.createdAt),
      }));
  }, [bookHighlights]);

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
        const savedProgress = getSavedProgress(slug);
        const pageNum = readMatch[2]
          ? parseInt(readMatch[2], 10)
          : (savedProgress?.page || 1);

        // Find book in BOOKS array (defined in books.js)
        const book = BOOKS.find(b => b.slug === slug);
        if (book) {
          setActiveBook(book);
          setPage(pageNum);
          if (savedProgress?.viewMode && !readMatch[2]) {
            setViewMode(savedProgress.viewMode);
          }
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
      <div class="app-container">
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
              const progress = getSavedProgress(book.slug);
              const hasProgress = progress && progress.page > 1;
              return html`
                <div class="book-card" key=${book.slug} onClick=${() => {
                  if (progress) {
                    setActiveBook(book);
                    setPage(progress.page);
                    setViewMode(progress.viewMode || 'en');
                  } else {
                    setActiveBook(book);
                    setPage(1);
                    setViewMode('en');
                  }
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
                    ${hasProgress && html`
                      <div class="book-card__last-read">🕐 ${getRelativeTime(progress.lastRead)}</div>
                    `}
                  </div>
                  <div class="book-card__content">
                    <h3 class="book-card__title">${book.title}</h3>
                    <div class="book-card__author">Tác giả: ${book.author}</div>
                    <p class="book-card__desc">${book.description}</p>
                    <div class="book-card__footer">
                      <span>📖 ${hasProgress ? `${progress.page}/${book.pageCount} trang` : `${book.pageCount} trang`}</span>
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
  function renderHighlightsPanel() {
    if (!highlightsPanelOpen) return null;

    return html`
      <div class="highlights-panel">
        <div class="highlights-panel__header">
          <span class="highlights-panel__title">🖍 Highlights (${bookHighlights.length})</span>
          <button class="nav-btn" onClick=${() => setHighlightsPanelOpen(false)}>✕</button>
        </div>
        <div class="highlights-panel__body">
          ${bookHighlights.length === 0 && html`
            <div class="highlights-panel__empty">
              Chưa có highlight nào.<br />
              Bôi đen text trong trang sách để bắt đầu.
            </div>
          `}
          ${groupedHighlights.map(group => html`
            <div class="highlights-panel__group" key=${group.page}>
              <div class="highlights-panel__group-title">Trang ${group.page}</div>
              ${group.items.map(item => html`
                <button
                  key=${item.id}
                  class="highlights-panel__item"
                  onClick=${() => jumpToHighlight(item)}
                >
                  <span
                    class="highlights-panel__item-color"
                    style=${{ backgroundColor: item.color }}
                  />
                  <span class="highlights-panel__item-content">
                    <span class="highlights-panel__item-text">${item.text}</span>
                    ${item.note && html`<span class="highlights-panel__item-note">${item.note}</span>`}
                    <span class="highlights-panel__item-meta">${item.lang.toUpperCase()}</span>
                  </span>
                </button>
              `)}
            </div>
          `)}
        </div>
      </div>
    `;
  }

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

          <button class=${`btn-icon ${highlightsPanelOpen ? 'active' : ''}`} onClick=${() => setHighlightsPanelOpen(v => !v)} title="Highlights & Ghi chú">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 20h9"></path>
              <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path>
            </svg>
          </button>

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

      <div
        class=${`reader-workspace ${chatOpen ? 'chat-open' : ''} ${highlightsPanelOpen ? 'highlights-open' : ''}`}
        style=${chatOpen ? { '--chat-width': `${chatWidth}px` } : {}}
      >
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

        ${renderHighlightsPanel()}

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

// --- Bilingual Sentence Highlight Sync Helpers ---

function splitIntoSentences(text) {
  if (!text) return [];
  
  const sentences = [];
  let currentStart = 0;
  
  const boundaryRegex = /([.!?])(\s+|$)/g;
  let match;
  
  const abbrevs = [
    'mr', 'mrs', 'dr', 'ms', 'prof', 'sr', 'jr', 'vs', 'etc', 'eg', 'ie', 'al',
    'st', 'av', 'rd', 'capt', 'gen', 'col', 'lt', 'sgt', 'rep', 'sen', 'oct', 'nov', 'dec',
    'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'tp', 'ts', 'ths', 'gs', 'hcm'
  ];
  
  while ((match = boundaryRegex.exec(text)) !== null) {
    const boundaryIdx = match.index;
    
    const precedingText = text.substring(currentStart, boundaryIdx);
    const lastWordMatch = precedingText.match(/(\b\w+)$/);
    const lastWord = lastWordMatch ? lastWordMatch[1].toLowerCase() : '';
    
    if (abbrevs.includes(lastWord)) {
      continue;
    }
    
    // Split including exact boundary punctuation and its trailing whitespace
    const sentenceEnd = boundaryIdx + 1 + match[2].length;
    const sentenceText = text.substring(currentStart, sentenceEnd);
    if (sentenceText.length > 0) {
      sentences.push(sentenceText);
    }
    currentStart = sentenceEnd;
  }
  
  if (currentStart < text.length) {
    const remaining = text.substring(currentStart);
    if (remaining.length > 0) {
      sentences.push(remaining);
    }
  }
  
  return sentences;
}

function segmentParagraph(pElement, pIdx) {
  const text = pElement.textContent;
  const sentences = splitIntoSentences(text);
  
  if (sentences.length <= 1) {
    const span = pElement.ownerDocument.createElement('span');
    span.className = 'sentence-node';
    span.dataset.sentenceId = `p-${pIdx}-s-0`;
    while (pElement.firstChild) {
      span.appendChild(pElement.firstChild);
    }
    pElement.appendChild(span);
    return;
  }
  
  const sentenceSpans = sentences.map((sText, sIdx) => {
    const span = pElement.ownerDocument.createElement('span');
    span.className = 'sentence-node';
    span.dataset.sentenceId = `p-${pIdx}-s-${sIdx}`;
    return span;
  });
  
  let currentSentenceIdx = 0;
  let currentSentenceRemainingLen = sentences[0].length;
  
  const childNodes = Array.from(pElement.childNodes);
  pElement.innerHTML = '';
  
  childNodes.forEach(node => {
    if (node.nodeType === 3) { // Text Node
      let nodeText = node.textContent;
      while (nodeText.length > 0 && currentSentenceIdx < sentences.length) {
        if (nodeText.length <= currentSentenceRemainingLen) {
          const textNode = pElement.ownerDocument.createTextNode(nodeText);
          sentenceSpans[currentSentenceIdx].appendChild(textNode);
          currentSentenceRemainingLen -= nodeText.length;
          nodeText = '';
        } else {
          const part = nodeText.substring(0, currentSentenceRemainingLen);
          const textNode = pElement.ownerDocument.createTextNode(part);
          sentenceSpans[currentSentenceIdx].appendChild(textNode);
          
          nodeText = nodeText.substring(currentSentenceRemainingLen);
          
          currentSentenceIdx++;
          if (currentSentenceIdx < sentences.length) {
            currentSentenceRemainingLen = sentences[currentSentenceIdx].length;
          }
        }
      }
    } else if (node.nodeType === 1) { // Element Node
      sentenceSpans[currentSentenceIdx].appendChild(node);
      currentSentenceRemainingLen -= node.textContent.length;
      if (currentSentenceRemainingLen <= 0 && currentSentenceIdx < sentences.length - 1) {
        currentSentenceIdx++;
        currentSentenceRemainingLen = sentences[currentSentenceIdx].length;
      }
    }
  });
  
  sentenceSpans.forEach(span => {
    if (span.textContent.length > 0) {
      pElement.appendChild(span);
    }
  });
}

function segmentDocSentences(doc) {
  const article = doc.querySelector('article') || doc.body;
  if (!article) return;
  
  const paragraphs = article.querySelectorAll('p, .chapter-start, .no-indent, h1, h2, h3, li');
  paragraphs.forEach((p, idx) => {
    if (!p.querySelector('.sentence-node')) {
      segmentParagraph(p, idx);
    }
  });
}

function injectHighlightCSS(doc, isEnglish) {
  if (doc.getElementById('bilingual-highlight-style')) return;
  const style = doc.createElement('style');
  style.id = 'bilingual-highlight-style';
  
  const highlightColor = isEnglish 
    ? 'rgba(56, 189, 248, 0.18)'
    : 'rgba(250, 204, 21, 0.20)';
    
  const hoverColor = isEnglish
    ? 'rgba(56, 189, 248, 0.08)'
    : 'rgba(250, 204, 21, 0.08)';

  style.textContent = `
    .sentence-node {
      transition: background-color 0.2s ease;
      border-radius: 3px;
      cursor: pointer;
      display: inline;
    }
    .sentence-node:hover {
      background-color: ${hoverColor};
    }
    .sentence-node.highlight-sync {
      background-color: ${highlightColor} !important;
    }
    mark.reader-highlight {
      border-radius: 3px;
      padding: 0 1px;
      cursor: pointer;
      position: relative;
      color: inherit;
      box-decoration-break: clone;
      -webkit-box-decoration-break: clone;
    }
    mark.reader-highlight[data-has-note="true"]::after {
      content: '';
      position: absolute;
      top: -3px;
      right: -3px;
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #2563eb;
      border: 1px solid #fff;
    }
    mark.reader-highlight--pulse {
      animation: readerHighlightPulse 1.2s ease;
    }
    @keyframes readerHighlightPulse {
      0%, 100% { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0); }
      50% { box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.35); }
    }
    .reader-highlight-toolbar {
      position: fixed;
      z-index: 9999;
      transform: translate(-50%, -100%);
      display: flex;
      align-items: center;
      gap: 4px;
      padding: 5px 7px;
      background: rgba(17, 24, 39, 0.92);
      backdrop-filter: blur(12px);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 10px;
      box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35);
      animation: readerToolbarIn 0.15s ease;
    }
    .reader-highlight-toolbar__colors {
      display: flex;
      gap: 4px;
    }
    .reader-highlight-toolbar__color {
      width: 18px;
      height: 18px;
      border-radius: 50%;
      border: 1.5px solid rgba(255, 255, 255, 0.3);
      cursor: pointer;
      padding: 0;
    }
    .reader-highlight-toolbar__color:hover {
      transform: scale(1.1);
    }
    .reader-highlight-toolbar__icon {
      width: 22px;
      height: 22px;
      border-radius: 6px;
      border: 1px solid rgba(255, 255, 255, 0.1);
      background: rgba(255, 255, 255, 0.08);
      font-size: 11px;
      cursor: pointer;
      padding: 0;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }
    .reader-highlight-toolbar__icon:hover {
      background: rgba(255, 255, 255, 0.16);
    }
    .reader-highlight-sticky {
      position: fixed;
      z-index: 9999;
      width: 168px;
      min-height: 68px;
      background: linear-gradient(160deg, #fef9c3 0%, #fde68a 55%, #fcd34d 100%);
      border: 1px solid rgba(180, 130, 0, 0.35);
      border-radius: 1px 1px 1px 0;
      box-shadow: 1px 2px 0 rgba(180, 130, 0, 0.15), 3px 5px 12px rgba(0, 0, 0, 0.2);
      padding: 8px 8px 4px;
      transform: rotate(-1.5deg);
      animation: readerStickyIn 0.2s ease;
    }
    .reader-highlight-sticky__input {
      width: 100%;
      min-height: 48px;
      background: transparent;
      border: none;
      resize: none;
      font-family: 'Segoe Print', 'Comic Sans MS', cursive, sans-serif;
      font-size: 12px;
      line-height: 1.45;
      color: #422006;
      outline: none;
      padding: 0;
    }
    .reader-highlight-sticky__input::placeholder {
      color: rgba(66, 32, 6, 0.45);
    }
    .reader-highlight-sticky__footer {
      display: flex;
      justify-content: flex-end;
      gap: 2px;
      margin-top: 2px;
    }
    .reader-highlight-sticky__btn {
      background: transparent;
      border: none;
      width: 20px;
      height: 20px;
      border-radius: 4px;
      font-size: 11px;
      color: rgba(66, 32, 6, 0.55);
      cursor: pointer;
      padding: 0;
    }
    .reader-highlight-sticky__btn:hover {
      background: rgba(66, 32, 6, 0.08);
      color: #422006;
    }
    .reader-highlight-sticky__btn--save {
      font-weight: 700;
      color: rgba(66, 32, 6, 0.75);
    }
    @keyframes readerToolbarIn {
      from { opacity: 0; transform: translate(-50%, calc(-100% + 4px)); }
      to { opacity: 1; transform: translate(-50%, -100%); }
    }
    @keyframes readerStickyIn {
      from { opacity: 0; transform: rotate(-1.5deg) scale(0.92); }
      to { opacity: 1; transform: rotate(-1.5deg) scale(1); }
    }
  `;
  doc.head.appendChild(style);
}

function getParagraphs(doc) {
  const article = doc.querySelector('article') || doc.body;
  return Array.from(article.querySelectorAll(PARAGRAPH_SELECTOR));
}

function getSelectionInfo(doc, selection) {
  if (!selection || selection.isCollapsed) return null;
  const text = selection.toString().trim();
  if (!text) return null;

  const range = selection.getRangeAt(0);
  let container = range.commonAncestorContainer;
  if (container.nodeType === 3) container = container.parentElement;
  const paragraph = container.closest(PARAGRAPH_SELECTOR);
  if (!paragraph) return null;

  const paragraphs = getParagraphs(doc);
  const paragraphIndex = paragraphs.indexOf(paragraph);
  if (paragraphIndex === -1) return null;

  const preRange = doc.createRange();
  preRange.selectNodeContents(paragraph);
  preRange.setEnd(range.startContainer, range.startOffset);
  const startOffset = preRange.toString().length;
  const endOffset = startOffset + range.toString().length;

  return { paragraphIndex, startOffset, endOffset, text: range.toString() };
}

function wrapTextRange(doc, paragraph, startOffset, endOffset, highlightData) {
  const walker = doc.createTreeWalker(paragraph, NodeFilter.SHOW_TEXT);
  let charCount = 0;
  let startNode = null;
  let startNodeOffset = 0;
  let endNode = null;
  let endNodeOffset = 0;

  while (walker.nextNode()) {
    const node = walker.currentNode;
    const nodeLen = node.textContent.length;
    if (startNode === null && charCount + nodeLen > startOffset) {
      startNode = node;
      startNodeOffset = startOffset - charCount;
    }
    if (endNode === null && charCount + nodeLen >= endOffset) {
      endNode = node;
      endNodeOffset = endOffset - charCount;
      break;
    }
    charCount += nodeLen;
  }

  if (!startNode || !endNode) return false;

  const range = doc.createRange();
  range.setStart(startNode, startNodeOffset);
  range.setEnd(endNode, endNodeOffset);

  const mark = doc.createElement('mark');
  mark.className = 'reader-highlight';
  mark.dataset.highlightId = highlightData.id;
  mark.style.backgroundColor = highlightData.color;
  if (highlightData.note) {
    mark.dataset.hasNote = 'true';
    mark.title = highlightData.note;
  }

  try {
    range.surroundContents(mark);
  } catch (e) {
    const contents = range.extractContents();
    mark.appendChild(contents);
    range.insertNode(mark);
  }
  return true;
}

function applyStoredHighlights(doc, slug, pageNum, lang) {
  const highlights = loadHighlights(slug)
    .filter(h => h.page === pageNum && h.lang === lang)
    .sort((a, b) => {
      if (a.paragraphIndex !== b.paragraphIndex) {
        return a.paragraphIndex - b.paragraphIndex;
      }
      return b.startOffset - a.startOffset;
    });

  const paragraphs = getParagraphs(doc);
  highlights.forEach(h => {
    const paragraph = paragraphs[h.paragraphIndex];
    if (!paragraph) return;
    wrapTextRange(doc, paragraph, h.startOffset, h.endOffset, h);
  });
}

function reapplyHighlightsInIframes(slug, pageNum, lang) {
  const selector = lang === 'en' ? '.en-pane-iframe' : '.vi-pane-iframe';
  const iframe = document.querySelector(selector);
  if (!iframe?.contentDocument) return;
  const doc = iframe.contentDocument;
  removeReaderHighlightUI(doc);
  doc.querySelectorAll('mark.reader-highlight').forEach(el => {
    const parent = el.parentNode;
    while (el.firstChild) parent.insertBefore(el.firstChild, el);
    parent.removeChild(el);
  });
  segmentDocSentences(doc);
  applyStoredHighlights(doc, slug, pageNum, lang);
}

function removeReaderHighlightUI(doc) {
  if (!doc) return;
  doc.querySelectorAll('.reader-highlight-toolbar, .reader-highlight-sticky').forEach(el => el.remove());
}

function removeAllReaderHighlightUI() {
  document.querySelectorAll('.reader-iframe').forEach(iframe => {
    if (iframe.contentDocument) removeReaderHighlightUI(iframe.contentDocument);
  });
}

function showReaderStickyNote(doc, anchorRect, options) {
  doc.querySelectorAll('.reader-highlight-sticky').forEach(el => el.remove());

  const noteEl = doc.createElement('div');
  noteEl.className = 'reader-highlight-sticky';
  const noteWidth = 168;
  let noteX = anchorRect.right + 6;
  if (noteX + noteWidth > doc.documentElement.clientWidth - 8) {
    noteX = Math.max(8, anchorRect.left - noteWidth - 6);
  }
  noteEl.style.left = `${noteX}px`;
  noteEl.style.top = `${anchorRect.top}px`;

  const textarea = doc.createElement('textarea');
  textarea.className = 'reader-highlight-sticky__input';
  textarea.placeholder = 'Ghi chú...';
  textarea.value = options.note || '';

  const footer = doc.createElement('div');
  footer.className = 'reader-highlight-sticky__footer';

  const cancelBtn = doc.createElement('button');
  cancelBtn.className = 'reader-highlight-sticky__btn';
  cancelBtn.type = 'button';
  cancelBtn.title = 'Hủy';
  cancelBtn.textContent = '✕';
  cancelBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    noteEl.remove();
  });

  const saveBtn = doc.createElement('button');
  saveBtn.className = 'reader-highlight-sticky__btn reader-highlight-sticky__btn--save';
  saveBtn.type = 'button';
  saveBtn.title = 'Lưu';
  saveBtn.textContent = '✓';

  const handleSave = () => {
    const text = textarea.value;
    if (options.mode === 'create') {
      highlightAppContext?.createHighlight?.(options.selectionInfo, options.lang, options.color, text);
    } else {
      highlightAppContext?.updateHighlight?.(options.highlightId, { note: text });
    }
    noteEl.remove();
  };

  saveBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    handleSave();
  });

  textarea.addEventListener('keydown', (e) => {
    e.stopPropagation();
    if (e.key === 'Escape') noteEl.remove();
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSave();
    }
  });

  footer.appendChild(cancelBtn);
  footer.appendChild(saveBtn);
  noteEl.appendChild(textarea);
  noteEl.appendChild(footer);
  noteEl.addEventListener('mousedown', (e) => e.stopPropagation());
  doc.body.appendChild(noteEl);
  textarea.focus();
}

function showReaderHighlightToolbar(doc, anchorRect, options) {
  removeReaderHighlightUI(doc);

  const toolbar = doc.createElement('div');
  toolbar.className = 'reader-highlight-toolbar';
  toolbar.style.left = `${anchorRect.left + anchorRect.width / 2}px`;
  toolbar.style.top = `${anchorRect.top - 6}px`;

  const colors = doc.createElement('div');
  colors.className = 'reader-highlight-toolbar__colors';

  HIGHLIGHT_COLORS.forEach(c => {
    const btn = doc.createElement('button');
    btn.type = 'button';
    btn.className = 'reader-highlight-toolbar__color';
    btn.style.backgroundColor = c.value;
    btn.title = c.label;
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (options.mode === 'create') {
        highlightAppContext?.createHighlight?.(options.selectionInfo, options.lang, c.value);
      } else {
        highlightAppContext?.updateHighlight?.(options.highlightId, { color: c.value });
      }
    });
    colors.appendChild(btn);
  });
  toolbar.appendChild(colors);

  const noteBtn = doc.createElement('button');
  noteBtn.type = 'button';
  noteBtn.className = 'reader-highlight-toolbar__icon';
  noteBtn.title = 'Ghi chú';
  noteBtn.textContent = '📝';
  noteBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    toolbar.remove();
    const existing = options.highlightId && highlightAppContext?.slug
      ? loadHighlights(highlightAppContext.slug).find(h => h.id === options.highlightId)
      : null;
    showReaderStickyNote(doc, anchorRect, {
      mode: options.mode,
      lang: options.lang,
      selectionInfo: options.selectionInfo,
      highlightId: options.highlightId,
      color: existing?.color || HIGHLIGHT_COLORS[0].value,
      note: existing?.note || '',
    });
  });
  toolbar.appendChild(noteBtn);

  if (options.mode === 'edit') {
    const delBtn = doc.createElement('button');
    delBtn.type = 'button';
    delBtn.className = 'reader-highlight-toolbar__icon';
    delBtn.title = 'Xóa';
    delBtn.textContent = '🗑';
    delBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      highlightAppContext?.deleteHighlight?.(options.highlightId);
    });
    toolbar.appendChild(delBtn);
  }

  toolbar.addEventListener('mousedown', (e) => e.stopPropagation());
  doc.body.appendChild(toolbar);
}

function highlightSentenceAcrossIframes(sentenceId) {
  const enIframe = document.querySelector('.en-pane-iframe');
  const viIframe = document.querySelector('.vi-pane-iframe');
  
  [enIframe, viIframe].forEach(iframe => {
    if (iframe && iframe.contentDocument) {
      const doc = iframe.contentDocument;
      doc.querySelectorAll('.sentence-node.highlight-sync').forEach(el => {
        el.classList.remove('highlight-sync');
      });
      const targetNode = doc.querySelector(`.sentence-node[data-sentence-id="${sentenceId}"]`);
      if (targetNode) {
        targetNode.classList.add('highlight-sync');
      }
    }
  });
}

function clearAllHighlights() {
  const enIframe = document.querySelector('.en-pane-iframe');
  const viIframe = document.querySelector('.vi-pane-iframe');
  
  [enIframe, viIframe].forEach(iframe => {
    if (iframe && iframe.contentDocument) {
      iframe.contentDocument.querySelectorAll('.sentence-node.highlight-sync').forEach(el => {
        el.classList.remove('highlight-sync');
      });
    }
  });
}

function registerIframeHighlightListeners(iframeWin, doc, iframeEl, lang) {
  doc.addEventListener('mousedown', (e) => {
    if (e.target.closest('mark.reader-highlight, .reader-highlight-toolbar, .reader-highlight-sticky')) return;
    removeReaderHighlightUI(doc);
  });

  doc.addEventListener('mouseup', (e) => {
    setTimeout(() => {
      const selection = iframeWin.getSelection();
      const selectedText = selection.toString().trim();
      const clickedMark = e.target.closest('mark.reader-highlight');

      if (clickedMark) {
        const highlightId = clickedMark.dataset.highlightId;
        const rect = clickedMark.getBoundingClientRect();
        showReaderHighlightToolbar(doc, rect, {
          mode: 'edit',
          lang,
          highlightId,
        });
        if (highlightAppContext?.slug) {
          const existing = loadHighlights(highlightAppContext.slug).find(h => h.id === highlightId);
          if (existing?.note) {
            showReaderStickyNote(doc, rect, {
              mode: 'edit',
              highlightId,
              lang,
              note: existing.note,
            });
          }
        }
        selection.removeAllRanges();
        return;
      }

      if (selectedText.length > 2) {
        const selectionInfo = getSelectionInfo(doc, selection);
        if (selectionInfo) {
          const rect = selection.getRangeAt(0).getBoundingClientRect();
          showReaderHighlightToolbar(doc, rect, {
            mode: 'create',
            lang,
            selectionInfo,
          });
        }
        return;
      }

      let sentenceNode = null;
      if (selectedText.length > 0) {
        const node = selection.anchorNode;
        if (node) {
          sentenceNode = node.parentElement.closest('.sentence-node');
        }
      } else {
        sentenceNode = e.target.closest('.sentence-node');
      }

      if (sentenceNode) {
        const sentenceId = sentenceNode.dataset.sentenceId;
        highlightSentenceAcrossIframes(sentenceId);
      } else {
        removeReaderHighlightUI(doc);
        clearAllHighlights();
      }
    }, 10);
  });
}

// Render the application to root body element
render(html`<${App} />`, document.body);
