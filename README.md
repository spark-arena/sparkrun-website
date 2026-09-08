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
2. CI builds every pull request; make sure `npm run build` passes locally first.
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
