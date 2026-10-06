# No-key genealogy search APIs: live verification (2026-10-05)

All tests were run with curl from Rob's Mac, using `User-Agent: KindredCompass/1.0 research test`, at most about 5 requests per API and at least 3 s apart. Raw responses are saved in `./raw/`.

## Summary

| # | API | Status | Key? | Live result |
|---|-----|--------|------|-------------|
| 1a | LoC page full text (`fulltext_file` → tile.loc.gov text-services) | **WORKS** | No | 200 in 0.9 s. Full page OCR came back as JSON and contains the Alonzo Whitcomb obituary |
| 1b | LoC `/resource/...?fo=json` (page metadata) | **WORKS**, but a slow `q=` sometimes fails | No | With `&q=whitcomb`: **503 after 45 s**. Without `q` and with `&at=page,resource,segments`: 200 in 1.5 s |
| 1c | LoC Chronicling America search (`/collections/chronicling-america/?fo=json`) | **WORKS but slow and flaky** | No | First try: 503 after 45 s. Retry: 200 in 33 s, **1.8 MB** for 3 results |
| 1d | LoC books / genealogy search (`/books/?fa=subject:genealogy`) | **WORKS** | No | 200 in 3.2 s. 27 hits, with `text_file`/`fulltext_derivative` URLs |
| 2a | Internet Archive `advancedsearch.php` | **WORKS** | No | 200 in 0.4 s |
| 2b | IA Scrape API `/services/search/v1/scrape` | **WORKS** | No | 200 in 0.8–1.3 s |
| 2c | IA full-text (in-book) search: Open Library `search/inside.json` | **WORKS (slow)** | No | 200 in 21 s, 59 hits for `"Alonzo Whitcomb"`, with highlighted snippets |
| 2d | IA FTS backend `be-api.us.archive.org/ia-pub-fts-api` | **BLOCKED / unstable** (beta, undocumented except in the Python lib) | No | 503 "No server is available" |
| 2e | IA legacy `api.archivelab.org/v1/search/books` | **NOT AVAILABLE** (dead) | — | Timed out after 30 s with no connection |
| 2f | IA `_djvu.txt` OCR download | **WORKS** | No | 200 in 2.9 s, 76 KB |
| 3 | DigitalNZ v3 `records.json` (includes Papers Past) | **WORKS without a key** (a key is recommended) | Optional | 200 in 1.2 s |
| 4 | UK National Archives Discovery API | **WORKS** (no key; terms ask you to register your IP by email) | No (IP registration requested) | 200 in 0.3–0.45 s |
| 5 | WikiTree API `searchPerson` / `getProfile` | **WORKS** | No (`appId` strongly advised) | 200 in 0.3–0.7 s |
| 6 | Arkivverket / Digitalarkivet | **NOT AVAILABLE** as a general person-search API. Only a legacy **1910-census geo API** works | No | `api.digitalarkivet.no/v1/census/1910/search_property_geo` → 200 in 0.45 s |
| 7a | FamilySearch API | **NEEDS KEY + partner approval** | Yes | Not tested |
| 7b | HathiTrust | **NOT AVAILABLE** (no full-text search API; Bib API looks up by ID only) | — | Not tested |
| 7c | Elephind 2.0 | **NOT AVAILABLE** (subscription site relaunched Sept 2025, no documented API) | — | Not tested |
| skip | Europeana, Trove | NEEDS KEY (skipped as instructed) | Yes | — |

---

## 1. Library of Congress (loc.gov JSON API)

**Docs**
- Endpoints: https://www.loc.gov/apis/json-and-yaml/requests/endpoints/
- Text Services: https://www.loc.gov/apis/micro-services/text-services/
- Limits: https://www.loc.gov/apis/json-and-yaml/working-within-limits/
- Legal: https://www.loc.gov/legal/

**Terms / limits**
- Published rate limits:

  | Service | Limit | Block if exceeded |
  |---|---|---|
  | JSON/YAML API for loc.gov | "20" requests per minute | "1 hour" |
  | Text Services | "150" requests per minute | "1 hour" |
  | Image Services | "150" requests per minute | "1 hour" |

  The limits page warns that clients may get "429 status codes or HTML pages with CAPTCHAs" even under the limits when traffic is heavy. It advises that "rate limiting is strongly encouraged" and that clients "pause when encountering 429".
