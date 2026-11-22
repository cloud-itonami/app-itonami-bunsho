// One inline module script for the restricted-wasm-v1 guest (KOTOBA-159). The sandboxed guest is a
// single self-contained document and the host policy admits exactly one guest script by hash, so
// the app's ES modules are inlined here: each module becomes an async function scope that returns
// its exports, in dependency order, and its imports become reads of those scopes. Only the forms the
// migrated apps use are accepted; anything else fails the build instead of being guessed:
//   import x from "./a.js"            import { a, b as c } from "../dir/a.mjs"
//   import type ... (removed)         export { a, b as c } from "./a.js"
//   export function|async function|const|let|class name      export default <expr>
// Module names are paths relative to one root ("ui/app.js", "domain/index.js").
import { readFile } from "node:fs/promises";
import { posix } from "node:path";

const SPEC = String.raw`["'](\.{1,2}\/[\w./-]+\.m?js)["']`;
const IMPORT = new RegExp(String.raw`^import\s+(?:(\w+)|\{([^}]*)\})\s+from\s+${SPEC};?\s*$`);
const IMPORT_TYPE = /^import\s+type\b.*;?\s*$/;
const REEXPORT = new RegExp(String.raw`^export\s+\{([^}]*)\}\s+from\s+${SPEC};?\s*$`);
const EXPORT_DECL = /^export\s+(async\s+function|function|const|let|class)\s+(\w+)/;
const EXPORT_DEFAULT = /^export\s+default\s+/;

const names = (list) => list.split(",").map((s) => s.trim()).filter(Boolean).filter((s) => !s.startsWith("type "))
  .map((s) => { const [orig, alias] = s.split(/\s+as\s+/); return { orig, alias: alias ?? orig }; });

function transform(name, text) {
  const dir = posix.dirname(name);
  const resolveSpec = (spec) => posix.normalize(posix.join(dir, spec));
  const imports = [];
  const exportsList = [];
  let hasDefault = false;
  let reexport = 0;
  const lines = text.split("\n").map((line) => {
    if (IMPORT_TYPE.test(line)) return "";
    const im = IMPORT.exec(line);
    if (im) {
      const target = resolveSpec(im[3]);
      imports.push(target);
      const scope = `__m[${JSON.stringify(target)}]`;
      if (im[1]) return `const ${im[1]} = ${scope}.default;`;
      return `const { ${names(im[2]).map(({ orig, alias }) => (orig === alias ? orig : `${orig}: ${alias}`)).join(", ")} } = ${scope};`;
    }
    const re = REEXPORT.exec(line);
    if (re) {
      const target = resolveSpec(re[2]);
      imports.push(target);
      // A re-export adds properties to the returned object and binds no local name, so it cannot
      // clash with an import of the same name in this module.
      const local = `__re${reexport++}`;
      for (const { orig, alias } of names(re[1])) exportsList.push(`${alias}: ${local}.${orig}`);
      return `const ${local} = __m[${JSON.stringify(target)}];`;
    }
    if (/^\s*import\b/.test(line)) throw new Error(`${name}: unsupported import: ${line}`);
    const ex = EXPORT_DECL.exec(line);
    if (ex) { exportsList.push(ex[2]); return line.replace(/^export\s+/, ""); }
    if (EXPORT_DEFAULT.test(line)) { hasDefault = true; return line.replace(EXPORT_DEFAULT, "const __default = "); }
    if (/^\s*export\b/.test(line)) throw new Error(`${name}: unsupported export: ${line}`);
    return line;
  });
  const returns = [...exportsList, ...(hasDefault ? ["default: __default"] : [])].join(", ");
  return { imports, body: `${lines.join("\n")}\nreturn { ${returns} };` };
}

/**
 * modules: { "path/name.js": text }, entry: "ui/app.js". Returns the script text. Throws on a cycle,
 * a missing module, `</script`, or a form the transform does not accept.
 */
export function bundleModules(modules, entry) {
  const parsed = Object.fromEntries(Object.entries(modules).map(([name, text]) => [name, transform(name, text)]));
  const order = [];
  const state = new Map();
  const visit = (name, path) => {
    if (!parsed[name]) throw new Error(`guest bundle: ${path.join(" -> ")} imports ${name}, which is not in the bundle`);
    if (state.get(name) === "done") return;
    if (state.get(name) === "visiting") throw new Error(`guest bundle: import cycle at ${[...path, name].join(" -> ")}`);
    state.set(name, "visiting");
    for (const dep of parsed[name].imports) visit(dep, [...path, name]);
    state.set(name, "done");
    order.push(name);
  };
  visit(entry, []);
  const parts = ["const __m = Object.create(null);"];
  for (const name of order) {
    // Every scope is async, so a module's top-level await keeps working (the guest script is a module).
    parts.push(`// ---- ${name}\n__m[${JSON.stringify(name)}] = await (async () => {\n${parsed[name].body}\n})();`);
  }
  const script = parts.join("\n");
  if (/<\/script/i.test(script)) throw new Error("guest bundle contains </script");
  return script;
}

export async function readModules(dir, names) {
  return Object.fromEntries(await Promise.all(names.map(async (n) => [n, await readFile(posix.join(dir, n), "utf8")])));
}
