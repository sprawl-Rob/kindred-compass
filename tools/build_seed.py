"""Build app/seed/directory_seed.json from curated entries.

The seed is versioned. Bump VERSION whenever entries change; the app applies new
versions on start-up (idempotently, preserving user edits field by field).
Facts here come from provider pages checked on CHECKED (raw findings in tools/research/); entries that could not be
checked are marked needs_verification and carry no unverified access/coverage claims.
Run:  .venv/bin/python tools/build_seed.py
"""
import json
from pathlib import Path

VERSION = 2
CHECKED = "2026-10-05"
SRC_AUTO = f"Provider pages checked {CHECKED} (page fetch or in-app browser)"
CHECKED_2 = "2026-10-07"
SRC_2 = f"Checked {CHECKED_2} in the in-app browser (search tested with a real query; terms and robots.txt read)"
US = {"country": "United States"}

P = []  # providers
C = []  # collections
R = []  # relations
W = []  # pathways


def prov(key, name, url, ptype, country=None, description=None):
    P.append({"key": key, "name": name, "homepage_url": url, "provider_type": ptype, "country": country, "description": description})


def coll(key, provider, name, url, **kw):
    e = {"key": key, "provider": provider, "name": name, "url": url,
         "entry_kind": "collection", "geo_scope": "unknown", "geo": [], "dates": [], "date_gaps": [], "languages": [],
         "record_types": [], "capabilities": [], "evidence_forms": [],
         "access_search": ["unknown"], "access_images": ["unknown"], "access_copies": ["unknown"],
         "integration_method": "outbound_link", "search_url": None, "search_url_template": None, "search_link_verified": False,
         "search_link_notes": None, "adapter_key": None, "terminology": [], "rights_notes": None, "limitations": None,
         "digitization_status": "unknown", "verification_status": "verified", "last_verified": CHECKED,
         "verification_source": SRC_AUTO, "link_health": "ok", "link_checked_at": CHECKED, "maintenance_notes": None,
         "tags": [], "pathways": []}
    e.update(kw)
    if e["verification_status"] == "needs_verification":
        e["last_verified"] = None
        e["link_health"] = kw.get("link_health", "unknown")
    if e["geo"] and e["geo_scope"] == "unknown":
        e["geo_scope"] = "listed"
    if e["search_url_template"] and e["search_link_verified"] and e["integration_method"] == "outbound_link":
        e["integration_method"] = "verified_search_link"
    C.append(e)


def dr(a, b, label=None):
    return {"from": a, "to": b, "label": label}


def state(region, county=None, municipality=None):
    return {"country": "United States", "region": region, "county": county, "municipality": municipality}


# ======================================================================= FOUNDATIONAL (US-first)
prov("familysearch", "FamilySearch", "https://www.familysearch.org/", "nonprofit_database", None,
     "Free genealogy service offering historical record search, full-text search of unindexed images, a catalog, and a research wiki.")
coll("familysearch-historical-records", "familysearch", "FamilySearch Historical Records (name search)", "https://www.familysearch.org/en/search/",
     entry_kind="search_service", repository_type="nonprofit_database", geo_scope="worldwide",
     description="Name-based search across FamilySearch's indexed historical record collections (e.g. birth, marriage, census, draft, and passenger records). Results link to collection information, citations and, where permitted, the original image.",
     record_types=["births", "baptisms", "marriages", "deaths", "burials", "censuses", "draft_registrations", "passenger_lists", "naturalization", "congregational_registers", "probate"],
     capabilities=["name_index", "browse_images"], evidence_forms=["index", "original_image"],
     access_search=["free"], access_images=["free", "free_account", "onsite"], access_copies=["unknown"],
     access_notes="Searching worked signed out in our check. Image access varies by collection: some images only at FamilySearch centers or affiliate libraries, some only on custodians' sites.",
     search_url="https://www.familysearch.org/en/search/",
     search_url_template="https://www.familysearch.org/en/search/record/results?q.givenName={given}&q.surname={surname}&q.birthLikeDate.from={year_from}&q.birthLikeDate.to={year_to}",
     search_link_verified=True, search_link_notes="Verified 2026-10-05 with a test query. The birth-year range behaves as a ranking hint, not a strict filter. Place parameters were not verified.",
     limitations="Index coverage varies by collection; many collections are images only (see Catalog and Full-Text Search).",
     languages=["Many (varies by collection)"], tags=["FamilySearch"], pathways=["african-american", "migration-immigration"])
coll("familysearch-full-text", "familysearch", "FamilySearch Full-Text Search", "https://www.familysearch.org/en/search/full-text",
     entry_kind="search_service", repository_type="nonprofit_database", geo_scope="worldwide",
     description="Machine-read (handwriting/OCR) full-text search across document images that have not been name-indexed, such as deeds, court documents, and church registers. Supports simple and advanced name/date/place searches.",
     record_types=["deeds", "court_cases", "wills", "probate", "congregational_registers", "military_service", "letters", "newspapers_general", "land_grants"],
     capabilities=["full_text"], evidence_forms=["original_image", "transcription"],
     access_search=["free_account"], access_images=["free_account", "onsite"],
     search_url="https://www.familysearch.org/en/search/full-text",
     search_link_notes="Results page requires sign-in, so the pre-filled URL pattern could not be verified.",
     limitations="Requires a free sign-in. Provider notes accuracy varies with handwriting style and image quality — try spelling variants and misreadings.",
     verification_status="partial", tags=["FamilySearch", "full text"])
coll("familysearch-catalog", "familysearch", "FamilySearch Catalog", "https://www.familysearch.org/en/search/catalog",
     entry_kind="catalog", repository_type="nonprofit_database", geo_scope="worldwide",
     description="Catalog of books, records, microfilm/image groups and other resources offered through FamilySearch, searchable by place, keyword, title, author, subject and surname. The main route to browse-only image sets that are not indexed.",
     record_types=["finding_aids", "collection_descriptions", "family_histories", "local_histories"],
     capabilities=["catalog", "browse_images"], evidence_forms=["finding_aid", "original_image", "published_analysis"],
     access_search=["free_account"], access_images=["free_account", "onsite"],
     search_url="https://www.familysearch.org/en/search/catalog",
     search_link_notes="Catalog results redirected to sign-in in our check; pre-filled URL not verified.",
     limitations="Catalog results required sign-in in our check. A separate FamilySearch Library Catalog lists physical items in Salt Lake City.",
     verification_status="partial", tags=["FamilySearch", "catalog", "browse images"])
coll("familysearch-wiki", "familysearch", "FamilySearch Research Wiki", "https://www.familysearch.org/en/wiki/Main_Page",
     entry_kind="guide", repository_type="nonprofit_database", geo_scope="worldwide",
     description="Community-edited research guides by place and topic that point to record sources at FamilySearch and elsewhere (marking paid sites).",
     record_types=[], capabilities=["catalog"], evidence_forms=["published_analysis", "finding_aid"],
     access_search=["free"], access_images=[], access_copies=[],
     search_url_template="https://www.familysearch.org/en/wiki/Special:Search?search={q}", search_link_verified=True,
     search_link_notes="Verified 2026-10-05 with a place query.",
     limitations="Guides, not records; community-edited.", tags=["guidance"])
coll("familysearch-us-archives-libraries", "familysearch", "FamilySearch Wiki: United States Archives and Libraries", "https://www.familysearch.org/en/wiki/United_States_Archives_and_Libraries",
     entry_kind="directory", repository_type="directory", geo=[US],
     description="Wiki guide listing U.S. archives and libraries useful for genealogy, as a starting point for finding local repositories.",
     capabilities=["catalog"], access_search=["free"], access_images=[], access_copies=[], tags=["directory", "local repositories"])

prov("ancestry", "Ancestry", "https://www.ancestry.com/", "commercial_database", "United States")
coll("ancestry-card-catalog", "ancestry", "Ancestry Card Catalog", "https://www.ancestry.com/search/collections/catalog",
     entry_kind="catalog", repository_type="commercial_database", geo_scope="worldwide",
     description="Searchable listing of Ancestry's record collections, filterable by category, location and decade; each entry shows its category and dates. Use it to find which Ancestry collection covers a place and period.",
     record_types=["births", "marriages", "deaths", "censuses", "electoral_rolls", "passenger_lists", "military_service", "newspapers_general", "probate", "trees", "photographs"],
     capabilities=["catalog", "name_index"], evidence_forms=["index", "original_image", "transcription", "contributed_tree"],
     access_search=["free"], access_images=["subscription"], access_copies=["subscription"],
     access_notes="The catalog can be searched free; most record images and transcriptions need a paid membership. Some libraries offer access.",
     search_url_template="https://www.ancestry.com/search/collections/catalog?keyword={q}", search_link_verified=True,
     search_link_notes="Verified 2026-10-05 with a place keyword.",
     limitations="Some collections are index-only. Contributed trees are clues, not proof.", tags=["catalog"])

prov("myheritage", "MyHeritage", "https://www.myheritage.com/", "commercial_database")
coll("myheritage-records", "myheritage", "MyHeritage historical records search", "https://www.myheritage.com/research",
     entry_kind="search_service", repository_type="commercial_database", geo_scope="worldwide",
     description="MyHeritage's search across its historical record collections, family trees, photos and member profiles.",
     record_types=["births", "marriages", "deaths", "censuses", "trees", "photographs"], capabilities=["name_index"],
     evidence_forms=["index", "original_image", "contributed_tree", "photograph"],
     access_search=["free"], access_images=["subscription"], access_copies=["subscription"],
     access_notes="From MyHeritage's help article (not directly verified): searching is free; a Data subscription is needed to view all record collections.",
     verification_status="needs_verification", maintenance_notes="Landing page showed a CAPTCHA to automated checks on 2026-10-05; details taken from a help article only.",
     limitations="Contributed trees are clues, not proof.")

