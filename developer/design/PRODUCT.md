# Product

## Register

product

## Users

Hemeria system and software engineers on spacecraft and flight software
programmes (ISIS, REVALTO and others). They log in through Keycloak and work
in one of four roles per project:

- Authors write and trace ECSS requirements (SRS, ADD, ICD) for hours a day.
- Reviewers comment on the documents they are named on.
- Readers consult the documents.
- Administrators manage the projects and their members.

French is the primary language. English is a peer translation and stays the
language of the tests and of the upstream project.

## Product purpose

StrictDoc is the requirements and documentation tool of the engineering
department. It works on `.sdoc` files: documents, sections, requirements with
UIDs, traceability between requirements and to source code, comments and
reviews, Word import and export, and several projects in one server.

Success: an engineer finds, edits and traces a requirement in seconds, and
the audit log records every change.

## Brand personality

The company design system applies as it is in THOR (see `DESIGN.md`). The
tricolor stripe, IBM Plex Sans headings, monospace identifiers, reticle frames and
status pills are what Hemeria looks like. Within that voice the tool stays
modern, usable and predictable. Confidence without bluster.

## Anti-references

- Glassmorphism and frosted decoration. No blurred panels and no gradient
  cards. StrictDoc is an instrument, not a marketing site.
- Gradient buttons. Solid fills only; emphasis comes from weight and
  placement.
- Soft pastel SaaS: rounded everything, Notion-style pastel cards, friendly
  empty states.
- Apologetic or chatty copy. Errors and labels state facts. No "Sorry", no
  "Oops", no exclamation marks.

## Design principles

1. Hemeria is the voice. The tricolor stripe, IBM Plex Sans eyebrows, monospace
   identifiers and reticle frames are the company identity. New screens
   extend it; no screen looks off-brand because that was easier.
2. Density that stays scannable. Engineers read long specifications and
   long tables. Requirement UIDs in monospace, weight contrast for
   hierarchy, spacing that groups related content.
3. Terse technical wording. "Exigence introuvable. Vérifiez l'UID." and not
   a sentence of apology.
4. Identifiers and keyboard first. UIDs, MIDs, document paths, relation types
   and dates are the shared language of the users. Frequent actions are one
   keystroke away.
5. Modern means crisp, fast and accessible: predictable interactions,
   immediate feedback, AA contrast, light mode. It does not mean rounded
   corners or decorative motion.

## Accessibility and inclusion

- WCAG AA contrast at least: 4.5:1 for text, 3:1 for interface components.
- Light mode only. StrictDoc has no theme switch, so the THOR dark themes are
  not carried over.
- Every text works in French first and reads naturally to a native speaker.
