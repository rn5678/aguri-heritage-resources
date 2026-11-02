# Aguri Heritage

## GitHub publishing pipeline

A portable source export and checked GitHub Actions publishing workflow are active for the existing `rn5678/aguri-heritage-resources` repository and Cloudflare project. See [development and publishing instructions](hosting/PIPELINE.md) for activation status, branch-based editing, verification and recovery. The large journal downloads remain in the existing GitHub Release.

An English and Bengali heritage website for the Aguri / Ugra Kshatriya community of West Bengal. History, culture, places and people form the main visitor experience. Books, periodicals and translations sit within Resources as supporting material.

## Open the website

Double-click **site/index.html**. You can also open **index-preview.html** in the parent folder. The articles, search, journal reader, scans and PDFs work locally without internet access or an account. Only external research links need internet access.

The complete site folder is about 520 MB because it contains faithful copies of both source PDFs and 342 scan images. Its homepage loads only a few small assets; the complete PDF files are fetched only when opened.

## What this edition includes

- **Aguris Today**, a contemporary essay under Culture in English and Bengali, covering land, migration, employment, marriage, politics, the Ugrakshatriya Mahasabha and enterprise. Includes a Culture-page overview, dated public Facebook evidence and numbered source notes. Published research, reported claims and interpretations remain distinct.
- Thirty-eight pages in each language (76 in total, including the contribution form, rights policies and private editor interface), plus two localised 404 pages, with eight primary navigation sections and supporting book, periodical and translation pages. The homepage welcomes readers with an overview of the Aguri community, followed by culture, places and notable personalities.
- A bilingual Research Topics page with twenty-one research directions and a dated progress overview: testing the Nagadee-origin hypothesis, digitising Burdwan estate records, kul panjikas and oral histories, everyday heritage, disadvantaged households, caste analysis in West Bengal, status claims, reservation recognition and unequal opportunity, comparative military settlement, Pratap Chandra Roy’s publishing network, and Manohar Ray’s scientific career. Each topic sets out a question and evidence/method; hypotheses and legal classifications are distinguished from established findings. Linked from Home, History, Origins and the Resources navigation, and included in search, PDF export and the sitemap.
- An Origins article, “From Nagadee to Jotedar: The Burdwan Raj and the Origins of the Aguris,” linked from the homepage and History in both editions. The English text and original 21-date timeline were imported from the owner's Claude document; the Bengali edition translates the article and includes a Bengali text version of the timeline. The imported source exports and provenance are retained in `research/origins-2026-10-01/`.
- Fourteen sourced biographical profiles covering public service, medicine, literature, cinema and scholarship. Individual notes document community connections and qualifications. Portraits and other documentary images appear where available, with a homepage people feature and provenance in `assets/people/credits.json`.
- Two original Bengali journal PDFs: Volume I, 175 scan images; Volume II, 167 scan images.
- A reader with volume and scan navigation, links to enlarge images, deep links, Bengali OCR search and reading-note search in the selected edition.
- Five selected reading notes in English and Bengali: Volume I scans 1, 2, 3 and 9, and Volume II scan 1.
- A Translations collection with five complete selections: the Volume II journal autobiography (pp. 1–5), Electricity (Volume I, pp. 12–23), both 1940 book prefaces, and the 1915 Prabasi review. One additional reading translates only the first editorial’s opening page and is clearly labelled as an extract.
- Original images beside each translated passage, English text downloads, Bengali transcriptions of the two prefaces and the Prabasi book review and explicitly uncorrected article OCR downloads.
- A dedicated Rajput O Ugrakshatriya book page with the complete 158-page Bengali PDF, an embedded reader, download links, publication details and a 98-page English translation. The English edition has an embedded reader, chapter links, all nine chapters, the surviving conclusion, original errata sheets and a closing translator’s note. Printed pages 142–143 are missing from the Bengali scan and that gap is marked. The latest approved PDF is stored in `assets/documents/Rajputs_and_Ugra_Kshatriyas_English_Translation.pdf` and copied into the portable site during rebuilding.
- A source catalogue with 220 entries, document type, access status, and links. Open questions and editorial follow-up are kept in `research/OPEN_POINTS.md` for internal project use.
- Research from Dutta’s complete 2023 chapter (pp. 297–324) and selected passages in Bhaumik’s book (2023 imprint), integrated into Home, History, Culture, Places, People, the historical book page and Resources. Includes the Hazras of Anguna’s rice-milling and coal-mining activities (Dutta, pp. 308–309), the historical population table, community reform, and attributed differences over origins. The supplied modern book PDFs remain research material outside the public assets.
- An attributed account of Bhattacharya’s Hindu Castes and Sects (1896), with its contents and Aguri chapter pages. The author’s military classification is distinguished from official army recruitment.
- A Bengali reading shelf and new English material from Rajput O Ugrakshatriya (1940), a Prabasi review (1915), and Bengali books and reporting. Selected original book leaves can be opened locally.
- Downloadable raw Bengali OCR for each volume and a contribution-record template.

The English edition is at the site root and the Bengali edition is at `bn/`. A top-right language selector on every page preserves the current route, query and fragment. Each edition has its own search index. Original documents and external websites retain their source languages. Bengali reading pages foreground the original scans and checked transcriptions, with the existing English translation in expandable comparison panels.

## Homepage stories

The English and Bengali homepages use the approved public-history design, with a shorter welcome, exploration links, a rotating story collection and an invitation to contribute family memories. The eight stories cover Origins, military settlers and community formation in Bengal, Pratap Chandra Ray, Yogadya’s village connections, the community journal, Ganapati Panja, Shakti Samanta and Aguris Today. Origins appears first and returns in every complete cycle. Both editions use the same story order, showing three cards on desktop, two on narrower screens and one on phones.