- The legal page is stricter for crawlers: "software programs submit a total of no more than 10 requests per minute". LoC reserves the right to block IPs that don't comply.
- No API key and no attribution format are required.
- Rights: the Library generally does not own the rights. Chronicling America pages from before 1927 are public domain in practice.
- **Recommendation:** throttle loc.gov to at most 10/min per IP (the most conservative figure). Text-services calls can go faster (150/min). Back off for an hour on a 429 or a CAPTCHA HTML page, and treat a 503 after a long wait as "LoC overloaded".

### 1a. Full OCR text of one Chronicling America page (CONFIRMED)

Step 1, get the page record without `q=`:
```
GET https://www.loc.gov/resource/sn86086481/1900-03-29/ed-1/?sp=5&fo=json&at=page,resource,segments
→ 200, 1.49 s, 6.9 KB
```
The same URL with `&q=whitcomb` and without `at=` returned **503 after 45 s**. Drop `q` on resource fetches and always pass `at=`.

The text URL appears in two places:
- `resource.fulltext_file`
- `page[]`, in the entry with `"use":"text"` → `fulltext_service`

Step 2, fetch the text:
```
GET https://tile.loc.gov/text-services/word-coordinates-service?segment=/service/ndnp/mb/batch_mb_gaia_ver02/data/sn86086481/0051717161A/1900032901/0911.xml&format=alto_xml&full_text=1
→ 200, 0.88 s, 30 KB, application/json
```

Response shape: `{ "<segment path>": { "full_text": "...newline-separated OCR..." } }`. Trimmed real excerpt:
```
"...BUSY LIFE IS ENDED\n\nAlonzo Whitcomb Dies of Bright’s\nDisease, After Rounding Out\nFour Score Years\n...He was born at Saxton’s River, Vt.,\nApril 30, 1818, and was a descendant\nof John Whitcomb, who came to Boston\nfrom England in 1630..."
```

Other useful `resource` fields:
- `pdf`
- `iiif_manifest_url`
- `segment_count` (pages in the issue)
- `page[].url` (.jp2, .pdf, ALTO `.xml`)

`segments[0]` holds page metadata:
- `date`, `title` ("Image 5 of The Worcester spy (Worcester, Mass.), March 29, 1900")
- `location_city/county/state/country`, `partof_title`, `number_lccn`, `number_page`
- `description` (the first ~1,000 characters of the OCR, not a keyword snippet)

**Shortcut without step 1:** the docs say Text Services also accepts `&q=term&relevant_snippet=1` for keyword snippets. We did not test this; the `full_text=1` path is the verified one.

### 1c. Chronicling America newspaper search
```
GET https://www.loc.gov/collections/chronicling-america/?q=whitcomb&dates=1900/1900&fa=location_state:massachusetts&c=3&fo=json
→ 1st try: 503 after 45.3 s (that request also had at=results,pagination and dates=1900-03-01/1900-03-31)
→ retry: 200, 33.3 s, 1.86 MB for 3 results (facets are heavy; try &at=results,pagination to slim it)
```

**Pagination:** `pagination.{total, current, perpage, next, last, page_list}`. Pages are `sp=N` and page size is `c=N` (options 25/50/100/150). Total here was 166.

**Filters:**
- Dates: `dates=YYYY/YYYY` or `dates=YYYY-MM-DD/YYYY-MM-DD`
- Place: `fa=location_state:massachusetts`, `fa=location_city:worcester`, `fa=location_county:...`; join several with `|` (`%7C`)
- Newspaper title: `fa=partof_title:...`

**Per-result fields:** `title`, `date`, `id`, `url` (page URL including `&q=`), `partof_title`, `location_state`, `location_city`, `number_page`, `description` (page OCR excerpt), `image_url`, `resources`.

Trimmed real result:
```json
{"title":"Image 5 of The Worcester spy (Worcester, Mass.), March 29, 1900","date":"1900-03-29",
 "id":"http://www.loc.gov/resource/sn86086481/1900-03-29/ed-1/?sp=5",
 "url":"https://www.loc.gov/resource/sn86086481/1900-03-29/ed-1/?sp=5&q=whitcomb",
 "partof_title":["the worcester spy (worcester, mass.) 1898-1904"],"location_state":["massachusetts"],
 "location_city":["worcester"],"number_page":["0000000005"]}
```

