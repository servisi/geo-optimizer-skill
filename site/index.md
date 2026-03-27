---
layout: default
title: Documentation
description: "Complete documentation for GEO Optimizer — the open-source toolkit to make websites visible to AI search engines like ChatGPT, Perplexity, Claude, and Gemini."
---

# GEO Optimizer Documentation

Optimize any website to be cited by ChatGPT, Perplexity, Claude, and Gemini.

---

## Quick Start

```bash
pip install geo-optimizer-skill
geo audit --url https://yoursite.com
```

Score 0-100 in 30 seconds. Then fix everything:

```bash
geo fix --url https://yoursite.com --apply
```

---

## Documentation

| Page | Description |
|------|-------------|
| [Getting Started](getting-started/) | Install and run your first audit |
| [GEO Audit](geo-audit/) | Full audit command — flags, formats, scoring |
| [GEO Fix](geo-fix/) | Auto-generate missing robots.txt, llms.txt, schema, meta |
| [llms.txt Generator](llms-txt/) | Generate `/llms.txt` from your sitemap |
| [Schema Injector](schema-injector/) | Generate and inject JSON-LD structured data |
| [MCP Server](mcp-server/) | Use from Claude, Cursor, Windsurf |
| [CI/CD Integration](ci-cd/) | GitHub Actions, GitLab CI, Jenkins |
| [AI Bots Reference](ai-bots-reference/) | All 22 AI crawlers with 3-tier classification |
| [42 GEO Methods](geo-methods/) | Research-backed citability methods with measured impact |
| [Scoring Rubric](scoring-rubric/) | How the 0-100 score is calculated across 7 categories |
| [AI Context Files](ai-context/) | Use as context in Claude, ChatGPT, Cursor, Windsurf |
| [Troubleshooting](troubleshooting/) | Common issues and solutions |

---

## Links

- [Live Demo](https://geo-optimizer-web.onrender.com) — Try the audit online
- [GitHub Repository](https://github.com/Auriti-Labs/geo-optimizer-skill)
- [PyPI Package](https://pypi.org/project/geo-optimizer-skill/)
- [Changelog](https://github.com/Auriti-Labs/geo-optimizer-skill/blob/main/CHANGELOG.md)
