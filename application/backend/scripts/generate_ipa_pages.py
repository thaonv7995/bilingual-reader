#!/usr/bin/env python3
"""Script to generate en-ipa pages with IPA lines interleaved under each wrapped English line using tight CSS flexbox wrappers."""

import argparse
import copy
import html
import json
import math
import os
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

# Setup path to allow backend imports if needed
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from books_core.paths import BookPaths

DICT_URL = "https://raw.githubusercontent.com/open-dict-data/ipa-dict/master/data/en_US.txt"
DICT_PATH = Path(__file__).parent / "en_US_ipa.txt"

# HTML Node Tree Classes
class Node:
    pass

class ElementNode(Node):
    def __init__(self, tag, attrs):
        self.tag = tag.lower()
        self.attrs = attrs  # List of (name, value)
        self.children = []

class TextNode(Node):
    def __init__(self, text):
        self.text = text

class CommentNode(Node):
    def __init__(self, text):
        self.text = text

class DeclNode(Node):
    def __init__(self, decl):
        self.decl = decl

class PINode(Node):
    def __init__(self, data):
        self.data = data

# Tree Builder
class HTMLTreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__()
        self.root = ElementNode("root", [])
        self.stack = [self.root]
        self.self_closing = {"img", "br", "hr", "input", "meta", "link", "base", "col", "embed"}

    def handle_starttag(self, tag, attrs):
        node = ElementNode(tag, attrs)
        self.stack[-1].children.append(node)
        if tag.lower() not in self.self_closing:
            self.stack.append(node)

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        for idx in range(len(self.stack) - 1, -1, -1):
            if self.stack[idx].tag == tag_lower:
                while len(self.stack) > idx:
                    self.stack.pop()
                break

    def handle_data(self, data):
        self.stack[-1].children.append(TextNode(data))

    def handle_comment(self, data):
        self.stack[-1].children.append(CommentNode(data))

    def handle_decl(self, decl):
        self.stack[-1].children.append(DeclNode(decl))

    def handle_pi(self, data):
        self.stack[-1].children.append(PINode(data))

# Serialize Tree to HTML
def serialize_node(node):
    if isinstance(node, ElementNode):
        if node.tag == "root":
            return "".join(serialize_node(c) for c in node.children)
            
        attr_parts = []
        for k, v in node.attrs:
            if v is not None:
                escaped_v = html.escape(v, quote=True)
                attr_parts.append(f' {k}="{escaped_v}"')
            else:
                attr_parts.append(f' {k}')
        attrs_str = "".join(attr_parts)
        
        self_closing = {"img", "br", "hr", "input", "meta", "link", "base", "col", "embed"}
        if node.tag in self_closing and not node.children:
            return f"<{node.tag}{attrs_str}>"
            
        children_str = "".join(serialize_node(c) for c in node.children)
        return f"<{node.tag}{attrs_str}>{children_str}</{node.tag}>"
        
    elif isinstance(node, TextNode):
        return node.text
    elif isinstance(node, CommentNode):
        return f"<!--{node.text}-->"
    elif isinstance(node, DeclNode):
        return f"<!{node.decl}>"
    elif isinstance(node, PINode):
        return f"<?{node.data}>"
    return ""