prov("findmypast", "Findmypast", "https://www.findmypast.com/", "commercial_database", "United Kingdom")
coll("findmypast", "findmypast", "Findmypast", "https://www.findmypast.com/",
     entry_kind="search_service", repository_type="commercial_database",
     geo=[{"country": "United Kingdom"}, {"country": "Ireland"}],
     description="Subscription genealogy site focused on British and Irish family history, including the 1921 Census of England and Wales, the 1939 Register, and the British Newspaper Archive.",
     record_types=["censuses", "population_registers", "military_service", "births", "baptisms", "marriages", "deaths", "burials", "institutional_registers", "passenger_lists", "newspapers_general", "obituaries"],
     capabilities=["name_index", "full_text"], evidence_forms=["index", "transcription", "original_image", "contributed_tree"],
     access_search=["free"], access_images=["subscription", "free_account"], access_copies=["subscription"],
     access_notes="Free search results show limited information; most records need a subscription or pay-as-you-go credits (provider help centre).",
     terminology=["1939 Register", "parish registers", "British Newspaper Archive"], tags=["UK", "Ireland", "newspapers"])

prov("nara", "U.S. National Archives (NARA)", "https://www.archives.gov/", "national_archive", "United States")
coll("nara-genealogy", "nara", "National Archives genealogy resources & Catalog", "https://www.archives.gov/research/genealogy",
     entry_kind="repository", repository_type="national_archive", geo=[US],
     description="NARA's genealogy portal (census, military, immigration and naturalization guidance; microfilm catalog; records digitized by partners) and the National Archives Catalog of federal records with digitized items.",
     record_types=["censuses", "military_service", "military_pensions", "passenger_lists", "naturalization", "land_grants", "court_cases", "finding_aids"],
     capabilities=["catalog", "name_index", "browse_images", "onsite", "request_only"], evidence_forms=["original_image", "finding_aid", "index", "transcription"],
     access_search=["free"], access_images=["free", "onsite"], access_copies=["paid_retrieval", "onsite"],
     search_url="https://catalog.archives.gov/", search_url_template="https://catalog.archives.gov/search?q={q}", search_link_verified=True,
     search_link_notes="Catalog search verified 2026-10-05 with a surname query.",
     limitations="Not all records are online; many genealogical series are digitized only by partner sites. Ordering copies usually needs exact citations.",
     tags=["federal records"], pathways=["african-american", "indigenous", "migration-immigration"])
coll("nara-1950-census", "nara", "1950 U.S. Census (National Archives)", "https://1950census.archives.gov/",
     entry_kind="collection", repository_type="national_archive", geo=[US], dates=[dr(1950, 1950, "1950 census, released April 1, 2022")],
     description="NARA's official site for the 1950 federal population census.", record_types=["censuses"], capabilities=["name_index", "browse_images"],
     evidence_forms=["original_image", "index"], access_search=["free"], access_images=["free"], access_copies=["free"],
     verification_status="partial", maintenance_notes="Site existence confirmed via NARA genealogy pages on 2026-10-05; search behaviour not separately tested.")

prov("nehgs", "American Ancestors (New England Historic Genealogical Society)", "https://www.americanancestors.org/", "historical_society", "United States")
coll("american-ancestors", "nehgs", "American Ancestors databases", "https://www.americanancestors.org/search/advanced-search",
     entry_kind="search_service", repository_type="historical_society", geo=[US, {"country": "Canada", "region": "Quebec"}],
     description="Nonprofit genealogical society (founded 1845) with 1,000+ searchable databases strongest for New England and New York, plus "
                 "Quebec/French-Canadian indexes (American-Canadian Genealogical Society), U.S. censuses, SSDI, Massachusetts vital records 1841–1910, "
                 "probate, church and town records, journals and newspapers.",
     record_types=["births", "marriages", "deaths", "baptisms", "burials", "censuses", "probate", "wills", "congregational_registers", "journals",
                   "newspapers_general", "family_histories", "local_histories", "military_service", "naturalization", "tax_lists", "land_grants"],
     capabilities=["name_index", "catalog", "browse_images", "onsite"], evidence_forms=["index", "original_image", "published_analysis", "transcription"],
     access_search=["free"], access_images=["subscription"], access_copies=["subscription", "onsite", "paid_retrieval"],
     access_notes="The name index is searchable without logging in (results show name, database, volume and page); record images and full details need membership.",
     search_url="https://www.americanancestors.org/search/advanced-search",
     search_url_template="https://www.americanancestors.org/search/database-search?firstname={given}&lastname={surname}&fromyear={year_from}&toyear={year_to}&location={place}&allData=true&searchPage=Advanced-Search&exactRecordType=true",
     search_link_verified=True,
     search_link_notes="Verified 2026-10-07 with a real query (name, years, location). Not searched automatically: robots.txt for app.americanancestors.org disallows /SearchResults/.",
     verification_status="verified", last_verified=CHECKED_2, verification_source=SRC_2, link_checked_at=CHECKED_2,
     terminology=["vital records", "NEHGS Register"], tags=["New England", "New York", "Quebec", "membership"])

prov("findagrave", "Find a Grave", "https://www.findagrave.com/", "cemetery_index")
coll("find-a-grave", "findagrave", "Find a Grave memorials", "https://www.findagrave.com/",
     entry_kind="search_service", repository_type="cemetery_index", geo_scope="worldwide",
     description="Community-created memorials for burials worldwide, with cemetery listings, grave photos, plot details and biographical notes.",
     record_types=["burials", "photographs"], capabilities=["name_index"], evidence_forms=["photograph", "transcription", "contributed_tree"],
     access_search=["free"], access_images=["free"], access_copies=[],
     search_url_template="https://www.findagrave.com/memorial/search?firstname={given}&lastname={surname}&birthyear={year}&birthyearfilter=10",
     search_link_verified=True,
     search_link_notes="Verified 2026-10-05. A free-text location parameter is ignored by the site (place filtering needs its internal location id), so filter by place on the site.",
     limitations="User-contributed; memorial biographies and family links are clues, not proof.", tags=["cemeteries"])

prov("blm", "Bureau of Land Management", "https://www.blm.gov/", "government_agency", "United States")
PUBLIC_LAND_STATES = ["Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Florida", "Idaho", "Illinois", "Indiana",
                      "Iowa", "Kansas", "Louisiana", "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
                      "New Mexico", "North Dakota", "Ohio", "Oklahoma", "Oregon", "South Dakota", "Utah", "Washington", "Wisconsin", "Wyoming"]
coll("blm-glo-records", "blm", "BLM General Land Office Records", "https://glorecords.blm.gov/s/",
     entry_kind="collection", repository_type="government_agency", geo=[state(s_) for s_ in PUBLIC_LAND_STATES],
     dates=[dr(1788, None, "Land title records"), dr(1810, None, "Survey plats and field notes")],
     description="Federal land conveyance records for the Public Land States — patents (including homestead patents), survey plats, field notes, tract books and Master Title Plats — served from a modernized GLO Records portal launched July 13, 2026.",
     record_types=["land_grants"], capabilities=["name_index", "browse_images"], evidence_forms=["original_image", "index"],
     access_search=["free"], access_images=["free"], access_copies=["unknown"],
     search_url="https://glorecords.blm.gov/s/",
     search_url_template="https://glorecords.blm.gov/s/advanced-search?searchTerm=%2Fsearch%3Fq%3D{q}%26page%3D1%26pageSize%3D25",
     search_link_verified=True, search_link_notes="Keyword search (names, counties, companies) verified 2026-10-05 on the new portal. Old deep links from before July 2026 no longer work.",
     limitations="Provider: the site does not contain every federal title record issued. Homestead application files are at the National Archives, not here. Covers Public Land States only (not the original 13 colonies, Texas, etc.).",
     maintenance_notes="Geography is the 30 federal Public Land States (standard list; not re-verified on the BLM site). BLM replaced the GLO site on 2026-07-13; re-check the search link periodically. Overview page: https://www.blm.gov/services/land-records/glo",
     tags=["land"])

# ======================================================================= NEWSPAPERS, BOOKS, DISCOVERY
prov("loc", "Library of Congress", "https://www.loc.gov/", "national_library", "United States")
coll("loc-chronicling-america", "loc", "Chronicling America (Library of Congress)", "https://www.loc.gov/collections/chronicling-america/",
     entry_kind="collection", repository_type="newspaper_archive", geo=[US], dates=[dr(1736, 1963, "Coverage dates reported by the loc.gov API")],
     description="Free digitized U.S. newspaper pages from the National Digital Newspaper Program, with OCR full-text search, page images, PDFs and OCR text. Useful for obituaries, marriage announcements, legal notices, social columns and migration clues.",
     record_types=["newspapers_general", "obituaries", "announcements", "legal_notices", "social_columns", "missing_persons"],
     capabilities=["full_text", "browse_images"], evidence_forms=["original_image", "transcription"],
     access_search=["free"], access_images=["free"], access_copies=["free"],
     integration_method="documented_api", adapter_key="loc_chronicling_america",
     search_url_template="https://www.loc.gov/collections/chronicling-america/?q={q}&dates={year_from}/{year_to}&fa=location_state:{state}",
     search_link_verified=True, search_link_notes="Verified via the documented loc.gov JSON API on 2026-10-05 (q, dates, location_state facet).",
     languages=["English", "German", "French", "Spanish", "Swedish", "Norwegian", "Czech", "Italian", "Polish"],
     rights_notes="The Library of Congress generally does not own rights to collection materials; users must determine copyright status themselves.",
     limitations="OCR quality varies, so names can be misread. Titles were selected by state program participants — coverage is not comprehensive. Legacy chroniclingamerica.loc.gov API was retired in 2025.",
     verification_status="verified", tags=["newspapers", "full text", "live search"])
