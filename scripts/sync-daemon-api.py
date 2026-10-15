#!/usr/bin/env python3
"""Sync bundled operation entries from core's generated DAEMON_API.md inventory.

Reads Markdown and literal source metadata without importing or running Sparkrun.
"""
import argparse
import ast
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / 'src/content/docs/developer-reference/daemon-api.mdx'
BEGIN = '{/* BEGIN DAEMON OPERATION REFERENCE */}'
END = '{/* END DAEMON OPERATION REFERENCE */}'
SOURCE_BEGIN = '<!-- BEGIN GENERATED DAEMON OPERATIONS -->'
SOURCE_END = '<!-- END GENERATED DAEMON OPERATIONS -->'
BUNDLED_SECTIONS = {'Core operations', 'Bundled Kubernetes plugin'}
# Keep the hidden benchmark failure-policy controls out of website guidance.
OMITTED_ARGUMENTS = {
    'benchmarks.run': {'exit_on_first_fail'},
    'benchmarks.resume': {'exit_on_first_fail'},
}


def descriptions_for(reference):
    source = reference.parent.parent / 'src/sparkrun/daemon/ops.py'
    tree = ast.parse(source.read_text())
    descriptions = next(
        ast.literal_eval(node.value) for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'DESCRIPTIONS' for target in node.targets)
    )
    supplemental = json.loads((ROOT / 'scripts/daemon-operation-descriptions.json').read_text())
    overlap = descriptions.keys() & supplemental.keys()
    if overlap:
        raise ValueError(f'Review supplemental descriptions now provided by core: {sorted(overlap)}')
    return descriptions | supplemental


def render(reference, descriptions):
    inventory = reference.split(SOURCE_BEGIN, 1)[1].split(SOURCE_END, 1)[0]
    output, names = [BEGIN, ''], set()
    included, sections = False, set()
    for line in inventory.splitlines():
        if line.startswith('## '):
            section = line.removeprefix('## ')
            included = section in BUNDLED_SECTIONS
            if included:
                sections.add(section)
        if not included:
            continue
        if line.startswith('| `'):
            cells = [cell.strip() for cell in line.strip('|').split('|')]
            if len(cells) != 5:
                raise ValueError(f'Unexpected operation row: {line}')
            operation, alias, mode, reservation, fields = cells
            name, path = operation.strip('`'), alias.strip('`')
            if name in names or not re.fullmatch(r'[a-z][a-z0-9_.-]+', name):
                raise ValueError(f'Duplicate or invalid operation: {name}')
            description = descriptions.get(name)
            if not isinstance(description, str) or not description.strip():
                raise ValueError(f'Missing operation description: {name}')
            names.add(name)
            if not path.startswith('/v1/') or reservation not in {'auto', 'controller', 'none'}:
                raise ValueError(f'Invalid path or reservation for {name}')
            kind, scope = mode.split(' / ')
            if kind not in {'job', 'query'} or scope not in {'read', 'operate', 'admin'}:
                raise ValueError(f'Unexpected execution kind or scope for {name}')
            output.extend([
                f'<details id="{name.replace(".", "-")}">',
                f'<summary><code>{name}</code> — {kind} / {scope}</summary>',
                '', description, '', f'**POST** {alias}', '',
                f'**Reservation:** `{reservation}`. **Operation version:** 1.', '',
            ])
            if fields == '`{}`':
                output.extend(['No arguments. Send `{}`.', ''])
            else:
                output.extend(['| Argument | Type | Required |', '| --- | --- | --- |'])
                requirements = []
                for field in fields.split(', '):
                    if field == 'one of `hosts` / `cluster` required':
                        requirements.append('Provide either `hosts` or `cluster`; this operation does not fall back to the default cluster.')
                        continue
                    match = re.fullmatch(r'`([a-z][a-z0-9_]*)(!?): ([a-z\[\]/]+)`', field)
                    if not match:
                        raise ValueError(f'Unexpected field for {name}: {field}')
                    key, required, datatype = match.groups()
                    if key in OMITTED_ARGUMENTS.get(name, ()):
                        continue
                    output.append(f'| `{key}` | `{datatype}` | {"Yes" if required else "No"} |')
                output.append('')
                for requirement in requirements:
                    output.extend([requirement, ''])
            output.extend(['</details>', ''])
        elif not line.startswith('|'):
            if line == '## Bundled Kubernetes plugin':
                output.extend([
                    '## Bundled Kubernetes plugin (experimental)', '',
                    'These Kubernetes operations are experimental. Their schemas and behavior may change; pin compatible versions when building clients.',
                ])
                continue
            output.append(line.replace(
                'Requires the loaded `k8s` integration and `integration.k8s`.',
                'Requires the loaded `k8s` plugin and the requested capability flags.'))
    if not names:
        raise ValueError('No operations found in the reference')
    if sections != BUNDLED_SECTIONS:
        raise ValueError(f'Missing bundled sections: {BUNDLED_SECTIONS - sections}')
    if descriptions.keys() - names:
        raise ValueError(f'Stale operation descriptions: {sorted(descriptions.keys() - names)}')
    output.append(END)
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(output)), len(names)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True, help="Core docs/DAEMON_API.md")
    parser.add_argument('--check', action='store_true', help='Check without writing')
    args = parser.parse_args()
    generated, count = render(args.reference.read_text(), descriptions_for(args.reference))
    original = PAGE.read_text()
    before, remainder = original.split(BEGIN, 1)
    _, after = remainder.split(END, 1)
    updated = before + generated + after
    if args.check:
        if original != updated:
            raise SystemExit('Daemon operation entries are stale; rerun without --check')
        print(f'Daemon API entries match all {count} bundled operations in {args.reference}')
    else:
        PAGE.write_text(updated)
        print(f'Synced {count} operation entries to {PAGE}')


if __name__ == '__main__':
    main()