# IPA Loading
def load_ipa_dict(book_path=None):
    if not DICT_PATH.is_file():
        print(f"Downloading IPA dictionary from {DICT_URL}...")
        try:
            urllib.request.urlretrieve(DICT_URL, DICT_PATH)
            print("Download complete.")
        except Exception as e:
            print(f"Error downloading dictionary: {e}", file=sys.stderr)
            sys.exit(1)

    ipa_dict = {}
    with open(DICT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) == 2:
                word = parts[0].strip().lower()
                ipa_raw = parts[1].strip()
                first_pron = ipa_raw.split(",")[0].strip().strip("/")
                ipa_dict[word] = first_pron
                
    # Manual extensions for missing book vocabulary
    manual_overrides = {
        "a": "ə",
        "the": "ðə",
        "an": "ən",
        "and": "ənd",
        "of": "əv",
        "to": "tə",
        "for": "fər",
        "at": "ət",
        "as": "əz",
        "was": "wəz",
        "are": "ər",
        "or": "ər",
        "your": "jər",
        "can": "kən",
        "from": "frəm",
        "but": "bət",
        "unequipped": "ˌənɪˈkwɪpt",
        "helipad": "ˈhɛlɪˌpæd",
        "brailsford": "ˈbɹeɪlzfɝd",
        "post-traumatic": "ˈpoʊst-tɹɔˈmætɪk",
        "medically": "ˈmɛdɪkli",
    }
    # Load custom book-specific overrides if custom_ipa.json exists
    if book_path:
        custom_path = Path(book_path) / "work" / "custom_ipa.json"
        if custom_path.is_file():
            try:
                with open(custom_path, "r", encoding="utf-8") as cf:
                    custom_data = json.load(cf)
                    # Convert keys to lowercase and update
                    custom_overrides = {k.strip().lower(): v.strip() for k, v in custom_data.items()}
                    ipa_dict.update(custom_overrides)
            except Exception as e:
                print(f"Warning: Failed to load custom IPA overrides: {e}", file=sys.stderr)

    return ipa_dict

# IPA Vowel set for checking linking/liaison
IPA_VOWELS = {'ɑ', 'æ', 'ʌ', 'ɔ', 'ɛ', 'ɪ', 'i', 'u', 'ɜ', 'ə', 'ɝ', 'a', 'e', 'o', 'ʊ', 'ɒ', 'y'}

def starts_with_vowel(ipa_text):
    # Remove stress marks, length marks, spaces, and non-letters to find the first sound
    cleaned = re.sub(r"[ˈˌː\s\d\W]", "", ipa_text)
    if not cleaned:
        return False
    return cleaned[0] in IPA_VOWELS

def standardize_ipa(ipa):
    # Convert unstressed schwa 'ə' to standard 'ɪ' in common prefixes, suffixes, and weak positions
    # 1. -ically -> -ikli
    ipa = re.sub(r"əkli", "ɪkli", ipa)
    # 2. -ily -> -ili
    ipa = re.sub(r"əli", "ɪli", ipa)
    # 3. past tense ending -ted / -ded -> -tid / -did (represented by [td]əd -> [td]ɪd at end of word)
    ipa = re.sub(r"([td])əd\b", r"\1ɪd", ipa)
    ipa = re.sub(r"([td])əd‿", r"\1ɪd‿", ipa)
    # 4. plural/third-person ending -es -> -iz after sibilants
    ipa = re.sub(r"([szʃʒ]|tʃ|dʒ)əz\b", r"\1ɪz", ipa)
    ipa = re.sub(r"([szʃʒ]|tʃ|dʒ)əz‿", r"\1ɪz‿", ipa)
    # 5. superlative -est -> -ist
    ipa = re.sub(r"əst\b", "ɪst", ipa)
    ipa = re.sub(r"əst‿", "ɪst‿", ipa)
    # 6. suffix -ity -> -iti
    ipa = re.sub(r"əti\b", "ɪti", ipa)
    ipa = re.sub(r"əti‿", "ɪti‿", ipa)
    # 7. prefixes de-, re-, be-, ex-, e- when at start of words (e.g. de-/di-/da- -> dɪ-, re-/ri-/ra- -> rɪ-, be-/bi-/ba- -> bɪ-)
    ipa = re.sub(r"(?<![ˈˌ])\b(d|r|b)[iə]", r"\1ɪ", ipa)
    ipa = re.sub(r"\bəgˈz", r"ɪgˈz", ipa)
    
    # 8. Convert incorrect ɜːrˈ prefix (arrived) to standard əˈr
    ipa = re.sub(r"ɜːrˈ", "əˈr", ipa)
    
    # 9. Add length mark ː to stressed long vowels i, u, ɑ, ɔ
    ipa = re.sub(r"([ˈˌ][b-df-hj-np-tv-zʃʒθðŋrltwdg]*)([iuɑɔ])(?![ː])", r"\1\2ː", ipa)
    
    return ipa

