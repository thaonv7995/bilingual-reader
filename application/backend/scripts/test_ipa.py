import re
import urllib.request
from pathlib import Path

DICT_URL = "https://raw.githubusercontent.com/open-dict-data/ipa-dict/master/data/en_US.txt"
DICT_PATH = Path(__file__).parent / "en_US_ipa.txt"

def download_dict():
    if not DICT_PATH.is_file():
        print(f"Downloading IPA dictionary from {DICT_URL}...")
        urllib.request.urlretrieve(DICT_URL, DICT_PATH)
        print("Download complete.")

def load_dict():
    download_dict()
    ipa_dict = {}
    with open(DICT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) == 2:
                word = parts[0].strip().lower()
                ipa_raw = parts[1].strip()
                # Pick the first pronunciation if multiple
                first_pron = ipa_raw.split(",")[0].strip().strip("/")
                ipa_dict[word] = first_pron
    return ipa_dict

def translate_text(text, ipa_dict):
    # Regex to split into words and non-words
    tokens = re.findall(r"[a-zA-Z']+|[^a-zA-Z']+", text)
    result = []
    has_words = False
    
    for token in tokens:
        if token.strip() and re.match(r"^[a-zA-Z']+$", token):
            word_lower = token.lower()
            if word_lower in ipa_dict:
                result.append(ipa_dict[word_lower])
                has_words = True
            else:
                result.append(token)
        else:
            result.append(token)
            
    if has_words:
        # Enclose the whole translated block in slashes
        joined = "".join(result)
        # Clean up double spaces or formatting
        joined = re.sub(r'\s+', ' ', joined)
        return f"/{joined.strip()}/"
    return None

if __name__ == "__main__":
    d = load_dict()
    test_phrases = [
        "Atomic Habits",
        "An Easy & Proven Way to Build Good Habits & Break Bad Ones",
        "JAMES CLEAR",
        "an imprint of Penguin Random House",
        "1. an extremely small amount of a thing; the single irreducible unit of a larger system."
    ]
    for p in test_phrases:
        print(f"EN:  {p}")
        print(f"IPA: {translate_text(p, d)}")
        print("-" * 40)
