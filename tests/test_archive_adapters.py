"""Key-based archive adapters: request mapping and response parsing against documented shapes (fake HTTP)."""
import pytest

from app.integrations.base import IntegrationError, SearchQuery
from app.integrations.keyed import DPLAAdapter, EuropeanaAdapter, NARACatalogAdapter, TroveAdapter


def fake(resp, seen):
    def get(url, params):
        seen.append((url, params))
        return resp
    return get


def test_keys_required():
    for cls in (DPLAAdapter, NARACatalogAdapter, TroveAdapter, EuropeanaAdapter):
        with pytest.raises(IntegrationError) as e:
            cls(http_get=fake({}, [])).search(SearchQuery(text="Ferris"))
        assert e.value.code == "no_key"


def test_dpla_mapping():
    seen = []
    resp = {"count": 1, "docs": [{"id": "abc", "isShownAt": "https://library.example/item/1", "dataProvider": {"name": "Fitchburg Library"},
                                  "sourceResource": {"title": ["Ferris family photograph"], "date": [{"displayDate": "1890"}],
                                                     "description": ["Josiah Ferris and family"], "spatial": [{"name": "Fitchburg (Mass.)"}]}}]}
    r = DPLAAdapter(http_get=fake(resp, seen), api_key="k" * 32).search(SearchQuery(text="Josiah Ferris", phrase=True, year_from=1880, year_to=1900, state="Massachusetts"))
    p = seen[0][1]
    assert p["q"] == '"Josiah Ferris"' and p["sourceResource.date.after"] == "1880" and p["sourceResource.spatial.state"] == "Massachusetts" and p["api_key"]
    h = r.hits[0]
    assert (h.title, h.url, h.date_text, h.place_text, h.collection) == ("Ferris family photograph", "https://library.example/item/1", "1890",
                                                                        "Fitchburg (Mass.)", "Fitchburg Library")


def test_nara_mapping_text_and_html_on_bad_key():
    resp = {"body": {"hits": {"total": {"value": 1}, "hits": [{"_source": {"record": {
        "naId": 123, "title": "Pension file of Josiah Ferris", "productionDates": [{"logicalDate": "1890-01-01T00:00:00Z"}],
        "scopeAndContentNote": "Civil War pension", "digitalObjects": [{"extractedText": "Josiah Ferris, private, Co. B"}]}}}]}}}
    a = NARACatalogAdapter(http_get=fake(resp, []), api_key="key123")
    r = a.search(SearchQuery(text="Josiah Ferris"))
    assert r.hits[0].url == "https://catalog.archives.gov/id/123" and r.total == 1 and r.hits[0].date_text == "1890-01-01"
    assert "private, Co. B" in a.fetch_text(r.hits[0])
    bad = NARACatalogAdapter(http_get=fake("<html>Catalog</html>", []), api_key="wrong")
    with pytest.raises(IntegrationError) as e:
        bad.search(SearchQuery(text="x"))
    assert e.value.code == "auth" and "API key" in e.value.message


def test_trove_mapping_strips_markup_and_keeps_attribution():
    seen = []
    resp = {"category": [{"records": {"total": 2, "article": [{"id": "9", "heading": "Family <b>Notices</b>", "date": "1885-03-02",
                                                              "troveUrl": "https://trove.nla.gov.au/newspaper/article/9", "snippet": "FERRIS — On the <b>2nd</b>",
                                                              "title": {"title": "The Argus", "state": "Victoria"}}]}}]}
    r = TroveAdapter(http_get=fake(resp, seen), api_key="k").search(SearchQuery(text="Ferris", year_from=1880, year_to=1889, state="Victoria"))
    p = seen[0][1]
    assert "date:[1880-01-01T00:00:00Z TO 1889-12-31T00:00:00Z]" in p["q"] and p["l-state"] == "Victoria" and p["encoding"] == "json"
    h = r.hits[0]
    assert h.title == "Family Notices" and h.snippet == "FERRIS — On the 2nd" and h.place_text == "Victoria" and "Trove" in h.extra["attribution"]
    assert not TroveAdapter.supports_text   # full text needs an exemption under Trove's terms


def test_europeana_mapping():
    resp = {"totalResults": 1, "items": [{"id": "/1/x", "title": ["Kirchenbuch Fehrs"], "year": ["1860"], "edmIsShownAt": ["https://archive.example/x"],
                                         "dataProvider": ["Landesarchiv"], "edmPlaceLabel": ["Holstein"]}]}
    r = EuropeanaAdapter(http_get=fake(resp, []), api_key="k").search(SearchQuery(text="Fehrs", year_from=1850, year_to=1870, country="Germany"))
    h = r.hits[0]
    assert (h.title, h.url, h.date_text, h.place_text) == ("Kirchenbuch Fehrs", "https://archive.example/x", "1860", "Holstein")


def test_loc_page_text_two_step_and_keeps_query_string():
    from app.integrations.base import Hit
    from app.integrations.loc import ChroniclingAmericaAdapter
    seen = []

    def get(url, params):
        seen.append((url, params))
        if "tile.loc.gov" in url:
            return {"/service/x.xml": {"full_text": "BUSY LIFE IS ENDED\nAlonzo Whitcomb Dies"}}
        return {"resource": {"fulltext_file": "https://tile.loc.gov/text-services/word-coordinates-service?segment=/x.xml&full_text=1"}}
    t = ChroniclingAmericaAdapter(http_get=get).fetch_text(Hit(item_id="x", title="t", url=None, text_ref="http://www.loc.gov/resource/sn1/1900-03-29/ed-1/?sp=5&q=whitcomb"))
    assert "Alonzo Whitcomb" in t
    assert seen[0][0] == "https://www.loc.gov/resource/sn1/1900-03-29/ed-1/" and seen[0][1]["sp"] == "5" and "q" not in seen[0][1]
    assert "segment=" in seen[1][0]


def test_open_library_and_papers_past_mapping():
    from app.integrations.open_apis import InternetArchiveTextAdapter, PapersPastAdapter
    ol = {"hits": {"total": {"value": 2}, "hits": [{"fields": {"identifier": ["histfitch00"], "meta_title": ["History of Fitchburg"], "meta_year": [1887], "page_num": [[214]]},
                                                    "highlight": {"text": ["partnership of {{{Josiah Ferris}}} and his brother"]}, "availability": {"status": "open"}}]}}
    r = InternetArchiveTextAdapter(http_get=lambda u, p: ol).search(SearchQuery(text="Josiah Ferris", phrase=True))
    h = r.hits[0]
    assert r.total == 2 and h.url == "https://archive.org/details/histfitch00/page/n214" and "{{{" not in h.snippet and h.date_text == "1887"
    seen = []
    dnz = {"search": {"result_count": 1, "results": [{"id": 5, "title": "DEATHS (Otago Daily Times, 2 May 1900)", "date": ["1900-05-02T00:00:00.000Z"],
                                                      "landing_url": "https://paperspast.natlib.govt.nz/newspapers/ODT19000502.2.3", "fulltext": "FERRIS.—On May 1, Josiah Ferris"}]}}
    a = PapersPastAdapter(http_get=lambda u, p: seen.append(p) or dnz)
    r = a.search(SearchQuery(text="Josiah Ferris", year_from=1895, year_to=1905))
    params = seen[0]
    assert ("and[primary_collection][]", "Papers Past") in params and ("or[decade][]", "1890") in params and ("or[decade][]", "1900") in params
    assert "Josiah Ferris" in a.fetch_text(r.hits[0]) and r.hits[0].url.startswith("https://paperspast")
    assert PapersPastAdapter.cache_days == 30 and PapersPastAdapter.optional_key