The carousel advances every eight seconds while visible. Previous/next arrows, story dots, a position counter, Pause/Play and touch swiping let readers control it. Manual navigation pauses rotation until Play is selected. Hover, keyboard focus, background tabs and scrolling out of view temporarily suspend automatic movement. Reduced-motion preferences disable autoplay unless the reader explicitly selects Play. Offscreen cards cannot receive keyboard focus; without JavaScript, all stories remain available as a static collection.

Edit the bilingual stories and homepage body in `content/index.html` and `content/bn/index.html`. `homepage.py` supplies the homepage shell while retaining shared metadata, search, sharing, citation, contribution and page-view services. Presentation and carousel behavior live in `assets/homepage-public-history.css`, `assets/homepage-carousel.css`, `assets/homepage-services.css` and `assets/homepage-carousel.js`; homepage asset URLs include content versions to refresh cached files. Rebuild and publish to apply source changes.

The former weekly selection subsystem and its saved state remain available for pages that explicitly include its insertion marker; they do not control the current homepage stories. Historical weekly-feature records remain under `output/weekly-feature-2026-10-11/` and `output/weekly-carousel-2026-10-11/`. Current publication evidence is in the [12 October publication receipt](output/homepage-publication-2026-10-12/publication.json), with [live browser-check results](output/homepage-publication-2026-10-12/live-browser-checks.json) recorded separately. Use the normal site checker for both editions after editing.

## Editorial limits

**342 scan images processed does not mean 342 pages verified or translated.** Most PDF images contain two printed pages. All machine OCR is explicitly unreviewed, and there is no full-volume English translation. The selected translations, headings and passages were compared visually with the source scans. The five complete shorter selections do not mean five whole volumes or books. The separate book translation covers all surviving main text and front matter, with uncertain readings identified; it is not a fully verified scholarly edition. One review phrase and some damaged editorial text remain explicitly unclear. The translations await independent language review. Binding shadows, damaged print and faint characters remain limitations of the originals.

The earlier six-page English translation is retained in `research/previous-translation.pdf` for comparison. It is not treated as a primary source. Research findings and corrections are documented in `research/REVIEW.md`.

## Edit and rebuild

### Visual content editor

Double-click **Aguri Content Editor.app** in this folder. It opens the editor in your browser. Choose a biography or main page from the left, select English or Bengali, and click the text to edit it. Select words to apply bold, italic, underline, strikethrough, superscript or subscript. You can add or remove links, clear formatting, and align the selected block left, centre, right or justified. Photograph cards let you replace or delete an image and edit its description; photo credits are editable below the photograph.

Click **Save changes** (or press **Command+S**) to save locally, rebuild and check the site. **Preview** opens the saved page.

Choose **+ Add page** in the sidebar to create a new **Article**, **General page** or **Biography**. Enter its English and Bengali title and introduction, choose its website section, and check the page address before creating it. The editor creates both language editions with editable starter sections, rebuilds and checks the site, then opens the new page. A link appears in the selected website section; the page is also included in site search and the sitemap. Creation saves locally; use the existing **Publish…** flow when the completed content is ready to go online.

Choose **Page types** to add a reusable type, such as “Family history” or “Village profile”. Give it a name and description and choose one of the three starter templates. The new type becomes available in **Add page**, labels its pages in the editor sidebar, and can be found using the sidebar search. The page and type definitions are saved in `content/editor-pages.json` alongside the normal English and Bengali HTML sources. Duplicate or reserved page addresses are rejected, and a failed creation check restores the previous files.

To add a complete paragraph, use **+ Add above** or **+ Add below** beside an existing text block, then type or paste its text. The toolbar’s **+ Add text block** adds beside the selected block. **Jump to text** finds blocks quickly in a long article. Use **Delete block** to remove an entire visible text block, including headings, list items, table text and captions. Its text and citations are removed together when you save. Use **Delete photo** on an image; the editor also removes its caption when they form one photograph. Until saving, **Restore** or **Undo block change** brings removed content back, including its unsaved edits. New blocks can also be removed or undone, and **Discard changes** resets pending additions, removals, formatting and text edits. Existing link destinations are retained as invisible anchors, and profile names remain available as page metadata when their visible headings are removed.

**Update Bengali when I save English** uses the existing ChatGPT subscription signed in to Codex on this Mac. It starts from the current bilingual content and translates only future changed, safely matched passages in small batches after saving. No API key or separately billed API connection is used. It shares your normal Codex allowance; usage appears under the Bengali update controls. Unchanged passages cost nothing, validated results are cached, and empty paragraphs/citation-only removals are copied without a model call. A replaced photo also updates the unique matching Bengali photo, preserving its Bengali description. Photo descriptions themselves remain separately editable.

Existing English and Bengali sections sometimes differ. If a passage cannot be matched reliably, or you edit Bengali while its English update is pending, the editor names the page for review. Open its Bengali edition, edit and save it, then choose **Use saved Bengali for this page** after checking it. Publishing waits for enabled updates and reviews to finish. You can turn automatic updates off to edit and publish both saved versions manually. Translation failure preserves saved English and the previous Bengali content; choose **Retry update** after resolving a connection or subscription limit. Preview the Bengali wording before publishing, especially names and historical details.

With automatic Bengali updates enabled, deleting a safely matched English paragraph removes its Bengali counterpart without a model call. Adding a paragraph beside a safely matched block creates the corresponding Bengali position and translates only the new text. Uncertain matches are flagged for review. Manual Bengali additions and deletions leave English intact. All saved structural changes retain backups and run the normal website checks before succeeding.