coll("loc-genealogy-guides", "loc", "Library of Congress genealogy research guides", "https://guides.loc.gov/genealogy",
     entry_kind="guide", repository_type="national_library", geo=[US],
     description="Research guides from the Library of Congress Local History & Genealogy reading room on family histories, local histories and databases.",
     record_types=["family_histories", "local_histories"], capabilities=["catalog", "onsite"],
     access_search=["free", "library"], access_images=["library"], access_copies=["onsite"], verification_status="partial",
     maintenance_notes="Reading-room pages on loc.gov showed a Cloudflare check; guides.loc.gov was used instead.")

prov("newspaperarchive", "NewspaperArchive", "https://newspaperarchive.com/", "commercial_database")
coll("newspaperarchive", "newspaperarchive", "NewspaperArchive", "https://newspaperarchive.com/",
     entry_kind="collection", repository_type="newspaper_archive", geo_scope="worldwide",
     dates=[dr(1607, 2026, "As stated by provider (page title says 1700s–2026)")],
     description="Commercial historical newspaper archive emphasizing small-town papers, with name/keyword/title search and clippings.",
     record_types=["newspapers_general", "obituaries", "announcements", "legal_notices", "social_columns"],
     capabilities=["full_text", "name_index"], evidence_forms=["original_image", "transcription"],
     access_search=["free"], access_images=["subscription"], access_copies=["subscription"],
     limitations="Full content requires paid access. Provider's stated date range is inconsistent between pages.", tags=["newspapers"])

prov("dpla", "Digital Public Library of America", "https://dp.la/", "nonprofit_database", "United States",
     "Now maintained by Cleveland Public Library (announced 2026-09-15).")
coll("dpla", "dpla", "Digital Public Library of America", "https://dp.la/",
     entry_kind="catalog", repository_type="directory", geo=[US],
     description="Aggregated search of metadata for digitized photographs, texts, manuscripts, maps and recordings from U.S. libraries, archives and museums, linking to the holding institution.",
     record_types=["photographs", "local_histories", "family_histories", "letters", "diaries", "collection_descriptions", "yearbooks"],
     capabilities=["catalog"], evidence_forms=["photograph", "original_image", "finding_aid"],
     access_search=["free"], access_images=["free"], access_copies=["unknown"],
     search_url_template="https://dp.la/search?q={q}&after={year_from}&before={year_to}", search_link_verified=True,
     search_link_notes="Verified 2026-10-05; date filter narrowed results as expected.",
     rights_notes="Item access and reuse are governed by each contributing institution.",
     limitations="Metadata aggregator — the items themselves are at the contributing institutions.", tags=["discovery"])

prov("cyndislist", "Cyndi's List", "https://www.cyndislist.com/", "directory")
coll("cyndis-list", "cyndislist", "Cyndi's List", "https://www.cyndislist.com/",
     entry_kind="directory", repository_type="directory", geo_scope="worldwide",
     description="Free, categorized and cross-referenced directory of links to genealogy research sites.",
     capabilities=["catalog"], evidence_forms=["finding_aid"], access_search=["free"], access_images=[], access_copies=[],
     limitations="Links to external sites; individual links may be out of date.", tags=["directory"])

# ======================================================================= INTERNATIONAL
UK = [{"country": "United Kingdom"}]
EW = [{"country": "England"}, {"country": "Wales"}]
prov("tna-uk", "The National Archives (UK)", "https://www.nationalarchives.gov.uk/", "national_archive", "United Kingdom")
coll("tna-discovery", "tna-uk", "TNA Discovery catalogue", "https://discovery.nationalarchives.gov.uk/",
     entry_kind="catalog", repository_type="national_archive", geo=UK,
     description="Catalogue of records held by The National Archives (UK) and many other UK archives, with some digitised record series available to download.",
     record_types=["finding_aids", "collection_descriptions", "military_service", "wills", "naturalization", "onsite_material"],
     capabilities=["catalog", "browse_images"], evidence_forms=["finding_aid", "original_image"],
     access_search=["free"], access_images=["free"], access_copies=["free", "paid_retrieval"],
     access_notes="Digital downloads were free at the time of checking; copies of undigitised records are ordered.",
     search_url_template="https://discovery.nationalarchives.gov.uk/results/r?_q={q}", search_link_verified=True,
     search_link_notes="Verified 2026-10-05 with a surname query.", languages=["English"],
     terminology=["PCC wills", "WO 363 (soldiers' documents)", "naturalisation"], tags=["UK", "catalog"])
coll("tna-uk-main", "tna-uk", "The National Archives (UK) research guides", "https://www.nationalarchives.gov.uk/",
     entry_kind="guide", repository_type="national_archive", geo=UK,
     description="Research guides for family history in UK government records (military, wills, immigration, and more); some census and other records are offered through partner sites.",
     record_types=["military_service", "wills", "naturalization", "censuses"], capabilities=["catalog", "onsite"],
     access_search=["free"], access_images=["free", "onsite"], access_copies=["free", "paid_retrieval", "onsite"],
     verification_status="partial", tags=["UK", "guidance"])

prov("freebmd", "FreeBMD", "https://www.freebmd.org.uk/", "volunteer_project", "United Kingdom")
coll("freebmd", "freebmd", "FreeBMD (civil registration index)", "https://www.freebmd.org.uk/",
     entry_kind="collection", repository_type="volunteer_project", geo=EW, dates=[dr(1837, 1999, "Civil registration index; transcription incomplete")],
     description="Volunteer transcription of the civil registration index of births, marriages and deaths for England and Wales.",
     record_types=["births", "marriages", "deaths"], capabilities=["name_index"], evidence_forms=["index"],
     access_search=["free"], access_images=["unknown"], access_copies=["unknown"],
     search_link_notes="Search form uses POST; no shareable pre-filled link. Copy the query.",
     limitations="An index only — order certificates from the General Register Office. Transcription coverage is incomplete for some years.",
     terminology=["GRO index", "civil registration", "registration district", "quarter"], languages=["English"], tags=["UK", "free"])
prov("freecen", "FreeCEN", "https://www.freecen.org.uk/", "volunteer_project", "United Kingdom")
coll("freecen", "freecen", "FreeCEN (census transcriptions)", "https://www.freecen.org.uk/",
     entry_kind="collection", repository_type="volunteer_project", geo=UK, dates=[dr(1841, 1911, "Census years; partial coverage")],
     description="Volunteer transcriptions of 19th- and early 20th-century UK census returns.",
     record_types=["censuses"], capabilities=["name_index"], evidence_forms=["transcription"],
     access_search=["free"], access_images=[], access_copies=[],
     limitations="Coverage varies by county and year — check the coverage pages before treating a miss as meaningful.",
     languages=["English"], tags=["UK", "free"])
prov("freereg", "FreeREG", "https://www.freereg.org.uk/", "volunteer_project", "United Kingdom")
coll("freereg", "freereg", "FreeREG (parish register transcriptions)", "https://www.freereg.org.uk/",
     entry_kind="collection", repository_type="volunteer_project", geo=UK,
     description="Volunteer transcriptions of parish and nonconformist registers: baptisms, marriages and burials.",
     record_types=["baptisms", "marriages", "burials", "congregational_registers"], capabilities=["name_index"], evidence_forms=["transcription"],
     access_search=["free"], access_images=[], access_copies=[],
     limitations="Coverage varies by parish; dates covered differ per register.", terminology=["parish registers", "bishop's transcripts"],
     languages=["English", "Latin"], tags=["UK", "free"])

prov("scotlandspeople", "ScotlandsPeople", "https://www.scotlandspeople.gov.uk/", "government_agency", "United Kingdom")
coll("scotlandspeople", "scotlandspeople", "ScotlandsPeople", "https://www.scotlandspeople.gov.uk/",
     entry_kind="search_service", repository_type="government_agency", geo=[{"country": "Scotland"}],
     description="Official Scottish government records site: statutory registers of births, marriages and deaths, church registers, census returns, wills and testaments, valuation rolls and more.",
     record_types=["births", "marriages", "deaths", "baptisms", "banns", "burials", "censuses", "wills", "probate", "tax_lists", "institutional_registers"],
     capabilities=["name_index", "catalog", "browse_images", "onsite"], evidence_forms=["index", "original_image"],
     access_search=["free_account"], access_images=["paid_retrieval"], access_copies=["paid_retrieval", "onsite"],
     access_notes="Searching needs a free registration; viewing images uses pay-per-view credits (at checking, most images cost 6 credits at 25p each).",
     date_gaps=[], limitations="Statutory images are released on rolling closure periods (births 100 years, marriages 75, deaths 50).",
     terminology=["OPR (Old Parish Registers)", "statutory registers", "wills and testaments", "valuation rolls", "kirk session records"],
     verification_status="partial", languages=["English", "Scottish Gaelic", "Latin"], tags=["Scotland"])

prov("irishgenealogy", "IrishGenealogy.ie", "https://www.irishgenealogy.ie/", "government_agency", "Ireland")
coll("irishgenealogy", "irishgenealogy", "IrishGenealogy.ie (civil and church records)", "https://www.irishgenealogy.ie/",
     entry_kind="search_service", repository_type="government_agency", geo=[{"country": "Ireland"}],
     description="Irish government site for civil birth, marriage and death registers and some church registers.",
     record_types=["births", "marriages", "deaths", "baptisms", "burials"], capabilities=["name_index"], evidence_forms=["index", "original_image"],
     access_search=["unknown"], access_images=["unknown"], access_copies=["unknown"],
     verification_status="needs_verification", maintenance_notes="Site blocked automated checks (403) on 2026-10-05; secondary sources disagree on online date ranges. Verify in a browser.",
     terminology=["civil registration", "GRO", "rolling 100/75/50-year release"], tags=["Ireland"])
