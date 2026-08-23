# Security policy

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Open a private security advisory through the repository's *Security* tab, or contact the
maintainers directly. Include:

- what the issue is and what it lets an attacker do
- steps to reproduce, ideally with a deck or web page that demonstrates it
- the DeckScope version, your OS and Python version

You can expect an acknowledgement within a few days and an assessment shortly after. If
the report is valid we'll agree a disclosure timeline with you and credit you in the
release notes unless you'd rather we didn't.

## What counts

**In scope**

- A **prompt-injection bypass** — a technique that gets instructions past the screening
  layer and into a model. This is the most valuable class of report for this project.
- Content that escapes the trust-boundary fence.
- Leaking API keys or secrets into reports, logs, or the config file.
- Code execution triggered by a crafted deck or a crafted search result.
- Path traversal or arbitrary file writes through deck paths or output settings.
- The local app server being reachable from outside `127.0.0.1`.

**Out of scope**

- The AI producing a wrong or poor analysis. That's a quality issue — open a normal issue.
- Vulnerabilities in an AI provider's own service.
- A deck being *misleading* rather than *injecting*. Cherry-picked comparisons and
  truncated axes are the claim audit's job, not the security screen's.
- Image-borne injection. Text rendered inside a picture is not extracted and therefore not
  scanned. This is a documented limitation, not a bug — see
  [docs/SECURITY.md](docs/SECURITY.md).

## Known limits

The security layer is heuristic defence in depth, not a guarantee. It catches the known
families of injection well; a novel technique may pass. The trust-boundary instructions in
every system prompt are the backstop behind it, and no backstop is perfect.

Full threat model, every detection, and the limits in
**[docs/SECURITY.md](docs/SECURITY.md)**.

## Supported versions

The latest release. This is a young project; please upgrade before reporting.