### 1d. Other loc.gov collections: family histories and books

`/search/?...&fa=original-format:book` **302-redirects** to `/books/?...`, so call `/books/` directly and follow redirects (`-L`).
```
GET https://www.loc.gov/books/?q=whitcomb+family&fa=subject:genealogy&dates=1850/1920&c=5&fo=json
→ 200, 3.2 s, 105 KB, total 27
```

**Top-level keys:** `results`, `pagination`, `facets`, `search`, `breadcrumbs`, `content`, …

**Per-result fields:** `title`, `date`, `dates`, `id`, `url`, `contributor`, `subject`, `location`, `online_format`, `partof`, `description`, `resources[]`. Each `resources[]` entry has:
- `text_file` (plain-text OCR of the whole book)
- `fulltext_derivative` (JSON)
- `pdf`
- `url`

Trimmed real result:
```json
{"title":"Genealogies of Hadley families,","date":"1862","id":"http://www.loc.gov/item/09017086/",
 "location":["massachusetts","hatfield","hadley","amherst",...],"online_format":["online text","image","pdf"]}
{"title":"The county families of the United kingdom","date":"1882","id":"http://www.loc.gov/item/unk81054391/",
 "subject":["gentry","great britain","genealogy"],"contributor":["walford, edward"],
 "resources":[{"text_file":"https://tile.loc.gov/storage-services/public/gdc/0051398103A/0051398103A.text.txt",
   "fulltext_derivative":"https://tile.loc.gov/storage-services/public/gdc/0051398103A/0051398103A.text.json",
   "pdf":"https://tile.loc.gov/storage-services/public/gdc/0051398103A/0051398103A.pdf",
   "url":"https://www.loc.gov/resource/gdc.0051398103A/"}]}
```

**Other useful facets:**
- `fa=subject:genealogy`, `fa=subject:registers of births, etc.`
- `fa=location:massachusetts`
- `fa=online-format:online text`
- Other format endpoints: `/manuscripts/`, `/maps/` (e.g. Sanborn), `/photos/`, `/audio/`

---

## 2. Internet Archive

**Docs**
- Search help: https://archive.org/help/aboutsearch.htm
- Scrape API (Swagger): https://archive.org/services/search/v1
- Python library FTS source: https://archive.org/developers/_modules/internetarchive/search.html
- Open Library API guidelines: https://openlibrary.org/developers/api
- Open Library search-inside: https://openlibrary.org/dev/docs/api/search_inside

