# Rules for Generating English-IPA Interlinear Pages (`en-ipa`)

This document defines the layout, styling, and structural constraints for the `en-ipa` interlinear transcription pipeline. All books and pages processed for `en-ipa` must follow these rules, taking the verified rendering of `atomic-habits/output/en-ipa/page_0009.html` as the gold standard.

---

## Rule 1 — No A4 Height Constraints on Single Pages, but Page Splitting Required
While individual pages are allowed to grow to double-height due to interlinear IPA text, **they must be dynamically split into separate physical A4 sub-sheets (`.ipa-sub-sheet` containers) if they exceed 32 interlinear lines**.
* This prevents pages from overlapping or spilling onto subsequent sheets in the assembled book.
* Each sub-sheet maintains standard A4 dimensions (`210mm` x `297mm`) and margins.
* Page numbers and footers are cloned across all sub-sheets.

---

## Rule 2 — Word-by-Word Interleaved Structure
To ensure that the IPA transcription wraps dynamically alongside the English text when lines wrap:
1. Every alphabetic token (word) must be wrapped inside a `<span class="word-wrapper">` container.
2. Inside the wrapper, the English word goes into `<span class="en-word">` and the IPA translation goes into `<span class="ipa-word">`.
3. If a word is not found in the IPA dictionary (e.g., names or unknown vocabulary), it **must still be wrapped** in `.word-wrapper`, and an empty space `" "` must be output in `.ipa-word` to ensure 100% consistent word spacing and prevent WebKit mixed inline-block layout bugs.

```html
<!-- Example of word with IPA -->
<span class="word-wrapper">
  <span class="en-word">breathing</span>
  <span class="ipa-word">briðɪŋ‿</span>
</span>

<!-- Example of word without IPA (using empty space placeholder) -->
<span class="word-wrapper">
  <span class="en-word">unequipped</span>
  <span class="ipa-word"> </span>
</span>
```

---

## Rule 3 — Simplified Standard IPA Symbols
To match the standard IPA symbols commonly studied by students in schools and standard English dictionaries:
* Convert all narrow phonetic representations to standard symbols before outputting:
  * `ɹ` $\rightarrow$ **`r`** (e.g., `ˈstrit` instead of `ˈstɹit`)
  * `ɫ` $\rightarrow$ **`l`** (e.g., `ˈhɑˌspɪtəl` instead of `ˈhɑˌspɪtəɫ`)
  * `ɚ` $\rightarrow$ **`ər`** (e.g., `əˈnʌðər` instead of `əˈnəðɚ`)
  * `ɝ` $\rightarrow$ **`ɜːr`** (e.g., `hɜːr` instead of `hɝ`)
  * `ɡ` $\rightarrow$ **`g`** (double-story g for standard font rendering)
  * `ɛ` $\rightarrow$ **`e`** (short-e vowel as in `ˈmedɪkli` instead of `ˈmɛdəkli`)
* Standardize unstressed schwas `/ə/` $\rightarrow$ `/ɪ/` in common prefixes, suffixes, and weak syllables:
  * `-ically` $\rightarrow$ `/ɪkli/`
  * `-ily` $\rightarrow$ `/ɪli/`
  * past tense `-ted/-ded` $\rightarrow$ `/tɪd/, /dɪd/`
  * plural/third-person `-es` $\rightarrow$ `/ɪz/` (after sibilants)
  * superlative `-est` $\rightarrow$ `/ɪst/`
  * suffix `-ity` $\rightarrow$ `/ɪti/`
  * prefixes `de-`, `re-`, `be-` $\rightarrow$ `/dɪ-/, /rɪ-/, /bɪ-/` (when unstressed)
* Do not wrap the IPA output in leading/trailing slashes `/`.

---

## Rule 4 — Punctuation Attachment
To prevent punctuation marks (periods, commas, quotes, parentheses) from aligning with the IPA baseline (which shifts them to the bottom line), all punctuation must be attached directly to the adjacent word wrapper:
1. A word's trailing punctuation goes into `post_punct` and leading punctuation goes into `pre_punct`.
2. The punctuation is rendered in both the `.en-word` (top) and `.ipa-word` (bottom) elements.
3. This ensures the English line and the IPA line both have aligned punctuation and renders them correctly in their respective lines.

```html
<!-- Example of "entirely." -->
<span class="word-wrapper">
  <span class="en-word">entirely.</span>
  <span class="ipa-word">ɪnˈtaɪərli.</span>
</span>

<!-- Example of "unequipped." (no IPA) -->
<span class="word-wrapper">
  <span class="en-word">unequipped.</span>
  <span class="ipa-word"> .</span>
</span>
```

---

## Rule 5 — CSS Styles & Tokens
The CSS style block injected into `<head>` must use the following configuration:

```css
/* IPA Interlinear Translation Styles */
.word-wrapper {
  display: inline-flex !important;
  flex-direction: column !important;
  align-items: center !important;
  vertical-align: top !important;
  margin-left: -0.03em !important;
  margin-right: -0.03em !important;
  line-height: 1.1 !important;
  text-indent: 0 !important; /* Safari text-indent inheritance fix */
}

.en-word {
  display: block !important;
}

.ipa-word {
  display: block !important;
  font-size: 0.74em !important; /* Muted smaller font, slightly larger for legibility */
  color: var(--book-ink, #111111) !important; /* Solid book ink color (no gray/dithered printing) */
  font-family: Arial, Helvetica, sans-serif !important; /* Clean sans-serif with high contrast and legibility at small sizes */
  text-transform: none !important;
  font-weight: normal !important;
  font-style: italic !important; /* Normal italicized style */
  margin-top: 0.5mm !important;
  user-select: none !important; /* Prevent IPA selection when copying English */
  text-align: center !important;
}

/* Enable comfortable spacing and left alignment for paragraphs and blocks */
.book-page p, 
.book-page li, 
.book-page h1, 
.book-page h2, 
.book-page h3, 
.book-page h4, 
.book-page h5, 
.book-page h6, 
.book-page div:not(.toc-list):not(.toc-frontmatter):not(.toc-chapters):not(.toc-section):not(.word-wrapper) {
  line-height: 2.1 !important; /* Muted line-height to fit text better */
  text-align: left !important; /* Left alignment to avoid justified word stretching */
}

/* Reset outer constraints for en-ipa pages to allow inner sub-sheets to flow */
.book-page.book-page--sheet {
  height: auto !important;
  min-height: 0 !important;
  max-height: none !important;
  overflow: visible !important;
  background: transparent !important;
  box-shadow: none !important;
  padding: 0 !important;
  margin: 0 !important;
  width: auto !important;
}
.sheet-flow {
  height: auto !important;
  overflow: visible !important;
  padding: 0 !important;
  margin: 0 !important;
}

/* Make sub-sheets behave like independent A4 sheets */
.ipa-sub-sheet {
  box-sizing: border-box;
  width: 210mm;
  height: 297mm;
  padding: 20mm 20mm 15mm 20mm;
  position: relative;
  background: white;
  box-shadow: 0 16px 44px rgba(15, 23, 42, 0.18);
  margin: 0 auto 10mm auto;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
}

@media print {
  .ipa-sub-sheet {
    margin: 0;
    box-shadow: none;
    page-break-after: always;
  }
  .book-page {
    height: auto !important;
  }
}
```
