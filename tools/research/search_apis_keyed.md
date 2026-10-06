# Keyed archive search APIs for genealogy adapters

Researched 2026-10-05. Sources are official docs unless marked **[secondary]**. I sent requests without a key (or with a made-up key) to see the error format. I did not sign up for any keys.
Raw downloaded docs: `scratchpad/research/raw/` (NARA swagger v2/v3 JSON, Trove OpenAPI YAML, Trove v3 PDF, Europeana Confluence text, DPLA pages).

---

## 1. DPLA API v2 (`https://api.dp.la/v2`)

Source: https://pro.dp.la/developers/policies, /requests, /responses. WebFetch got a 403 from pro.dp.la, but curl worked.

### Getting a key
- **Free and instant, no approval step.** Send a POST with the email address in the path:
  ```
  curl -v -XPOST https://api.dp.la/v2/api_key/YOUR_EMAIL@example.com
  ```
  → `201 Created` `{"message":"API key created and sent via email"}`. The 32-char key arrives by email.
- Quote: "When you request an API key, DPLA captures only your e-mail address."
- Adapter UX: either the user runs the curl command, or the app offers a "request key" button that does the POST to the user's email. Only do the POST when the user clicks it.

### Sending the key
- Query parameter `api_key=<32 chars>`. The docs say: "you must include the ?api_key= parameter with the 32-character hash following." No header option is documented.

### Search template
```
GET https://api.dp.la/v2/items?q={keywords}
    &sourceResource.date.after={YYYY[-MM-DD]}&sourceResource.date.before={YYYY[-MM-DD]}
    &sourceResource.spatial={place}            # or sourceResource.spatial.state=Massachusetts
    &page={1..100}&page_size={1..500}
    &fields=id,isShownAt,object,dataProvider,sourceResource.title,sourceResource.date,sourceResource.description,sourceResource.spatial,sourceResource.type
    &api_key={KEY}
```
- `q`: keyword search over all text fields. AND is the default. `AND`/`OR` and `*` wildcards work. Use `+` for spaces and quotes for phrases.
- Fielded search: `sourceResource.title="..."`, `sourceResource.creator=`, `sourceResource.subject.name=`, `sourceResource.collection.title=`. Some fields are case-sensitive (`id`, `sourceResource.format`, ...).
- Dates: `sourceResource.date.after` / `.before` (the docs say "on or after" and "on or before"). `sourceResource.temporal.after/before` covers "about-ness".
- Place: `sourceResource.spatial`, `.spatial.name`, `.spatial.state` (full state name), `.spatial.coordinates`. Sort by distance with `sort_by_pin=lat,lon&sort_by=sourceResource.spatial.coordinates`.
- Pagination: "By default, we'll give you 10 items… page parameter (it's one-indexed). **The maximum page number is 100**… page_size… **500 items per page**". The deepest reachable result is about 50,000.
- Sort: `sort_by=<field>&sort_order=asc|desc`. Fetch by ID: `/v2/items/{id}` or `/v2/items/{id1},{id2}` (up to 50).