Translation state, cached results and usage stay in `local-editor/translation/`, outside the published site. Keep this folder with the project when backing it up. The editor invokes the installed Codex command with saved ChatGPT authentication, a read-only sandbox, no tools, and a bounded translation prompt. It neither reads authentication tokens itself nor changes global Codex settings. Closing a browser tab does not stop an update; keep the editor app running. The existing archival reading editions and source catalogues are outside this authoring feature.

To put your saved changes online, open **Publish via GitHub**. Prepare the update to build and check a fixed copy of all saved source, photographs and both language editions. Review the changed files, then choose **Send to GitHub**. The editor commits and pushes a new branch using this Mac's existing repository connection. Open the GitHub review link, create the pull request, and merge it after the required checks pass. GitHub then publishes to **https://aguri-heritage.in/** automatically. Return to the editor to track the release; it reports success only when the publishing workflow for that merged commit succeeds. Unsaved changes must be saved first; edits made after preparation require a fresh check. Saving and sending a branch alone do not publish.

To remove a citation, click its numbered badge or the **×** beside it. To clear a whole paragraph, click inside it, press **Command+A**, then **Delete**; this includes its citations. **Undo** restores accidental deletions. Saving renumbers the remaining citations and removes notes that are no longer cited on that page; sources still used elsewhere remain available.

Each save creates a source backup under `local-editor/backups/`. Existing links and profile identities are preserved when content is removed; a failed site check restores the previous source. Existing citations can be removed, while adding new or duplicated source markers through the text editor is blocked. If another application has changed a page, reload it before saving. The editor covers biographies and authored main pages; generated translation collections, source catalogues, archive viewers and contribution forms remain managed through their existing workflows.

The editor runs only on this Mac at `http://127.0.0.1:45873/`. Its launcher uses the Python 3.14 installation already present on this Mac. Preparation uses Git, Python and Node; sending uses the existing repository-scoped SSH key. GitHub holds the Cloudflare deployment token in its encrypted production environment. Neither credential is sent to the editor browser. Receipts and isolated checked copies stay under `local-editor/publishing/github/`, outside the published `site/` folder. If a connection drops while sending, check the recorded update again; the editor reconciles its branch and commit before retrying. GitHub review and merging use your signed-in GitHub browser, so no additional GitHub API credential is required. Visual Studio Code remains available for development work through `Aguri Heritage.code-workspace`, but is not needed for content edits or this publishing flow.

Editorial pages in both editions include **Cite this page** with a copyable project credit, page title, last-updated date and public URL. Citations remain readable without JavaScript; the copy button falls back to manual selection if clipboard access is blocked. Periodical-reader citations retain the selected volume and scan. These citations identify this website's page; original source authors and licences remain credited separately.

**Notes & sources** starts collapsed on articles in both editions, with the same disclosure arrow as the citation panel. Clicking a numbered reference or opening a direct note link reveals the relevant note. Keyboard and no-JavaScript readers can use the native disclosure. Notes expand for browser printing and return to their previous state afterward. The dedicated Resources source catalogue stays expanded. This presentation change preserves the existing editorial update dates. Run `node scripts/notes_browser_checks.cjs` with Playwright and Chrome available to check these behaviours.

**Page views** appears at the bottom of public pages when the same-origin counter service is available. It shows a shared, persistent visit total, not completed reads or unique readers. English and Bengali editions have separate totals; `.html` and homepage aliases share their canonical page's total. Counting starts when the service is activated, with no invented historical traffic. The browser counts only visible pages, using a 30-minute marker in session storage to avoid repeated refreshes in the same tab. An attempted increment also sets the marker, preferring a possible undercount to duplicate writes after a lost response. No visitor identity, IP address, referrer, cookie or event log is stored by this feature. File previews, editor/error pages, printing, and unavailable services omit the counter. A browser with blocked session storage still counts once per document, but refresh suppression is unavailable.

The existing Cloudflare Worker serves `GET /api/page-views?page=/history` (read only) and `POST /api/page-views` with JSON `{"page":"/history"}` (increment). Both return `{"page":"/history","views":1}`. The counter creates its own aggregate table on the first valid request through the existing `CONTRIBUTIONS_DB` binding, so publishing needs no additional account permissions. The additive `contributions/migrations/2026-10-09-page-views.sql` migration remains available for optional advance setup. Run `node --test scripts/test_page_views.mjs` and `node scripts/page_views_browser_checks.cjs` for counter checks. The local API preview in `scripts/serve_contributions.mjs` automatically initializes the counter table; local counts never seed the public database.

**Last updated** appears beneath each page introduction and remains visible in PDF exports. `page_history.py` keeps separate English and Bengali dates in `content/page-history.json`. Initial dates use the relevant saved content files' modification timestamps in India time, with that evidence recorded in the registry; they are not verified first-publication dates. Subsequent builds compare the page's editorial text, links and rendered source notes with the saved fingerprint and record the date a change is detected. Rebuilding unchanged content, touching files or changing shared styling does not reset dates. Keep the registry with the source files when moving or backing up the project. Form, editor and error pages omit these article tools. The visible date also supplies the page's structured `dateModified` metadata.

Run `python3 scripts/test_page_history.py` for date-persistence checks and `node scripts/citation_browser_checks.cjs` with Playwright and Chrome available for bilingual, mobile, clipboard, offline and print checks. Citation previews and check results are saved in `output/page-citations-2026-10-09/` outside the public site.

Use the browser's **Print** command to print an editorial page or save it as a PDF; there is no site export button. Choose **Save as PDF** (or **PDF → Save as PDF** on macOS) and turn off browser headers and footers. The print layout keeps the page title, article, documentary images and source notes, with a credit to the Aguri Heritage project and the public page address. Menus, breadcrumbs, side panels, search controls and embedded PDF viewers are excluded. Timeline text and translator notes expand for printing and return to their previous state afterwards. The complete source catalogue prints even if a screen filter is selected. Browser printing also works offline; the original book and journal PDF downloads remain separate.

