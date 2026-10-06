# Census sources: what can be searched automatically (checked 2026-10-06)

| Source | Automated search | Storing results | Notes |
|---|---|---|---|
| 1950 U.S. census, https://1950census.archives.gov | Yes. Undocumented JSON API behind the site (`/api/search?state=MA&county=Worcester&name=Johnson&page=1&size=25`). robots.txt: `Crawl-delay: 1`, nothing disallowed. | Public federal records. The bulk route is the AWS Open Data bucket `s3://nara-1950-census`. | Each result is one schedule page. `names` holds noisy OCR; `transcribe` holds volunteer-corrected names. The API may change without notice. |
| Census of Ireland 1901/1911, National Archives of Ireland | Yes. `GET https://api-census.nationalarchives.ie/census/query?surname=&firstname=&county=&census_year=` (also `image_group=` for a whole household). robots: `Crawl-delay: 1`. | Reuse terms are not published, so unsaved results are trimmed after 30 days. | One row per person: age, relationship, occupation, birthplace, religion; 1911 adds years married and children. |
| FamilySearch | **No.** Its terms forbid automated searching or harvesting without written permission. | No | The app only builds links. Collection IDs were checked against FamilySearch's public collection metadata. |
| Ancestry | **No.** Its terms forbid programmatic access beyond standard human use. | No | The app only builds links (`/search/collections/<dbid>/?name=Given_Surname&birth=YEAR_place&birth_x=N-0-0&residence=YEAR_town-county-state-usa`). |
| Riksarkivet census (folkräkningar) | No (CAPTCHA; robots.txt blocks AI agents) | — | Links only. Riksarkivet's open data API (CC0) currently returns birth and marriage registers only. |

Collection IDs used for links are listed in `app/searchlinks.py` (`COLLECTIONS`).

Which censuses hold which fields (summarised in `app/checklist.py`) comes from NARA's census guides at https://www.archives.gov/research/census.
Massachusetts state censuses: name-level returns survive only for 1855 and 1865.
