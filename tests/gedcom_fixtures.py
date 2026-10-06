"""Representative GEDCOM exports used by the import tests.

All people are fictional. Header and tag shapes follow documented Ancestry, Family Tree
Maker and RootsMagic exports (see docs/ancestry-import.md for sources).
"""
from __future__ import annotations

import io
import zipfile

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 48
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 48

# Header shape verbatim from a real 2024 Ancestry "Export tree" file (tree details replaced).
ANCESTRY_HEAD = """0 HEAD
1 SUBM @SUBM1@
1 SOUR Ancestry.com Family Trees
2 NAME Ancestry.com Member Trees
2 VERS 2024.01
2 _TREE Ferris Family Tree (fictional)
3 RIN 168300001
3 NOTE Ancestors of Josiah Ferris (fictional test tree)
3 _ENV prd
2 CORP Ancestry.com
3 PHON 801-705-7000
3 WWW www.ancestry.com
3 ADDR 1300 West Traverse Parkway
4 CONT Lehi, UT  84043
4 CONT USA
1 DATE 5 Oct 2026
2 TIME 08:01:12
1 GEDC
2 VERS 5.5.1
2 FORM LINEAGE-LINKED
1 CHAR UTF-8
0 @SUBM1@ SUBM
1 NAME Ancestry.com Member Trees Submitter
"""

ANCESTRY_V1 = ANCESTRY_HEAD + """0 @I112187149801@ INDI
1 NAME Josiah /Ferris/
2 GIVN Josiah
2 SURN Ferris
1 SEX M
1 BIRT
2 DATE abt 1852
2 PLAC Fitchburg, Worcester, Massachusetts, USA
2 SOUR @S94982896@
3 PAGE Year: 1880; Census Place: Fitchburg, Worcester, Massachusetts; Page: 12
3 _APID 1,6742::12345678
3 _APID 1,6742::12345679
3 DATA
4 TEXT Josiah Ferris, 28, machinist
4 WWW https://www.fold3.com/record/000000/fictional
1 BIRT
2 DATE 1849
2 PLAC New Hampshire, USA
2 NOTE Death record gives 1849 in New Hampshire.
1 DEAT
2 DATE 12 Mar 1903
2 PLAC Fitchburg, Worcester, Massachusetts, USA
2 CAUS Pneumonia
1 _MILT
2 DATE 1864-1865
2 PLAC Massachusetts, USA
2 NOTE 21st Massachusetts Infantry
1 _EMPLOY
2 DATE 1880
2 PLAC Fitchburg, Worcester, Massachusetts, USA
2 NOTE Putnam Machine Company
1 _CUSTOMTAG Preserve me
2 _DETAIL <script>alert('x')</script>
1 RESI
2 DATE Between 1870 and 1875
2 PLAC Nashua, Hillsborough, New Hampshire, USA
1 OCCU Machinist
2 DATE 1880
1 FAMS @F2@
1 FAMS @F3@
1 OBJE @O1@
2 _PRIM Y
2 _CROP
3 _LEFT 61
3 _TOP 85
3 _WDTH 244
3 _HGHT 340
3 _TYPE primary
1 OBJE @O2@
1 NOTE Family story: worked at the Putnam Machine Company. The note continues on a long li
2 CONC ne that Ancestry split mid-word.
2 CONT Second line of the note.
0 @I112187149802@ INDI
1 NAME Margarethe /Fehrs/
2 TYPE birth
1 NAME Margaret /Ferris/
2 TYPE married
1 SEX F
1 BIRT
2 DATE BET 1853 AND 1856
2 PLAC Holstein, Preußen
1 EVEN
2 TYPE Arrival
2 DATE 1868
2 PLAC New York, New York, USA
1 DEAT
2 DATE Before 1885
1 FAMS @F2@
0 @I112187149803@ INDI
1 NAME Zoë /Łukasiewicz/
1 SEX F
1 BIRT
2 DATE CAL 1860
2 PLAC Kraków, Galicia, Austria
1 FAMS @F3@
0 @I112187149804@ INDI
1 NAME George /Ferris/
1 SEX M
1 BIRT
2 DATE 4 Jul 1876
2 PLAC Fitchburg, Worcester, Massachusetts, USA
1 FAMC @F2@
1 FAMC @F3@
0 @I112187149805@ INDI
1 NAME Anna /Ferris/
1 SEX F
1 BIRT
2 DATE 1888
1 FAMC @F3@
0 @I112187149806@ INDI
1 NAME 王 /秀英/
1 SEX F
1 BIRT
2 DATE INT 1890 (about the time of the flood)
1 ADOP Y
1 FAMC @F3@
0 @F2@ FAM
1 HUSB @I112187149801@
1 WIFE @I112187149802@
1 CHIL @I112187149804@
1 MARR
2 DATE abt 1875
2 PLAC Fitchburg, Worcester, Massachusetts, USA
0 @F3@ FAM
1 HUSB @I112187149801@
1 WIFE @I112187149803@
1 CHIL @I112187149804@
2 _MREL step
1 CHIL @I112187149805@
1 CHIL @I112187149806@
2 _FREL adopted
2 _MREL adopted
1 MARR
2 DATE 1886
1 DIV
2 DATE AFT 1895
0 @S94982896@ SOUR
1 TITL 1880 United States Federal Census
1 AUTH Ancestry.com
1 PUBL Ancestry.com Operations Inc
1 REPO @R54102289@
1 _APID 1,6742::0
0 @R54102289@ REPO
1 NAME Ancestry.com
0 @O1@ OBJE
1 FILE
2 FORM jpg
3 TYPE image
3 _MTYPE portrait
3 _STYPE jpeg
3 _SIZE 97783
3 _WDTH 433
3 _HGHT 677
2 TITL Josiah portrait
1 RIN 0f67aeca-eefc-4dc0-b2c6-8c0865062e83
1 _CREA 2020-04-30 01:54:00.000
1 _ORIG u
1 _ATL N
0 @O2@ OBJE
1 FILE
2 FORM pdf
3 TYPE story
3 _MTYPE story
2 TITL Josiah's war story
1 RIN 9a1b2c3d-0000-4000-8000-000000000002
0 TRLR
"""