### Response mapping
Envelope: `{count, start, limit, docs:[...], facets}`
| Our field | DPLA path |
|---|---|
| id | `id` (32-hex). `@id` = `http://dp.la/api/items/{id}` |
| title | `sourceResource.title` (string or array) |
| date | `sourceResource.date.displayDate` (also `.begin`/`.end`; can be an object or an array of objects) |
| URL on provider site | `isShownAt` (contributing institution's page). DPLA's own page is `https://dp.la/item/{id}` |
| snippet/description | `sourceResource.description` (string or array) |
| place | `sourceResource.spatial[].name` (plus `.state`, `.coordinates`) |
| thumbnail | `object` |
| source | `dataProvider`, `provider.name` |
| rights | `sourceResource.rights` / `rights` |
Normalize values to arrays: many fields can be either a scalar or a list.

### Full text / OCR
- No full-text endpoint. DPLA aggregates metadata only. Follow `isShownAt` to the holding institution.

### Rate limits
- None published. Quote: "the DPLA will not restrict or rate-limit the use of its API. However, the DPLA reserves the right to protect the integrity of the API … from abuse (in its discretion), particularly activity that has the effect of denying or unduly degrading service to other API users."

### Terms
- Revocation: "access to the API will not ordinarily be rate-limited or revoked. The DPLA reserves the right to limit or revoke access … if … a user engages in abusive conduct".
- Availability: "it provides the API on a 'best effort' basis."
- Metadata licence **[from DPLA press and partner pages via search]**: all DPLA metadata is CC0, so caching and storing metadata is fine. Images and other media follow the item's own `rights`.
- No attribution requirement for metadata, but crediting `dataProvider` is good practice.

### Errors (tested 2026-10-05)
- Missing key and bad key give the same response: **HTTP 403**, `application/json`:
  `{"error":"invalid_api_key","message":"Invalid or inactive API key.","documentation":"https://pro.dp.la/developers/responses#errors"}`
- No rate-limit code is documented. Treat 429 and 5xx as retryable.

---

## 2. U.S. National Archives Catalog API v2 (`https://catalog.archives.gov/api/v2`)

Sources: https://www.archives.gov/research/catalog/help/api ; https://github.com/usnationalarchives/Catalog-API (README and official bulk-download scripts); Swagger at https://catalog.archives.gov/api/v2/swagger.json (UI: /api/v2/api-docs/). A **v3** spec also exists: `/api/v3/swagger.json`, path `/api/v3/records/search`.

### Getting a key
- **Email `Catalog_API@nara.gov`** with your name and the email address to tie the key to (archives.gov also asks for your "Catalog user name"). Quote (README): "To request a Catalog API key, please send an email to Catalog_API@nara.gov with your name and the email address you would like associated with your key."
- "The default API key is a read-only key." A read-write key (for tags and transcriptions) requires a Catalog account.
- Free. **Approval time is not stated.** A person handles it ("API key that was provided by our Catalog engineers"), so expect days.

### Sending the key
- Header **`x-api-key: <KEY>`**. Quote (swagger): "you can pass the API key into a REST API call in the x-api-key header of the request."
  ```
  curl "https://catalog.archives.gov/api/v2/records/search?q=constitution" -H "Content-Type: application/json" -H "x-api-key: YOUR_API_KEY"
  ```

### Search template
```
GET https://catalog.archives.gov/api/v2/records/search
    ?q={keywords}                     # boolean AND/OR/NOT, * wildcards, "exact phrases"; max 1024 chars
    &startDate={YYYY|YYYY-MM|YYYY-MM-DD}&endDate={same format as startDate}
    &geographicReference={place}      # matches subjects.heading where authorityType=geographicPlaceName
    &personOrOrg={name}               # authority/role headings
    &availableOnline=true             # only items/file units with digital objects
    &levelOfDescription=item|fileUnit|series|collection|recordGroup
    &typeOfMaterials=Textual Records|Photographs and other Graphic Materials|...
    &recordGroupNumber=..&ancestorNaId=..&creators=..&title=..&naId=..
    &page={1..10000}&limit={1..1000, default 20}
    &sourceIncludes=naId,title,productionDates,scopeAndContentNote,digitalObjects.objectUrl
    &abbreviated=true
    &includeExtractedText=true        # adds OCR text in record.digitalObjects.extractedText (default false)
Header: x-api-key: {KEY}
```
- Deep paging: `searchAfter=*` on the first request, then the `sort` array of the last hit. It works past 10,000 results but can't be combined with `page`/`sort`.
- Other useful filters: `exactDate=YYYY-MM-DD`, `recurringDateMonth`, `recurringDateDay`, `transcriptions_exist=true`, `tags_exist`, `objectType=JPG,PDF`.
- Date params search `record.productionDates.logicalDate`, `copyrightDates`, `releaseDates`, etc. Quote: "Only ancestors with levelOfDescription as 'series' will have their date fields searched."

### Response mapping
Envelope (from NARA's official `DownloadObjects_anySearch.py`): `j['body']['hits']['hits'][i]['_source']['record']`. The total is under `body.hits.total` (Elasticsearch-style, likely `{value: N}`; check against a live key).
| Our field | NARA path (`_source.record.*`) |
|---|---|
| id | `naId` (integer) |
| title | `title` |
| date | `productionDates[].logicalDate` (ISO; unknown parts become 01-01) or `coverageStartDate`/`coverageEndDate`; `inclusiveStartDate`/`inclusiveEndDate` on series |
| URL on provider site | not in the payload. Build `https://catalog.archives.gov/id/{naId}` |
| snippet/description | `scopeAndContentNote`, `generalNotes` |
| place | `subjects[]` where `authorityType == geographicPlaceName` → `heading` |
| level/type | `levelOfDescription`, `generalRecordsTypes` |
| hierarchy | `ancestors[]` (series/recordGroup title, `recordGroupNumber`) |
| digitized files | `digitalObjects[]`: `objectUrl` (direct S3 file URL), `thumbnailUrl`, `objectType`, `objectFilename`, `objectId`, `objectDesignator`, `objectDescription` |
| OCR | `digitalObjects[].extractedText` (only with `includeExtractedText=true`), `extractedTextAccurracy` [sic], `otherExtractedText` (partner OCR, `includeOtherExtractedText=true`) |
| rights | `useRestriction`, `accessRestriction` |

### Full text / transcriptions
- **Yes, digitized object URLs are returned** in `digitalObjects[].objectUrl` (e.g. `https://nara-media-001.s3.amazonaws.com/...`).
- **OCR**: use `includeExtractedText=true` on search, or `GET /api/v2/extractedText/{naId}?objectId={objectId}&page=&limit=`.
- **Search inside OCR or partner text**: `/records/search/by-other-extracted-text`, `/other-extracted-text/search`.
- **Crowd transcriptions**: `GET /api/v2/transcriptions/naId/{naId}`, `/transcriptions/search`, `/records/search/by-transcription`.
- Note: v3 removes this. Quote: "In the new 3.0 version of this API, the ExtractedText fields have been removed to reduce load". **Use v2 for OCR.**

### Rate limits
- Quote: "NARA limits the number of Catalog API requests to a default rate of 10,000 queries per month per API key. Exceeding this limit will cause the API key to be temporarily blocked until the first of the following month." Higher tiers go up to 150k/month on request (archives.gov).
- Adapter: keep a local monthly counter. 10k/month is about 330 per day.

### Terms
- (archives.gov) "All users agree they will not use the National Archives Catalog content or Catalog API service for any illegal or defamatory purpose"
- (archives.gov) "**Users will not scrape data or attempt to download all data from the Catalog via the API**". Use bulk datasets instead.
- README: "NARA's archival metadata is all assumed to be in the public domain, as a work of the federal government". Images are generally public domain too. Check `useRestriction` on each record.

### Errors (tested 2026-10-05). Important gotcha:
- A missing or invalid key returns **HTTP 200 with `content-type: text/html`**: the Catalog SPA's index.html (`x-cache: Error from cloudfront`). This happens even with `Accept: application/json`. CloudFront swaps the gateway's error page for the web app.
- **Adapter must treat a non-JSON / `text/html` response as an auth failure (or quota block).** Don't rely on status codes.
- Documented codes: 400 "Bad Request. Invalid search terms", 422 Unprocessable Entity, 404 (extractedText: no match), 500.
- The over-quota response isn't documented. It probably looks the same as the auth failure through CloudFront.

---

## 3. Trove API v3 (National Library of Australia) (`https://api.trove.nla.gov.au/v3`)

Sources: official OpenAPI spec https://api.trove.nla.gov.au/v3/trove-api-v3.yaml (downloaded); official PDF "Introducing Trove API v3 Beta" (trove.nla.gov.au/sites/default/files/attachments/2023-07/...). The trove.nla.gov.au HTML doc pages (technical guide, using-api, API terms) are behind an Anubis bot challenge, which I didn't try to get past. Terms and approval details therefore come from search-engine excerpts of the official pages and **[secondary]** Tim Sherratt / Trove Data Guide.

### Getting a key: **slow and requires approval**
- Steps: create a Trove account → log in → profile → **"For developers"** tab → fill in the API application form. **[secondary, Trove Data Guide; matches official snippet]**
- The form asks for your username and contact details, the call rate you need, why you want access, how you'll use the API, agreement to the Terms, and whether you need an **exemption** to the Terms.
- **Since ~May 2025 non-commercial keys are no longer automatic.** Quote [secondary, Sherratt 2025-05-07]: "Now you have to fill in a two page form justifying your proposed use. Your application is then assessed against a complex four level review matrix. **Responses are provided within 7 to 28 days.**"
- Free for non-commercial use. Commercial use is assessed case by case.
- Keys **expire 12 months after activation**, with renewal emails (official PDF).
- Anonymous access was removed. Quote [secondary]: "Unauthenticated access has now been disabled and all attempts to access the API without a key return an error." Confirmed by my test below. (The 2023 PDF's "10 calls per minute" anonymous tier no longer exists.)

### Sending the key
- Header **`X-API-KEY: <key>`** (recommended; it's the OpenAPI `securitySchemes.ApiKey`), or query `key=<key>`. Official PDF: "API keys can be provided either via a URL parameter (&key=<your key>) or as a Request Header (X-API-KEY=<your key>). The Request Header is the recommended option".

### Search template (newspapers)
```
GET https://api.trove.nla.gov.au/v3/result
    ?category=newspaper                       # required
    &q={keywords}                             # optional; supports indexes, e.g. date range below
    &l-artType=newspaper|gazette
    &l-state={New South Wales|Victoria|...}   # state of publication
    &l-title={newspaper title id}
    &l-decade={YYY}  (e.g. 188 = 1880-1889)
    &l-year={YYYY}   (newspapers: only with l-decade)
    &l-month={M}     (only with l-year)
    &l-category=Article|Advertising|Family notices|Detailed Lists, Results, Guides|...
    &l-illustrated=true&l-wordCount=<100 Words|100 - 1000 Words|1000+ Words
    &n={1..100, default 20}&s={* then nextStart}
    &sortby=relevance|datedesc|dateasc
    &reclevel=brief|full
    &include=articletext                      # see note
    &bulkHarvest=false
    &encoding=json                            # default is XML!
Header: X-API-KEY: {KEY}
```
- Date range inside `q` [secondary, Trove Data Guide / technical guide]: `date:[1880-01-01T00:00:00Z TO 1889-12-31T00:00:00Z]`. The docs note the first date is exclusive. A simpler option is to combine `l-decade` and `l-year` facets.
- Pagination: cursor-based. Spec: "use this 'nextStart' value with the 's' parameter… the 's' parameter must be URL encoded". There's no page-number jump. `records.next` gives the full next URL.
- `bulkHarvest=true` sorts by ID for stable harvests (not needed for interactive search).
- **`include=articletext` on `/v3/result`**: the official spec's `include` enum for `/result` lists only `all, comments, holdings, links, listitems, lists, subscribinglibs, tags, workversions`. `articletext` is listed only for `/v3/newspaper/{id}`. The Trove Data Guide says `include=articletext` works on search too. Prefer fetching per article (and see the terms on full text below).

### Response mapping (encoding=json)
Envelope: `{query, category:[{code:"newspaper", name, records:{s, n, total, next, nextStart, article:[...]}, facets}]}` → articles at `category[0].records.article[]`.
| Our field | Trove `article` field |
|---|---|
| id | `id` (string). Persistent ID is `identifier` (e.g. `https://nla.gov.au/nla.news-article{id}`) |
| title | `heading` |
| date | `date` (YYYY-MM-DD) |
| URL on provider site | `troveUrl` (web view, includes search terms for highlighting); `identifier` = persistent link; `url` = API URL |
| snippet | `snippet` (has `<b>` highlight tags; strip them) |
| place | `title.state` (state of publication); `title.title` = newspaper name; `title.id` |
| category | `category` (Article / Family notices / ...) |
| page | `page`, `pageSequence`, `trovePageUrl` |
| extras | `relevance.score/value`, `wordCount`, `correctionCount`, `illustrated` (Y/N), `status` ("coming soon"), `pdf[]` |
| full text | `articleText`: HTML fragment with `<p>`/`<span>`. Missing for e.g. Australian Women's Weekly and "coming soon" articles |

### Full-text endpoint
```
GET https://api.trove.nla.gov.au/v3/newspaper/{id}?include=articletext&reclevel=full&encoding=json
Header: X-API-KEY: {KEY}
```
- Technically available. **Under the terms you need an exemption to download full text** (see below).

### Rate limits
- Official PDF: "The standard quota (calls per minute) has been increased from 100/min to **200/min**." Approved keys can have custom quotas.
- The gateway is Kong (`x-kong-request-id` header). Over-quota should return **429** (Kong default `{"message":"API rate limit exceeded"}`). That's an inference, not documented.

### Terms (Trove API Terms of Use, https://trove.nla.gov.au/about/create-something/using-api/trove-api-terms-use)
These excerpts come from search-engine snippets of the official page, since I couldn't fetch it directly:
- Attribution: "If you display metadata retrieved via the Trove API … you must identify the source (i.e., the third party source of the item, as well as Trove) and state that your website or application uses data sourced from Trove and include a link to https://trove.nla.gov.au/" (and use their logo).
- Caching: "You may cache Trove metadata retrieved via the Trove API for up to **30 days** if you wish to enable offline functionality … or where making real-time calls would negatively affect the performance of your service."
- Scope: the API terms cover **metadata only**. The rights "do not extend to use of digital objects or images".
- Full text [secondary, Sherratt]: "If you want to download the full text of resources, such as digitised newspapers, you additionally need to apply for an exemption to the terms of use." The review matrix puts "Downloading/harvesting full-text records" and AI/ML uses at the higher review levels.
- The general Trove ToS bans "use any automated tool to access, copy or extract any content … without the Library's prior written consent". The API is the sanctioned route.
- **Adapter implications:**
  - Show snippet, heading, date and link out to `troveUrl`.
  - Show Trove attribution.
  - Cache metadata for 30 days at most.
  - Only fetch `articletext` if the user's key was approved with a full-text exemption. Make it a user setting, off by default.

### Errors (tested 2026-10-05)
- No key: **401**, `www-authenticate: Key`, `{"message":"No API key found in request","request_id":"…"}`
- Bad key: **401**, `{"message":"Unauthorized","request_id":"…"}`
- Spec error object for other failures: `{statusCode, statusText, description}`. A key still waiting for activation also returns 401: "it can take several minutes for the key to be activated" [secondary].

---

## 4. Europeana Search API (`https://api.europeana.eu/record/v2/search.json`)

Sources: Europeana Knowledge Base (Confluence) "Search API Documentation" (updated 2026-02-11) and "Accessing the APIs" (updated 2026-02-06), fetched via the Confluence REST API; "API FAQ"; "IIIF APIs Documentation".

### Getting a key
- Quote: "Since 28 May 2025 … You now need a **Europeana account** to access the Europeana APIs."
- **Personal key (instant, free):** sign up or log in at europeana.eu → top-right menu next to your nickname → **"Manage API keys"** → tick "I confirm that I have read and accept the API key terms of use" → **"Request a Personal API key"**. "Your key will appear in this section and can immediately be used." One personal key per account.
- **Project key:** a form in the same place, reviewed by support. "we aim to respond within 1–5 working days". "Requests from accounts that do not hold, or have not used, a Personal API key will be automatically rejected." Short-term project keys are available for research such as PhD work.

### Sending the key
- Preferred: header **`X-Api-Key: <WSKEY>`**.
- `wskey=<WSKEY>` query param still works but is "**now deprecated**. We will provide a grace period".

### Search template
```
GET https://api.europeana.eu/record/v2/search.json
    ?query={keywords}                 # Lucene/eDismax: "phrase", AND/OR/NOT, who:(...), where:(...), when:(...), Nicolas~
    &qf=YEAR:[1850 TO 1900]           # refinement; repeatable
    &qf=where:(Boston)                # or query field where:/edmPlaceLabel; geo: qf=distance(location,lat,lon,km)
    &qf=TYPE:TEXT
    &theme=newspaper                  # thematic collections: newspaper, ww1, migration, ...
    &reusability=open|restricted|permission
    &rows={1..100, default 12}
    &start={1..}                      # basic paging: start+rows ≤ 1000
    # or &cursor=*  then nextCursor    (deep paging; not with start)
    &profile=minimal|standard|rich|facets
    &sort=score+desc
Header: X-Api-Key: {KEY}
```
- Aggregated fields: `who` (creator/contributor/agents), `where` (spatial, place labels), `when` (created, temporal, date, year, issued), `what`, `text`.
- `YEAR` is a searchable/facet field mapping to result `year`. The docs only fully support date ranges on `timestamp_created/update`. For historical dates use `YEAR:[a TO b]` or `when:`.

### Response mapping
Envelope: `{apikey, success, requestNumber, itemsCount, totalResults, nextCursor, items:[...], facets}`.
| Our field | Europeana item field (minimal profile) |
|---|---|
| id | `id` (e.g. `/9200300/BibliographicResource_3000059204545`) |
| title | `title[]` (+ `dcTitleLangAware`) |
| date | `year[]` (no full date at minimal; `rich` adds `dcDate`-type fields). Fetch Record API for the exact date |
| URL on provider site | `edmIsShownAt[]` (provider page); `guid` = Europeana item page; `link` = Record API JSON URL |
| snippet/description | `dcDescription[]` (+ `dcDescriptionLangAware`) |
| place | `edmPlaceLabel` (standard profile and up), `edmPlaceLatitude/Longitude[]` |
| thumbnail | `edmPreview[]` |
| media | `edmIsShownBy[]` |
| source | `dataProvider[]`, `provider[]` |
| creator | `dcCreator[]` |
| type | `type` (TEXT/IMAGE/SOUND/VIDEO/3D) |
| rights | `rights[]` |

### Full text / OCR
- Newspapers and transcribed items use IIIF:
  - Manifest: `https://iiif.europeana.eu/presentation/{RECORD_ID}/manifest`
  - Full-text annotation page: `https://iiif.europeana.eu/presentation/{RECORD_ID}/annopage/{PAGE_ID}?profile=text&textGranularity=page`
  - Use `Accept: application/ld+json;profile="http://iiif.io/api/presentation/3/context.json"`.
- The FAQ also mentions a **Newspapers API** for "full-text" search across newspaper OCR. I didn't pull its docs; follow up if needed.
- Search filter: facet `TEXT_FULLTEXT=true`; `sort=is_fulltext+desc`.

### Rate limits
- No numbers published. Quote (Accessing the APIs, 2026): "The rate limits for personal keys have been progressively reduced until April 2026 to give customers with service-level requirements sufficient time to transition to project keys". Project keys "come with significantly higher usage limits".
- The older FAQ still says "You can query our APIs as often as you like without any throttling". That's **out of date**; ignore it.
- Responses include `requestNumber` ("number of request by this API key within the last 24 hours"), which suggests a daily window. Handle 429.

### Terms
- Metadata licence (FAQ): "All metadata from Europeana's APIs are provided as **CC0**, meaning you can reuse that metadata as you wish without any restrictions." Media follow each item's `rights`.
- Key confidentiality ("Accessing the APIs"): "Do not share them with third parties or expose them in user interfaces, code, or markup". An app shipped to users should have each user enter their own personal key.
- Abuse: "If abuse of an API key is detected, Europeana Foundation may impose additional usage limits or suspend or revoke access".
- The API Terms page itself returned 403 behind Cloudflare. These excerpts come from search snippets: "Users of the API are requested to use the 'Powered by Europeana' logo in close proximity to the Metadata whenever such Metadata are displayed". Europeana may "terminate individual Europeana API-keys that are used to display data … in contexts that are illegal, pornographic, defamatory or can be detrimental to the reputation of Europeana".
- Usage Guidelines for Metadata ask for attribution to the data sources "whenever possible" (a request, not a requirement).

### Errors
- Documented: 401 "Authentication credentials were missing or authentication failed", **429** "the application has reached its usage limit", 500. The body has `success:false` and `error`.
- Tested 2026-10-05:
  - No key: **401** `{"success":false,"error":"Unauthorized","message":"Invalid API key provided!","code":"invalid_apikey"}`
  - Bad key: **401** `{"success":false,"error":"API key is invalid","message":"Please register for an API key","code":"401_key_invalid"}`

---

## 5. DigitalNZ API v3: key is OPTIONAL

- Official getting-started page: "**You no longer need a key to access the DigitalNZ API.**" Blog (13 Dec 2021): keys are encouraged for regular or high-volume use and apps, and "a maximum query rate limit applies across all unauthenticated public requests" (number not published).
- Keyed requests use header **`Authentication-Token: <key>`**.
- Tested without a key on 2026-10-05: `GET https://api.digitalnz.org/v3/records.json?text=smith&per_page=1&fields=id,title,date,landing_url` → 200 JSON `{"search":{"page","per_page","result_count","results":[{id,title,date[],landing_url}]},"api_terms_of_use":"https://api.digitalnz.org/terms-of-use"}`.
- It includes Papers Past metadata. The adapter can be keyless with an optional key field.

## 6. FamilySearch API: not usable for this

- Developer site: "Access to the FamilySearch REST API … is free for both individuals and organizations". You apply via the "Third-Party Service Provider Application Form" (https://forms.office.com/r/EstYaQAZSm, linked from developers.familysearch.org) and approval comes by email.
- But the application page (https://www.familysearch.org/innovate/apply) says: "**API access for individual personal use will not be granted.**" Gallery or compatible-solution listing requires "a legal, registered business… Sole Proprietorships will not be eligible" (search snippet of the compatibility docs).
- Authentication is OAuth2 with **each user logging in to FamilySearch**. Only Places and Standardized Dates allow unauthenticated sessions.
- **Conclusion:** individual users can't plug in their own key for record search. Leave it out, or link out to familysearch.org search URLs.

## 7. Chronicling America: already done (keyless, loc.gov). Not repeated.

---

## Cross-API adapter notes
- **Where the key goes:**
  - DPLA: `?api_key=`
  - NARA: header `x-api-key`
  - Trove: header `X-API-KEY` (or `key=`)
  - Europeana: header `X-Api-Key` (`wskey=` deprecated)
  - DigitalNZ: optional header `Authentication-Token`
- **How to detect a bad key:**
  - DPLA: 403 with `error=invalid_api_key`
  - Trove: 401
  - Europeana: 401 with `code` in `invalid_apikey` / `401_key_invalid`
  - **NARA: 200 text/html.** Check the content-type.
- **Paging:**
  - DPLA: page ≤100 × page_size ≤500
  - NARA: page/limit ≤1000, or searchAfter
  - Trove: cursor `s`/`nextStart`, n ≤100
  - Europeana: start+rows ≤1000 or cursor, rows ≤100
- **Quota-sensitive:** NARA at 10k per month (count requests locally) and Trove at 200 per minute.
- **Getting a key, by speed:**
  - DPLA and Europeana personal: instant, self-serve.
  - NARA: email a human; time not stated.
  - Trove: 7–28 days with justification. Full text needs an extra exemption, and keys expire yearly.
