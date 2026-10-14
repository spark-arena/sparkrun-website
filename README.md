# sparkrun-website

Source for [sparkrun.dev](https://sparkrun.dev) — the documentation site for
[sparkrun](https://github.com/spark-arena/sparkrun), a CLI for launching, managing, and stopping
LLM inference workloads on NVIDIA DGX Spark systems.

Built with [Astro](https://astro.build) and [Starlight](https://starlight.astro.build), deployed to
Cloudflare Workers.

## Local development

Requires Node.js 22.

```sh
npm install
npm run dev      # dev server at localhost:4324
npm run build    # production build into dist/
npm run preview  # serve the production build locally
npm run check    # type-check and validate content collections
```

## Repository layout

| Path | Contents |
| --- | --- |
| `src/content/docs/` | Documentation pages (`.mdx`) — the bulk of the site |
| `src/components/landing/` | Landing-page React components |
| `src/components/overrides/` | Starlight component overrides |
| `src/styles/` | Global and landing-page CSS |
| `astro.config.mjs` | Site config, sidebar structure, and navigation |
| `public/` | Static assets served as-is |

## Contributing

Documentation improvements are welcome — corrections, clarifications, and new guides alike.

1. Open a pull request against `main`.
2. CI checks types, pinned Python/CLI contracts, the production build, and internal links on every pull request.
3. A maintainer reviews and merges. `main` is protected, so changes reach the live site only after
   review.

For sparkrun itself — the CLI, runtimes, and recipes — file issues and pull requests against
[spark-arena/sparkrun](https://github.com/spark-arena/sparkrun) instead.

Questions are welcome in [Discord](https://discord.gg/GH5kRgv6ZD).

## Deployment

Merging to `main` triggers a build and deploy to Cloudflare Workers via
`.github/workflows/deploy.yml`. Pull requests are built as a check but never deployed.

## License

This repository is dual-licensed:

- **Site code** — Astro and React components, styles, and configuration — is licensed under the
  [Apache License 2.0](LICENSE).
- **Documentation prose** under `src/content/docs/` is licensed under
  [CC BY 4.0](LICENSE-docs). Reuse, translate, and excerpt it freely with attribution.

Code samples embedded in the documentation — recipe YAML, shell commands, configuration snippets —
are Apache-2.0 like the rest of sparkrun, not CC BY. Copying a recipe out of the docs into your own
project carries no attribution obligation.

Copyright 2026 Scitrera LLC.

## Documentation contract checks

The website is prepared for the 0.4.0 release. Its verification reference is pinned
in `scripts/docs-contracts.json` to
`cf5e16b9a44079288fd0a712e240d250a3f69b07`. Update the verification pin and source
links at the release cut. Stable availability and
portable-daemon platform checks are release gates, not inferred from version text.
The reference includes domain-based daemon operations, plugin namespaces, shared
workload management, gateway discovery, model-cache usage/retention and optional
LRU cleanup, plugin loading controls and lifecycle plans, shared diagnostic capture
and plugin reporters, and reusable Docker/native Kubernetes log readers.
`gateway.sparkroute` remains off by default on every channel. The Daemon API reference covers core and bundled integrations;
its operation inventory excludes external plugins.

Website-only contributors can obtain the reference package without configuring a
cluster (Python 3.12+):

```sh
python3.12 -m venv .venv-docs
.venv-docs/bin/python -m pip install 'sparkrun @ git+https://github.com/spark-arena/sparkrun.git@cf5e16b9a44079288fd0a712e240d250a3f69b07'
.venv-docs/bin/python scripts/check-docs-contracts.py
npm run check
npm run build
npm run check:links
```

For an existing checkout at that commit, run its `.venv/bin/python` with
`scripts/check-docs-contracts.py --source /path/to/sparkrun`. Verification creates
temporary config/cache roots, disables telemetry/external sources, and rejects
network/child-process activity during initialization and validation. The synthetic
installed integrations exercise module-targeted discovery and the documented
plugin modules: lazy CLI loading, command help and callbacks with a stubbed host
probe, registry overlays/user overrides, recipe round trips, benchmark option
decoding/completion, setup checks, static manifests, idempotent lifecycle plans,
and diagnostic reporter registration, disabled behavior, nested capture, redaction,
and capture closure. Runtime checks cover command generation,
overrides, quoting, revision binding, templates, and unsupported parallelism without
launching a workload. Diagnostic fixtures write only temporary local bundles,
without host probes or log readers.

Runtime flag tables are generated from the same pinned source's static maps,
without importing Sparkrun. To update or verify them:

```sh
python3 scripts/sync-runtime-flags.py --source /path/to/pinned/sparkrun
python3 scripts/sync-runtime-flags.py --source /path/to/pinned/sparkrun --check
```

Review the surrounding prose for flags with special handling, placement-managed
arguments, aliases, and engine-version requirements when changing the source pin.
CI repeats the checks for stable/beta/alpha with advanced visibility both off and on
(`--channel stable --advanced 0`, for example). Python fences are parsed;
public imports and option constructors are checked without executing workloads.
CLI fences use Click parsers without invoking command/parameter callbacks. The
focused plugin fixture invokes its command only with the host probe replaced. Explicit
`[options]` usage lines are illustrative, not executable examples. Any exceptional
snippet must have a focused, explained entry in the contract manifest.

`check-built-links.py` verifies local targets, anchors, and sidebar coverage in
`dist/`. External source/community links and visual review are separate checks;
network availability is not part of the deterministic offline checks. Review the
homepage, a regular doc page, and wide CLI/code pages at desktop/mobile sizes in
both themes. The landing terminal recording is labeled as an earlier-release demo.
No verification command launches inference, rotates SSH keys, grants plugin trust,
exposes a daemon, or deploys the site. Deployment remains limited to pushes to main.

The page-by-page 0.4.0 review and local verification record is in
[`scripts/docs-review-0.4.json`](scripts/docs-review-0.4.json).

The expandable operation inventory on **Daemon API** is copied from core's generated
`docs/DAEMON_API.md` with a Markdown-only tool (no imports or handler execution).
It includes only the core and bundled Kubernetes sections; external plugin sections
are excluded during every sync. Hidden benchmark compatibility arguments are
omitted from the website tables by the sync tool's explicit omission list:

```sh
python3 scripts/sync-daemon-api.py --reference /path/to/sparkrun/docs/DAEMON_API.md
python3 scripts/sync-daemon-api.py --reference /path/to/sparkrun/docs/DAEMON_API.md --check
```

After changing the reference pin, regenerate these entries and review route,
identity, result, extension, and operational prose separately. Keep this reference
limited to bundled functionality when updating both the inventory and prose.
