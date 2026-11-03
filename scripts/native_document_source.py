"""Stage the existing browser compiler unit for a native Kotoba host.

Only the module export declaration changes. The original model, migration
codec, and BV2 view functions are the same as the browser build. Compilation
and runtime selection are the host's responsibility.
"""
from browser_source import stage as browser_stage

def stage(root):
    source = browser_stage(root)
    old = '(ns moji.editor (:export [main]))'
    new = '(ns moji.editor (:export [init view step browser-encode browser-decode browser-view-node legacy-convert main]))'
    if not source.startswith(old):
        raise ValueError('unexpected staged module declaration')
    return new + source[len(old):]
