#!/usr/bin/env python3
"""Check local href targets/anchors and sidebar reachability in built HTML."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids, self.links = set(), []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])


def main():
    pages = {path.relative_to(DIST).as_posix(): Page(path.read_text()) for path in DIST.rglob('*.html')}
    if not pages:
        raise SystemExit('No built HTML. Run npm run build first.')
    errors, links = set(), 0
    for source, page in pages.items():
        route = '/' + source.removesuffix('index.html')
        for href in page.links:
            parsed = urlsplit(urljoin('https://sparkrun.dev' + route, href))
            if parsed.netloc != 'sparkrun.dev' or parsed.scheme not in {'http', 'https'}:
                continue
            target = unquote(parsed.path).lstrip('/')
            file = DIST / target
            if file.is_dir() or not file.suffix:
                target = target.rstrip('/') + '/index.html' if target else 'index.html'
                file = DIST / target
            links += 1
            if not file.is_file():
                errors.add(f'{source}: missing target {href}')
            elif parsed.fragment and target in pages and unquote(parsed.fragment) not in pages[target].ids:
                errors.add(f'{source}: missing anchor {href}')
    slugs = re.findall(r"slug: '([^']+)'", (ROOT/'astro.config.mjs').read_text())
    expected = {p.relative_to(ROOT/'src/content/docs').with_suffix('').as_posix() for p in (ROOT/'src/content/docs').rglob('*.mdx')} - {'index'}
    for slug in expected - set(slugs):
        errors.add(f'Documentation page missing from sidebar: {slug}')
    for slug in slugs:
        if slug+'/index.html' not in pages:
            errors.add(f'Sidebar route missing from build: {slug}')
    if errors:
        print('\n'.join(sorted(errors)), file=sys.stderr)
        return 1
    print(f'Checked {links} internal links/anchors across {len(pages)} HTML pages and {len(slugs)} sidebar entries.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