Shared print attribution lives in `build.py`, print lifecycle handling in `assets/app.js`, and the page layout for PDF/printing in `assets/print.css`. Run `node scripts/pdf_export_checks.cjs` with Playwright and Chrome available to exercise browser print behavior and render representative PDFs for visual review. Printing uses the browser and bundled assets without a PDF service or extra runtime dependency.

1. Edit the English HTML fragments in `content/` and Bengali counterparts in `content/bn/`. Keep the same section order and shared heading IDs; the builder checks the section counts and aligns their anchors. Edit the six reading editions in `content/translations/*.json`; `translation_pages.py` generates their pages, downloads and archive links. The authoring scripts in `research/translations/` record the initial drafting work; do not rerun them after making direct editorial changes to the JSON without reconciling those changes.
2. Edit the source catalogue in `content/sources.json` and its Bengali descriptions in `content/bn/sources.json`. Source IDs, types and URLs are shared.
3. Use `[cite:source-id]` where a claim needs a citation. The build creates numbered notes with source links.
4. Edit `assets/reading-notes.js` and `assets/reading-notes-bn.js` for checked excerpts and reader notes. Keys use `v1-009` to mean Volume I, PDF scan 9.
5. Run `python3 build.py` from this directory.
6. Run `python3 scripts/check_site.py` to check both language editions, corresponding page routes and section anchors, local links, citation targets, search indexes and archive completeness.

The builder uses Python’s standard library and keeps every public asset under `site/`. The production URL is https://aguri-heritage.in/. Deployment `ce58050b-0919-4ff2-acc8-8b5432bfa55e` published the custom-domain SEO settings on 9 October 2026. The migration was completed and verified on 10 October: ordinary DNS/HTTPS works, both `www` and the legacy `pages.dev` host permanently redirect to corresponding pages, Google successfully read the 78-URL sitemap, and both English and Bengali homepages are indexed with the new URLs selected as canonical. Google Change of Address was validated and submitted. Indexing of all 78 pages is not yet established. The redundant 09:00 IST follow-up was paused. GoDaddy still displays an obsolete forwarding setting after three failed deletion attempts; it is not serving through current tested DNS and is nonblocking cleanup. See `hosting/README.md` and `research/SEO-MAINTENANCE.md` for evidence. The large journal downloads are served through GitHub Releases. Local builds do not automatically update the public site. The contribution service is a separate Cloudflare Pages worker with private D1 storage; its existing database binding and editor secret remain in use. See `contributions/README.md`.

## OCR workflow

`scripts/ocr_journals.py` uses local Poppler rendering and Tesseract Bengali + English recognition. It splits scanned spreads into left and right leaves before recognition. The resulting files retain volume and PDF scan numbers. It is resumable: existing per-scan JSON records are reused. Pillow and pypdf are needed for this utility, but not for normal rebuilding.

Intermediate machine confidence values are available in the per-scan JSON records for triage. They are not validated character accuracy percentages. Never use them as proof that a name or claim is correct.

The standard recogniser was compared with a Bengali-only model and the Tesseract `tessdata_best` Bengali model on the contents page. Neither resolved all difficult names reliably. The downloaded model remains in `research/ben-best.traineddata`; its upstream source is https://github.com/tesseract-ocr/tessdata_best. The public OCR layer uses the complete Bengali + English run, while English reading notes rely on visual comparison.

## Preservation

- The owner’s PDFs in the eBooks folder were not modified.
- The supplied `aguri-heritage-website.zip` in the parent folder was not modified.
- The earlier content and builder are retained as `research/original-content.tar.gz` and `research/build-original.py`.
- `site/` is generated output. Edit `content/` and `assets/`, then rebuild.
- Screenshots and verification results are in `research/`; they are not part of the public website.

## Maintaining both editions

`localization.py` holds Bengali navigation labels, page titles and shared interface translations. `bengali_readings.py` uses `content/bn/readings.json` to render the six Bengali reading interfaces and their collection page. Their original Bengali scans, checked preface and review transcriptions and existing English translations come from the same source records as the English edition. Do not back-translate the English text and present it as a historical original, or turn unreviewed OCR into a verified transcription.

Three Noto Serif Bengali font weights are bundled under `assets/fonts/`, with the SIL Open Font License and source credits. Fonts, page search and language switching require no third-party translation or font service. Navigation URLs carry the selected language. A manual language choice sets the first-party `aguri_language` preference cookie for one year; no tracking cookie is added.

The homepage uses “River of Memory” in `assets/burdwan-river-of-memory.webp`, an original AI-generated watercolor-style artwork selected by the owner on 4 October 2026. It depicts an imagined Burdwan landscape combining paddy fields, river life and Bijoy Toron / Curzon Gate; it is not a geographic or historical reconstruction. Both editions show the complete artwork with translated alt text and a caption below it. The original PNG, generation prompts and two alternative concepts are preserved in `output/homepage-artwork-2026-10-04/`. The earlier `assets/rarh-landscape.svg` remains available as a previous design.

### Topic artwork throughout the website

Three coordinated ink-and-watercolour vignettes were added to the English and Bengali homepage topic tiles on 9 October 2026. Their optimized files are in `assets/topic-tiles/`; original PNGs, exact built-in image-generation prompts, artwork metadata, previous source files and desktop/mobile previews are in `output/home-topic-tiles-2026-10-09/`. These are contemporary decorative illustrations, not historical documents, artefact replicas or a geographic map. The tiles keep their original copy and destinations, align on desktop and stack on mobile.