prov("nai", "National Archives of Ireland", "https://nationalarchives.ie/", "national_archive", "Ireland")
coll("nai-census", "nai", "National Archives of Ireland census search", "https://nationalarchives.ie/collections/search-the-census/",
     entry_kind="collection", repository_type="national_archive", geo=[{"country": "Ireland"}],
     dates=[dr(1901, 1901, "Census 1901"), dr(1911, 1911, "Census 1911"), dr(1926, 1926, "Census 1926 (phased release)"), dr(1821, 1851, "Surviving pre-1901 fragments")],
     date_gaps=[dr(1861, 1891, "Censuses 1861–1891 do not survive")],
     description="Free search of the 1901 and 1911 Irish censuses, surviving 1821–1851 fragments, and the phased release of the 1926 census.",
     record_types=["censuses"], capabilities=["name_index", "browse_images"], evidence_forms=["index", "original_image"],
     access_search=["free"], access_images=["free"], access_copies=["onsite", "unknown"],
     verification_status="partial", tags=["Ireland", "free"],
     maintenance_notes="Census search moved to nationalarchives.ie/collections/search-the-census/ (noted 2026-10-05). The 1861–1891 gap is general knowledge, recorded here as a known gap; verify wording on provider site.")

prov("lac", "Library and Archives Canada", "https://www.canada.ca/en/library-archives.html", "national_archive", "Canada")
coll("lac-genealogy", "lac", "Library and Archives Canada genealogy collections", "https://www.canada.ca/en/library-archives.html",
     entry_kind="repository", repository_type="national_archive", geo=[{"country": "Canada"}], dates=[dr(1825, 1931, "National census search")],
     description="Canada's national archive: census search, immigration and passenger lists, military personnel files (including First World War CEF), land petitions and citizenship records.",
     record_types=["censuses", "passenger_lists", "military_service", "land_grants", "naturalization", "citizenship_files"],
     capabilities=["name_index", "catalog", "browse_images"], evidence_forms=["index", "original_image"],
     access_search=["free"], access_images=["free"], access_copies=["free", "unknown"],
     search_link_notes="Collection Search returned 403 to automated checks; no verified link pattern.",
     verification_status="partial", languages=["English", "French"], tags=["Canada"], pathways=["indigenous"])
prov("archives-ontario", "Archives of Ontario", "https://www.archives.gov.on.ca/", "state_archive", "Canada")
coll("archives-ontario", "archives-ontario", "Archives of Ontario", "https://www.archives.gov.on.ca/en/index.aspx",
     entry_kind="repository", repository_type="state_archive", geo=[{"country": "Canada", "region": "Ontario"}],
     description="Ontario's provincial archive. Its vital statistics registrations are served mainly through partner sites (FamilySearch with a free account; Ancestry free in the reading room).",
     record_types=["births", "marriages", "deaths", "deeds", "land_grants", "court_cases"], capabilities=["catalog", "onsite"],
     access_search=["free_account", "library"], access_images=["free_account", "onsite"], access_copies=["paid_retrieval", "onsite"],
     verification_status="partial", tags=["Canada", "provincial archive"])
prov("banq", "Bibliothèque et Archives nationales du Québec (BAnQ)", "https://www.banq.qc.ca/", "state_archive", "Canada")
coll("banq", "banq", "BAnQ (Québec national library and archives)", "https://www.banq.qc.ca/",
     entry_kind="repository", repository_type="state_archive", geo=[{"country": "Canada", "region": "Québec"}],
     description="Québec's national library and archives: civil-status (baptisms, marriages, burials), notarial records, archival fonds and photographs.",
     record_types=["baptisms", "marriages", "burials", "deeds", "court_cases", "photographs"], capabilities=["catalog"],
     access_search=["free"], access_images=["unknown"], access_copies=["unknown"], languages=["French"],
     terminology=["état civil", "baptêmes, mariages, sépultures (BMS)", "actes notariés", "greffes de notaires"],
     verification_status="partial", tags=["Canada", "French-language"])

prov("nla", "National Library of Australia", "https://www.nla.gov.au/", "national_library", "Australia")
coll("trove", "nla", "Trove", "https://trove.nla.gov.au/",
     entry_kind="collection", repository_type="national_library", geo=[{"country": "Australia"}],
     dates=[dr(1803, 1954, "Digitised newspapers (generally to 1954; some later)")],
     description="National Library of Australia discovery service with free full-text search of digitised Australian newspapers, government gazettes, books, photographs and maps.",
     record_types=["newspapers_general", "obituaries", "announcements", "legal_notices", "social_columns", "missing_persons", "photographs", "local_histories"],
     capabilities=["full_text", "catalog"], evidence_forms=["original_image", "transcription", "photograph"],
     access_search=["free"], access_images=["free"], access_copies=["free"],
     search_link_notes="A newspapers URL pattern exists but the site showed an automated-traffic check during testing, so it is not marked verified. Trove has a documented API that requires a key (not implemented).",
     limitations="OCR text is machine-generated; corrected text varies.", verification_status="partial", tags=["Australia", "newspapers", "full text"])
prov("nsw-state-archives", "Museums of History NSW — State Archives Collection", "https://mhnsw.au/", "state_archive", "Australia")
coll("nsw-state-archives", "nsw-state-archives", "NSW State Archives Collection", "https://mhnsw.au/collections/state-archives-collection/",
     entry_kind="repository", repository_type="state_archive", geo=[{"country": "Australia", "region": "New South Wales"}],
     dates=[dr(1788, None, "Collection"), dr(1791, 1873, "Convicts index"), dr(1839, 1896, "Assisted immigrants index"), dr(1841, 1841, "1841 census index")],
     description="New South Wales state archives with name indexes to convict, immigration, 1841 census, probate, inquest and divorce records.",
     record_types=["passenger_lists", "censuses", "probate", "court_cases", "divorces", "institutional_registers"],
     capabilities=["name_index", "catalog", "onsite"], evidence_forms=["index", "original_image"],
     access_search=["free"], access_images=["free", "onsite"], access_copies=["unknown"],
     maintenance_notes="Old /archive/ URL now redirects here (noted 2026-10-05).", tags=["Australia", "state archive"])
prov("prov", "Public Record Office Victoria", "https://prov.vic.gov.au/", "state_archive", "Australia")
coll("prov-victoria", "prov", "Public Record Office Victoria", "https://prov.vic.gov.au/",
     entry_kind="repository", repository_type="state_archive", geo=[{"country": "Australia", "region": "Victoria"}],
     dates=[dr(1836, None, "Holdings"), dr(1840, 1985, "Inquest deposition files")],
     description="Victoria's state archive: wills and probate, inquests, passenger and immigration records, land, wards of state and photographs.",
     record_types=["wills", "probate", "court_cases", "passenger_lists", "deeds", "land_grants", "institutional_registers", "photographs"],
     capabilities=["catalog", "onsite"], access_search=["free"], access_images=["free", "onsite"], access_copies=["unknown"],
     verification_status="partial", tags=["Australia", "state archive"])

prov("natlib-nz", "National Library of New Zealand", "https://natlib.govt.nz/", "national_library", "New Zealand")
coll("natlib-nz-family-history", "natlib-nz", "National Library of NZ — family history", "https://natlib.govt.nz/researchers/family-history",
     entry_kind="guide", repository_type="national_library", geo=[{"country": "New Zealand"}],
     description="Family-history guidance and resources at the National Library of New Zealand, including newspapers, electoral rolls, directories and shipping arrivals.",
     record_types=["newspapers_general", "electoral_rolls", "city_directories", "passenger_lists"], capabilities=["catalog", "onsite"],
     access_search=["free"], access_images=["onsite", "free"], access_copies=["unknown"], verification_status="partial", tags=["New Zealand"])
coll("papers-past", "natlib-nz", "Papers Past", "https://paperspast.natlib.govt.nz/",
     entry_kind="collection", repository_type="newspaper_archive", geo=[{"country": "New Zealand"}],
     dates=[dr(1800, 1999, "Newspapers of the 19th and 20th centuries (titles vary)")],
     description="Free digitised New Zealand and Pacific newspapers, magazines, letters and diaries, and parliamentary papers with full-text search.",
     record_types=["newspapers_general", "obituaries", "announcements", "legal_notices", "social_columns", "letters", "diaries"],
     capabilities=["full_text", "browse_images"], evidence_forms=["original_image", "transcription"],
     access_search=["free"], access_images=["free"], access_copies=["free"],
     search_url_template="https://paperspast.natlib.govt.nz/newspapers?query={q}", search_link_verified=True,
     search_link_notes="Verified 2026-10-05 with a surname query. Date filters exist on the site (DD-MM-YYYY) but are applied there.",
     languages=["English", "Māori"], tags=["New Zealand", "newspapers", "full text"])
prov("archives-nz", "Archives New Zealand", "https://www.archives.govt.nz/", "national_archive", "New Zealand")
coll("archives-nz", "archives-nz", "Archives New Zealand collections", "https://collections.archives.govt.nz/",
     entry_kind="repository", repository_type="national_archive", geo=[{"country": "New Zealand"}], dates=[dr(1840, None, "Government records")],
     description="New Zealand government archives: probate files, immigration and passenger records, military personnel files, land records.",
     record_types=["probate", "passenger_lists", "military_service", "deeds", "land_grants"], capabilities=["catalog", "onsite", "request_only"],
     evidence_forms=["finding_aid", "original_image"], access_search=["free"], access_images=["free", "onsite"], access_copies=["paid_retrieval"],
     verification_status="partial", tags=["New Zealand"])
prov("nz-dia", "NZ Department of Internal Affairs", "https://www.bdmhistoricalrecords.dia.govt.nz/", "government_agency", "New Zealand")
coll("nz-bdm-historical", "nz-dia", "NZ Births, Deaths & Marriages Historical Records", "https://www.bdmhistoricalrecords.dia.govt.nz/",
     entry_kind="collection", repository_type="government_agency", geo=[{"country": "New Zealand"}],
     description="Index of historical New Zealand births (100+ years old), deaths (50+ years old or born 80+ years ago) and marriages (75+ years old).",
     record_types=["births", "deaths", "marriages"], capabilities=["name_index"], evidence_forms=["index"],
     access_search=["free"], access_images=[], access_copies=["paid_retrieval"], tags=["New Zealand"])

