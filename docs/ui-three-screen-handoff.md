# SignalX frontend screen handoff

Implemented on October 7, 2026 from the three supplied PNG references, reusing the existing logo, workspace shell, design tokens, icons, avatars, product selection and inbox. No dependencies, backend schemas or API contracts were added.

## Branch stack and commits

| Feature branch | Base | Feature tip |
| --- | --- | --- |
| `feat/signalx-workspace-overview` | `feat/signalx-product-profile` at `05f28a5` | `0702305` |
| `feat/signalx-import-validation` | Overview at `0702305` | `7f7a2be` |
| `feat/signalx-analysis-progress` | Import validation at `7f7a2be` | Includes both preceding screens |

Auth, branding, Product profile and the lead inbox were already present in the selected base. The UI branches were not assumed to be integrated into main.

Overview commits:

- `0c3447f` — `feat(overview): build workspace summary and shared workflow layout`
- `bcb9ac7` — `feat(overview): add decision feedback and recent run panels`
- `ddf4b43` — `test(overview): verify connected metrics demo navigation and mobile layout`
- `0702305` — `style(overview): align run metadata with reference header hierarchy`

Import validation commits:

- `ea321f4` — `feat(imports): add local CSV preflight and labeled validation fixture`
- `10b9738` — `feat(imports): build validation review and preserve atomic import workflow`
- `7f7a2be` — `test(imports): cover CSV errors replacement retries and responsive review`

Analysis progress commits:

- `c84eb4b` — `feat(analysis): build run progress stages and honest run details`
- `2451339` — `feat(analysis): add arriving results source guards and review navigation`
- `2d57ea2` — `test(analysis): verify polling recovery isolation and responsive status states`
- A separate `docs(ui)` commit records this handoff.

No feature branches were pushed or merged into main. During implementation an external checkout and integration merge changed the shared checkout to main. The first feature commit was transferred to the Overview branch; main was returned to the external merge at `c66d790`. That integration and all unrelated work were preserved. The pre-existing untracked `.vscode/` directory was left untouched.

## Screens and behavior

| Screen | Route | Main files |
| --- | --- | --- |
| Workspace overview | `/dashboard` | `frontend/app/dashboard/page.tsx`, `components/workflow/useOverview.ts` |
| Import validation | `/imports` | `frontend/app/imports/page.tsx`, `imports.css`, `lib/csv-validation.ts` |
| Analysis progress | `/runs/[id]` | `frontend/app/runs/[id]/page.tsx`, `progress.css`, `components/workflow/useRunProgress.ts`, `useRunResults.ts`, `ArrivingResults.tsx` |

Shared files include `app/workflow.css`, `components/workflow/WorkflowUI.tsx`, `components/useWorkspaceProducts.ts` and `lib/run-context.ts`. `WorkspaceShell.tsx` preserves demo mode across navigation and marks Imports active for run routes. The inbox accepts a `lead_id` query parameter so demo review actions open the selected conversation.

- Overview has the four metrics, decision counts, nested review list, feedback sample and recent run table. Connected metrics and review rows come from the latest selected run and the existing APIs.
- Import validation checks file type, 5 MB size, UTF-8 encoding, required and duplicate headers, 500-message limit, quoted/multiline cells, empty values, length limits, duplicate message IDs and timezone-bearing timestamps. Preview and validation do not persist messages. The server importer remains authoritative and rejects invalid imports atomically.
- Start analysis in connected mode imports the validated CSV and requests a run using the backend's configured provider. Failed run creation can be retried without re-uploading the successful import and with the same idempotency key. Changing source inputs invalidates the relevant cached import/key.
- Analysis reads real queued/running/completed/partial/failed/interrupted states. Active runs poll every two seconds; terminal states stop polling. Connection failures pause polling and offer explicit retry. Counts include processed failures, with successful results ready calculated as processed minus failed.
- The arriving-results table shows up to three respond/review opportunities from the existing paginated API. Detail responses must match the analysis, run, message and batch before source text is displayed. Available results and row actions open review screens; they never send messages.
- Cards reflow on small screens. Dense tables scroll horizontally with keyboard focus. Controls have labels and focus indicators, progress has accessible values, and reduced-motion preferences are respected.

## Explicit demo previews

Run the existing frontend with `npm.cmd run dev` from `frontend`, then visit:

- `/dashboard?demo=1`
- `/imports?demo=1`
- `/runs/demo-run-024?demo=1` — static 14/20 snapshot, 70%, 12 ready, 2 failed, 6 remaining

The demo import fixture intentionally has 22 rows, including the two blocking errors at CSV lines 8 and 17. Replacing it with a valid file enables **Preview analysis**, which opens `/runs/demo-import?demo=1` with zero processed messages and the selected file metadata. It does not import the file or create an AI job. Demo state previews are manual snapshots; no timer fabricates progress. Overview run links preserve their completed/partial snapshot state.

## Verification

Commands were run in `frontend` using `npm.cmd` because PowerShell blocks the `npm.ps1` wrapper:

| Command | Result |
| --- | --- |
| `npm.cmd run generate:api` | Passed; generated types unchanged |
| `npm.cmd run typecheck` | Passed on the final implementation |
| `npm.cmd run build` | Passed on the final implementation |
| `npm.cmd test` | All 50 tests passed, including existing auth, products, inbox and evidence suites |
| `npm.cmd test -- tests/overview.spec.ts tests/imports.spec.ts tests/analysis.spec.ts` | All 14 tests passed after the final visual and navigation refinements |
| `git diff --check` | Passed |

The project defines no lint script or lint configuration. A separate lint check could not be run through the existing scripts. Backend tests were not run: this work changes only frontend and handoff documentation, and the backend was not modified. Live backend imports, workers, authentication isolation and paid provider calls were not exercised; connected browser tests intercept API responses.

Headless Microsoft Edge rendered all three screens at desktop 1285×900 and mobile 390×844. Screenshots were visually inspected and mobile document-width checks passed. Inspection caught and corrected a mobile overflow and missing shared warning styles.

Generated screenshots, intentionally left in the existing ignored test-results directory:

- [Overview desktop](../frontend/test-results/overview-desktop.png) / [mobile](../frontend/test-results/overview-mobile.png)
- [Import desktop](../frontend/test-results/imports-desktop.png) / [mobile](../frontend/test-results/imports-mobile.png)
- [Analysis desktop](../frontend/test-results/analysis-desktop.png) / [mobile](../frontend/test-results/analysis-mobile.png)

## Remaining limitations

- This UI base does not expose workspace run history, persisted feedback or measured provider cost through its frontend contract. Connected Overview shows the latest selected run and unavailable feedback values. Only explicit demo mode shows example history/feedback. Mock cost is labeled $0.00; real provider cost is unavailable.
- Run responses do not include community or filename. Metadata from a run started in this browser tab is retained in session storage; otherwise the UI uses the batch identifier and states that community data is unavailable.
- Individual failed-message diagnostics and worker retry operations are not exposed by the current API. The UI shows aggregate failures/run errors, preserves successful results and offers Imports for creating a new run explicitly.
- Product selection uses the existing product list endpoint, limited to its first 100 entries. The preview shows the first three CSV records, not the whole file.
- No deployment or live real-provider readiness is claimed. Online MVP authentication/user isolation, deployment and provider operation remain outside this frontend verification and require the corresponding backend/release work.