# Translate a text string into a list of Nodes (incorporating word wrappers)
def translate_text_node_to_nodes(text, ipa_dict):
    # Normalize all consecutive whitespaces (spaces, tabs, newlines) to a single space
    cleaned_whitespace = re.sub(r"\s+", " ", text)
    # Normalize smart apostrophes first to handle contractions correctly
    normalized = cleaned_whitespace.replace("’", "'").replace("‘", "'").replace("`", "'")
    
    # Split by words, whitespaces, and punctuation
    tokens = re.findall(r"[a-zA-Z']+|\s+|[^a-zA-Z'\s]+", normalized)
    
    items = []
    
    def is_word_token(t):
        return bool(re.match(r"^[a-zA-Z']+$", t))
        
    def is_whitespace_token(t):
        return bool(re.match(r"^\s+$", t))
        
    i = 0
    n = len(tokens)
    while i < n:
        t = tokens[i]
        if is_whitespace_token(t):
            items.append(t)
            i += 1
        elif is_word_token(t):
            pre_punct = ""
            # If the last item in items is a standalone punctuation token, attach it as preceding punctuation
            if items and isinstance(items[-1], tuple) and items[-1][0] == "punct":
                pre_punct = items.pop()[1]
                
            post_punct = ""
            next_idx = i + 1
            # Look ahead for any trailing punctuation tokens
            while next_idx < n and not is_word_token(tokens[next_idx]) and not is_whitespace_token(tokens[next_idx]):
                post_punct += tokens[next_idx]
                next_idx += 1
                
            items.append({
                "type": "word",
                "word": t,
                "pre": pre_punct,
                "post": post_punct
            })
            i = next_idx
        else:
            items.append(("punct", t))
            i += 1
            
    # Now, check for linking/liaison between words (consonant-to-vowel or vowel-to-vowel)
    word_indices = [idx for idx, item in enumerate(items) if isinstance(item, dict) and item["type"] == "word"]
    
    # Pre-lookup IPA for all words
    for idx in word_indices:
        item = items[idx]
        word_lower = item["word"].lower()
        ipa_val = ipa_dict.get(word_lower, None)
        item["ipa"] = ipa_val
        
    # Apply liaison/linking rules
    for k in range(len(word_indices)):
        idx = word_indices[k]
        item = items[idx]
        ipa = item["ipa"]
        if ipa:
            # Check if there is a next word and no punctuation pause in between
            if k + 1 < len(word_indices):
                next_idx = word_indices[k + 1]
                next_item = items[next_idx]
                
                # Check if there is any pause (punctuation) between these two words
                has_pause = False
                for mid_idx in range(idx + 1, next_idx):
                    mid_item = items[mid_idx]
                    if isinstance(mid_item, tuple) and mid_item[0] == "punct":
                        has_pause = True
                        break
                    if item["post"] or next_item["pre"]:
                        has_pause = True
                        break
                        
                if not has_pause:
                    next_ipa = next_item["ipa"]
                    if next_ipa and starts_with_vowel(next_ipa):
                        # Add tie symbol to current word's IPA
                        item["ipa"] = ipa + "‿"
                        
    # Generate final HTML Nodes
    nodes = []
    for item in items:
        if isinstance(item, str):
            # Whitespace
            nodes.append(TextNode(item))
        elif isinstance(item, tuple) and item[0] == "punct":
            # Standalone punctuation
            nodes.append(TextNode(item[1]))
        elif isinstance(item, dict) and item["type"] == "word":
            wrapper = ElementNode("span", [("class", "word-wrapper")])
            
            # English word with punctuation
            en_text = item["pre"] + item["word"] + item["post"]
            en_span = ElementNode("span", [("class", "en-word")])
            en_span.children.append(TextNode(en_text))
            wrapper.children.append(en_span)
            
            # IPA word with punctuation
            ipa = item["ipa"]
            if ipa:
                simplified_ipa = ipa.replace("ɹ", "r").replace("ɫ", "l").replace("ɚ", "ər").replace("ɝ", "ɜːr").replace("ɡ", "g").replace("ɛ", "e")
                standardized = standardize_ipa(simplified_ipa)
                ipa_text = item["pre"] + standardized + item["post"]
                ipa_span = ElementNode("span", [("class", "ipa-word")])
                ipa_span.children.append(TextNode(ipa_text))
                wrapper.children.append(ipa_span)
            else:
                # No IPA translation: keep punctuation, and the word is a space
                ipa_text = item["pre"] + " " + item["post"]
                ipa_span = ElementNode("span", [("class", "ipa-word")])
                ipa_span.children.append(TextNode(ipa_text))
                wrapper.children.append(ipa_span)
                
            nodes.append(wrapper)
            
    return nodes