prov("arkivverket", "Arkivverket (National Archives of Norway)", "https://www.digitalarkivet.no/en/", "national_archive", "Norway")
coll("digitalarkivet", "arkivverket", "Digitalarkivet", "https://www.digitalarkivet.no/en/",
     entry_kind="search_service", repository_type="national_archive", geo=[{"country": "Norway"}],
     description="Norway's digital archive: searchable transcriptions and scanned church books (parish registers), censuses, emigration protocols, probate, court and property records.",
     record_types=["baptisms", "marriages", "burials", "congregational_registers", "censuses", "passenger_lists", "probate", "court_cases", "deeds"],
     capabilities=["name_index", "browse_images", "full_text"], evidence_forms=["transcription", "original_image", "index"],
     access_search=["free"], access_images=["free"], access_copies=["free"],
     access_notes="Copies of some material can also be requested from the archives.",
     search_url_template="https://www.digitalarkivet.no/en/search/persons?s={q}", search_link_verified=True, search_link_notes="Verified 2026-10-05.",
     languages=["Norwegian", "Danish (older records)"], terminology=["kirkebøker (church books)", "folketelling (census)", "emigrantprotokoller", "skifte (probate)", "bygdebøker (farm histories)", "gard (farm name)"],
     tags=["Norway", "free"])

prov("archion", "Archion", "https://www.archion.de/en/", "commercial_database", "Germany")
coll("archion", "archion", "Archion (Protestant church books)", "https://www.archion.de/en/",
     entry_kind="collection", repository_type="religious_archive", geo=[{"country": "Germany"}],
     description="Online portal for scanned German Protestant church books (baptisms, marriages, burials, confirmations) from participating church archives.",
     record_types=["baptisms", "marriages", "burials", "congregational_registers"], capabilities=["browse_images", "full_text"], evidence_forms=["original_image"],
     access_search=["subscription"], access_images=["subscription"], access_copies=["subscription"],
     access_notes="Paid passes (monthly, quarterly, annual) — check current prices on the site.", languages=["German", "Latin"],
     terminology=["Kirchenbücher", "Taufen", "Trauungen", "Beerdigungen", "Konfirmationen", "evangelisch"],
     limitations="Mostly browse-by-parish; you need to know the parish (Kirchspiel). Old German script (Kurrent) is common.",
     tags=["Germany", "church books"])
prov("matricula", "Matricula", "https://data.matricula-online.eu/en/", "nonprofit_database")
coll("matricula", "matricula", "Matricula (Catholic parish registers)", "https://data.matricula-online.eu/en/",
     entry_kind="collection", repository_type="religious_archive",
     geo=[{"country": "Germany"}, {"country": "Austria"}, {"country": "Poland"}, {"country": "Slovenia"}, {"country": "Serbia"}, {"country": "Belgium"}],
     description="Free portal for scanned Catholic parish registers (baptisms, marriages, deaths) from participating archives in Central Europe, browsable by parish.",
     record_types=["baptisms", "marriages", "burials", "congregational_registers"], capabilities=["browse_images"], evidence_forms=["original_image"],
     access_search=["free"], access_images=["free"], access_copies=["unknown"], languages=["German", "Latin", "Polish", "Slovenian"],
     terminology=["Matriken", "Taufbuch", "Trauungsbuch", "Sterbebuch", "Pfarre"],
     limitations="Browse-only: no name index. Participating countries listed here are an initial selection — check the site's archive list.",
     verification_status="verified", maintenance_notes="Country list should be checked against the site's participating archives.", tags=["Central Europe", "browse images"])

prov("geneanet", "Geneanet", "https://en.geneanet.org/", "commercial_database", "France")
coll("geneanet", "geneanet", "Geneanet", "https://en.geneanet.org/",
     entry_kind="search_service", repository_type="commercial_database", geo_scope="worldwide",
     description="Genealogy platform strong in continental Europe (especially France) with member family trees, cemetery records, archival indexes, and digitised books and newspapers.",
     record_types=["trees", "burials", "births", "marriages", "deaths", "censuses", "family_histories", "newspapers_general"],
     capabilities=["name_index", "full_text"], evidence_forms=["contributed_tree", "index", "photograph", "transcription"],
     access_search=["free_account", "subscription"], access_images=["free", "subscription"], access_copies=["unknown"],
     search_url_template="https://en.geneanet.org/fonds/individus/?go=1&nom={surname}&prenom={given}", search_link_verified=True,
     search_link_notes="Verified 2026-10-05.", languages=["French", "English", "and others"],
     limitations="Many results are contributed trees — clues, not proof.", verification_status="partial", tags=["Europe", "France"])

prov("jewishgen", "JewishGen", "https://www.jewishgen.org/", "nonprofit_database")
coll("jewishgen", "jewishgen", "JewishGen databases", "https://www.jewishgen.org/",
     entry_kind="search_service", repository_type="nonprofit_database", geo_scope="worldwide",
     description="Jewish genealogy databases including Holocaust records, burial records (JOWBR), town and community records, and family trees.",
     record_types=["burials", "births", "marriages", "deaths", "trees", "local_histories", "casualties"],
     capabilities=["name_index"], evidence_forms=["index", "transcription", "contributed_tree"],
     access_search=["free_account"], access_images=["unknown"], access_copies=["unknown"],
     search_link_notes="Search form uses POST; no shareable pre-filled link.",
     terminology=["shtetl", "JOWBR", "KehilaLinks", "Yizkor books"], verification_status="partial",
     tags=["Jewish genealogy"], pathways=["displacement"])

# ======================================================================= LOCAL REPOSITORIES (initial, incomplete)
LOCAL_NOTE = "Local coverage is an initial sample and is not comprehensive."
coll("ny-state-archives", "ny-state-archives-prov", "New York State Archives — genealogy", "https://www.archives.nysed.gov/research/featured-topic-genealogy",
     entry_kind="repository", repository_type="state_archive", geo=[state("New York")],
     description="New York State Archives genealogy resources, including vital record indexes, military service, land, court and probate-related records.",
     record_types=["births", "marriages", "deaths", "military_service", "deeds", "land_grants", "court_cases", "probate"],
     capabilities=["name_index", "catalog"], access_search=["free"], tags=["New York", "state archive"])
prov("ny-state-archives-prov", "New York State Archives", "https://www.archives.nysed.gov/", "state_archive", "United States")
prov("pa-state-archives-prov", "Pennsylvania State Archives", "https://www.pa.gov/agencies/phmc/pa-state-archives", "state_archive", "United States")
coll("pa-state-archives", "pa-state-archives-prov", "Pennsylvania State Archives", "https://www.pa.gov/agencies/phmc/pa-state-archives",
     entry_kind="repository", repository_type="state_archive", geo=[state("Pennsylvania")],
     description="Pennsylvania's state archive of government records and private papers.", record_types=["onsite_material", "military_service", "land_grants"],
     capabilities=["onsite"], verification_status="partial", tags=["Pennsylvania", "state archive"])
prov("lva", "Library of Virginia", "https://www.lva.virginia.gov/", "state_archive", "United States")
coll("library-of-virginia", "lva", "Library of Virginia research guides", "https://lva-virginia.libguides.com/",
     entry_kind="repository", repository_type="state_archive", geo=[state("Virginia")],
     description="Library of Virginia guides to vital records, land patents, military, tax, and records relating to enslaved people.",
     record_types=["births", "marriages", "deaths", "land_grants", "military_service", "tax_lists"], capabilities=["catalog"],
     access_search=["free"], tags=["Virginia", "state archive"], pathways=["african-american"])
prov("ohc", "Ohio History Connection", "https://www.ohiohistory.org/", "historical_society", "United States")
coll("ohio-history-connection", "ohc", "Ohio History Connection Archives & Library", "https://www.ohiohistory.org/research/archives-library/",
     entry_kind="repository", repository_type="historical_society", geo=[state("Ohio")], dates=[dr(1908, 1970, "Death certificates held")],
     description="Ohio's state archives and library, including Ohio death certificates (1908–1970).", record_types=["deaths", "onsite_material", "local_histories"],
     capabilities=["onsite"], verification_status="partial", maintenance_notes="Notice on 2026-10-05: library reopening by appointment only from October 8.",
     tags=["Ohio"])
prov("whs", "Wisconsin Historical Society", "https://www.wisconsinhistory.org/", "historical_society", "United States")
coll("wisconsin-historical-society", "whs", "Wisconsin Historical Society — family history", "https://www.wisconsinhistory.org/research/family-history/",
     entry_kind="repository", repository_type="historical_society", geo=[state("Wisconsin")], dates=[dr(None, 1907, "Pre-1907 vital records index")],
     description="Wisconsin's state historical society: pre-1907 vital records, newspapers and obituaries, local and family histories.",
     record_types=["births", "marriages", "deaths", "newspapers_general", "obituaries", "local_histories", "family_histories"],
     capabilities=["name_index", "catalog", "onsite"], access_search=["free"], access_images=["onsite"], access_copies=["onsite", "paid_retrieval"], tags=["Wisconsin"])
prov("tsla", "Texas State Library and Archives Commission", "https://www.tsl.texas.gov/", "state_archive", "United States")
coll("texas-state-archives", "tsla", "Texas State Library & Archives — genealogy", "https://www.tsl.texas.gov/arc/genfirst",
     entry_kind="repository", repository_type="state_archive", geo=[state("Texas")],
     description="Texas genealogy resources: vital record indexes, tax rolls, city directories, newspapers, military service records.",
     record_types=["births", "deaths", "marriages", "tax_lists", "city_directories", "newspapers_general", "military_service"],
     capabilities=["catalog", "name_index", "browse_images", "onsite"], access_search=["free", "free_account", "library"],
     access_images=["free", "library"], access_copies=["onsite", "paid_retrieval"], tags=["Texas"])