# Repeat export: Josiah gains a fact, the 1849 birth was deleted in the tree, Margarethe's
# record identifier changed (same person), a new child appears, and a different person reuses @I105@.
ANCESTRY_V2 = ANCESTRY_V1.replace("""1 BIRT
2 DATE 1849
2 PLAC New Hampshire, USA
2 NOTE Death record gives 1849 in New Hampshire.
""", "").replace("""1 OCCU Machinist
2 DATE 1880
""", """1 OCCU Machinist
2 DATE 1880
1 RESI
2 DATE 1900
2 PLAC Fitchburg, Worcester, Massachusetts, USA
""").replace("@I112187149802@", "@I112187149902@").replace("""0 @I112187149805@ INDI
1 NAME Anna /Ferris/
1 SEX F
1 BIRT
2 DATE 1888
""", """0 @I112187149805@ INDI
1 NAME Walter /Brooks/
1 SEX M
1 BIRT
2 DATE 1801
""").replace("""0 @F2@ FAM""", """0 @I112187149807@ INDI
1 NAME Clara /Ferris/
1 SEX F
1 BIRT
2 DATE 1879
1 FAMC @F2@
0 @F2@ FAM""").replace("""1 CHIL @I112187149804@
1 MARR
2 DATE abt 1875""", """1 CHIL @I112187149804@
1 CHIL @I112187149807@
1 MARR
2 DATE abt 1875""")


def ancestry_zip(text: str = None) -> bytes:
    """Ancestry delivers the export inside a ZIP."""
    return zip_bytes({"Ferris Family Tree (fictional).ged": (text or ANCESTRY_V1).encode("utf-8")})