# DOM Traversal and In-Place Translation
def process_tree(node, ipa_dict, skip_tags, skip_classes):
    if not isinstance(node, ElementNode):
        return [node]

    # If it is a tag to skip, return as-is
    if node.tag in skip_tags:
        return [node]

    # Check for skipped classes
    attrs_dict = dict(node.attrs)
    node_classes = attrs_dict.get("class", "").split()
    if any(c in skip_classes for c in node_classes):
        return [node]

    # Process children
    new_children = []
    for child in node.children:
        if isinstance(child, TextNode):
            translated_nodes = translate_text_node_to_nodes(child.text, ipa_dict)
            new_children.extend(translated_nodes)
        else:
            processed = process_tree(child, ipa_dict, skip_tags, skip_classes)
            new_children.extend(processed)
            
    node.children = new_children
    return [node]

def inject_style(root_node):
    # Find <head> tag and append a style tag
    def find_head(node):
        if isinstance(node, ElementNode):
            if node.tag == "head":
                return node
            for child in node.children:
                res = find_head(child)
                if res:
                    return res
        return None

    head = find_head(root_node)
    if head:
        style_content = """
    /* IPA Interlinear Translation Styles */
    .word-wrapper {
      display: inline-flex !important;
      flex-direction: column !important;
      align-items: center !important;
      vertical-align: top !important;
      margin-left: -0.03em !important;
      margin-right: -0.03em !important;
      line-height: 1.1 !important;
      text-indent: 0 !important;
    }
    .en-word {
      display: block !important;
    }
    .ipa-word {
      display: block !important;
      font-size: 0.74em !important;
      color: var(--book-ink, #111111) !important; /* Solid book ink color (no gray/dithered printing) */
      font-family: Arial, Helvetica, sans-serif !important; /* Clean sans-serif with high contrast */
      text-transform: none !important;
      font-weight: normal !important;
      font-style: italic !important;
      margin-top: 0.5mm !important;
      user-select: none !important;
      text-align: center !important;
    }
    /* Increase line spacing to accommodate interlinear text and disable justified stretching */
    .book-page p, 
    .book-page li, 
    .book-page h1, 
    .book-page h2, 
    .book-page h3, 
    .book-page h4, 
    .book-page h5, 
    .book-page h6, 
    .book-page div:not(.toc-list):not(.toc-frontmatter):not(.toc-chapters):not(.toc-section):not(.word-wrapper) {
      line-height: 2.1 !important;
      text-align: left !important;
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
        margin: 0 !important;
        box-shadow: none !important;
        page-break-after: always !important;
      }
      .book-page {
        height: auto !important;
        min-height: 0 !important;
        max-height: none !important;
        overflow: visible !important;
        page-break-after: avoid !important;
        page-break-before: avoid !important;
      }
    }
"""
        style_node = ElementNode("style", [])
        style_node.children.append(TextNode(style_content))
        head.children.append(style_node)