Contemporary watercolour illustrations remain part of the visual collection in both language editions. The 9 October design refresh gives original documents prominence in Archives, Resources, the historical book and Translations; People and biography headers lead with their credited portraits, family photographs or other surviving documentary images. Profiles without a verified portrait use a text-led header. Existing biography paintings are retained as smaller, labelled illustrations after the life story. Places uses a bilingual regional orientation map based on official district sources. The Origins artwork follows the owner's request for a mounted Bengali Aguri warrior of the Nagadee army, presented as an artistic interpretation rather than a verified uniform or reconstruction. The Culture illustration depicts pioneers building rice mills and mining enterprises. Biography illustrations refer to each subject's documented work and legacy; the original portraits, archival images, source scans and article text remain in place.

`assets/page-artworks/catalog.json` preserves the optimized illustration collection, dimensions, bilingual titles and alt text. `page_artwork.py` routes headers through `portrait_headers.py`, `document_headers.py` and `places_map.py` before falling back to the topic illustration. Each header has a responsive layout and a dedicated stylesheet. Original image credits and scan files remain intact. The error pages reuse River of Memory to guide readers home. Decorative topic illustrations are omitted from article PDF exports. When adding a new page, add its artwork entry to the catalogue; the builder reports a missing entry.

The original PNGs, exact generation prompts, visual-review records and a complete local artwork gallery are saved in `output/page-artworks-2026-10-04/`. The gallery is a review artifact, separate from the public website.

For future illustrations, follow the restrained direction established by `assets/topic-tiles/`: one clear subject, generous ivory space, fine green or sepia ink lines, light watercolour and muted terracotta or sage accents. Vary the subject by topic; reserve expansive landscape paintings for feature stories. Keep original portraits and documents as the leading image when available. Generate no lettering inside decorative artwork and never substitute an imagined likeness, document or geographic boundary for evidence. The homepage hero and Origins scenes remain the existing selections. Local previews and pre-change sources for the broader refresh are kept in `output/design-refresh-2026-10-09/`.

Thirteen faint page watermarks complement the illustrations on wide screens: line-art motifs drawn from Bardhaman’s temple terracotta and folk crafts (Nava Kailash on Home, terracotta panels on History, a Natungram owl on Culture, and others; the full list is in `output/watermarks-2026-10-08/README.md`). The SVGs are in `assets/watermarks/` and are used as CSS masks by the "Page watermarks" block at the end of `assets/style.css`. Each motif sits in the free column beside the reading column, is clipped to the article body, and is hidden on phones, in print and in PDF exports. The About page credits the sources of the ornaments. Generators and review screenshots are in `output/watermarks-2026-10-08/`.

The Origins article also contains five owner-requested body illustrations: an artistic interpretation of the traditional account of Satyabati and Sobha Singh, Kirtichand accompanied by Aguri Nagadee soldiers beneath a brick victory gate, Nagadee troops confronting Maratha Bargi cavalry, Nagadee infantry fighting East India Company troops at a river crossing, and sacred-thread investiture described for a section of the Aguri community. Both editions place them after the corresponding historical passages, retain the mounted warrior at the top, and label the new scenes as artistic interpretations. The mounted warrior and the three Nagadee military scenes use period-inspired chest armour; their clothing, equipment and settings remain artistic interpretations rather than verified reconstructions. The optimized body images are `assets/origins/satyabati-sobha-singh.webp`, `assets/origins/nagadee-victory-gate-armoured.webp`, `assets/origins/nagadee-bargi-battle-plunder.webp`, `assets/origins/nagadee-company-battle-armoured.webp` and `assets/origins/aguri-upanayan.webp`; original PNGs and exact prompts are recorded in the artwork output folder. These body illustrations remain visible in article PDF exports. The main illustration collection contains 39 unique artworks across 35 page topics (the research page reuses the reading-room illustration). The revised Bargi scene shows fierce horsemen carrying plunder in sacks, cloth bundles and brass vessels. Armour and plunder revisions use distinct asset filenames; exact prompts and final paths are collected in `output/page-artworks-2026-10-04/upanayan-armour-artwork-record.json`.

## Search discovery and individual biographies

`profile_pages.py` builds the fourteen individual biographies in each edition from the authored people-page fragments, retaining all biographical paragraphs, source notes and photograph credits. The collection displays previews with links to the full profiles and preserves its old anchors.

`seo.py` generates descriptive search titles, canonical URLs, reciprocal language links, social metadata, structured data, `sitemap.xml`, `robots.txt` and Cloudflare response rules. `content/site-config.json` stores the production URL and public Google ownership-verification token. The builder writes localised 404 pages and excludes them from search and the sitemap. The site checker validates these rules alongside existing content checks.

See [the internal SEO maintenance note](research/SEO-MAINTENANCE.md) and `hosting/cloudflare/deployment.json` for Google setup status and the latest deployment. Research notes are not part of the public site.


## Community contributions — first release

`contribute.html` and `bn/contribute.html` accept stories, photographs/documents and corrections without visitor accounts. A prominent header action and the existing invitations lead to the form. Each article has a correction link that carries its page, section and current journal volume/scan. Up to three JPEG, PNG, WebP, PDF or UTF-8 TXT attachments are accepted, each at most 1,500,000 bytes; larger originals can be supplied through a source link. Name and email are optional. Publication consent and attachment permissions are explicit, and public name credit is optional.

A successful submission is stored before the site displays a receipt. Its private tracking link permits status checks and follow-up messages. Keep that link private and save the receipt; it is not emailed automatically. When the service is unavailable, the form says so, keeps the text on screen and offers a draft download. Nothing is submitted merely by opening or filling the form.

