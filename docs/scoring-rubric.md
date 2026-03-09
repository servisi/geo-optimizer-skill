# GEO Scoring Rubric

This document explains how the GEO Score (0–100) is computed. Based on the Princeton KDD 2024 research paper on Generative Engine Optimization.

---

## Score Bands

| Band | Range | Meaning |
|------|-------|---------|
| **Critical** | 0–40 | AI engines cannot reliably cite you |
| **Foundation** | 41–70 | Partially visible — key signals missing |
| **Good** | 71–90 | Well-optimized, AI-accessible |
| **Excellent** | 91–100 | Fully optimized for GEO |

---

## Categories and Weights (v3.0)

The total score is the sum of all points earned across 5 categories, capped at 100.

### 1. robots.txt — max 20 pts

| Signal | Points | Condition |
|--------|--------|-----------|
| `robots_found` | 5 | File exists and is reachable |
| `robots_citation_ok` | 15 | All 3 citation bots allowed (OAI-SearchBot, ClaudeBot, PerplexityBot) |
| `robots_some_allowed` | 8 | At least some AI bots allowed (partial credit, not cumulative with citation_ok) |

> **Citation bots** are the most critical: OAI-SearchBot, ClaudeBot, PerplexityBot drive real-time citations in ChatGPT, Claude, and Perplexity.

### 2. llms.txt — max 20 pts

| Signal | Points | Condition |
|--------|--------|-----------|
| `llms_found` | 10 | `/llms.txt` exists at site root |
| `llms_h1` | 3 | File has a top-level H1 heading |
| `llms_sections` | 4 | File has H2 content sections |
| `llms_links` | 3 | File contains at least one URL link |

### 3. Schema JSON-LD — max 25 pts

| Signal | Points | Condition |
|--------|--------|-----------|
| `schema_website` | 10 | `WebSite` schema present in page `<head>` |
| `schema_faq` | 10 | `FAQPage` schema present |
| `schema_webapp` | 5 | `WebApplication` schema present |

### 4. Meta Tags — max 20 pts

| Signal | Points | Condition |
|--------|--------|-----------|
| `meta_title` | 5 | `<title>` tag present and non-empty |
| `meta_description` | 8 | `<meta name="description">` present |
| `meta_canonical` | 3 | `<link rel="canonical">` present |
| `meta_og` | 4 | Open Graph tags present (`og:title`, `og:description`) |

### 5. Content Quality — max 15 pts

| Signal | Points | Condition |
|--------|--------|-----------|
| `content_h1` | 4 | Page has at least one `<h1>` heading |
| `content_numbers` | 6 | Page contains statistics (numbers, percentages) |
| `content_links` | 5 | Page contains external citation links |

---

## Total Points Reference

| Category | Max Points |
|----------|-----------|
| robots.txt | 20 |
| llms.txt | 20 |
| Schema JSON-LD | 25 |
| Meta Tags | 20 |
| Content Quality | 15 |
| **Total** | **100** |

---

## Princeton GEO Methods ROI

Research-backed methods ranked by citation rate improvement:

| Method | Citation Boost | Priority |
|--------|---------------|----------|
| Cite Sources | +115% | High |
| Statistics & Numbers | +40% | High |
| Quotations | +40% | High |
| Fluency Optimization | +17% | Medium |
| Easy to Understand | +14% | Medium |
| Keywords | +11% | Low |
| Authoritative Tone | +9% | Low |

Source: *GEO: Generative Engine Optimization*, Aggarwal et al., Princeton KDD 2024.

---

## Changelog

| Version | Change |
|---------|--------|
| v3.0.0 | `schema_website` aumentato a 10 pts, `meta_description` a 8 pts, `content_numbers` a 6 pts |
| v1.5.0 | Pesi originali del documento precedente |
