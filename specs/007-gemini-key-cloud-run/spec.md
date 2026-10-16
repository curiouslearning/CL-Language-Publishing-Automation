# Feature Specification: Gemini Key for the Hosted Generator

**Feature Branch**: `007-gemini-key-cloud-run`

**Created**: 2026-10-15

**Status**: Draft

**Input**: User description: "Add google gemini api enable it and add it to secret manager access that in the project make sure everything is set for google run deployment"

## Context

The generator page is deployed to Cloud Run in the `ftm-language-generator` project (spec 005, README "Deploy to Cloud Run"). The optional AI language check (spec 003) already supports Gemini, but the hosted page has no AI key attached, because the provider hadn't been decided. As a result, turning on the AI check on the hosted page always reports the check as unavailable / not configured.

This feature records the decision: **Gemini is the provider for the hosted page**. The Gemini API is enabled in the `ftm-language-generator` project, a key belonging to that project is stored in Secret Manager, and only the generator's runtime identity can read it. Local testing keeps using the developer's own key in `.env`, unchanged.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - AI check works on the hosted page (Priority: P1)

A content team member opens the hosted generator, signs in with their curiouslearning.org account, turns on "AI language check" and generates a language. After the pipeline finishes, the AI review runs and its findings (or "no issues") appear in the run summary, exactly as they do when the page runs locally.

**Why this priority**: This is the whole point of the feature. Today the toggle exists on the hosted page but can never produce a result.

**Independent Test**: Deploy, open the hosted page, generate a known language (e.g. Hindi) with the AI check on, and confirm the AI section shows a real review with the answering model and token counts (with "Show tokens used" on), not "unavailable".

**Acceptance Scenarios**:

1. **Given** the deployed page with the key attached, **When** a signed-in user generates a language with the AI check on, **Then** the AI section shows the review produced by the configured Gemini model.
2. **Given** the same language was reviewed before on the same running instance with unchanged content, **When** it is generated again, **Then** the earlier result is reused and no new request is made (existing cache behaviour).
3. **Given** the AI check is off, **When** a language is generated, **Then** no request is sent to Gemini.

---

### User Story 2 - The key is kept secret and owned by the project (Priority: P1)

A project maintainer can see that the Gemini key used in production belongs to the `ftm-language-generator` project, is stored only in Secret Manager, and can be read only by the generator's runtime identity (and project admins). It never appears in the repository, the container image, the build upload, the deploy settings, or the page.

**Why this priority**: Constitution principle V (no secrets in the repository). A leaked key can be abused and billed to the project.

**Independent Test**: Inspect the repository, the built image and the Cloud Run service configuration: the key value appears in none of them; the service refers to the secret only by name. Check the secret's access list: only the runtime identity has read access besides admins.

**Acceptance Scenarios**:

1. **Given** the deployed service, **When** its configuration is viewed, **Then** it shows a reference to the Gemini secret, never the key value.
2. **Given** the key, **When** it is used for anything other than the Gemini API (e.g. another Google API), **Then** it is refused, because the key is restricted to the Gemini API.
3. **Given** a person or identity other than the runtime identity and project admins, **When** it tries to read the secret, **Then** access is denied.

---

### User Story 3 - One documented setup and deploy (Priority: P2)

A maintainer following the README's "Deploy to Cloud Run" section can enable the Gemini API, create and restrict the key, store it, grant access and deploy, without having to work anything out on their own. Rotating the key later is a documented step that needs no code change.

**Why this priority**: The setup is done rarely and by different people; undocumented steps get lost.

**Independent Test**: A maintainer who didn't build the feature follows only the README and ends with a working hosted AI check.

**Acceptance Scenarios**:

1. **Given** the README, **When** a maintainer follows the one-time setup and deploy steps, **Then** the hosted AI check works with no extra steps.
2. **Given** a new key version is added to the secret, **When** the service is redeployed (or a new instance starts), **Then** the new key is used and no file in the repository changes.

---

### Edge Cases