Editors use `review.html` (or its Bengali edition), protected by a private server-verified editor key. The key and loaded personal information stay only in browser memory until lock, reload or navigation. The dashboard filters/searches submissions, downloads private attachments, records public responses and private editorial notes, and keeps review history. Concurrent changes cannot silently overwrite another editor's work. Exported review JSON includes private details and must be handled accordingly. Approval does not automatically alter an article: editors apply the accepted change to authored content, rebuild/publish it, then link the live page when marking the contribution Published.

The editor page is excluded from the site search and sitemap and is marked noindex; server authentication, not its hidden URL, protects the data. Contribution and editor pages intentionally omit article tools. Database files, server configuration, test fixtures and editor keys never go into the public output.

For a functional local preview with Node 24 or later, run `node scripts/serve_contributions.mjs` after rebuilding. The preview listens only at `http://127.0.0.1:8788/`; its private local editor key is saved under `contributions/.local/editor-key.txt`. It uses the real production request handler with a local SQLite adapter. Local submissions do not reach the public site. Do not reuse this local test key for production.

Verification: `node scripts/test_contributions.mjs` tests the backend without dependencies. `node scripts/contribution_browser_checks.cjs` uses Playwright/Chrome, temporary isolated data and both language editions to exercise the full flow. Hosting prerequisites and activation instructions are in `contributions/README.md`.

## Copyright, reuse and contributor terms

Original copyrightable project-owned material is **all rights reserved**, with
limited reuse permissions; this is not a blanket Creative Commons release.
`LICENSE.txt` summarises the scope. The bilingual policies are authored in
`content/rights.html`, `content/contributor-terms.html` and their Bengali
counterparts. The footer links them on every page, including error pages, and
article PDF exports retain a short rights notice and policy link. The About
page explains how community participation fits this policy.

The policy permits ordinary reading, link sharing, private personal-study
copies and limited attributed quotations for noncommercial discussion or
review. Broader republication, mirrors, translations and commercial reuse of
protected project-owned material require permission unless an existing licence
or applicable law already permits them. Contributor ownership, item-specific
third-party licences, public-domain material, legal exceptions and earlier
valid public licences remain intact. AI artwork is covered only to the extent
that applicable law recognises rights. A copyright notice does not technically
prevent copying or establish trademark registration.

Contributor terms version **2026-10-04** gives the project a nonexclusive,
worldwide, royalty-free permission limited to operating and preserving this
bilingual project. Submission requires a fresh, unchecked consent choice.
Changing a submission's purpose clears that choice. Private rights enquiries
have separate private-handling consent and confer no publication licence.
Editors can see recorded terms acceptance; older submissions are explicitly
identified as legacy rather than silently relicensed. See
`contributions/README.md` for the storage and compatibility details.

Keep the complete wording of each accepted version in project records before
changing the policies. Update both languages and the form/backend version
together; do not expand existing contributors' permissions retroactively.

## Biography update — 11 October 2026

Updated the English and Bengali profiles of Shakti Samanta, Satya Kinkar Sahana and Jadabendra Nath Panja from the owner-supplied biographies in `Aguri Research for website`. The full narratives, source qualifications and linked references are retained. Sahana and Panja use the portraits embedded in the supplied documents; Samanta uses a new unchanged portrait from Aradhana Films. Public captions follow the owner’s requested neutral wording; full source provenance remains in the corresponding `research/*-profile-2026-10-11/` records. The homepage and People collection use the new Samanta photo and updated credit. Panja’s History summary now agrees with the supplied account of leaving legal practice in 1921.

The site passed link/citation/language validation and desktop/mobile checks at 1440, 390 and 320 pixels. Backups, screenshots and validation records are in `output/biography-update-2026-10-11/`.

## Benoy Choudhury and profile removals — 11 October 2026

Benoy Choudhury’s English and Bengali profiles now incorporate the supplied bilingual public-history biography, including family, labour organising, Operation Barga and his later life. His existing credited portrait is retained. Haricharan Bandhu and Dr Dhanapati Panja’s individual profiles and People listings have been removed, together with orphan profile assets and their selection notes. The site now contains fourteen biographies in each language. Rebuilding retires the four old profile pages and regenerates search and the sitemap. Backups, source extraction and verification records are under `research/benoy-profile-2026-10-11/` and `output/benoy-profile-removals-2026-10-11/`.

## Hare Krishna Konar update — 11 October 2026

The English and Bengali biography now follows the supplied public-history profile, covering family life, Bibha Konar’s famine relief, imprisonment, legislative proposals, land reform and the conflicts of his ministerial years. Existing verified family photograph retained. Source notes distinguish retrospective recollections, contributor-supplied property details and proposed legislation; the text places Operation Barga after his death. Preparation and checks are in `research/konar-profile-2026-10-11/` and `output/konar-profile-2026-10-11/`. Retired Haricharan Bandhu and Dr Dhanapati Panja URLs now have permanent redirects to their language’s People collection in the Cloudflare package.

## Food, village life and Manohar Ray — 11 October 2026

The supplied public-history manuscripts are incorporated into both language editions. `food-and-village-life` is a separate Culture article covering harvest food, posto, macher tok, village worship, Nasigram’s Saraswati Puja and local educational, musical and sporting lives. Culture includes a direct introduction/link, and the article participates in language switching, site search, sitemap, page history, source notes and Culture breadcrumbs. It reuses the existing, clearly labelled river-and-fields illustration. Dated local evidence and regional family memories are distinguished from community-wide customs; no caste identity is inferred from names. The Culture page’s closing research-gap note now acknowledges those local records.