**Terms / limits**
- The IA Terms of Use page (https://archive.org/about/terms.php) is JS-rendered and could not be extracted. The clause widely cited in secondary sources and IA forum threads is that access "is provided at no cost to you and is granted for scholarship and research purposes only". Verify it manually in a browser.
- IA publishes no numeric rate limit.
- `robots.txt` only disallows `/control/` and `/report/`, so search endpoints and `/download/` are not disallowed.
- Downloading `_djvu.txt` for public-domain (pre-1930) items is normal and permitted use. For in-copyright or lending-library items (e.g. `printdisabled`, `inlibrary`), the text file is usually access-restricted; do not try to get around that.
- Open Library guidelines:
  - Rate: "1 request per second" anonymous, "3 requests per second" when identified.
  - Identify yourself with a User-Agent containing "the name of your application and ... contact email".
  - Do: "Make useful, time-sensitive requests on behalf of human users" and "Cache responses whenever possible".
  - Don't: "Please do not use our APIs to bulk download metadata". Bulk use should go to the dumps instead.
  - User-initiated searches fit these terms exactly.

### 2a. advancedsearch.php (metadata search, Solr)
```
GET https://archive.org/advancedsearch.php?q=title%3A%28whitcomb%29+AND+mediatype%3Atexts+AND+date%3A%5B1850-01-01+TO+1930-12-31%5D&fl[]=identifier&fl[]=title&fl[]=date&fl[]=year&fl[]=creator&fl[]=subject&fl[]=coverage&fl[]=collection&fl[]=description&rows=3&page=1&sort[]=date+asc&output=json
→ 200, 0.43 s, numFound 290
```

**Shape:** `{responseHeader:{status,QTime,params}, response:{numFound,start,docs:[...]}}`

**Pagination:** `rows` + `page` (1-based). Deep paging is capped (around 10k); use the scrape API for more.

**Filters:**
- Dates: `date:[YYYY-MM-DD TO YYYY-MM-DD]` or `year:[1850 TO 1930]`
- Place: `coverage:` is sparse, so add place words to `q` or use `subject:`
- Genealogy collections: `collection:allen_county` (Allen County Public Library's genealogy collection), `collection:americana`, `subject:genealogy`
- City directories: `subject:"city directories"` or `title:directory AND subject:<city>`

Trimmed real doc:
```json
{"identifier":"sermon00seym","title":"Sermon & addresses at the ordination of Mr. William C. Whitcomb : as pastor of the Congregational Church and Society, in Stoneham, Mass., ...","creator":"Seymour, J. L.","date":"1855-01-01T00:00:00Z","year":1855,"subject":"Whitcomb, William C. (William Chalmers), 1820-1864.","collection":["congregationallibrary","americana"]}
```

**Item URL:** `https://archive.org/details/{identifier}`

### 2b. Scrape API (cursor paging)
```
GET https://archive.org/services/search/v1/scrape?q=whitcomb%20AND%20(collection%3Agenealogy%20OR%20subject%3Agenealogy)%20AND%20year%3A%5B1850%20TO%201930%5D&fields=identifier,title,year,creator,subject,collection&count=100
→ 200, 0.83 s, {"items":[...],"count":14,"total":14}
```
- `collection:genealogy` alone returned **0 results**. The genealogy books sit in `allen_county`, so use `subject:genealogy` and/or `collection:allen_county`.
- `count` must be between 100 and 9999 (the minimum is 100).
- When there are more results, the response includes `cursor`; pass `&cursor=...` to get the next batch. With no cursor in the response, there are no more batches.

Trimmed real item:
```json
{"identifier":"annalsreminiscen00whit_0","title":"Annals and reminiscences of Jamaica Plain","creator":["Whitcomb, Harriet Manning","Rogers, Bruce, 1870-1957. cn"],"collection":["allen_county","americana"],"subject":"genealogy","year":1897}
```

### 2c. Full-text search inside books (WORKS via Open Library)
```
GET https://openlibrary.org/search/inside.json?q=%22Alonzo%20Whitcomb%22&limit=3
→ 200, 21.2 s, 11 KB, hits.total = 59
```
- **Top-level keys:** `hits`, `took`, `timed_out`, `_shards`, `aggregations`, `fts-api`. This is the IA FTS Elasticsearch response.
- Paging: `page=N` (Open Library convention; not verified).
- Date filtering: filter client-side on `fields.meta_year`.
- Snippets: highlighted terms are wrapped in `{{{ }}}`.

**Per-hit fields:**
- `fields.identifier[0]` → IA id
- `fields.meta_title`, `meta_creator`, `meta_year`, `meta_date`, `meta_collection`
- `fields.page_num`
- `highlight.text[]` (snippets)
- `edition.{key,title,authors,ocaid}`
- `availability.{status,is_readable,is_lendable}`

Trimmed real hit:
```json
{"fields":{"identifier":["americanlathebui0000cope"],"meta_title":["American lathe builders : 1810-1910"],"meta_year":[2001],"page_num":[[214]],"meta_collection":["internetarchivebooks","printdisabled",...]},
 "highlight":{"text":["partnership of Carter Whitcomb and his brother {{{Alonzo Whitcomb}}} (1818-1900) formed in 1849 to make chain drive", "...{{{Alonzo Whitcomb}}}, Jr. (1862-1936) took over when his father died in 1900..."]},
 "availability":{"status":"private","is_readable":false,"is_printdisabled":true}}
```
- Results include in-copyright lending books (`availability.status`). Show the snippet and link to `https://archive.org/details/{id}/page/n{page}`; don't fetch their text.
- **Per-book search inside:** `https://{server}/fulltext/inside.php?item_id={id}&doc={id}&path={dir}&q=...`. Get `server` and `dir` from `https://archive.org/metadata/{id}`. Open Library labels it "an experimental API and can change in future". Not tested live.

### 2d/2e. Other FTS endpoints
- `https://be-api.us.archive.org/ia-pub-fts-api?q=!L "Alonzo Whitcomb"&size=3` (used by the `internetarchive` Python library, beta): **503 "No server is available"** on our test. Leaving out `q=` returns `{"msg":"The parameter q or text is required."}`. Not reliable; prefer 2c.
- `https://api.archivelab.org/v1/search/books`: **dead** (connection timeout).

### 2f. Book OCR text
```
GET https://archive.org/download/{id}/{id}_djvu.txt
→ 302 to dnNNN.*.archive.org/0/items/{id}/{id}_djvu.txt → 200, 2.9 s, 76 KB plain text
```
- Follow redirects.
- The file name is not always `{id}_djvu.txt`. Check `https://archive.org/metadata/{id}` → `files[]` for the "DjVuTXT" format.

---

## 3. DigitalNZ API v3 (includes Papers Past)

**Docs**
- https://digitalnz.org/developers/api-docs-v3
- Search records: https://digitalnz.org/developers/api-docs-v3/search-records-api-v3
- Swagger: https://app.swaggerhub.com/apis-docs/DigitalNZ/Records/3

**Terms:** https://digitalnz.org/about/terms-of-use/developer-api-terms-of-use

**Key status:** the key is now optional. DigitalNZ removed "the requirement for an API key (secret ID) to access public data", but "a maximum query rate limit applies across all unauthenticated public requests". A key goes in the header `Authentication-Token: {key}`.

**Terms:**
- Rate: "10,000 API calls per day, per API key". Users without a key share "10,000 API calls per day in total" — this pool is shared by every anonymous caller.
- Non-commercial use of metadata is permitted. Commercial use needs the commercial terms and a key.
- Caching: "cache DigitalNZ metadata ... for up to 30 days" for non-commercial use.
- Attribution, required: "identify the online source ... and provide a hyperlink to the page on the online source's website containing the content item" (use `landing_url`/`source_url`). Crediting DigitalNZ itself is optional but appreciated.
- **Recommendation:** get a free key for production, since the anonymous pool is shared nationally.

**Request (tested):**
```
GET https://api.digitalnz.org/v3/records.json?text=whitcomb&and[primary_collection][]=Papers+Past&and[year][]=1900&per_page=3&page=1
→ 200, 1.2 s, result_count 41
GET https://api.digitalnz.org/v3/records.json?text=whitcomb+otago&and[primary_collection][]=Papers+Past&and[decade][]=1890&fields=id,title,display_date,date,landing_url,source_url,collection_title,fulltext&per_page=2&page=2&sort=date&direction=asc&facets=year&facets_per_page=3
→ 200, 1.4 s, result_count 82, facets {"year":{"1899":22,"1890":16,"1893":10}}
```
- `and[collection_title][]=...` returned **400** `"No field configured ... with name 'collection_title'"`. You cannot filter on newspaper title that way.

**Shape:** `{search:{page, per_page, result_count, request_url, results:[...], facets}}`

**Pagination:** `page` (1-based) and `per_page` (max 100).

**Filters:**
- Dates: `and[year][]=1900`, `and[decade][]=1890`, `and[century][]=1800`. You can also use `or[year][]=...` repeated (not tested); no range syntax is documented.
- Place: `geo_bbox=N,W,S,E` (rarely set for newspapers), or add place words to `text`.
- Sort: `sort=date&direction=asc|desc`.

**Field mapping:**

| Need | Field |
|---|---|
| title | `title` ("OVERLAND PASSENGERS. (Otago Daily Times, 27 June 1900)") |
| date | `date[0]` / `display_date` |
| url | `landing_url` (Papers Past article) |
| text | `fulltext` (**full article OCR**, lower-cased; can be many KB, so trim with `fields=`) |
| newspaper | `collection_title[0]` / `publisher[0]` |
| id | `id` |
| rights | `rights`, `usage` |

Trimmed real result:
```json
{"id":24180096,"title":"OVERLAND PASSENGERS. (Otago Daily Times, 27 June 1900)","display_date":"27-06-1900","date":["1900-06-27T00:00:00.000Z"],
 "collection_title":["Otago Daily Times","Papers Past"],"primary_collection":["Papers Past"],"category":["Newspapers"],
 "rights":"No known copyright restrictions","usage":["Share","Modify","Use commercially"],
 "landing_url":"https://paperspast.natlib.govt.nz/newspapers/ODT19000627.2.10",
 "fulltext":"overland passengers ... messrs j burns r meffin jm clark s j evans b e h whitcomb j webster ..."}
```

---

## 4. The National Archives (UK) Discovery API

**Docs**
- Sandbox: https://discovery.nationalarchives.gov.uk/API/sandbox/index
- Terms: https://www.nationalarchives.gov.uk/terms-and-conditions/discovery-for-developers-about-the-application-programming-interface-api/

**Status:** live. It is described as a beta "with some functionality still to be developed". Our calls worked from an unregistered IP with no key.

**Terms (verbatim):**
- Access: "If you would like access to our API, please contact us via email and include the IP address from which you will be sending requests" (webmaster@nationalarchives.gov.uk). **Send that email before production.**
- Licence: use is allowed "for personal use, educational purposes or commercial use under the Open Government Licence".
- Rate: "you should make no more than 3,000 API calls per day at a rate of no more frequently than one request per second. We may choose to limit the number of API calls more formally in the future."
- Caching: "Please do not cache or store any content returned by the API." This matters for result caching.
- Branding: no use of the TNA logo.

**Request:** send header `Accept: application/json`; otherwise the response is XML.
```
GET https://discovery.nationalarchives.gov.uk/API/search/records?sps.searchQuery=whitcomb&sps.dateFrom=1850-01-01&sps.dateTo=1920-12-31&sps.resultsPageSize=3&sps.page=0
→ 200, 0.30 s, count 978
GET https://discovery.nationalarchives.gov.uk/API/search/records?sps.searchQuery=whitcomb%20worcester&sps.dateFrom=1800-01-01&sps.dateTo=1900-12-31&sps.heldByCode=TNA&sps.resultsPageSize=2&sps.batchStartMark=*&sps.sortByOption=DATE_ASCENDING
→ 200, 0.45 s, count 3, nextBatchMark "-3565900800000|-3534451200000"
```

**Shape:** `{records:[...], count, nextBatchMark, taxonomySubjects, timePeriods, departments, catalogueLevels, closureStatuses, sources, repositories, heldByReps, ...}`

**Pagination:** two options.
- `sps.page` (0-based) + `sps.resultsPageSize`
- Cursor: `sps.batchStartMark=*`, then pass back `nextBatchMark`. It is empty when you page by `sps.page`.

**Filters:**
- Dates: `sps.dateFrom` / `sps.dateTo` (YYYY-MM-DD)
- Holder: `sps.heldByCode=TNA|OTH|ALL` (OTH = local record offices)
- Also: `sps.departmentReferences`, `sps.catalogueLevels`, `sps.sortByOption`
- Place: no structured place filter (`places[]` is usually empty), so put the place in `sps.searchQuery`.

**Field mapping:**

| Need | Field |
|---|---|
| title | `title` |
| date | `coveringDates` (text), `startDate`/`endDate` (dd/mm/yyyy), `numStartDate` |
| url | `https://discovery.nationalarchives.gov.uk/details/r/{id}` |
| snippet | `description` (+ `context`) |
| place | `heldBy[]`, `places[]` |
| id | `id`, plus `reference` (citation such as "MH 12/14021/257") |

Trimmed real record:
```json
{"id":"C14237660","reference":"MH 12/14021/257","coveringDates":"1856 Jan 21","startDate":"21/01/1856","heldBy":["The National Archives, Kew"],"department":"MH",
 "title":"Folio(s) 322-323. Printed annual return from Henry Saunders, Clerk to the Guardians of the Kidderminster...",
 "description":"... 'Insane Persons, Lunatics and Idiots' chargeable to each parish ... Elizabeth Whitcomb, from Kidderminster Foreign. ..."}
{"id":"c8abafe4-7b4e-4d1d-9897-c886fb8c7718","reference":"MS 517/A/8/5/38/47","title":"Whitcombe (a.k.a. Whitcomb), William","coveringDates":"1910",
 "heldBy":["Birmingham: Archives, Heritage and Photography Service"],"description":"Settlement papers and visitors' reports. Year of emigration: 1910"}
```

---

## 5. WikiTree API

**Docs**
- https://github.com/wikitree/wikitree-api (README.md, searchPerson.md, getProfile.md)
- https://www.wikitree.com/wiki/Help:API_Documentation

**Terms:**
- The README asks for `appId`: "API queries without an id will be subject to strict rate limits." No numbers are published.
- Only public and open profiles are returned without login. For a private profile, "you only receive a privacy-limited data set".
- The wikitree.com Help/Terms pages returned **HTTP 202 with an empty body** (a bot challenge) to curl. We did not try to bypass it; the following comes from search snippets of those pages:
  - ToS: "No Automated Copying ... any automated system ... that ... sends more request messages ... than a human can reasonably produce". Use the API, not page scraping.
  - Help:App_Policies: "Biographies from WikiTree should not be displayed on external websites". Data should not be cached beyond the user's session.
  - The service is for individual, non-commercial use unless WikiTree consents.
- **WikiTree is a contributed, collaborative tree, not a primary source.** Label it as such. Show names, dates and places, link to `https://www.wikitree.com/wiki/{Name}`, and don't show the bio text.

**Requests (tested):**
```
GET https://api.wikitree.com/api.php?action=searchPerson&LastName=Whitcomb&BirthDate=1820-01-01&dateSpread=10&fields=Id,Name,FirstName,MiddleName,LastNameAtBirth,BirthDate,DeathDate,BirthLocation,DeathLocation,Privacy,Father,Mother,Gender&limit=3&start=0&appId=KindredCompass
→ 200, 0.28 s, total 569
GET https://api.wikitree.com/api.php?action=getProfile&key=Whitcomb-701&fields=Id,Name,FirstName,LastNameAtBirth,BirthDate,DeathDate,BirthLocation,DeathLocation,Father,Mother,Spouses,Children,Bio,DataStatus&bioFormat=text&appId=KindredCompass
→ 200, 0.29 s
```
- A narrower search (`FirstName=Alonzo&BirthDate=1818-04-30&dateSpread=5&BirthLocation=Vermont`) returned `total 0`.
- Undated profiles match by default (one hit had `BirthDate 0000-00-00`). Add `dateInclude=both` to require dates.

**Shape:**
- searchPerson: `[ {status:0, matches:[...], total, start, limit} ]`. Note it is wrapped in an array.
- getProfile: `[ {page_name, profile:{...}, status} ]`

**Pagination:** `start` + `limit` (1–100).

**Filters:**
- Names: `FirstName`, `LastName`
- Dates: `BirthDate`/`DeathDate` (YYYY-MM-DD) + `dateSpread` (1–20 years), `dateInclude=both|neither`
- Places: `BirthLocation`, `DeathLocation`
- Family: `fatherLastName`, `motherLastName`
- Surname matching: `skipVariants=1`, `lastNameMatch=strict`

**Field mapping:**

| Need | Field |
|---|---|
| title | `FirstName` + `LastNameAtBirth` |
| date | `BirthDate` / `DeathDate` (`0000-00-00` means unknown; `1853-00-00` means year only) |
| url | `https://www.wikitree.com/wiki/{Name}` |
| place | `BirthLocation` / `DeathLocation` |
| id | `Id` / `Name` (WikiTree ID, e.g. Whitcomb-701) |
| parents | `Father`, `Mother` (numeric Ids) |

Trimmed real match:
```json
{"Id":10713743,"Name":"Whitcomb-701","FirstName":"James","LastNameAtBirth":"Whitcomb","BirthDate":"1824-10-19","DeathDate":"1886-07-18",
 "BirthLocation":"Richmond, Chittenden, Vermont, United States","DeathLocation":"Sacramento, California, United States",
 "Privacy":60,"Privacy_IsOpen":true,"Gender":"Male","Father":5176241,"Mother":5176240}
```

`getProfile` with `fields=Bio` returned wiki markup even with `bioFormat=text`. Its source list can be mined for citations, but don't display it.

---

## 6. Arkivverket / Digitalarkivet (Norway)

**Status:** NOT AVAILABLE as a general, documented person-search API.
- The website person search (https://www.digitalarkivet.no/search/persons) is HTML only.
- `https://api.digitalarkivet.no/` and `https://www.digitalarkivet.no/api` both return **404**.

**robots.txt** (www.digitalarkivet.no):
- `Disallow: /` for a long list of AI agents, including `Claude-User`, `ClaudeBot`, `ChatGPT-User`, `anthropic-ai`.
- `User-Agent: * Crawl-delay: 5`
- **Do not scrape the HTML person search.**

A third-party unofficial wrapper exists (github.com/toreau/digitalarkivet-api-v2). It wraps the public HTML pages, so it is not an official API and the same robots and terms concerns apply.

**Legacy official API that still works:** the 1910 census, searched by geographic point. Docs (PDF, 2022-06-16): https://xml.arkivverket.no/folketellinger/API_1910_koord.pdf
```
GET https://api.digitalarkivet.no/v1/census/1910/search_property_geo?latitude=61.2130&longitude=6.5660&precision=5000&include_persons=1&limit=1
→ 200, 0.45 s, count 181
```
- The documented example (`&s=Berg*`, no precision) returned `{"count":0,"results":[],"total_found":0}`.
- Parameters: `latitude`, `longitude`, `precision` (m), `s` (name/property, `*` wildcard), `limit`, `page`, `include_persons=1`, `include_apartments=1`.
- Result fields: `gaardsnavn_gateadr`, `kommune_sokn`, `fylke`, `hendelsesdato`, `coordinates`, and `persons[]` with `fornavn`, `slektsnavn`, `fodselsaar`, `fodested`, `yrke`, `familiestilling`, `sivilstand`.

Trimmed real result:
```json
{"efid":"bf01036717000017","gaardsnavn_gateadr":"Nygaard","fylke":"Sogn og Fjordane","kommune_sokn":"Balestrand","hendelsesdato":"1910-12-01",
 "tittel_en":"1910 census for Balestrand","coordinates":{"lat":61.1724,"lon":6.5363},
 "persons":[{"id":"pf01036717000018","fornavn":"Hermund I.","slektsnavn":"Thue","kjonn":"m","familiestilling":"hf","sivilstand":"g","yrke":"gaardbr selveier, jægteskipper","fodselsaar":"1873-03-25","fodested":"Kvamsø Vik"}]}
```

Only niche value, since it covers 1910 only and needs coordinates. No terms page for this API was found. Treat it as public open data, keep it to 1 request every 5 s or slower, and link users to digitalarkivet.no for real searches.

---

## 7. Others

- **FamilySearch:** NEEDS KEY + partner approval.
  - Applicants fill in a Third-Party Service Provider application. An app key is issued for the sandbox; Beta and Production keys require a compatibility review and signed agreements (Compatible Product Affiliate Agreement, Security Assessment, Production App Key Request and Use Agreement).
  - "Sole Proprietorships are not eligible" for listing; only registered businesses and non-profits are.
  - Users also need OAuth2 sign-in.
  - Docs: https://developers.familysearch.org/main/docs/getting-started and https://www.familysearch.org/innovate/app-approval-considerations
- **HathiTrust:** NOT AVAILABLE for search.
  - The APIs are "not search APIs". The Bibliographic API looks up records by OCLC/LCCN/ISBN/HTID; the Data API (page OCR) needs a key.
  - Full-text search is web-only (babel.hathitrust.org/cgi/ls).
  - Possible use: after finding a book elsewhere, link to `https://catalog.hathitrust.org/api/volumes/brief/oclc/{n}.json`.
- **Elephind:** shut down in 2023 and relaunched as "Elephind 2.0" (Veridian) in September 2025 as a subscription site. No public API is documented. Skip.
- **Open Library search.json:** works without a key under the same guidelines as 2c. Useful for book metadata, but advancedsearch covers this.

---

## Implementation checklist

1. Use a per-host throttle:

   | Host | Limit |
   |---|---|
   | loc.gov | ≤10/min (published API limit is 20/min) |
   | tile.loc.gov | ≤150/min |
   | TNA | 1/s and ≤3,000/day |
   | DigitalNZ | anonymous pool of 10k/day shared nationally; get a key |
   | Open Library | 1/s, or 3/s with a contact-bearing UA |
   | archive.org | ~1/s polite |
   | WikiTree | low; always send `appId` |
   | Digitalarkivet | ≤1 per 5 s |

2. Send `User-Agent: KindredCompass/1.0 (+contact email)`, which Open Library explicitly asks for.
3. Use long timeouts: loc.gov searches took up to 33–45 s and can return 503. Open Library inside search took 21 s. Treat 429, 503, or a CAPTCHA HTML page as back-off-and-skip, never retry in a tight loop. For a LoC 429, wait an hour.
4. Caching rules differ by source:
   - DigitalNZ: up to 30 days.
   - TNA: "do not cache or store".
   - WikiTree: session only, no bios.
   - LoC and IA public-domain OCR: cache freely.
5. Always link back to the source page: DigitalNZ requires it, and it is good practice for all.
