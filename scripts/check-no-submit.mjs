// Copied from cloud-itonami/itonami-lib scripts/build.mjs (PR #2, 7ac52696; unchanged in v0.1.2), unchanged, until the
// app builds import it from the lib.
/**
 * The restricted sandbox has no allow-forms: a submit event never fires.
 * Throws when guest code relies on one (a submit listener, onsubmit,
 * requestSubmit or form.submit()) or markup has a type=submit control. Use
 * bindForm (src/form.js) and <button type="button" data-submit> instead.
 */
export function checkNoSubmit(text, what) {
  const rules = [
    [/addEventListener\(\s*["'`]submit["'`]/, "a submit listener"],
    [/\bonsubmit\s*=/, "an onsubmit handler"],
    [/\.requestSubmit\s*\(/, "requestSubmit()"],
    [/\.submit\s*\(\s*\)/, "form.submit()"],
    [/<(button|input)\b[^>]*\btype\s*=\s*["']?submit\b/i, "a type=submit control"],
  ];
  for (const [re, name] of rules) {
    if (re.test(text)) throw new Error(`${what} relies on ${name}, which never fires in the restricted-wasm-v1 sandbox; use bindForm and <button type="button" data-submit>`);
  }
}