- **Secret missing or not readable** (e.g. setup skipped, permission not granted): the deploy should fail clearly rather than produce a page whose AI check silently never works; if a running page ends up without a key, the AI check reports "not configured / unavailable" with the reason, never "no issues", and the language package is still generated (AI check stays advisory).
- **Key revoked, wrong or restricted to the wrong API**: the AI check reports "Gemini API key rejected"; the run still completes.
- **Free-tier / quota limit reached**: reported as a rate limit, as today; the run still completes.
- **Gemini API not enabled in the project**: reported as unavailable with Google's reason; setup docs list enabling the API as the first step.
- **Provider later switched to Claude in `config.json`**: the hosted page then has no Claude key and reports "not configured"; it never silently uses Gemini instead (existing rule). Switching the hosted provider is out of scope here.
- **Local runs**: a developer's `.env` key still works locally and takes no part in the deploy; the deploy never reads `.env`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Gemini API MUST be enabled in the `ftm-language-generator` project.
- **FR-002**: A Gemini API key MUST be created in the `ftm-language-generator` project and restricted so that it can be used only with the Gemini API.
- **FR-003**: The key MUST be stored in Secret Manager in the `ftm-language-generator` project as a single named secret, and nowhere else (not in the repository, image, build upload, deploy file, or service environment as a literal value).
- **FR-004**: Only the generator's runtime identity (`ftm-generator-run`) MUST be granted read access to that secret; the build identity MUST NOT need to read it.
- **FR-005**: The Cloud Run deploy MUST attach the secret to the service so that the AI check finds the key in the same place it already looks for it, with no change to how the AI check reads keys locally.
- **FR-006**: The hosted page MUST use Gemini as the AI provider, with the model and fallback models already chosen in `config.json`.
- **FR-007**: The deploy MUST always pick up the current version of the secret, so rotating the key requires only adding a new secret version and redeploying.
- **FR-008**: If the key is missing, rejected or rate-limited, the AI check MUST report itself unavailable with the reason and the pipeline run MUST still complete as before (spec 003 behaviour unchanged).
- **FR-009**: The README "Deploy to Cloud Run" section MUST document, as copy-paste steps: enabling the API, creating and restricting the key, storing it as a secret, granting the runtime identity access, deploying, and rotating the key.
- **FR-010**: `CLAUDE.md`, the README "Secrets" section and the deploy file comments MUST be updated so they no longer say "no AI key is attached / provider not decided", and so they say which key is used where (project key on Cloud Run; personal key in `.env` locally).
- **FR-011**: The `.dockerignore` / `.gcloudignore` exclusions of `.env` and other secret files MUST remain in force.

### Key Entities

- **Gemini API key (production)**: a key owned by the `ftm-language-generator` project, restricted to the Gemini API, used only by the hosted page.
- **Gemini key secret**: the Secret Manager entry holding that key; versioned, readable only by the runtime identity.
- **Runtime identity** (`ftm-generator-run`): the identity the hosted page runs as; already reads the web OAuth client secret.
- **Local developer key**: the developer's personal Gemini key in `.env`; used only for local runs, unaffected by this feature.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the hosted page, 100% of runs with the AI check on and a valid key produce a real AI review (findings or "no issues"), not "not configured".
- **SC-002**: The key value appears in 0 tracked files, 0 image layers and 0 visible service settings.
- **SC-003**: Exactly one non-admin identity (the runtime identity) can read the Gemini secret.
- **SC-004**: A maintainer can complete the one-time setup and first deploy from the README alone in under 15 minutes.
- **SC-005**: Rotating the key takes no repository change and at most two documented steps (add a version, redeploy).
- **SC-006**: When the AI check is unavailable for any reason, 100% of language packages are still generated as before.

## Assumptions

- Gemini (not Claude) is the decided provider for the hosted page; this reverses the CLAUDE.md note that "the project's Gemini key isn't used anywhere".
- The key is a new one created in `ftm-language-generator`, not the developer's personal AI Studio key, so usage and billing belong to the project.
- The `ftm-language-generator` project has billing enabled (Cloud Run requires it), so Gemini usage from this key may be billed at the paid tier rather than the free tier. Usage is small (about 1.5 K input tokens per language) and visible through the existing token display (spec 006).
- Every signed-in curiouslearning.org user of the hosted page may turn on the AI check; no extra permission is added.
- The AI result cache on Cloud Run lives only as long as the instance; losing it only means a repeated request, which is acceptable.
- Running the one-time setup commands needs a project Owner (or equivalent), as for the existing setup.
- Out of scope: switching the hosted provider to Claude, a Claude key secret, the generated-package download (R10), and any change to how the AI check itself reviews content.