prov("ca-state-archives-prov", "California State Archives", "https://www.sos.ca.gov/archives", "state_archive", "United States")
coll("california-state-archives", "ca-state-archives-prov", "California State Archives collections", "https://www.sos.ca.gov/archives/collections",
     entry_kind="repository", repository_type="state_archive", geo=[state("California")],
     description="California's state government records and maps.", record_types=["onsite_material"], capabilities=["catalog", "onsite"],
     access_search=["free"], verification_status="partial", tags=["California"])
prov("nc-archives", "State Archives of North Carolina", "https://archives.ncdcr.gov/", "state_archive", "United States")
coll("nc-state-archives", "nc-archives", "State Archives of North Carolina — ordering copies", "https://archives.ncdcr.gov/researchers/services/ordering-copies",
     entry_kind="repository", repository_type="state_archive", geo=[state("North Carolina")],
     description="North Carolina's state archive, including Bible records, state records and private collections; copies can be ordered.",
     record_types=["family_histories", "onsite_material", "court_cases", "probate"], capabilities=["catalog", "onsite", "request_only"],
     access_search=["free"], access_images=["onsite"], access_copies=["paid_retrieval"], tags=["North Carolina"])
prov("il-archives", "Illinois State Archives", "https://www.ilsos.gov/departments/archives/", "state_archive", "United States")
coll("illinois-state-archives", "il-archives", "Illinois State Archives — genealogy research", "https://www.ilsos.gov/departments/archives/gen-research.html",
     entry_kind="repository", repository_type="state_archive", geo=[state("Illinois")],
     description="Illinois State Archives genealogy indexes (vital records, census, public land sales) and copy requests.",
     record_types=["births", "deaths", "marriages", "censuses", "land_grants"], capabilities=["name_index", "onsite", "request_only"],
     access_search=["free"], access_copies=["paid_retrieval", "onsite"], tags=["Illinois"])
prov("ma-archives", "Massachusetts Archives", "https://www.sec.state.ma.us/divisions/archives/", "state_archive", "United States")
coll("massachusetts-archives", "ma-archives", "Massachusetts Archives — genealogy", "https://www.sec.state.ma.us/divisions/archives/research/genealogy.htm",
     entry_kind="repository", repository_type="state_archive", geo=[state("Massachusetts")],
     description="Massachusetts state archives genealogy research page.", verification_status="needs_verification",
     maintenance_notes="Site blocked automated checks on 2026-10-05; verify content and access in a browser.", tags=["Massachusetts"])
prov("mass-registries", "Massachusetts Registries of Deeds (masslandrecords.com)", "https://www.masslandrecords.com/", "registry_of_deeds", "United States")
coll("masslandrecords", "mass-registries", "Massachusetts registries of deeds portal", "https://www.masslandrecords.com/",
     entry_kind="repository", repository_type="registry_of_deeds", geo=[state("Massachusetts")],
     description="Portal to Massachusetts county registries of deeds.", record_types=["deeds", "mortgages"],
     verification_status="needs_verification", maintenance_notes="Site blocked automated checks on 2026-10-05; verify search coverage and access in a browser.",
     tags=["Massachusetts", "deeds"])
prov("mass-courts", "Massachusetts Probate and Family Court", "https://www.mass.gov/orgs/probate-and-family-court", "probate_court", "United States")
coll("worcester-probate", "mass-courts", "Worcester Probate and Family Court", "https://www.mass.gov/locations/worcester-probate-and-family-court",
     entry_kind="repository", repository_type="probate_court", geo=[state("Massachusetts", "Worcester")],
     description="Probate and Family Court for Worcester County, Massachusetts (location and contact page).",
     record_types=["probate", "wills", "guardianships"], capabilities=["onsite", "request_only"], access_search=["free"],
     verification_status="partial", limitations="The court page does not describe historical probate files; older files may be held elsewhere (e.g. state archives or online via commercial sites).",
     tags=["Massachusetts", "probate"])
prov("cook-county-clerk", "Cook County Clerk", "https://www.cookcountyclerkil.gov/", "county_clerk", "United States")
coll("cook-county-genealogy", "cook-county-clerk", "Cook County Clerk genealogy records", "https://www.cookcountyclerkil.gov/vital-records/birth-death-records/genealogy-records",
     entry_kind="repository", repository_type="county_clerk", geo=[state("Illinois", "Cook")],
     description="Cook County (Illinois) clerk's genealogy vital records page.", record_types=["births", "deaths", "marriages"],
     verification_status="needs_verification", maintenance_notes="Page returned 'Access denied' to automated checks on 2026-10-05.", tags=["Illinois", "Chicago"])
prov("acpl", "Allen County Public Library — The Genealogy Center", "https://www.acpl.lib.in.us/genealogy", "public_library", "United States")
coll("acpl-genealogy-center", "acpl", "The Genealogy Center (Allen County Public Library)", "https://www.acpl.lib.in.us/genealogy",
     entry_kind="repository", repository_type="public_library", geo_scope="worldwide",
     description="Large public-library genealogy collection in Fort Wayne, Indiana, with family and local histories and a periodicals index.",
     record_types=["family_histories", "local_histories", "journals"], capabilities=["catalog", "name_index", "onsite"],
     access_search=["free"], access_copies=["onsite"], verification_status="partial", tags=["library"])
prov("nygb", "New York Genealogical & Biographical Society (NYG&B)", "https://www.newyorkfamilyhistory.org/", "historical_society", "United States")
coll("nygb-online-records", "nygb", "NYG&B online records and collections", "https://www.newyorkfamilyhistory.org/online-records",
     entry_kind="search_service", repository_type="historical_society", geo=[state("New York")],
     description="Members' online collections for New York State and City: county histories, vital-record substitutes, church and town records, "
                 "cemetery, census, court, land, probate, military, naturalization and immigration records, directories, compiled genealogies, "
                 "the NYG&B Record (1870– ) and the New York Researcher. Searchable by name, keywords, record category and county.",
     record_types=["births", "marriages", "deaths", "baptisms", "burials", "censuses", "probate", "wills", "court_cases", "deeds", "military_service",
                   "naturalization", "passenger_lists", "city_directories", "congregational_registers", "family_histories", "local_histories", "journals",
                   "newspapers_general", "biographies"],
     capabilities=["name_index", "full_text", "browse_images"], evidence_forms=["original_image", "transcription", "index", "published_analysis"],
     access_search=["subscription"], access_images=["subscription"], access_copies=["subscription"],
     access_notes="Members only. Terms: personal research use; no sharing of access; no downloading of whole or significant portions of a database.",
     search_url="https://www.newyorkfamilyhistory.org/online-records", search_link_verified=False,
     search_link_notes="The search form posts through an anti-bot check, so it can't be pre-filled by a link; paste the name and choose the county. "
                       "Not searched automatically (terms and anti-bot protection).",
     verification_status="verified", last_verified=CHECKED_2, verification_source=SRC_2, link_checked_at=CHECKED_2,
     tags=["New York", "membership"])

prov("hchs", "Herkimer County Historical Society", "https://herkimercountyhistory.org/", "historical_society", "United States")
coll("hchs-library", "hchs", "Herkimer County Historical Society library (Eckler Building, Herkimer, NY)", "https://herkimercountyhistory.org/rescources/",
     entry_kind="repository", repository_type="historical_society", geo=[state("New York", "Herkimer")],
     dates=[dr(1790, 1880, "Federal and NY state census copies: 1790–1880 incl. 1825, 1835, 1845, 1855, 1865"),
            dr(1790, 1900, "Will index / abstracts of wills"), dr(1800, 1944, "Newspaper marriages & obituaries; Evening Telegram obituary index 1923–1944"),
            dr(1869, 1995, "City directories (Herkimer, Mohawk, Ilion, Frankfort, Little Falls, Dolgeville)"), dr(None, 1930, "Cemetery transcriptions")],
     description="Research library of the Herkimer County Historical Society: transcriptions of every Herkimer County cemetery to 1930, newspaper "
                 "marriage and obituary files (1800s; Herkimer/Ilion Citizen 1867–1921; Evening Telegram 1900–1920 and an obituary index 1923–1944), "
                 "city directories 1869–1995, census copies including the 1825–1865 NY state censuses, a will index 1790s–1900, family genealogies and "
                 "surname files, town histories, gazetteers and atlases.",
     record_types=["censuses", "burials", "obituaries", "marriages", "city_directories", "wills", "probate", "family_histories", "local_histories",
                   "onsite_material", "transcriptions"],
     capabilities=["onsite", "request_only"], evidence_forms=["transcription", "index", "published_analysis", "original_image"],
     access_search=["onsite", "paid_retrieval"], access_images=["onsite"], access_copies=["onsite", "paid_retrieval"],
     access_notes="Open Mon–Fri 10–4 (and summer Saturdays); $5 day use, free for members. Research by staff for a $30 donation, free for members: "
                  "email herkimerhistoryresearch@yahoo.com. The website's members-only page holds members' articles, not databases.",
     search_url="https://herkimercountyhistory.org/rescources/", search_link_verified=False,
     search_link_notes="No online search. Ask the Society (the person page drafts a research request).",
     verification_status="verified", last_verified=CHECKED_2, verification_source=SRC_2, link_checked_at=CHECKED_2,
     tags=["New York", "Herkimer County", "Mohawk Valley", "membership"])

prov("nypl", "New York Public Library", "https://www.nypl.org/", "public_library", "United States")
coll("nypl-milstein", "nypl", "NYPL Milstein Division (U.S. history, local history & genealogy)", "https://www.nypl.org/about/divisions/milstein-division",
     entry_kind="repository", repository_type="public_library", geo=[state("New York", "New York")],
     description="New York Public Library's division for U.S. history, local history and genealogy.", record_types=["family_histories", "local_histories", "city_directories"],
     verification_status="needs_verification", maintenance_notes="Blocked automated checks on 2026-10-05.", tags=["New York", "library"])
