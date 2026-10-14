#!/usr/bin/env python3
"""Sync bundled operation entries from core's generated DAEMON_API.md inventory.

This reads Markdown only; it never imports plugins or executes operation handlers.
"""
import argparse
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


def render(reference):
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
            names.add(name)
            if not path.startswith('/v1/') or reservation not in {'auto', 'controller', 'none'}:
                raise ValueError(f'Invalid path or reservation for {name}')
            kind, scope = mode.split(' / ')
            if kind not in {'job', 'query'} or scope not in {'read', 'operate', 'admin'}:
                raise ValueError(f'Unexpected execution kind or scope for {name}')
            output.extend([
                f'<details id="{name.replace(".", "-")}">',
                f'<summary><code>{name}</code> — {kind} / {scope}</summary>',
                '', f'**POST** {alias}', '',
                f'**Reservation:** `{reservation}`. **Operation version:** 1.', '',
            ])
            if fields == '`{}`':
                output.extend(['No arguments. Send `{}`.', ''])
            else:
                output.extend(['| Argument | Type | Required |', '| --- | --- | --- |'])
                for field in fields.split(', '):
                    match = re.fullmatch(r'`([a-z][a-z0-9_]*)(!?): ([a-z\[\]/]+)`', field)
                    if not match:
                        raise ValueError(f'Unexpected field for {name}: {field}')
                    key, required, datatype = match.groups()
                    if key in OMITTED_ARGUMENTS.get(name, ()):
                        continue
                    output.append(f'| `{key}` | `{datatype}` | {"Yes" if required else "No"} |')
                output.append('')
            output.extend(['</details>', ''])
        elif not line.startswith('|'):
            output.append(line.replace(
                'Requires the loaded `k8s` integration and `integration.k8s`.',
                'Requires the loaded `k8s` plugin and the requested capability flags.'))
    if not names:
        raise ValueError('No operations found in the reference')
    if sections != BUNDLED_SECTIONS:
        raise ValueError(f'Missing bundled sections: {BUNDLED_SECTIONS - sections}')
    output.append(END)
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(output)), len(names)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True, help="Core docs/DAEMON_API.md")
    parser.add_argument('--check', action='store_true', help='Check without writing')
    args = parser.parse_args()
    generated, count = render(args.reference.read_text())
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