The Manohar Ray profile retains its established route and visual treatment while expanding the account of Nasigram, fluid dynamics and Royal Society review, the 1940 Lahore professorship, Agra College’s 1960–1970 principalship and mathematics textbooks. Publisher biographical claims are attributed, and undocumented personal dates and the Lahore–Agra chronology remain open. Source extraction, original-file backups and source reviews are under `research/editorial-updates-2026-10-11/`; this release’s browser and publication records are under `output/weekly-carousel-2026-10-11/`.

## Returning-browser carousel fix — 11 October 2026

The live in-app browser retained the earlier static-feature assets: the new five-slide HTML was present, but controls stayed hidden and the carousel never initialized. Live asset responses advertise a four-hour browser cache. Homepage carousel CSS and JavaScript now include a content-derived version in their URLs, in both editions, so a fresh deployment picks up changed assets without requiring users to clear browser data. The carousel behavior and accessibility preferences are unchanged. Diagnosis, publication and live checks are in `output/carousel-live-fix-2026-10-11/`.

## Water landscape article — 11 October 2026

The supplied research note is adapted into `water-landscape`, a bilingual public history article under Places. Both Places editions include an executive summary and link to the complete article. The article preserves distinctions between documented village/family histories and proposed river-basin connections, identifies Ruud’s village names as pseudonyms, and avoids unverified Nasigram irrigation figures or caste-wide military-settlement claims. Gazetteer and government irrigation/audit references support the canal chronology. Navigation, breadcrumbs, language switching, search, sitemap and page history include the new route; the header reuses the labelled geography illustration. Source extraction, checks and backups are under `research/water-landscape-2026-10-11/`; layout and publication records are under `output/water-landscape-2026-10-11/`.

## History page redesign — 13 October 2026

The English and Bengali History pages use the approved chronology-first layout (“Option B — Through time”) with the homepage’s header, footer, colours and type. `history_page.py` applies the homepage shell to History, as `homepage.py` does for Home; metadata, search, citations, notes, sharing, page counts and the correction link still come from `build.py`. Presentation is in `assets/history-page.css` and the header menu and language links in `assets/history-page.js`; both URLs carry content versions.

The authored bodies in `content/history.html` and `content/bn/history.html` were reorganised rather than rewritten. The overview sits beside the evidence key; the six turning points and fourteen key dates form one time line in four eras, with existing documentary images and labelled illustrations on the turning points; the five origin accounts are shown as cards; and the chapters stay in the existing disclosure, listed by title above it. Where a key date repeated a turning point (1760, 1888, 1913) the turning-point text is kept and the details remain in the chapters; the 1802, 1942 and 1967 key-date texts appear beneath their turning points. No source was dropped. New interface labels (era names, “Turning point”, “How to read the labels”, “The full account”) exist in both languages; the Bengali labels await language review. Evidence tags carry a kind class (`evidence-documented`, `-reported`, `-tradition`, `-interpretation` or `-record`) that draws their mark. Both editions keep the same eleven H2 sections in the same order, and the old `#key-dates` anchor now leads to the era navigation.

These edits were made outside the content editor, so the editor’s Bengali-update pairing for History needs a fresh baseline: open History in Bengali, check it, then choose **Use saved Bengali for this page**. Publishing waits for this step. Backups of the previous sources and generated pages, and the checks, are in `output/history-option-b-2026-10-13/`.


## Bing search setup — 16 October 2026

Bing Webmaster Tools already verifies this site and reports the canonical sitemap as Success. The property's display label includes `www`, but Bing recognizes the canonical apex domain under the same property. Preserve the existing `BingSiteAuth.xml`, canonical origin and redirects. A live homepage test passed with no SEO issues; the homepage indexing request was accepted. These observations do not establish completed indexing or rankings.

`content/site-config.json` now contains `indexnow_key`, a **public ownership-verification key**. `seo.py` writes its root `.txt` file on every build. The checked publisher calls `scripts/indexnow.py` after Cloudflare confirms the production version is live. The initial notification is explicitly seeded once; later publications notify only added, changed or removed canonical pages. Successful unchanged builds make no submission. Manual dashboard uploads require running `python3 scripts/indexnow.py` after confirming the exact prepared version is live. Notifications never deploy the website themselves.

The submission inventory and last receipt live in `local-editor/indexnow/`, outside the public upload. Keep this state with the project to avoid duplicate submissions. HTTP 200 means received; 202 means key validation pending. Neither guarantees crawling, indexing or ranking. Notification failure preserves publication success and the retry inventory. After resolving a network or verification failure, retry against the confirmed deployed snapshot with `python3 scripts/indexnow.py --site local-editor/publishing/<preparation-id>/site`. Do not run an initial `--all` again to request unchanged URLs. Relaunch the content editor after updating its publisher code if it was already running.

The site checker now catches missing/duplicate page titles, duplicate descriptions, invalid/future modification dates, schema/history mismatches, and missing Bing/IndexNow verification files. Canonical URLs, language alternates, robots rules and truthful editorial dates remain in place. Evidence and the scoped publication receipt are under `output/bing-seo-2026-10-16/`.

## Military settlers article — 21 October 2026

The bilingual History article `military-settlers-bengal.html` publishes the supplied *Military settlers and community formation in Bengal* document, with its complete prose, three tables, four source figures and 31 linked source notes. Its page metadata lives in `content/editor-pages.json`; both language sources remain editable under `content/`. A catalogued custom page can now use the existing illustrated header. Article-specific responsive table and figure styles are in `assets/military-settlers.css`.

Two new interpretive illustrations appear as the article header and as the second story in the Home and History carousels. Web assets are in `assets/military-settlers/`; original generated images, exact prompts, document extraction, source comparison and publication evidence are kept outside the public site under `output/military-settlers-2026-10-21/`. The History carousel inventory is now six stories; both homepages contain eight.