prov("bpl", "Boston Public Library", "https://www.bpl.org/", "public_library", "United States")
coll("bpl-genealogy", "bpl", "Boston Public Library — genealogy", "https://www.bpl.org/genealogy/",
     entry_kind="repository", repository_type="public_library", geo=[state("Massachusetts", "Suffolk", "Boston")],
     description="Boston Public Library genealogy resources: published genealogies, town histories, passenger lists, newspapers and an obituary index.",
     record_types=["family_histories", "local_histories", "passenger_lists", "newspapers_general", "obituaries"],
     capabilities=["catalog", "name_index", "onsite"], access_search=["library", "free"], access_images=["library"], access_copies=["onsite"],
     tags=["Massachusetts", "library"])
prov("nyhistory", "New-York Historical Society", "https://www.nyhistory.org/", "historical_society", "United States")
coll("ny-historical-library", "nyhistory", "New-York Historical Society library", "https://www.nyhistory.org/library",
     entry_kind="repository", repository_type="historical_society", geo=[state("New York", "New York")],
     description="Research library with manuscripts, graphics and digital images relating to New York history.",
     record_types=["letters", "diaries", "photographs", "finding_aids", "manuscript_catalogs"], capabilities=["catalog", "full_text", "onsite"],
     access_search=["free"], access_images=["free"], tags=["New York"])
prov("hsp", "Historical Society of Pennsylvania", "https://hsp.org/", "historical_society", "United States")
coll("hsp", "hsp", "Historical Society of Pennsylvania — family history", "https://hsp.org/start-your-family-history-hsp",
     entry_kind="repository", repository_type="historical_society", geo=[state("Pennsylvania", "Philadelphia")],
     description="Manuscripts and genealogy collections at the Historical Society of Pennsylvania.",
     record_types=["family_histories", "manuscript_catalogs", "letters"], capabilities=["catalog", "onsite"], access_copies=["paid_retrieval"],
     verification_status="partial", tags=["Pennsylvania"])
prov("mnhs", "Minnesota Historical Society", "https://www.mnhs.org/", "historical_society", "United States")
coll("mnhs-people", "mnhs", "Minnesota Historical Society people search", "https://www.mnhs.org/search/people",
     entry_kind="collection", repository_type="historical_society", geo=[state("Minnesota")],
     description="Name search across Minnesota birth, death, census, veterans' graves and Gold Star Roll records.",
     record_types=["births", "deaths", "censuses", "burials", "casualties"], capabilities=["name_index"], access_search=["free"], tags=["Minnesota"])
prov("phs", "Presbyterian Historical Society", "https://pcusa.org/historical-society", "religious_archive", "United States")
coll("presbyterian-historical-society", "phs", "Presbyterian Historical Society church record surveys", "https://pcusa.org/historical-society/collections/research-tools/church-record-surveys",
     entry_kind="repository", repository_type="religious_archive", geo=[US],
     description="Presbyterian church records (baptisms, marriages) and ministers' biographical files; research requests by fee.",
     record_types=["baptisms", "marriages", "congregational_registers", "biographies"], capabilities=["catalog", "request_only", "onsite"],
     access_search=["free"], access_copies=["paid_retrieval"], access_notes="Provider lists a fee-based biographical research service.", tags=["religious archive"])
prov("aja", "American Jewish Archives", "https://www.americanjewisharchives.org/", "religious_archive", "United States")
coll("american-jewish-archives", "aja", "American Jewish Archives", "https://www.americanjewisharchives.org/",
     entry_kind="repository", repository_type="religious_archive", geo=[state("Ohio", "Hamilton", "Cincinnati")],
     description="Archive of American Jewish history: manuscripts, congregational and organizational records.",
     record_types=["congregational_registers", "manuscript_catalogs", "letters"], capabilities=["catalog", "onsite"], verification_status="partial",
     tags=["religious archive", "Jewish genealogy"])
prov("moravian", "Moravian Archives (Bethlehem)", "https://www.moravianchurcharchives.org/", "religious_archive", "United States")
coll("moravian-archives", "moravian", "Moravian Archives, Bethlehem", "https://www.moravianchurcharchives.org/research/",
     entry_kind="repository", repository_type="religious_archive", geo=[state("Pennsylvania", "Northampton", "Bethlehem")],
     description="Archives of the Moravian Church (Northern Province): baptisms, marriages, funerals and church registers.",
     record_types=["baptisms", "marriages", "burials", "congregational_registers"], capabilities=["name_index", "catalog", "onsite"],
     access_search=["free"], maintenance_notes="Site notice on 2026-10-05: online finding aid and digitized images not working properly since 30 Sep 2026.",
     tags=["religious archive"])
prov("archny", "Archdiocese of New York Archives", "https://www.archny.org/", "religious_archive", "United States")
coll("archdiocese-ny-archives", "archny", "Archdiocese of New York — archives & genealogy", "https://www.archny.org/archives-genealogy",
     entry_kind="repository", repository_type="religious_archive", geo=[state("New York")],
     description="Requests for sacramental records (baptisms, marriages) from the Archdiocese of New York.",
     record_types=["baptisms", "marriages", "congregational_registers"], capabilities=["request_only"], access_copies=["paid_retrieval"], tags=["religious archive", "Catholic"])
prov("aoc", "Archdiocese of Cincinnati Archives", "https://resources.catholicaoc.org/", "religious_archive", "United States")
coll("archdiocese-cincinnati-archives", "aoc", "Archdiocese of Cincinnati — genealogy requests", "https://resources.catholicaoc.org/offices/archives/genealogy",
     entry_kind="repository", repository_type="religious_archive", geo=[state("Ohio")],
     description="Genealogy requests for sacramental records (baptisms, marriages, burials) held by the Archdiocese of Cincinnati.",
     record_types=["baptisms", "marriages", "burials"], capabilities=["request_only"], access_search=["paid_retrieval"], access_copies=["paid_retrieval"],
     tags=["religious archive", "Catholic"])
prov("cla", "Congregational Library & Archives", "https://congregationallibrary.org/", "religious_archive", "United States")
coll("congregational-library", "cla", "Congregational Library & Archives", "https://congregationallibrary.org/researching-congregational-story",
     entry_kind="repository", repository_type="religious_archive", geo=[state("Massachusetts", "Suffolk", "Boston")],
     description="Congregational church records, ministers' obituaries and yearbooks, with some digitized records.",
     record_types=["congregational_registers", "baptisms", "marriages", "obituaries", "yearbooks"], capabilities=["catalog", "name_index", "browse_images", "onsite"],
     access_search=["free"], access_images=["free"], access_copies=["onsite"], tags=["religious archive", "New England"])
coll("nara-state-archives-list", "nara", "NARA list of state archives", "https://www.archives.gov/research/alic/reference/state-archives.html",
     entry_kind="directory", repository_type="directory", geo=[US], description="National Archives list of links to U.S. state archives (page data as of April 2022).",
     capabilities=["catalog"], access_search=["free"], access_images=[], access_copies=[], tags=["directory", "state archives"])
prov("cosa", "Council of State Archivists", "https://www.statearchivists.org/", "directory", "United States")
coll("cosa-directory", "cosa", "Council of State Archivists member directory", "https://business.statearchivists.org/directory/FindStartsWith?term=%23%21",
     entry_kind="directory", repository_type="directory", geo=[US], description="Directory of U.S. state and territorial archives.",
     capabilities=["catalog"], access_search=["free"], access_images=[], access_copies=[], verification_status="partial", tags=["directory", "state archives"])

# ======================================================================= PATHWAY COLLECTIONS
coll("nara-freedmens-bureau", "nara", "Freedmen's Bureau records (NARA RG 105)", "https://www.archives.gov/research/african-americans/freedmens-bureau",
     entry_kind="collection", repository_type="national_archive", geo=[US], dates=[dr(1865, 1872)],
     description="Records of the Bureau of Refugees, Freedmen, and Abandoned Lands, 1865–1872 — labor contracts, marriage records, rations, letters — key sources for African American families after emancipation. Images are available through partner sites.",
     record_types=["marriages", "employment", "court_cases", "letters", "poor_relief"], capabilities=["browse_images", "catalog"],
     access_search=["free"], access_images=["free_account"], access_copies=["paid_retrieval"],
     access_notes="NARA guidance page; digitized images are browseable via FamilySearch (free account) and other partners.",
     pathways=["african-american"], tags=["African American research"])
coll("nara-african-american", "nara", "NARA African American Heritage", "https://www.archives.gov/research/african-americans",
     entry_kind="guide", repository_type="national_archive", geo=[US],
     description="National Archives hub for researching African American history and families in federal records.",
     capabilities=["catalog"], access_search=["free"], pathways=["african-american"], tags=["African American research", "guidance"])
coll("loc-african-american-family-histories", "loc", "LOC guide: African American Family Histories and Genealogies", "https://guides.loc.gov/african-american-family-histories",
     entry_kind="guide", repository_type="national_library", geo=[US],
     description="Library of Congress resource guide to published African American family histories and genealogies.",
     record_types=["family_histories"], capabilities=["catalog"], access_search=["free"], access_images=["library"], access_copies=["onsite"],
     pathways=["african-american"], tags=["African American research", "guidance"])
coll("nara-dawes", "nara", "Dawes Records of the Five Civilized Tribes", "https://www.archives.gov/research/native-americans/dawes",
     entry_kind="collection", repository_type="national_archive", geo=[state("Oklahoma")], dates=[dr(1898, 1914)],
     description="Enrollment cards, applications and related records created by the Dawes Commission for the Cherokee, Chickasaw, Choctaw, Creek and Seminole Nations, 1898–1914.",
     record_types=["population_registers", "court_cases"], capabilities=["name_index", "browse_images", "catalog"],
     access_search=["free"], access_images=["free"], access_copies=["paid_retrieval"], pathways=["indigenous"], tags=["Indigenous research"],
     limitations="Appearing (or not) on the rolls does not determine present-day tribal citizenship, which each tribal nation decides.")