FTM = """0 HEAD
1 SOUR FTM
2 NAME Family Tree Maker for Windows
2 VERS 24.2.2.580
2 CORP The Software MacKiev Company
1 DEST GED55
1 DATE 1 OCT 2026
1 GEDC
2 VERS 5.5.1
2 FORM LINEAGE-LINKED
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Henry /Ferris/
1 SEX M
1 BIRT
2 DATE 1820
2 PLAC Lunenburg, Worcester, Massachusetts, USA
2 OBJE
3 FILE C:\\Users\\Rob\\Documents\\Family Tree Maker\\Ferris Media\\birth-register.png
3 FORM png
3 TITL Birth register page
1 OBJE
2 FILE C:\\Users\\Rob\\Documents\\Family Tree Maker\\Ferris Media\\henry.jpg
2 FORM jpg
1 OBJE
2 FILE C:\\Users\\Rob\\Documents\\Family Tree Maker\\Ferris Media\\missing-letter.pdf
2 FORM pdf
1 OBJE
2 FILE portrait.jpg
2 FORM jpg
1 FAMS @F1@
0 @I2@ INDI
1 NAME Mary /Lane/
1 SEX F
1 FAMS @F1@
0 @I3@ INDI
1 NAME Thomas /Ferris/
1 SEX M
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
2 _FREL Step
2 _MREL Natural
1 MARR
2 DATE 1845
0 TRLR
"""
# FTM 2019 shape: UTF-8 with BOM, DEST FTM, _PHOTO primary photo, _LINK + _JUST on citations, FSID.
FTM2019 = ("\ufeff" + """0 HEAD
1 SOUR FTM
2 NAME Family Tree Maker for Windows
2 VERS 24.0.1.1252
2 CORP The Software MacKiev Company
1 DEST FTM
1 DATE 3 Oct 2026
1 GEDC
2 VERS 5.5.1
2 FORM LINEAGE-LINKED
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Lydia /Gates/
1 SEX F
1 FSID ABCD-123
1 _PHOTO @M1@
1 BIRT
2 DATE 1830
2 SOUR @S1@
3 PAGE Vol. 2, p. 14
3 _LINK https://search.ancestry.com/cgi-bin/sse.dll?db=61632&h=1558842&indiv=try
3 _JUST Age at death implies birth about 1830
0 @M1@ OBJE
1 FILE C:\\FTM\\Gates Media\\lydia.jpg
2 FORM jpg
1 _DATE 1870
0 @S1@ SOUR
1 TITL Massachusetts, Town and Vital Records
0 TRLR
""").replace("\n", "\r\n").encode("utf-8")

FTM_MEDIA = {
    "Ferris Media/birth-register.png": PNG,
    "Ferris Media/henry.jpg": JPG,
    "Other Folder/portrait.jpg": JPG,
    "Ferris Media/portrait.jpg": JPG,
    "Unreferenced/random.png": PNG,
}

# RootsMagic, ANSEL-encoded: "José" is written as ANSEL acute (0xE2) before "e".
ROOTSMAGIC_ANSEL = (b"""0 HEAD
1 SOUR RootsMagic
2 NAME RootsMagic
2 VERS 10.0.3.0
1 DEST RootsMagic
1 DATE 2 OCT 2026
1 GEDC
2 VERS 5.5.1
2 FORM LINEAGE-LINKED
1 CHAR ANSEL
0 @I1@ INDI
1 NAME Jos\xe2e /Garc\xe2ia/
1 SEX M
1 _UID 7F3A2B9C4D5E6F708192A3B4C5D6E7F8A9B0
1 BIRT
2 DATE 1750/51
2 PLAC Sevilla, Andaluc\xe2ia, Spain
2 _PRIM Y
1 FAMC @F1@
2 PEDI adopted
1 OBJE
2 FILE media\\scan.png
2 FORM png
0 @I2@ INDI
1 NAME Mar\xe2ia /L\xe2opez/
1 SEX F
1 _UID 11112222333344445555666677778888AAAA
1 FAMS @F1@
0 @F1@ FAM
1 WIFE @I2@
1 CHIL @I1@
0 TRLR
""").replace(b"\n", b"\r\n")

BROKEN = """0 HEAD
1 GEDC
2 VERS 5.5
1 CHAR ASCII
0 @I1@ INDI
1 NAME Broken /Example/
this line has no level number
3 DATE 1900
1 BIRT
2 DATE 1901
"""


def zip_bytes(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def evil_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("tree.ged", ANCESTRY_V1)
        z.writestr("../../escape.png", PNG)
        z.writestr("/abs/path.png", PNG)
        info = zipfile.ZipInfo("link.png")
        info.external_attr = (0o120777 << 16)
        z.writestr(info, "/etc/passwd")
    return buf.getvalue()


def bomb_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("tree.ged", ANCESTRY_V1)
        z.writestr("huge.png", b"\x00" * (30 * 1024 * 1024))
    return buf.getvalue()