## Research topics refresh — 21 October 2026

The English and Bengali Research Topics pages now distinguish evidence already available in newer articles from pending archival and fieldwork tasks. A dated progress overview links military settlement, landholding, family histories, recognition, publishing, scientific careers and everyday life. The page has 21 topics, including new follow-ups on comparative military settlement, Pratap Chandra Roy’s publishing network and Manohar Ray’s career. The 1767 establishment totals and the conflicting marriage accounts are explicitly qualified.

Production deployment `fabe5ca5-fd25-4219-9bb0-d173e8ddf855` was confirmed at 22:07:42 IST. Only the two research pages, their search indexes and the sitemap changed in the upload. Both live article bodies match the checked pages; site-wide link/citation checks and desktop/mobile reviews passed. Backups, source-change records, screenshots and publication evidence are in `output/research-refresh-2026-10-21/`. The local editor’s research translation baseline was updated after bilingual review.


## Freedom struggle article — 23 October 2026

Published “Aguris in the Freedom Struggle and Its Impact on Aguri Society” in English and Bengali under History, covering participation and social change through the 1950s. The selected cover leads both editions and appears in the History and homepage story carousels. The History collection now has seven stories; the homepage has nine. The article retains 26 narrative paragraphs and 20 source notes.

English: https://aguri-heritage.in/aguris-freedom-struggle

Bengali: https://aguri-heritage.in/bn/aguris-freedom-struggle

Canonical production deployment: `6752e8a5-778d-4a6e-b58f-136eea131440`. Both live editions, image loading, carousel links, mobile layouts and citation navigation were checked. The unrelated saved military-settler draft was preserved locally and excluded from this release. Publication, scope and verification records are in `output/aguri-freedom-struggle-2026-10-23/`.


## Regional homepage language — 23 October 2026

The existing Pages Worker negotiates only `/` and `/index.html` on GET/HEAD. A valid explicit `?lang=en` or `?lang=bn` choice takes precedence, then a saved `aguri_language=en|bn` cookie, then Cloudflare IP metadata. India (`IN`) and subdivision `WB` select Bengali; other or unknown locations select English. Full `IN-WB` is accepted defensively, with an exact `West Bengal` name fallback only when subdivision code is absent. Geolocation is not saved as a preference.

The visible page selectors save only manual choices in one host-only cookie (`Path=/`, `SameSite=Lax`, `Secure` over HTTPS, one-year lifetime). English homepage toggle links include `?lang=en`, so switching to English does not loop in West Bengal when cookies are blocked. Existing query values and fragments stay with the chosen route. Explicit `/bn/` pages and direct article links remain in their requested language. No browser GPS, permission request, third-party geolocation or new storage binding is used.

Both negotiated English responses and Bengali temporary 302 redirects send `private, no-store` and CDN no-store headers. `_routes.json` invokes the existing Worker for `/api/*`, `/` and `/index.html` only; other pages and assets remain static. The uploader continues to package `_worker.js` as an active advanced-mode Worker, with the existing contribution/D1 settings retained. Homepage invocations use the existing combined Workers/Pages Functions free quota; no plan or account settings were changed.

Run `node --test scripts/test_homepage_language.mjs scripts/test_language_controls.mjs` plus the existing publisher/API regressions. Publication and scope evidence is stored in `output/regional-language-2026-10-23/`. Geographic cases in the automated tests are simulated, not proof of any particular visitor's physical IP classification.

Confirmed production deployment `0936c7f6-b25e-4d6e-b26c-16c0056164bf` at 23:45:32 IST on 23 October 2026. All 89 indexed live pages match their checked content and canonical/language metadata; all 11 checked script/profile assets match byte for byte. The real cookie-free English alias chain, manual preference round trips, no-store headers and browser toggles passed. Regional geography cases were simulated. Existing `fail_open=true` and the shared Functions quota were retained; quota exhaustion can bypass automatic negotiation and serve static content.

## Contact form — unpublished draft

A local English/Bengali Contact Us page and mandatory-CAPTCHA mail adapter are
prepared for review. No contact delivery credentials or receiving inbox have
been configured, and this draft has not been published. See
[`contributions/CONTACT.md`](contributions/CONTACT.md) for the explicit setup
decisions, security requirements and mocked local tests.


## Tuhin Kumar Roy profile — 2 November 2026

Published the supplied *Tuhin Kumar Roy: A life in chemical engineering* document in English and Bengali under People. Both profiles preserve all 25 narrative paragraphs, six sections, ten source notes and 29 citation occurrences. The original 591 × 799 portrait is extracted unchanged from the supplied DOCX and credited to *Current Science* (10 October 2019, p. 1222). The Bengali prose and notes were checked against the English source.

English: https://aguri-heritage.in/person-tuhin-kumar-roy

Bengali: https://aguri-heritage.in/bn/person-tuhin-kumar-roy

The new biography uses the normal authored People collection and remains editable there. Related source entries are in both source catalogues, with bibliography anchors, search records and sitemap entries. The release was overlaid on the verified production snapshot so unrelated saved drafts remained local. Final canonical production deployment: `d7cfb470-11be-4c0a-9b30-278c2dbc8fee`. Both live profiles and all eleven added/changed files were verified against the checked release, accounting only for Cloudflare's email-link transformation. Site-wide link/citation checks, desktop/mobile layouts and language switching passed. Source, translation and attribution records are in `research/tuhin-kumar-roy-2026-11-01/`; scope, screenshots and publication evidence are in `output/tuhin-kumar-roy-2026-11-01/`.
