# Development and publishing through GitHub

The selected flow is:

**Edit → local preview → GitHub branch → pull request checks → merge to main → checked Cloudflare deployment.**

The source repository is [rn5678/aguri-heritage-resources](https://github.com/rn5678/aguri-heritage-resources). The existing `journals-v1` release and its download URLs stay in place. Production remains the existing Cloudflare Pages project `aguri-heritage`, serving https://aguri-heritage.in/.

This implementation uses GitHub Actions to build and upload to Cloudflare. Cloudflare does not pull the repository in this arrangement. It avoids a domain migration and preserves the current production database and contact-service settings. Cloudflare [does not convert Direct Upload projects to Git integration](https://developers.cloudflare.com/pages/get-started/direct-upload/); [Actions-based uploads](https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/) are supported for the current project.

## Activation status

Activated on **2 November 2026**. The [first automated production release](https://github.com/rn5678/aguri-heritage-resources/actions/runs/41470798431) passed all checks and deployed commit `d9050c3c664b2487d71eed6febf791bf3a03cf77` as Cloudflare deployment `687b915c-4360-4d93-bc8e-d4b110928a4c`. Both homepages, contribution/contact configuration, page-view reads and the journal redirect passed live checks. The local editor is now marked for GitHub-only publishing; relaunch any already-running editor to load the new publisher code.

The production environment accepts only `main`. Branch protection requires an up-to-date pull request and the **Build and verify website** check, including for administrators; force pushes and branch deletion are disabled. A second-person approval is not required. Its account-restricted Pages token expires **2 November 2027** and must be renewed in GitHub before that date. Its value is not stored in the source repository. The first complete source import used a non-forced fast-forward push after local validation; later releases use the pull-request flow below.

Setup reference (activation completed; retain for recovery):

1. Enable authenticated Git pushes from this Mac to this repository. Use a repository-scoped credential with source and workflow write access, or an authenticated GitHub CLI session. Never put a token in a Git remote URL or source file.
2. Create a Cloudflare API token with **Account → Cloudflare Pages → Edit**, limited to the account holding `aguri-heritage`. Store it in GitHub's `production` environment as `CLOUDFLARE_API_TOKEN`; restrict that environment to `main`. The account ID is public configuration already fixed in the workflow. Do not copy the Mac's renewable Wrangler login token into GitHub.
3. Push the initial source branch, inspect its passing **Build and verify website** check, and merge it into `main`.
4. Verify that **Publish website** succeeds for the merged commit and that Cloudflare reports that same commit as canonical production. Check both language homepages, a journal download, and the contact/contribution service.
5. Require pull requests and the **Build and verify website** status check for `main`. For a solo-maintained repository, no second-person approval is needed. Do not allow force pushes or deletion of `main`.
6. After the GitHub release is verified, save `{"github_only": true}` in the original authoring folder's `local-editor/github-publishing.json` and relaunch the content editor. Its Save and Preview remain available; **Publish via GitHub** now prepares and submits source through this flow. The marker is local and never committed. The retired direct uploader remains blocked by the marker.

Cloudflare production secrets and the `CONTRIBUTIONS_DB` binding remain configured in Cloudflare. The deployment script reads and fingerprints the configuration before uploading, then checks that it is unchanged afterward. It never writes database records, bindings or secrets. Preview deployments are not enabled by these workflows; local previews and pull-request build checks are the review steps for this initial setup.

## Development and publishing options

### Publish from the local content editor

1. Open `http://127.0.0.1:45873/`, save your edits, and preview both languages. Finish any enabled Bengali updates and required reviews.
2. Open **Publish via GitHub** and prepare the update. The editor builds the saved website, exports only public source into an isolated Git checkout, and runs the same checks as GitHub.
3. Review the changed files and choose **Send to GitHub**. This commits and pushes a new `editor/update-*` branch; it does not change the live website.
4. Open the GitHub review link, choose **Create pull request**, inspect the change and passing checks, then **Merge pull request**. The existing protection rules apply.
5. Return to the editor's publishing panel. It follows that pull request and the publishing workflow for its exact merged commit. **View live website** is offered once publication succeeds.

The shared `hosting/source-repository` checkout must be clean. Each preparation has its own checked copy and receipt under ignored `local-editor/publishing/github/`; the editor never resets unrelated Git changes or force-pushes. A changed saved source invalidates a prepared submission. Source changed independently on GitHub must be reconciled into the authoring folder before exporting. GitHub review uses your existing browser sign-in; the editor needs no GitHub API token and does not use Cloudflare credentials. If sending is interrupted, it checks the recorded branch and commit before trying again. Local editing can continue while a submitted update waits for review or deployment.

### Continue using the existing Mac authoring folder

The current authoring folder links many published assets into `Aguri_Research_Library`. Keep those links and the library intact. `scripts/export_source.py` copies only approved source and public asset files into `hosting/source-repository`, replacing asset links with normal files. It excludes credentials, local databases, editor state, backups, research, generated site output and the two large journal PDFs. A tracked `.source-export.json` records which files the exporter owns.

Start a change with a clean checkout of current `main`, then create a branch:

```bash
git -C hosting/source-repository switch main
git -C hosting/source-repository pull --ff-only
git -C hosting/source-repository switch -c update/describe-change
```

Save and preview changes in the authoring folder, then run:

```bash
python3 build.py
python3 scripts/check_site.py
python3 scripts/export_source.py hosting/source-repository --dry-run
python3 scripts/export_source.py hosting/source-repository
git -C hosting/source-repository add -A
cd hosting/source-repository
python3 scripts/ci_build.py
git status --short
git commit -m "Describe the website change"
git push -u origin HEAD
```

The initial import alone needs `--adopt-existing README.md`, because the repository previously contained the journal-resource README. Future exports refuse uncommitted or independently changed destination files. If another contributor edits GitHub source, bring that edit back into the local authoring files before exporting again; never overwrite remote changes with a blind export.

The build may regenerate translation assets. Review and stage those outputs if changed, and repeat the export after reconciling source rather than committing an inconsistent export manifest. Keep editorial dates in `content/page-history.json` committed with the content change. CI deliberately fails if rebuilding would alter them.

### Develop directly in a Git clone

Clone the repository, create a branch, edit source, build locally, run checks, commit and push. Python 3.13 and Node 24 are the CI versions. The static build and tests use their standard libraries; a browser preview can run with `python3 -m http.server 8000 --directory site`. In this portable clone the two journal originals remain online downloads; a complete offline copy still lives in the original authoring setup.

Choose one authoring location for each change. If editing this exported clone directly, reconcile those edits with the Mac authoring folder and export manifest before the next export from that folder.

## What each workflow does

- **Website checks:** runs Python and JavaScript tests, builds the site, checks editorial dates, links, citations, language routes and scans, and prepares the Cloudflare folder. Pull requests receive no Cloudflare credential and cannot publish.
- **Publish website:** runs the same checks on a `main` commit, installs the pinned Wrangler dependency, confirms `main` has not advanced, uploads only `hosting/cloudflare/site`, and verifies the commit and canonical production deployment. One production run executes at a time. A build failure stops publication.

Generated `site/` and `hosting/cloudflare/` folders are not source-controlled. The public journal release remains the large-file download location. No paid storage or new hosting project is introduced by this change.

The existing local IndexNow receipt cache is not copied into CI. Search discovery remains available through the sitemap. Until a separate persistent CI notification state is added, run the existing IndexNow tool against the verified deployed snapshot if changed-page notifications are needed; do not repeatedly seed all URLs from a fresh CI checkout.

## Recovery

For an urgent recovery, use Cloudflare's [rollback](https://developers.cloudflare.com/pages/configuration/rollbacks/) to select a known-good production deployment. Then revert the faulty commit through a GitHub pull request, so the next automatic deployment retains the correction. A deployment that failed before upload leaves production untouched. If upload succeeded but verification failed, inspect Cloudflare and the GitHub run before retrying.

After migration, avoid direct uploads from the old editor or dashboard for ordinary releases: they bypass GitHub history and can be overwritten by the next automatic release.
