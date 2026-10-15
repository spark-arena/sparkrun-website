#!/usr/bin/env python3
"""Sync runtime flag tables from core's static maps without importing core."""
import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN = '{/* BEGIN RUNTIME FLAGS */}'
END = '{/* END RUNTIME FLAGS */}'
RUNTIMES = {
    'vllm': ('_vllm_common', 'VLLM'),
    'sglang': ('sglang', '_SGLANG'),
    'llama-cpp': ('llama_cpp', '_LLAMA_CPP'),
    'trtllm': ('trtllm', '_TRTLLM'),
    'atlas': ('atlas', '_ATLAS'),
    'modular-max': ('modular_max', '_MAX'),
}


def literal(node, names):
    if isinstance(node, ast.Name):
        return names[node.id]
    if isinstance(node, ast.Dict):
        return {literal(k, names): literal(v, names) for k, v in zip(node.keys, node.values)}
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        return [literal(item, names) for item in node.elts]
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == 'frozenset' and len(node.args) == 1 and not node.keywords):
        return frozenset(literal(node.args[0], names))
    return ast.literal_eval(node)


def constants(path):
    names = {}
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                names[node.targets[0].id] = literal(node.value, names)
            except (KeyError, ValueError, TypeError):
                pass  # Only static declarations are used; no source code is executed.
    return names


def render(source, slug, module, prefix):
    rel = f'src/sparkrun/runtimes/{module}.py'
    data = constants(source / rel)
    flags = dict(data[prefix + '_FLAG_MAP'])
    booleans = data.get(prefix + '_BOOL_FLAGS', ())
    if isinstance(booleans, dict):
        flags.update(booleans)
    negatable = data.get(prefix + '_NEGATABLE_BOOL_FLAGS', ())
    valued_booleans = data.get(prefix + '_VALUE_BOOL_FLAGS', ())
    revision = json.loads((ROOT / 'scripts/docs-contracts.json').read_text())['revision']
    lines = [BEGIN, '', f'Mappings: [sparkrun 0.4.0 source](https://github.com/spark-arena/sparkrun/blob/{revision}/{rel}).', '',
             '| Engine flag | Key under `defaults` | Value form |', '|---|---|---|']
    for key, flag in flags.items():
        if key in negatable:
            form = f'Boolean; `false` emits `--no-{flag[2:]}`'
        elif key in booleans:
            form = 'Boolean toggle; `true` emits the flag'
        elif key in valued_booleans:
            form = 'Explicit `true` / `false` value'
        elif slug == 'llama-cpp' and key == 'flash_attn':
            form = '`"on"`, `"off"`, `"auto"`; booleans become on/off'
        else:
            form = 'Value'
        lines.append(f'| `{flag}` | `{key}` | {form} |')
    lines.extend(['', END])
    return '\n'.join(lines), len(flags)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path, help='Pinned Sparkrun source tree')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    stale, count = [], 0
    for slug, (module, prefix) in RUNTIMES.items():
        page = ROOT / f'src/content/docs/runtimes/{slug}.mdx'
        original = page.read_text()
        before, rest = original.split(BEGIN, 1)
        _, after = rest.split(END, 1)
        generated, rows = render(args.source, slug, module, prefix)
        updated = before + generated + after
        count += rows
        if original != updated:
            stale.append(slug)
            if not args.check:
                page.write_text(updated)
    if args.check and stale:
        raise SystemExit('Stale runtime tables: ' + ', '.join(stale))
    print(f'{"Checked" if args.check else "Synced"} {count} flag mappings across {len(RUNTIMES)} runtime pages')


if __name__ == '__main__':
    main()
