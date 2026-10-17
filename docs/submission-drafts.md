# Submission drafts

Drafts only. Nothing here has been submitted. The rules below were read from each target's README, CONTRIBUTING file and templates on 2026-10-17. Check them again before you submit, because lists change their rules often.

On that date the repository had 1 star, and it was created on 2026-10-14.

## Before any submission

1. Merge the plugin packaging into `main`. Until then, `/plugin marketplace add 3351666087/scan-to-vector-skill` and the `curl … | bash` one-liner do not work for anyone else.
2. Run `claude plugin validate --strict .` in the repository and check that it prints `✔ Validation passed`.
3. From a clean machine or account, run the two install commands in the README and start a session to confirm the skill is listed.
4. Optional: tag the release (`git tag v0.1.0`) so reviewers can see which version they looked at. Raise `version` in `.claude-plugin/plugin.json` with every release. Users who already installed the plugin only get an update when that number changes.

## Where each submission goes

| Target | How it takes submissions | Gate | Earliest realistic date |
| --- | --- | --- | --- |
| Anthropic's plugin directory (the `claude-plugins-official` marketplace) | Developer portal at [claude.ai/directory/manage](https://claude.ai/directory/manage), which needs a paid claude.ai plan. The repository's README sends third-party plugins to the [submission form](https://clau.de/plugin-directory-submission). Pull requests are not the intake route. | Anthropic review | Once `main` has the plugin |
| [VoltAgent/awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills) (~36k★) | PR adding one line | "Real community usage". Brand-new skills are declined, with no number given | After some adoption |
| [heilcheng/awesome-agent-skills](https://github.com/heilcheng/awesome-agent-skills) (~6k★) | PR adding one line | 20 or more stars **and** older than 14 days. A bot checks every PR | 2026-10-28, and only with 20 stars |
| [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) (~56k★) | Web issue form only, filled in by a person. PRs and `gh` submissions are refused | Older than 14 days with commits after the first day, **or** 100 stars | 2026-10-28 |
| [travisvn/awesome-claude-skills](https://github.com/travisvn/awesome-claude-skills) (~15k★) | PR | 10 stars or it is closed automatically. The PR must not be generated or submitted with AI help | Once it has 10 stars, written by you |
| [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) (~77k★) | PR that copies the skill folder into their repository and adds a README line | Maintainer review | Any time, but see the note in section 6 |

---

## 1. Anthropic's plugin directory

The task asked for a pull request to `anthropics/claude-plugins-official`, but that repository does not take third-party plugins through PRs. Its README sends them to the submission form, and the Claude Code docs ([Submit to Anthropic's directory](https://code.claude.com/docs/en/plugins/publish#submit-to-anthropics-directory)) send them to the developer portal. The most recent outside PRs to that repository were closed without merging. Use the text below in the portal or form. A PR version comes after it in case you want one anyway.

Before submitting, work through the [pre-submission checklist](https://claude.com/docs/plugins/pre-submission-checklist) and the [component support table](https://claude.com/docs/plugins/platform-support#compare-component-support-by-app). This plugin ships only a skill, plus a Python helper the skill runs. On claude.ai and in Cowork, the helper needs an environment where PyMuPDF and Pillow can be installed.

The directory also reads optional listing fields from `plugin.json`: `icon`, `documentationUrl`, `supportUrl`, `privacyPolicyUrl` and `termsOfServiceUrl`. They are not set yet. Claude Code before v2.1.281 reports them as unknown fields under `--strict`, and the CLI on this machine was v2.1.220. If the portal asks for them, these values would fit:

```json
"documentationUrl": "https://github.com/3351666087/scan-to-vector-skill#readme",
"supportUrl": "https://github.com/3351666087/scan-to-vector-skill/issues"
```

### Portal / form fields

- **Plugin name:** `scan-to-vector`
- **Display name:** Scan to Vector
- **Repository:** https://github.com/3351666087/scan-to-vector-skill
- **Category:** productivity
- **Keywords:** pdf, scan, ocr, vector, typesetting, digitization, charts
- **License:** MIT. The demo scans are public domain, and the demo font uses the SIL Open Font License.
- **Short description:** Rebuild scanned books, manuals, worksheets and charts as searchable, newly typeset PDFs with vector diagrams, checked page by page against the scan.
- **Long description:**

  > scan-to-vector is a skill for rebuilding scanned documents, rather than adding an invisible OCR layer on top of them. Claude inventories every source page in a page ledger, reconciles OCR against the image, retypesets the text as real searchable text, and redraws diagrams and charts as vector paths from measured geometry or recovered data. Photographs and engravings stay as labelled raster crops. Before delivery it reviews the rebuild against the scan using contact sheets, close inspection and a bundled PyMuPDF audit script, and it writes a delivery note saying what is vector, what stays raster and what is still unresolved.
  >
  > The repository has two worked examples from public-domain scans, with build scripts: a page of Byrne's 1847 *Euclid* (text, colour diagrams, an engraved initial), and Playfair's 1786 trade chart, digitised into 81 yearly values per series and redrawn from that data.

- **What it needs:** Python 3.10+ with PyMuPDF and Pillow for the bundled helper. OCR and typesetting tools are whatever the user's project already has.
- **What it does not do:** It has no MCP servers, hooks or network calls, and it collects no data. The skill tells Claude not to delete source files or publish results unless the user asks.
- **How to try it:** Install the plugin, then ask: "Use scan-to-vector to rebuild `demo/byrne-euclid-I-11/source/scan.jpg` as a searchable PDF and check it against the scan."

### If you open a PR anyway

**Title:** `Add scan-to-vector to external_plugins`

**Body:**

```markdown
Adds **scan-to-vector** (https://github.com/3351666087/scan-to-vector-skill), a skill-only plugin that rebuilds scanned pages as searchable, newly typeset PDFs with vector diagrams, checked page by page against the scan.

- Components: one skill (`skills/scan-to-vector/SKILL.md`) and a Python helper it calls (`scripts/pdf_tool.py`, PyMuPDF + Pillow). No MCP servers, hooks or network access.
- `claude plugin validate --strict .` passes in the source repository, which is also a single-plugin marketplace (`/plugin marketplace add 3351666087/scan-to-vector-skill`).
- License: MIT.
- Worked examples with build scripts: `demo/byrne-euclid-I-11` and `demo/playfair-1786`.

I'm the author. This PR description was drafted with Claude Code.
```

**Marketplace entry:** put in the commit SHA you want reviewed.

```json
{
  "name": "scan-to-vector",
  "displayName": "Scan to Vector",
  "description": "Rebuild scanned books, manuals, worksheets and charts as searchable, newly typeset PDFs with vector diagrams, checked page by page against the scan.",
  "author": { "name": "Null3351", "url": "https://github.com/3351666087" },
  "category": "productivity",
  "source": {
    "source": "url",
    "url": "https://github.com/3351666087/scan-to-vector-skill.git",
    "sha": "<40-character commit sha>"
  },
  "homepage": "https://github.com/3351666087/scan-to-vector-skill"
}
```

---

## 2. VoltAgent/awesome-agent-skills

Their rules: add one line to the end of the matching subcategory under "Community Skills", keep the description to 10 words or fewer, and title the PR `Add skill: author/skill-name`. They decline skills that are brand new and have no users yet.

**Subcategory:** Productivity and Collaboration. Other document-processing skills such as `PSPDFKit-labs/nutrient-agent-skill` are listed there.

**PR title:** `Add skill: 3351666087/scan-to-vector`

**Line:**

```markdown
- **[3351666087/scan-to-vector](https://github.com/3351666087/scan-to-vector-skill)** - Rebuild scanned pages as searchable PDFs with vector diagrams
```

**Body:**

```markdown
Adds 3351666087/scan-to-vector to Community Skills > Productivity and Collaboration.

It rebuilds scanned books, manuals, worksheets and charts as newly typeset, searchable PDFs, redraws diagrams and charts as vectors, and checks each page against the scan. The repository includes SKILL.md, a PDF audit helper with tests, and two public-domain worked examples.
```

---

## 3. heilcheng/awesome-agent-skills

Their rules (`AGENTS.md`): the repository needs 20 or more stars and must be older than 14 days. Edit only `README.md`, adding one line at the end of an existing category under `## Community Skills`, inside its `<details>` block. The description must be under 100 characters with no marketing language. A bot checks every PR. They also ask agents to disclose that they drafted the PR.

**Category:** Productivity and Collaboration

**PR title:** `Add 3351666087/scan-to-vector-skill to Productivity and Collaboration`

**Line** (86 characters of description):

```markdown
- [3351666087/scan-to-vector-skill](https://github.com/3351666087/scan-to-vector-skill) - Rebuild scanned pages as searchable, typeset PDFs with vector diagrams and page checks
```

**Body** (their template; tick each box yourself only once it is true):

```markdown
**Skill repository:** https://github.com/3351666087/scan-to-vector-skill

**Category:** Productivity and Collaboration

### Checklist

- [ ] The link is a public GitHub repository (or folder) that contains a `SKILL.md` with `name` and `description` frontmatter
- [ ] The repository has at least 20 stars and is older than 14 days
- [ ] I searched `README.md` and this repository is not already listed or in another open PR
- [ ] I only edited `README.md`, adding at most 5 lines to the end of an existing category
- [ ] Each line uses the format `- [owner/repo](https://github.com/...) - Description under 100 characters`
- [ ] This is not a directory, marketplace, badge, or promotional link

### Disclosure

- [ ] I am the author or a maintainer of this skill
- [ ] This PR was written by an AI agent (name it: Claude Code)
```

Tick the last box if you submit this text as drafted.

---

## 4. hesreallyhim/awesome-claude-code

Submissions go only through the [web issue form](https://github.com/hesreallyhim/awesome-claude-code/issues/new?template=recommend-resource.yml), and a person has to fill it in. Submitting a PR or using `gh` can get you temporarily restricted. Submit one resource at a time. Write the description as a plain statement of what the tool does: one line, not addressed to the reader, no emojis. The checklist in the form contains a box that must be left unticked, so read each box rather than ticking them all.

- **Display Name:** scan-to-vector
- **Category:** Skills
- **Link:** https://github.com/3351666087/scan-to-vector-skill
- **Author Name:** Null3351
- **Author Link:** https://github.com/3351666087
- **Description:** A Claude Code skill and plugin that rebuilds scanned books, manuals, worksheets and charts as searchable, newly typeset PDFs, redrawing diagrams and charts as vectors and checking every page against the scan with a page ledger and a PDF audit.

---

## 5. travisvn/awesome-claude-skills

Their CONTRIBUTING file says a PR for a repository under 10 stars is closed automatically, and that PRs must not be "explicitly generated / submitted with AI-assistance". So there is deliberately no drafted text here. If you submit, write the PR yourself. They ask for:

- the skill's name and repository link
- a 1–2 sentence description
- prerequisites: Python 3.10+, PyMuPDF, Pillow
- the license: MIT

---

## 6. ComposioHQ/awesome-claude-skills

This list copies the skill into its own repository (`scan-to-vector/SKILL.md`) and adds a README line. The copy there would not receive your later changes, so a link-only list may serve you better. If you do submit:

**Category:** Productivity & Organization

**PR title:** `Add Scan to Vector skill`

**Line** (alphabetical within the category):

```markdown
- [Scan to Vector](./scan-to-vector/) - Rebuilds scanned pages as searchable, newly typeset PDFs with vector diagrams, checked page by page against the scan.
```

**Body:**

```markdown
Adds Scan to Vector, a skill that rebuilds scanned books, manuals, worksheets and charts as newly typeset, searchable PDFs instead of adding a hidden OCR layer.

- Problem it solves: scans of worksheets, manuals and old books that need to be printed, searched or reused, where an OCR layer leaves diagrams as pixels and the page as a photo.
- Who uses it: anyone digitising printed teaching material, manuals or historical documents, and anyone recovering the data behind a scanned chart.
- Example: "Use scan-to-vector to rebuild worksheet.pdf as a clean, searchable PDF. Keep every question and answer blank; redraw the diagrams as vectors."
- Upstream and worked examples: https://github.com/3351666087/scan-to-vector-skill
```
