#!/usr/bin/env python3
"""Stage canonical Bunsho sources into the current browser compiler unit."""
import re

def stage(root):
    source = (root / 'src/moji/editor.kotoba').read_text(encoding='utf-8')
    source, n = re.subn(r'\A\(ns\s+moji\.editor[\s\S]*?\(:export \[[^\]]*\]\)\)',
                        '(ns moji.editor (:export [main]))', source, count=1)
    anchor = '(defn main [] :i64\n  (+ (test-index-core)'
    if n != 1 or source.count(anchor) != 1:
        raise SystemExit('unexpected editor source')
    source = source[:source.index(anchor)]
    # Stage the canonical Kotoba modules in one compilation unit until the native
    # browser project linker supports this source graph; fail if a namespace moves.
    modules = [
        ('json_string.kotoba', r'\A\(ns\s+moji\.json-string\s*\(:export \[json-unquote\]\)\)'),
        ('json_parse.kotoba', r'\A\(ns\s+moji\.json-parse\s*\(:export \[json-parse json-object-field json-array-item json-array-tokens\]\)\s*\(:require \[moji\.json-string :as js\]\)\)'),
        ('legacy_document.kotoba', r'\A\(ns\s+moji\.legacy-document\s*\(:export \[legacy-convert\]\)\s*\(:require \[moji\.json-string :as js\]\s*\[moji\.json-parse :as json\]\)\)'),
        ('legacy_snapshot.kotoba', r'\A\(ns\s+moji\.legacy-snapshot\s*\(:export \[legacy-snapshot-encode legacy-snapshot-decode\]\)\s*\(:require \[moji\.legacy-document :as legacy\]\)\)'),
    ]
    for filename, pattern in modules:
        module = (root / 'src/moji' / filename).read_text(encoding='utf-8')
        module, matched = re.subn(pattern, '', module, count=1)
        if matched != 1:
            raise SystemExit('unexpected namespace in ' + filename)
        module = module.replace('(js/json-unquote ', '(json-unquote ').replace('(json/json-', '(json-').replace('(legacy/legacy-convert ', '(legacy-convert ')
        source += '\n' + module
    source += '\n' + (root / 'src/moji/browser-entry.kotoba').read_text(encoding='utf-8')
    return source