def get_attr(node, name, default=""):
    if not isinstance(node, ElementNode):
        return default
    for k, v in node.attrs:
        if k == name:
            return v
    return default

def count_words_in_tree(node):
    if not isinstance(node, ElementNode):
        return 0
    if "word-wrapper" in get_attr(node, "class"):
        return 1
    count = 0
    for child in node.children:
        count += count_words_in_tree(child)
    return count

def get_text_content(node):
    if isinstance(node, TextNode):
        return node.text
    if not isinstance(node, ElementNode):
        return ""
    return "".join(get_text_content(c) for c in node.children)

def estimate_line_count(node):
    if not isinstance(node, ElementNode):
        return 0.0
    
    cls = get_attr(node, "class")
    # Ignore header and footer in running calculation
    if node.tag in ("header", "footer") or "running-head" in cls or "book-footer" in cls:
        return 0.0
        
    tag = node.tag
    if tag in ("p", "li"):
        word_count = count_words_in_tree(node)
        if word_count == 0:
            return 0.0
        return math.ceil(word_count / 10.5) + 0.2
    elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        return 2.0
    elif tag in ("figure", "table", "img"):
        return 6.0
    elif tag == "pre":
        text_content = get_text_content(node)
        line_count = len(text_content.strip().split("\n"))
        return line_count * 1.5 + 2.0
    else:
        total = 0.0
        for child in node.children:
            total += estimate_line_count(child)
        if total == 0.0:
            return 1.0
        return total

def clone_node(node):
    if isinstance(node, TextNode):
        return TextNode(node.text)
    elif isinstance(node, ElementNode):
        cloned = ElementNode(node.tag, list(node.attrs))
        for child in node.children:
            cloned.children.append(clone_node(child))
        return cloned
    elif isinstance(node, PINode):
        return PINode(node.data)
    elif isinstance(node, DeclNode):
        return DeclNode(node.decl)
    return node

def split_articles_to_subsheets(node):
    if not isinstance(node, ElementNode):
        return
    
    if node.tag == "article" and "sheet-flow" in get_attr(node, "class"):
        header = None
        footer = None
        content_nodes = []
        for child in node.children:
            if isinstance(child, ElementNode):
                cls = get_attr(child, "class")
                if child.tag == "header" or "running-head" in cls:
                    header = child
                elif child.tag == "footer" or "book-footer" in cls:
                    footer = child
                else:
                    content_nodes.append(child)
            else:
                if isinstance(child, TextNode) and not child.text.strip():
                    continue
                content_nodes.append(child)
                
        sheets = []
        current_group = []
        current_weight = 0.0
        MAX_LINES = 32.0  # Optimized threshold for interlinear lines per A4 sheet
        
        for c in content_nodes:
            weight = estimate_line_count(c)
            if current_weight + weight > MAX_LINES and current_group:
                sheets.append(current_group)
                current_group = [c]
                current_weight = weight
            else:
                current_group.append(c)
                current_weight += weight
                
        if current_group:
            sheets.append(current_group)
            
        new_children = []
        for idx, group in enumerate(sheets):
            subsheet = ElementNode("div", [("class", "ipa-sub-sheet")])
            
            if header:
                subsheet.children.append(clone_node(header))
                
            for c in group:
                subsheet.children.append(c)
                
            if footer:
                subsheet.children.append(clone_node(footer))
                
            new_children.append(subsheet)
            
        node.children = new_children
        return
        
    for child in node.children:
        split_articles_to_subsheets(child)

