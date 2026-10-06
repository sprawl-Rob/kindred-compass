"""PDF family-tree charts: boxes + connecting lines → people, families and GEDCOM (synthetic chart, invented people)."""
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.pdfimport import ftm_chart as fc


def _text(x, y, size, s):
    return f"BT /F1 1 Tf {size} 0 0 {size} {x} {y} Tm ({s}) Tj ET\n"


def _box(x0, y0, x1, y1):
    return f"0.9 g {x0} {y0} {x1 - x0} {y1 - y0} re B*\n0 g\n"


def make_chart(tmp_path):
    c = "1 0 0 1 0 0 cm\n"
    c += "".join(_text(200 + i * 40, 900, 64.8, ch) for i, ch in enumerate("Sample"))
    # child box: ancestor first, then a sister
    c += _box(50, 400, 200, 470) + _text(55, 455, 10.8, "Mr. Kid Sample") + _text(60, 445, 5.4, "Born: May 01, 1900 in Fitchburg, MA") \
        + _text(55, 425, 10.8, "Ms. Maria Sample \\(Sister") + _text(55, 415, 10.8, "Agnes\\)") + _text(60, 405, 5.4, "Born: 1902")
    # mother drawn ABOVE the child, father below: parents are told apart by Mr./Ms., not position
    c += _box(270, 560, 420, 600) + _text(275, 585, 10.8, "Ms. Ma Jones") + _text(280, 575, 5.4, "Born: October 1874 in St. Albert, Quebec,") \
        + _text(280, 568, 5.4, "Canada")
    c += _box(260, 260, 410, 300) + _text(265, 285, 10.8, "Mr. Pa Sample") + _text(270, 275, 5.4, "Married: June 02, 1895 in Boston, MA") \
        + _text(270, 268, 5.4, "Died: in Fitchburg, MA")
    # connectors: child top edge → mother's left edge; child bottom edge → father's left edge
    c += "120 470 m 120 580 l S\n120 580 m 270 580 l S\n120 400 m 120 280 l S\n120 280 m 260 280 l S\n"
    w = PdfWriter()
    page = w.add_blank_page(1000, 1000)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    st = DecodedStreamObject()
    st.set_data(c.encode("latin-1"))
    page[NameObject("/Contents")] = w._add_object(st)
    p = tmp_path / "chart.pdf"
    with open(p, "wb") as f:
        w.write(f)
    return p


def test_chart_people_families_and_gedcom(tmp_path):
    ch = fc.parse_pdf(make_chart(tmp_path).read_bytes())
    assert ch.title == "Sample"
    names = {p.name: p for p in ch.people.values()}
    assert set(names) == {"Kid Sample", "Maria Sample", "Ma Jones", "Pa Sample"}
    assert names["Maria Sample"].note == "Sister Agnes" and names["Maria Sample"].sex == "F"
    assert ("BIRT", "October 1874", "St. Albert, Quebec, Canada") in names["Ma Jones"].facts   # wrapped place joined
    assert ("DEAT", None, "Fitchburg, MA") in names["Pa Sample"].facts
    fam = ch.families[0]
    assert ch.people[fam["husb"]].name == "Pa Sample" and ch.people[fam["wife"]].name == "Ma Jones"
    assert {ch.people[k].name for k in fam["children"]} == {"Kid Sample", "Maria Sample"}
    assert fam["marr"] == ("June 02, 1895", "Boston, MA")
    ged = fc.to_gedcom(ch, "chart.pdf")
    assert "1 NAME Kid /Sample/" in ged and "2 DATE 1 MAY 1900" in ged and "2 DATE 2 JUN 1895" in ged and "2 NICK Sister Agnes" in ged


def test_dates_and_names():
    assert fc.ged_date("February 08, 1750/51") == "8 FEB 1750/51"
    assert fc.ged_date("October 1874") == "OCT 1874" and fc.ged_date("1906") == "1906"
    assert fc.split_name("Pierre Lavoie dit Lafleur", set()) == ("Pierre", "Lavoie dit Lafleur")
    assert fc.split_name("Marie Louise St. Onge", {"st. onge"}) == ("Marie Louise", "St. Onge")


def test_pdf_import_goes_through_preview_and_commit(make_client, tmp_path):
    c = make_client()
    path = make_chart(tmp_path)
    r = c.c.post("/api/imports", files={"gedcom": ("chart.pdf", path.read_bytes(), "application/pdf")}, headers={"X-Kindred": "1"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["plan"]["detection"]["product"] == "pdf_chart" and b["plan"]["counts"]["people"] == 4
    done = c.ok("post", f"/api/imports/{b['id']}/commit")
    t = c.ok("get", f"/api/projects/{done['project_id']}/tree")
    names = {t["pedigree"]["name"]} | {p["name"] for p in t["pedigree"]["parents"]}
    assert {"Pa Sample", "Ma Jones"} <= names