coll("loc-indian-census-rolls", "loc", "Indian Census Rolls (LOC guide)", "https://guides.loc.gov/native-americans/rolls",
     entry_kind="guide", repository_type="national_library", geo=[US], dates=[dr(1885, 1935, "Range as given on the guide page checked 2026-10-05")],
     description="Library of Congress guide to the Indian Census Rolls kept by agents of the Bureau of Indian Affairs (originals at the National Archives).",
     record_types=["censuses"], capabilities=["browse_images"], access_search=["free"], verification_status="partial",
     pathways=["indigenous"], tags=["Indigenous research", "guidance"],
     maintenance_notes="Some sources cite 1885–1940 for these rolls; the guide page checked gave 1885–1935. Verify per agency.")
coll("nara-native-american", "nara", "NARA American Indian and Alaska Native records", "https://www.archives.gov/research/native-americans",
     entry_kind="guide", repository_type="national_archive", geo=[US],
     description="National Archives hub for federal records about American Indian and Alaska Native people.",
     capabilities=["catalog", "onsite"], access_search=["free"], access_copies=["onsite"], pathways=["indigenous"], tags=["Indigenous research", "guidance"])
coll("lac-first-nations-genealogy", "lac", "LAC: First Nations genealogy", "https://www.canada.ca/en/library-archives/collection/research-help/indigenous-history/first-nations-genealogy.html",
     entry_kind="guide", repository_type="national_archive", geo=[{"country": "Canada"}],
     description="Library and Archives Canada guidance for First Nations genealogy, including Indian Registers and treaty annuity paylists.",
     record_types=["population_registers"], capabilities=["catalog", "browse_images", "request_only"], access_search=["free"], access_images=["free"],
     access_copies=["onsite", "paid_retrieval"], pathways=["indigenous"], tags=["Indigenous research", "Canada"])
prov("cwig", "Child Welfare Information Gateway", "https://www.childwelfare.gov/", "government_agency", "United States")
coll("cwig-adoption-records", "cwig", "Access to Adoption Records (state statutes series)", "https://www.childwelfare.gov/resources/access-adoption-records/",
     entry_kind="guide", repository_type="government_agency", geo=[US],
     description="Summaries of state laws on access to adoption records by adoptees, birth parents and others.", capabilities=["catalog"], access_search=["free"],
     limitations="The state-law summary states it is current only through 12-31-2019 — check each state's current law.", pathways=["adoption"], tags=["adoption"])
coll("cwig-birth-relatives", "cwig", "Searching for Birth Relatives (factsheet)", "https://www.childwelfare.gov/resources/searching-birth-relatives/",
     entry_kind="guide", repository_type="government_agency", geo=[US], description="Factsheet on searching for birth relatives, registries and intermediaries.",
     access_search=["free"], pathways=["adoption"], tags=["adoption"])
coll("familysearch-us-adoption", "familysearch", "FamilySearch Wiki: United States Adoption", "https://www.familysearch.org/en/wiki/United_States_Adoption",
     entry_kind="guide", repository_type="nonprofit_database", geo=[US], description="Wiki guide to U.S. adoption research, including orphan train records.",
     capabilities=["catalog"], access_search=["free"], pathways=["adoption"], tags=["adoption", "guidance"])
prov("arolsen", "Arolsen Archives", "https://arolsen-archives.org/", "national_archive", "Germany")
coll("arolsen-online", "arolsen", "Arolsen Archives online collections", "https://collections.arolsen-archives.org/en/search",
     entry_kind="collection", repository_type="national_archive", geo_scope="worldwide", dates=[dr(1933, 1959, "Nazi persecution and its aftermath (approximate)")],
     description="Searchable online archive on victims and survivors of Nazi persecution, forced labour, and displaced persons, with document images.",
     record_types=["institutional_registers", "passenger_lists", "employment", "casualties", "population_registers"], capabilities=["name_index", "browse_images"],
     access_search=["free"], access_images=["free"], access_copies=["unknown"], pathways=["displacement"], tags=["displacement", "Holocaust"])
prov("ushmm", "United States Holocaust Memorial Museum", "https://www.ushmm.org/", "national_archive", "United States")
coll("ushmm-individual-research", "ushmm", "USHMM Holocaust Survivors and Victims resources & ITS archive", "https://www.ushmm.org/remember/resources-holocaust-survivors-victims/individual-research",
     entry_kind="collection", repository_type="national_archive", geo_scope="worldwide", dates=[dr(1933, 1959, "Approximate")],
     description="USHMM's Holocaust Survivors and Victims Database and research help, including requests for searches in the International Tracing Service (ITS) digital archive.",
     record_types=["institutional_registers", "passenger_lists", "casualties"], capabilities=["name_index", "onsite", "request_only"],
     access_search=["free"], access_images=["onsite"], access_copies=["free"], pathways=["displacement"], tags=["displacement", "Holocaust"])
coll("nara-passenger-arrival", "nara", "NARA Passenger Arrival Records", "https://www.archives.gov/research/immigration/passenger-arrival.html",
     entry_kind="guide", repository_type="national_archive", geo=[US], dates=[dr(1820, 1982)],
     description="National Archives guidance on federal passenger arrival records and where they can be searched (some via partner sites).",
     record_types=["passenger_lists"], capabilities=["browse_images", "request_only"], access_search=["free", "subscription"],
     access_images=["free_account", "subscription"], access_copies=["paid_retrieval"], pathways=["migration-immigration"], tags=["immigration"])
coll("nara-naturalization", "nara", "NARA Naturalization Records", "https://www.archives.gov/research/immigration/naturalization",
     entry_kind="guide", repository_type="national_archive", geo=[US], dates=[dr(1790, 1991)],
     description="National Archives guidance on naturalization records in federal courts.", record_types=["naturalization"],
     capabilities=["request_only", "onsite"], access_copies=["paid_retrieval"], pathways=["migration-immigration"], tags=["immigration"],
     limitations="Before 1906, naturalizations could take place in any court — many are in county or state courts, not federal records.")
prov("uscis", "U.S. Citizenship and Immigration Services", "https://www.uscis.gov/", "government_agency", "United States")
coll("uscis-genealogy", "uscis", "USCIS Genealogy Program", "https://www.uscis.gov/records/genealogy",
     entry_kind="collection", repository_type="government_agency", geo=[US], dates=[dr(1906, None, "Federal immigration and naturalization files from 1906")],
     description="Fee-based requests for historical immigration and naturalization files (e.g. C-files, A-files, visa files) held by USCIS.",
     record_types=["naturalization", "citizenship_files", "passenger_lists"], capabilities=["request_only"],
     access_search=["paid_retrieval"], access_images=["paid_retrieval"], access_copies=["paid_retrieval"], pathways=["migration-immigration"], tags=["immigration"])
prov("ellis-island", "Statue of Liberty – Ellis Island Foundation", "https://www.statueofliberty.org/", "nonprofit_database", "United States")
coll("ellis-island-passenger-search", "ellis-island", "Ellis Island Foundation passenger search", "https://www.statueofliberty.org/arrival-search/",
     entry_kind="collection", repository_type="nonprofit_database", geo=[state("New York", "New York")],
     description="Searchable arrival records for the Port of New York from the Statue of Liberty–Ellis Island Foundation.",
     record_types=["passenger_lists"], capabilities=["name_index"], access_copies=["paid_retrieval"], verification_status="partial",
     pathways=["migration-immigration"], tags=["immigration"])

# ======================================================================= RELATIONS (overlap)
def rel(key, a, b, relation, note):
    R.append({"key": key, "a": a, "b": b, "relation": relation, "note": note})

rel("rel-fs-fulltext-catalog", "familysearch-full-text", "familysearch-catalog", "overlaps", "Both reach FamilySearch's unindexed image sets — one by text, one by place/catalog.")
rel("rel-nara-freedmens-fs", "nara-freedmens-bureau", "familysearch-historical-records", "overlaps", "Freedmen's Bureau images are browseable at FamilySearch.")
rel("rel-freebmd-fmp", "freebmd", "findmypast", "overlaps", "Both index England & Wales civil registration; transcriptions differ, so search both.")
rel("rel-ancestry-fs-census", "ancestry-card-catalog", "familysearch-historical-records", "overlaps", "U.S. censuses are indexed separately by both; indexes differ.")
rel("rel-loc-npa", "loc-chronicling-america", "newspaperarchive", "overlaps", "Some titles appear in both; OCR differs.")
rel("rel-ellis-nara", "ellis-island-passenger-search", "nara-passenger-arrival", "overlaps", "New York arrivals are indexed by several providers; indexes differ.")
rel("rel-ontario-fs", "archives-ontario", "familysearch-historical-records", "overlaps", "Ontario vital registrations are served via FamilySearch (free account).")

# ======================================================================= PATHWAYS
PW = json.loads((Path(__file__).resolve().parent / "research" / "local_and_pathways.json").read_text())["pathways"]
for p in PW:
    W.append({"key": p["key"], "title": p["title"], "summary": p["summary"], "cautions": p["cautions"],
              "steps": [{"title": s["title"], "detail": s["detail"], "guidance_url": s["guidance_url"]} for s in p["steps"]],
              "sources": [{"title": s["title"], "url": s["url"]} for s in p["guidance_sources"] if s.get("fetch_ok", True)],
              "last_verified": CHECKED, "verification_status": "verified"})

# Fix pathway keys used on collections to match research keys
for c in C:
    c["pathways"] = [{"migration-immigration": "migration-immigration"}.get(x, x) for x in c["pathways"]]

out = {"version": VERSION, "generated_from": "tools/build_seed.py", "checked_on": CHECKED,
       "coverage_note": "Initial curated directory. It is NOT comprehensive: local repositories and international resources are a starting sample.",
       "providers": P, "collections": C, "relations": R, "pathways": W}
dest = Path(__file__).resolve().parent.parent / "app" / "seed" / "directory_seed.json"
dest.write_text(json.dumps(out, indent=1, ensure_ascii=False))
print(f"wrote {dest}: {len(P)} providers, {len(C)} collections, {len(R)} relations, {len(W)} pathways")