def process_html_file(in_path: Path, out_path: Path, ipa_dict):
    content = in_path.read_text(encoding="utf-8")
    
    # Parse HTML into tree
    builder = HTMLTreeBuilder()
    builder.feed(content)
    builder.close()
    
    # Define tags to skip and classes to skip
    skip_tags = {'head', 'style', 'script', 'title', 'pre', 'code', 'figure'}
    skip_classes = {'entry-pronunciation', 'cover-art', 'cover'}
    
    # Process tree starting from root's children
    processed_children = []
    for child in builder.root.children:
        processed_children.extend(process_tree(child, ipa_dict, skip_tags, skip_classes))
    builder.root.children = processed_children
    
    # Split article content into multiple A4 sub-sheets if it overflows
    split_articles_to_subsheets(builder.root)
    
    # Inject style block
    inject_style(builder.root)
    
    # Serialize back to HTML
    output_html = serialize_node(builder.root)
    
    # Write to file
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output_html, encoding="utf-8")

def main():
    parser = argparse.ArgumentParser(description="Generate English-IPA interlinear pages using CSS flexbox")
    parser.add_argument("--book", required=True, help="Path to the book root folder")
    parser.add_argument("--pages", help="Comma-separated list or range of pages to process (e.g. 5-10)")
    parser.add_argument("--all", action="store_true", help="Process all pages")
    args = parser.parse_args()

    book_root = Path(args.book).resolve()
    book = BookPaths.open(book_root)
    
    en_dir = book.pages_dir("en")
    if not en_dir.is_dir():
        print(f"Error: English pages directory not found at {en_dir}", file=sys.stderr)
        sys.exit(1)
        
    ipa_dir = book.output_dir / "en-ipa"
    ipa_dir.mkdir(parents=True, exist_ok=True)
    
    # Load IPA dictionary
    ipa_dict = load_ipa_dict(args.book)
    
    # Parse page specification
    all_en_pages = sorted(en_dir.glob("page_*.html"))
    if not all_en_pages:
        print("No English page HTML files found.", file=sys.stderr)
        sys.exit(1)
        
    pages_to_process = []
    if args.all:
        pages_to_process = all_en_pages
    elif args.pages:
        # Support ranges like 5-10
        if "-" in args.pages:
            try:
                start_p, end_p = map(int, args.pages.split("-"))
                for p_path in all_en_pages:
                    try:
                        p_num = int(p_path.stem.split("_")[1])
                        if start_p <= p_num <= end_p:
                            pages_to_process.append(p_path)
                    except ValueError:
                        continue
            except ValueError:
                print("Invalid range format. Use e.g. 5-10", file=sys.stderr)
                sys.exit(1)
        else:
            # Support comma-separated list
            try:
                nums = set(map(int, args.pages.split(",")))
                for p_path in all_en_pages:
                    try:
                        p_num = int(p_path.stem.split("_")[1])
                        if p_num in nums:
                            pages_to_process.append(p_path)
                    except ValueError:
                        continue
            except ValueError:
                print("Invalid list format. Use e.g. 5,6,7", file=sys.stderr)
                sys.exit(1)
    else:
        # Default to a few demo pages if not specified: pages 5 to 10
        print("No pages specified. Processing demo pages (5-10)...")
        for p_path in all_en_pages:
            try:
                p_num = int(p_path.stem.split("_")[1])
                if 5 <= p_num <= 10:
                    pages_to_process.append(p_path)
            except ValueError:
                continue
                
    if not pages_to_process:
        print("No matching pages found to process.")
        sys.exit(1)
        
    print(f"Processing {len(pages_to_process)} pages...")
    for idx, p_path in enumerate(pages_to_process):
        out_path = ipa_dir / p_path.name
        print(f"  [{idx+1}/{len(pages_to_process)}] Processing {p_path.name} -> {out_path.relative_to(book_root)}")
        try:
            process_html_file(p_path, out_path, ipa_dict)
        except Exception as e:
            print(f"  ✗ Failed to process {p_path.name}: {e}", file=sys.stderr)
            
    print("IPA page generation complete!")

if __name__ == "__main__":
    main()
