# GEDCOM exports from Ancestry, Family Tree Maker and RootsMagic: research notes

Researched 2026-10-05. Confidence labels used below:

- **[CONFIRMED-OFFICIAL]**: the vendor's own help page or the gedcom.io spec says so.
- **[CONFIRMED-SAMPLE]**: seen in a real vendor-generated file that is publicly available (URL given).
- **[SECONDARY]**: a reputable third party says so (a parser's source code, a tool vendor's documentation, Tamura Jones).
- **[UNCONFIRMED]**: plausible, but I found no reliable source. Do not treat as fact.

Main real-world samples used (downloaded and inspected):

| Label | URL | Producer |
|---|---|---|
| **ANC-2024** | https://github.com/oh-kay-blanket/family-plot/blob/main/src/gedcoms/plunkett_ancestry.ged | Real Ancestry "Export tree" file, `VERS 2024.01`, dated 15 Jun 2024, 8,058 lines. This tree was originally uploaded from Gramps, so some NOTE text is Gramps import residue. |
| **FTM-2019** | https://github.com/D-Jeffrey/gedcom-samples/blob/main/pres/pres2020.ged | Family Tree Maker for Windows 24.0.1.1252 (FTM 2019 line), MacKiev, 2020 |
| **FTM-2014win** | https://github.com/gramps-project/gramps/blob/master/data/tests/imp_FTM_LINK.ged and `imp_FTM_PHOTO.ged` | FTM 2014 (22.0.0.1410) and FTM 2012 (21.0.0.723) for Windows |
| **FTM-Mac** | https://github.com/frizbog/gedcom4j/blob/master/sample/ftmcustomtags.ged | FTM for Mac 22.2.5 (Mac 3), with every custom fact type filled in |
| **FTM-2012** | https://github.com/D-Jeffrey/gedcom-samples/blob/main/habs/Habsburg.ged | FTM 20.0.0.376 (2013), `CHAR ANSI` |
| **RM-7** | https://github.com/gramps-project/gramps/blob/master/data/tests/imp_bug_8322_test.ged | RootsMagic 7.0.2.2 header (the body was hand-edited for tests) |

---

## A. Ancestry.com "Export tree"

### A.1 How to export, and what file you get
- Steps: **Trees** tab, pick the tree, **More (⋯)**, **Tree Settings**, then under *Manage your tree* click **Export tree**, then **Export**, wait, then **Download Your GEDCOM File**. [CONFIRMED-OFFICIAL] https://help.ancestry.com/hc/en-us/articles/53933352542867-Uploading-and-Downloading-Trees
- **You get a ZIP:** "Your GEDCOM File will be downloaded inside a Zip file. You'll need to unzip or open the file to access the GEDCOM File." [CONFIRMED-OFFICIAL] (same URL). So an importer should accept `.zip` and extract the single `.ged` inside. The name of the `.ged` inside the ZIP is [UNCONFIRMED].
- Only the tree **owner** can export. No membership is required. [CONFIRMED-OFFICIAL] (same URL). Ancestry always exports the whole tree and there are no options. [SECONDARY] https://dataminingdna.com/download-your-ancestry-tree-to-gedcom-a-complete-guide/ and https://ancestoriq.com/guides/export-tree-from-ancestry/

### A.2 GEDCOM version, character set and encoding
- `1 GEDC / 2 VERS 5.5.1 / 2 FORM LINEAGE-LINKED` and `1 CHAR UTF-8`. [CONFIRMED-SAMPLE] ANC-2024.
- Older exports (the "Ancestry.com Family Trees (2010.3)" generation) declared `2 VERS 5.5`. Seen in parser test fixtures that copy that header: https://github.com/TheGeneGenieProject/GeneGenie.Gedcom/blob/master/GeneGenie.Gedcom.Tests/Data/multiple-sources.ged and https://github.com/vmiklos/ged2dot/blob/master/tests/happy.ged. Those are test files, not raw exports. [SECONDARY]
- "UTF-8 BOM, CRLF line endings": [SECONDARY] https://github.com/ggoosen/gedcom-mcp (README). The ANC-2024 copy on GitHub has no BOM and LF endings, but git may have normalised it. Importers should tolerate either.
- Lines can run past 255 characters (the longest line in ANC-2024 is 259). Ancestry splits long text with `CONC`, sometimes in the middle of a word (`... Bertha. V` / `2 CONC arious records ...`). [CONFIRMED-SAMPLE]

### A.3 HEAD structure ([CONFIRMED-SAMPLE] ANC-2024, verbatim. The tree name is shown as it appears in that public file.)
```
0 HEAD
1 SUBM @SUBM1@
1 SOUR Ancestry.com Family Trees
2 NAME Ancestry.com Member Trees
2 VERS 2024.01
2 _TREE Plunkett Family Tree
3 RIN 168307991
3 NOTE Ancestors of Dennis Plunkett
3 _ENV prd
2 CORP Ancestry.com
3 PHON 801-705-7000
3 WWW www.ancestry.com
3 ADDR 1300 West Traverse Parkway
4 CONT Lehi, UT  84043
4 CONT USA
1 DATE 15 Jun 2024
2 TIME 08:01:12
1 GEDC
2 VERS 5.5.1
2 FORM LINEAGE-LINKED
1 CHAR UTF-8
0 @SUBM1@ SUBM
1 NAME Ancestry.com Member Trees Submitter
```
- `HEAD.SOUR._TREE` holds the **tree name**. `_TREE.RIN` is the **numeric Ancestry tree id** and `_TREE.NOTE` is the tree description. Tamura Jones also says `HEAD.SOUR._TREE.RIN` "seems to be used to provide the unique number identifying the particular Ancestry.com tree". [SECONDARY] https://www.tamurajones.net/GEDCOMRIN.xhtml
- `_ENV prd` is presumably the production environment. [UNCONFIRMED meaning]
- No `1 FILE`, `1 DEST` or `1 LANG` in the 2024 sample. Older exports had `1 DEST GED55`. [SECONDARY]

### A.4 Record xref formats ([CONFIRMED-SAMPLE] ANC-2024)
- INDI: `@I112187149819@`, which is `I` plus a long numeric id (12 digits here). This is Ancestry's person id. The `pid` in Ancestry person URLs is the same kind of id, but I found **no source** that documents xref = pid. [UNCONFIRMED]
- FAM: `@F2@`, `@F3@`, ... These are short sequential ids, **not** long ones.
- SOUR: `@S94982896@` (long numeric). REPO: `@R54102289@` (long numeric).
- OBJE: `@O1@`, `@O2@`, ... (short sequential, prefix `O`).
- SUBM: `@SUBM1@`.
- The 2010-era exports used `@P123@` for people, as in the GeneGenie and ged2dot fixtures above. [SECONDARY]

### A.5 Person and family structures ([CONFIRMED-SAMPLE] ANC-2024)
- Names come out as `1 NAME Given /Surname/` plus `2 GIVN` and `2 SURN`, with optional `2 NSFX`. A citation can sit under NAME (`2 SOUR @S..@`).
- **The parent-child relationship type is written on the FAM record, not with PEDI**:
  ```
  0 @F2@ FAM
  1 HUSB @I...@
  1 WIFE @I...@
  1 CHIL @I...@
  2 _FREL adopted
  1 CHIL @I...@
  2 _MREL step
  ```
  Values seen are lower-case: `adopted`, `step`, `unknown`. When there is no `_FREL`/`_MREL`, the link is biological (implied). There are **no `PEDI` lines** in ANC-2024. `INDI.FAMC` has no substructure, and a person can have several `FAMC`.
- `1 ADOP Y` appears on adopted children. [CONFIRMED-SAMPLE]
- Custom fact tags seen: `_MILT` (military), `_EMPLOY` (employment), and `EVEN` with `2 TYPE Arrival`, `TYPE Departure` or `TYPE NaturalizationPetition`, or a free-text TYPE. Standard tags seen: BIRT, DEAT, BURI, MARR, RESI, BAPM, PROB. `_DEG`, `_DCAUSE` and similar do exist in Ancestry/FTM vocabularies but are not in this sample. The Gramps importer lists FTM/Ancestry custom event tags: `_CIRC _COML _DEST _DNA _DCAUSE _EMPLOY _EXCM _EYC _FUN _HEIG _INIT _MILTID _MISN _NAMS _ORDI _ORIG _SEPR _WEIG`, plus `_DEG _ELEC _MDCL _MILT`. [SECONDARY] https://github.com/gramps-project/gramps/blob/maintenance/gramps52/gramps/plugins/lib/libgedcom.py (CUSTOMEVENTTAGS, around line 736). **Note:** in Gramps' list, `_ORIG` is a *fact* ("Origin"). In Ancestry exports, `OBJE._ORIG` is something different (see A.7).
- **Dates are free text typed by users and are passed through unchanged.** ANC-2024 contains `abt 1880`, `Abt 1880`, `About 1884`, `Before 1951`, `12 Dec` (no year), `2 Juli 1850`, `17 August 1977`, `1 Jun 1918-1919`, `1910-1939`, `Jul Abt 1874`, `??`, and mixed-case months (`Apr` and `APR`). Parsers must be case-insensitive and keep the original string. [CONFIRMED-SAMPLE]
- `_MTTAG` (Ancestry's own person "tags", such as DNA match or Hint) is a **top-level record**. Its xref looks like `T19` and it has a `RIN` (here `19`). [SECONDARY] https://www.tamurajones.net/GEDCOMRIN.xhtml, and https://www.reuniontalk.com/forum/using-reunion-14/99887-ancestry-tags ("*New [_MTTAG]"). I could not confirm exactly how a person points to a `_MTTAG` record (the line under INDI). [UNCONFIRMED]
- Ancestry writes `UID` **without the underscore** for ids that came in as `_UID` (for example from RootsMagic). [SECONDARY] https://www.tamurajones.net/GEDCOMRIN.xhtml and https://sqlitetoolsforrootsmagic.com/ancestry-com-sync/
- `_FREL`/`_MREL` values other than adopted, step and unknown (for example `foster`, `guardian`, `related`, `private`) are [UNCONFIRMED] for Ancestry exports.

### A.6 Citations and `_APID`
Real structure ([CONFIRMED-SAMPLE] ANC-2024):
```
1 RESI
2 DATE 1997
2 PLAC Tucson, Arizona, USA
2 SOUR @S95188560@
3 PAGE "U.S., School Yearbooks, 1880-2012"; School Name: Sabino High School; Year: 1997
3 _APID 1,1265::597288148
...
1 SOUR @S95188560@            <- person-level citation (level 1/2 rather than 2/3)
2 PAGE ...
2 _APID 1,1265::597288148
...
0 @S94982896@ SOUR
1 TITL California, Passenger and Crew Lists, 1882-1959
1 AUTH Ancestry.com
1 PUBL Ancestry.com Operations Inc
1 REPO @R54102289@
1 _APID 1,7949::0              <- source-level APID: record part is 0
0 @R54102289@ REPO
1 NAME Ancestry.com
```
- A citation may have **more than one `_APID`** (two `3 _APID` lines under one `2 SOUR`). [CONFIRMED-SAMPLE]
- A citation can carry `DATA / WWW <url>` (seen for a Fold3 link) and `OBJE @O..@`. `DATA/TEXT` is rare in this sample. [CONFIRMED-SAMPLE]
- **Format** `_APID <n>,<dbid>::<recordid>`. The source record uses `<recordid>` = `0`. The `n` before the comma was `1` in every example found, and its meaning is undocumented. [CONFIRMED-SAMPLE for the shape; SECONDARY for the meaning]
  - T2G (John Cardinal) says an APID "includes a database number and a record number in the format 'database::record'", and that these come from the Ancestry URL parameters `dbid=` and `h=`. https://www.tmgtogedcom.com/en/apid.htm
  - SQLite Tools for RootsMagic gives the format as `_APID 1,<ID>::<Header #>`, where `<Header #>` is the URL `h=` value. https://sqlitetoolsforrootsmagic.com/ancestry-com-sync/
  - Gramps code comment: "Ancestry.com database and page id"; and "This tag identifies the location of the cited page in the relevant Ancestry.com database." (libgedcom.py, `__citation__apid`)
- **Building a URL from an APID**: the only documented rule is community-sourced, **not** from Ancestry: "An APID such as '1,234::567890' becomes the URL http://search.ancestry.com/cgi-bin/sse.dll?indiv=1&dbid=234&h=567890". [SECONDARY] https://nerok00.github.io/ancestry-image-downloader/. It is consistent with the T2G dbid/h mapping above, and with the URLs FTM itself writes in `_LINK` (`https://search.ancestry.com/cgi-bin/sse.dll?db=61632&h=1558842&indiv=try`, from FTM-2019). Treat it as best-effort. The link needs an Ancestry login and subscription, and Ancestry has not published it. The newer `discoveryui-content/view/<h>:<dbid>` form is [UNCONFIRMED].

### A.7 Media (OBJE)
Official: "A GEDCOM file is a text-only file that contains all of the facts and information for a tree; photos, media, and similar items are not included." And: "GEDCOM files created on Ancestry after November 2022 do hold information about where your media files are saved on Ancestry. If you re-upload the GEDCOM file to Ancestry later, we'll relink the media files." [CONFIRMED-OFFICIAL] https://help.ancestry.com/hc/en-us/articles/53933352542867-Uploading-and-Downloading-Trees

Real OBJE record ([CONFIRMED-SAMPLE] ANC-2024, `_USER` hashes shortened):
```
0 @O1@ OBJE
1 FILE
2 FORM jpg
3 TYPE image
3 _MTYPE portrait
3 _STYPE jpeg
3 _SIZE 97783
3 _WDTH 433
3 _HGHT 677
2 TITL <caption>
1 RIN 0f67aeca-eefc-4dc0-b2c6-8c0865062e83      <- GUID media id
1 _DSCR <description>
1 _META <metadataxml><cemetery /><transcription /></metadataxml>
1 _CREA 2020-04-30 01:54:00.000
1 _USER jUwU...==
2 _ENCR 1
1 _CLON                                            <- media copied from another tree
2 _TID 17288138                                    <- source tree id
2 _PID 488748437                                   <- source person id
2 _OID 353e087d-200e-4d97-8f38-f4a28a3adc55      <- original object GUID
2 _USER ...
3 _ENCR 1
2 _DATE 2010-09-02 23:44:44.000
1 _ORIG u                                          <- 'u' (user upload?) ; also seen: 'fold3'
1 _ATL N                                           <- Y/N, meaning unknown
```
- **`1 FILE` is empty** in all 23 OBJE records of ANC-2024. In this sample there is no URL and no path. The "where it's stored" information is the GUID in `RIN` (and `_CLON._OID`). Gedcom Publisher/GedSite download media using "the Ancestry-supplied ID and media type, for example, '1521bb39-76d6-4dcd-a9bc-154866af36fa.jpeg'". [SECONDARY] https://www.gedsite.com/en/ancestryfamilytrees.htm. GedSite also says exports "often include media file references that use URLs to refer to web pages". So FILE may contain a URL in other exports. [SECONDARY]
- Values seen: `_MTYPE` = `portrait`, `document`, `story`. `3 TYPE` = `image` or `story`. `FORM` = `jpg` or `pdf`. **Uploaded "stories" appear as OBJE records** (FORM pdf, `TYPE story`) with no content.
- An OBJE record can also carry `1 DATE` and `1 PLAC` (free text, for example `1 DATE 1910-1939`, or `1 DATE 6/29/2014 6:39:08 PM`).
- The person-to-media link, with the primary photo and crop box:
  ```
  1 OBJE @O8@
  2 _PRIM Y
  2 _CROP
  3 _LEFT 61
  3 _TOP 85
  3 _WDTH 244
  3 _HGHT 340
  3 _TYPE primary
  ```
  [CONFIRMED-SAMPLE]. The meanings of `_ATL`, `_ORIG`, `_ENV` and `_ENCR` are [UNCONFIRMED].
- `_PHOTO` (the FTM primary-photo pointer) does **not** appear in the Ancestry sample. Ancestry uses `_PRIM Y` on the link instead.
- **Getting the media files themselves:** the export has none. Ancestry's help documents a per-item save from the media viewer (the download icon). [SECONDARY] https://legacyfamilytree.smartertrack.com/kb/a106/how-to-download-pictures-from-family-trees-at-ancestry_com.aspx. For bulk download, the options are third-party: the "Ancestry Media Download" Chrome extension (https://dataminingdna.com/download-your-ancestry-tree-to-gedcom-a-complete-guide/), or syncing to FTM/RootsMagic (TreeSync), which download media. Ancestry does not offer a "download all media" ZIP. [SECONDARY]

### A.8 Living people
- The export has **no privacy options**: "There is no privacy option in the export flow, because there are no options at all." [SECONDARY] https://ancestoriq.com/guides/export-tree-from-ancestry/. ANC-2024 includes people born in the 1990s with full names, dates and yearbook citations, so living people are exported in full. [CONFIRMED-SAMPLE]

### A.9 What Ancestry does NOT include
| Item | Status | Source |
|---|---|---|
| Photos, documents and other media files | Not included (only references; see A.7) | [CONFIRMED-OFFICIAL] help.ancestry.com article above |
| DNA results and matches | Not in the GEDCOM. Raw DNA is a separate download (`dna-data-<date>.zip` with a .txt inside, via DNA Settings, then Download DNA data, then an email link that expires after 7 days and works once). "DNA match lists cannot be downloaded or exported at this time." | [CONFIRMED-OFFICIAL] https://help.ancestry.com/hc/en-us/articles/53933317283603-Downloading-DNA-Data |
| ThruLines, ethnicity estimate | Not exported (they are DNA-derived; match lists are explicitly not exportable) | [CONFIRMED-OFFICIAL] for matches; ThruLines [UNCONFIRMED] but implied |
| Hints, comments, record images | No official statement found. Hints and comments do not appear in ANC-2024. Record images are media, so they are not included (only the `_APID` link). | [UNCONFIRMED] |
| Stories | Uploaded story files appear only as OBJE metadata (TYPE story, no content) | [CONFIRMED-SAMPLE] |
| Notes | **Included**: `1 NOTE` on persons, `2 NOTE` on facts | [CONFIRMED-SAMPLE]; MacKiev also says "Vital information, notes, and sources are usually retained" https://support.mackiev.com/889069-Uploading-and-Downloading-GEDCOM-Files-on-Ancestry |
| Alternate (duplicate) facts | Multiple RESI, BIRT and so on appear. Which one is "preferred" is [UNCONFIRMED] | sample |
| Account data (messages, billing) | Separate "Request account data" CSV download. Ancestry says trees, DNA and media are downloaded separately. | [CONFIRMED-OFFICIAL] https://help.ancestry.com/hc/en-us/articles/53933330503187-Requesting-a-Download-of-Your-Account-Data |

---

## B. Family Tree Maker (Ancestry era to MacKiev; FTM 2014, 2017, 2019, 2024)

### B.1 Headers ([CONFIRMED-SAMPLE])
FTM 2019 for Windows (FTM-2019):
```
0 HEAD
1 SOUR FTM
2 VERS 24.0.1.1252
2 NAME Family Tree Maker for Windows
2 CORP The Software MacKiev Company
3 ADDR 30 Union Wharf
4 CONT Boston, MA 02109
3 PHON (617) 227-6681
1 DEST FTM
1 DATE 6 JUL 2020
1 CHAR UTF-8
1 FILE US_Presidents_2020_2020-07-06.ged
1 SUBM @SUBM@
1 GEDC
2 VERS 5.5.1
2 FORM LINEAGE-LINKED
0 @SUBM@ SUBM
```
The file starts with a UTF-8 BOM (EF BB BF). [CONFIRMED-SAMPLE]

Ancestry-era FTM 2014 for Windows (FTM-2014win):
```
1 SOUR FTM
2 VERS Family Tree Maker (22.0.0.1410)
2 NAME Family Tree Maker for Windows
2 CORP Ancestry.com
...
1 DEST GED55
1 CHAR UTF-8
1 FILE D:\Family Tree Maker\imp_FTM_LINK.ged
...
2 VERS 5.5
```
Older FTM (2012, 20.0.0.376) wrote `1 CHAR ANSI` (FTM-2012). Tamura Jones covers the history: the Ancestry-era FTM had an invalid long VERS, `DEST GED55`, claimed 5.5 while really being 5.5.1, and used ANSI before FTM 2014 SP7. MacKiev's first release fixed these (`VERS 22.0.1.1429`, declares 5.5.1, UTF-8 **with BOM**, `DEST FTM`, FILE without a path). [SECONDARY] https://www.tamurajones.net/Ancestry.comAndSoftwareMacKievFamilyTreeMakerGEDCOMHeader.xhtml

### B.2 Record and xref formats ([CONFIRMED-SAMPLE] FTM-2019)
`@I1@`, `@F1@`, `@S1@`, `@R1@`, `@M1@` (media), `@N1@` (shared notes), `@SUBM@`. Dates are normalised to upper-case `DD MON YYYY` and `ABT YYYY`. Places get `3 MAP / 4 LATI N33.6671 / 4 LONG W93.5916`.

### B.3 Custom tags
| Tag | Context | Values and notes | Status |
|---|---|---|---|
| `_FREL`, `_MREL` | `FAM.CHIL` (not INDI.FAMC) | `Natural` (capitalised; 1,245 of 1,245 in FTM-2019), `Step`, `Guardian` (FTM-Mac). Gramps PR #2524 reports `Unknown` and `Related` in real FTM files. Gramps maps `birth/natural/step/adopted/foster`. FTM's UI offers biological, adopted, step, foster, guardian, and so on, but MacKiev does not publish the full list (https://support.mackiev.com/347725-Specifying-a-Relationship-Type-and-Relationship-Status-in-FTM-2024). Expected values: `Natural, Adopted, Step, Foster, Guardian, Related, Unknown`, plus possibly `Sealed` and `Private` [the last two UNCONFIRMED]. | [CONFIRMED-SAMPLE] FTM-2019, FTM-Mac; [SECONDARY] https://github.com/gramps-project/gramps/pull/2524 |
| `_PHOTO @Mn@` | `INDI` (level 1) | Primary photo pointer. FTM also writes `1 OBJE @Mn@`. Gramps: "This handles the FTM _PHOTO feature, which identifies an OBJE to use as the person's primary photo." | [CONFIRMED-SAMPLE] + [SECONDARY] libgedcom.py |
| `_LINK <url>` | citation (`n SOUR` under a fact), level 3 | For example `3 _LINK https://search.ancestry.com/cgi-bin/sse.dll?db=61632&h=1558842&indiv=try` | [CONFIRMED-SAMPLE] FTM-2019 |
| `_JUST <text>` | citation | Citation quality justification | [CONFIRMED-SAMPLE] FTM-Mac; [SECONDARY] Gramps ("FTM Citation Quality Justification") |
| `_DATE`, `_TEXT` | `OBJE` record (level 2, under FILE) | Windows: `2 _DATE 5/20/2017 1:51:01 PM`; `2 _TEXT` caption/description. Mac writes `2 DATE 9/19/16, 11:40:36 AM` instead. | [CONFIRMED-SAMPLE] |
| `_MILT`, `_MILTID`, `_EMPLOY`, `_DCAUSE`, `_DEG`, `_ELEC`, `_EXCM`, `_FUN`, `_HEIG`, `_WEIG`, `_INIT`, `_MISN`, `_NAMS`, `_ORDI`, `_ORIG`, `_DNA`, `_DEST`, `_CIRC`, `_MDCL`, `_SEPR` (FAM) | INDI/FAM facts | All seen in FTM-Mac (`ftmcustomtags.ged`). `_MILT` also appears in FTM-2019. | [CONFIRMED-SAMPLE] |
| `FSID` | INDI | FamilySearch id (no underscore), for example `1 FSID GQS9-2KW` | [CONFIRMED-SAMPLE] FTM-2019 |
| `_SCBK`, `_PRIM` | OBJE link | Scrapbook and primary flags. Gramps ignores `_SCBK`. Not seen in the FTM-2019 sample; may be older FTM (FTW) only. | [UNCONFIRMED for FTM 2019/2024] |
| `_MSTAT` | FAM | Not found in any FTM sample. The only documentation found is My Family Tree's extension list. | [UNCONFIRMED for FTM] |
| `_TYPE`, `_SDATE`, `_FOOT` | — | Not seen in the FTM samples | [UNCONFIRMED] |

FTM citation shape ([CONFIRMED-SAMPLE] FTM-2019):
```
2 SOUR @S22@
3 PAGE New York State Department of Health; Albany, NY, USA; New York State Marriage Index
3 DATA
4 TEXT Record for Donald Clark
3 OBJE @M11@
3 _LINK https://search.ancestry.com/cgi-bin/sse.dll?db=61632&h=1558842&indiv=try
```
FTM-2019 has no `_APID` at all; FTM writes `_LINK` URLs instead. Whether FTM writes `_APID` when exporting a tree synced with Ancestry is [UNCONFIRMED] (sqlitetoolsforrootsmagic describes `_APID` in an FTM 2014 / Ancestry sync context).

### B.4 Media paths ([CONFIRMED-SAMPLE])
- Windows FTM 2019 writes **absolute Windows paths** to the "<tree name> Media" folder:
  ```
  0 @M31@ OBJE
  1 FILE C:\FTM\US_Presidents_2020 Media\Photo_Bill_Clinton.jpg
  2 FORM jpg
  2 TITL William J Clinton
  2 _DATE 1/20/1993
  2 _TEXT Photo from Wikimedia Foundation
  ```
- FTM for Mac (FTM-Mac) wrote a bare filename: `1 FILE Vitruvian_man.jpg`. Absolute `/Users/...` paths on Mac are [UNCONFIRMED].
- File names often embed the Ancestry collection name, for example `1880 United States Federal Census - David Trotter Patterson.jpg`.

### B.5 Export dialog options ([CONFIRMED-OFFICIAL])
Windows: https://support.mackiev.com/572636-Export-and-Import-of-GEDCOM-Files-in-Family-Tree-Maker. Mac: https://support.mackiev.com/620984-Export-and-Import-of-GEDCOM-Files-in-Family-Tree-Makerfor-Mac
- Scope: *Entire file* or *Selected individuals*. Option: *Include only items linked to selected individuals*.
- Output format: a GEDCOM entry in the dropdown (the article does not list version choices).
- *Privatize living people*, *Include private facts*, *Include private notes*.
- *Include Media files* (Mac: "Media files. Select this checkbox to export links to media files in your tree") and *Private media*. **Only links are exported; the media files themselves are not.**
- *Export as password protected ZIP file*.
- The character set is chosen in a second "Export to GEDCOM" dialog.
- MacKiev: media come through "if a folder with all the media files is present on your computer and the GEDCOM file was created with all the correct media links included."

---

## C. RootsMagic (7, 8, 9, 10, 11)

### C.1 Header ([CONFIRMED-SAMPLE] RM-7; later versions are assumed to follow the same shape)
```
0 HEAD
1 SOUR RootsMagic
2 NAME RootsMagic
2 VERS 7.0.2.2
2 CORP RootsMagic, Inc.
3 ADDR PO Box 495
4 CONT Springville, UT 84663
4 CONT USA
3 PHON 1-800-ROOTSMAGIC
1 DEST RootsMagic
1 DATE 26 JAN 2015
1 FILE rm.ged
1 GEDC
2 VERS 5.5.1
2 FORM LINEAGE-LINKED
1 CHAR UTF-8
```
- The same shape for RM 8, 9 and 10 with `2 VERS 8.x/9.x/10.x` is [UNCONFIRMED]; I found no public raw sample.
- Encoding: RootsMagic "always uses UTF-8" for export and includes the BOM (RM4 review). [SECONDARY] https://www.tamurajones.net/RootsMagic4GEDCOM.xhtml. RootsMagic has really been GEDCOM 5.5.1 since 1.0. [SECONDARY] https://www.tamurajones.net/RootsMagicGEDCOMVersion.xhtml
- **GEDCOM 7 export: not supported** up to RM 10 and 11. Only GEDCOM 7 *import* exists. Community statements (no staff statement): https://community.rootsmagic.com/t/status-of-gedcom-7-in-roots-magic/14761 and https://community.rootsmagic.com/t/gedcom-7-0-import-in-rm9/6492. [SECONDARY]

### C.2 Export dialog ([CONFIRMED-OFFICIAL]) https://help.rootsmagic.com/RM9/exporting-data.html and https://help.rootsmagic.com/RM11/exporting-data.html
- People: entire database, select from list, or a named group.
- Checkboxes: "notes, sources, LDS information, addresses, tasks, multimedia links, note formatting (bold, etc.), and extra details (RootsMagic specific tags)".
- Privacy: privatize living people (names: full or "Living"; facts: all, none or partial), include private facts, include {private} notes, strip { } brackets.
- No option for GEDCOM version or character set is documented.
- **"Extra details (RM specific)"**: when unchecked, there are no RootsMagic fact-type definitions, no sentence templates, no `_COLOR`, and **no place latitude/longitude**. [SECONDARY] https://www.gedsite.com/en/rootsmagic.htm and https://tng.community/index.php?/forums/topic/13717-gedcom-export-using-rootsmagic-extra-details-rm-specific-option/

### C.3 Tags
| Tag | Context | Notes | Status |
|---|---|---|---|
| `_UID` | INDI | For example `1 _UID B9C4D3F0D254674AA1B9023745BEBFE551C1` (32 hex digits plus a 4-hex checksum) | [CONFIRMED-SAMPLE] RM-7 |
| `_TMPLT` with `TID`, `FIELD/NAME/VALUE` | SOUR record | Source-template fields | [CONFIRMED-SAMPLE] (RM4) https://www.geneamusings.com/2011/02/peeking-at-rootsmagic-4-source.html |
| `_SUBQ`, `_BIBL` | SOUR record | Subsequent footnote and bibliography text; may contain `<i>` HTML | same |
| `_EVDEF` | top level | RM fact-type definitions ("schema" tag) | [SECONDARY] https://github.com/FamilySearch/gedcom5-java (README); Tamura Jones RM4 review |
| `_SDATE` | event | Sort date (DATE syntax). RootsMagic is listed as a producer. | [SECONDARY] https://jfcardinal.github.io/GEDCOM-5.5.2/extensions.html |
| `_PRIM` | multimedia link | Primary photo. RootsMagic is listed as a producer. | [SECONDARY] same |
| `_SHAR` / `_ROLE` | event | Witnesses and shared events. RootsMagic is listed as a producer. | [SECONDARY] same; GedSite "RootsMagic's witness and role GEDCOM extensions" |
| `_FREL`, `_MREL` | FAM.CHIL | RM **exports `_FREL`/`_MREL` rather than PEDI**: "Several applications export _FREL and _MREL records including Family Tree Maker, Legacy, and RootsMagic." The claim that RM does not use PEDI on export comes from a search-result summary of Gedcom Publisher pages, not a verbatim quote, so treat it as likely. RM values (likely `Birth`, `Adopted`, `Step`, `Foster`, `Related`, `Guardian`, `Sealed`) are [UNCONFIRMED]. | [SECONDARY] https://www.gedcompublisher.com/en/pe-item-parent-section.htm |
| `_COLOR` | INDI | Colour coding, only with Extra details on | [SECONDARY] GedSite |
| `_FSFTID` | INDI | FamilySearch id (GEDKeeper test file, minimal) | [SECONDARY] https://github.com/Serg-Norseman/GEDKeeper/blob/master/projects/GKTests/Resources/test_rootsmagic.ged |
| Sort-date dash numbers | DATE | `12 JUN 1900-1` | [SECONDARY] GedSite |
| `_PLAC` (place records) | — | Listed for RM by J. F. Cardinal's draft | [SECONDARY], whether RM writes it by default is [UNCONFIRMED] |

### C.4 Media FILE paths
- Internally, RM 7 stores absolute drive-letter paths. RM 8, 9 and 10 store either absolute paths or **relative paths with prefix symbols**: `?` = media folder from preferences, `~` = home directory, `*` = folder of the database file. [SECONDARY] https://community.rootsmagic.com/t/relative-paths-for-media-items/12771
- How these appear in the GEDCOM `FILE` line (expanded to absolute paths, or left with the symbols) is **[UNCONFIRMED]**. Charted Roots claims "typically relative paths to a media folder next to your .rmtree file" (https://chartedroots.com/guides/research/migrate-from-rootsmagic/), but that is not authoritative. Importers should handle absolute Windows paths (`C:\...`), POSIX paths, bare filenames and `?\`/`~\`/`*\` prefixes.

---

## D. Specifications (gedcom.io)

Sources: GEDCOM 5.5.1 PDF https://gedcom.io/specifications/ged551.pdf and FamilySearch GEDCOM 7.0 https://gedcom.io/specifications/FamilySearchGEDCOMv7.html

### D.1 5.5.1 ([CONFIRMED-OFFICIAL])
- `CHILD_TO_FAMILY_LINK:= n FAMC @<XREF:FAM>@ / +1 PEDI <PEDIGREE_LINKAGE_TYPE> / +1 STAT <CHILD_LINKAGE_STATUS> / +1 <<NOTE_STRUCTURE>>`. FAMS is the spouse link.
- `PEDIGREE_LINKAGE_TYPE:= [ adopted | birth | foster | sealing ]`. "foster = indicates child was included in a foster or guardian family."
- `CHARACTER_SET:= [ ANSEL | UTF-8 | UNICODE | ASCII ]`. The spec says "the preferred character set is ANSEL". "The IBMPC character set is not allowed." (Real files also say `ANSI`, as in FTM-2012, which is non-standard.)
- Dates:
  - `DATE_APPROXIMATED:= ABT|CAL|EST <DATE>`
  - `DATE_RANGE:= BEF <DATE> | AFT <DATE> | BET <DATE> AND <DATE>`
  - `DATE_PERIOD:= FROM <DATE> | TO <DATE> | FROM <DATE> TO <DATE>`
  - `INT <DATE> (<DATE_PHRASE>) | (<DATE_PHRASE>)`
  - `DATE_CALENDAR_ESCAPE:= @#DHEBREW@ | @#DROMAN@ | @#DFRENCH R@ | @#DGREGORIAN@ | @#DJULIAN@ | @#DUNKNOWN@` (Gregorian is the default)
  - `YEAR_GREG:= <NUMBER> | <NUMBER>/<DIGIT><DIGIT>`, for example `15 APR 1699/00` (dual dating before 1752). `(B.C.)` marks dates before the common era.
- Lines: total line length "must not exceed 255 (wide) characters". Long values are split with `CONC` (joined with no separator) or `CONT` (new line).
- Multimedia record: `0 @XREF:OBJE@ OBJE / +1 FILE <MULTIMEDIA_FILE_REFN> {1:M} / +2 FORM / +3 TYPE <SOURCE_MEDIA_TYPE> / +2 TITL`. Ancestry follows this (`2 FORM jpg / 3 TYPE image`).

### D.2 7.0 ([CONFIRMED-OFFICIAL])
- `HEAD.GEDC.VERS 7.0` is required.
- **UTF-8 only.** "The first character in each data stream should be U+FEFF, the byte-order mark". `CONC` was removed; only `CONT` remains. ANSEL and other character sets are gone.
- Date ABNF:
  ```
  DateValue  = [ date / DatePeriod / dateRange / dateApprox ]
  DatePeriod = [ "TO" D date ] / "FROM" D date [ D "TO" D date ]
  date       = [calendar D] [[day D] month D] year [D epoch]
  dateRange  = "BET" D date D "AND" D date / "AFT" D date / "BEF" D date
  dateApprox = ("ABT" / "CAL" / "EST") D date
  calendar   = "GREGORIAN" / "JULIAN" / "FRENCH_R" / "HEBREW" / extTag
  epoch      = "BCE" / extTag
  ```
  There are no `@#D...@` escapes and no `INT`. The spec says: "Versions 5.3 through 5.5.1 allowed phrases inside DateValue payloads. Date phrases were moved to the PHRASE substructure in version 7.0." So `INT` plus a phrase becomes `DATE <value>` with `PHRASE <text>`.
- **Dual dates** (Appendix 6.2): the date is stored as one normalised date plus a PHRASE: `2 DATE 30 JAN 1649` / `3 PHRASE 30 January 1648/49`. The 5.5.1 `1648/49` year syntax is gone.
- **PEDI enum** (`g7:enumset-PEDI`): `ADOPTED`, `BIRTH`, `FOSTER` ("foster or guardian family"), `SEALING`, `OTHER` ("should have a PHRASE substructure"). Values are upper-case. `PHRASE` is allowed under PEDI.
- **GEDZIP** (chapter 4): a zip archive containing an entry `gedcom.ged` plus one entry for each local FILE path. File names are case-sensitive UTF-8 and not percent-escaped. The `.gdz` extension is recommended. META-INF and MANIFEST.MF are discouraged.

---

## E. Snippets for test fixtures (short, real)

**Ancestry 2024 (ANC-2024)**: see the header in A.3. Person, citation and media link, with names generic and ids real:
```
0 @I112187149819@ INDI
1 NAME <Given> /<Surname>/
2 GIVN <Given>
2 SURN <Surname>
1 SEX F
1 FAMC @F2@
1 FAMC @F3@
...
1 SOUR @S95188560@
2 PAGE "U.S., School Yearbooks, 1880-2012"; School Name: Sabino High School; Year: 1997
2 _APID 1,1265::597288148
1 OBJE @O8@
2 _PRIM Y
2 _CROP
3 _LEFT 61
3 _TOP 85
3 _WDTH 244
3 _HGHT 340
3 _TYPE primary
...
1 _MILT
2 DATE 1917
2 SOUR @S95190009@
3 _APID 1,7895::148773
1 EVEN
2 TYPE Arrival
2 DATE 1919
```

**FTM 2019 (FTM-2019)**: header in B.1. Person and family:
```
0 @I1@ INDI
1 NAME William Jefferson /Clinton/
1 SEX M
1 BIRT
2 DATE 19 AUG 1946
2 PLAC Hope, Hempstead, Arkansas, USA
3 MAP
4 LATI N33.6671
4 LONG W93.5916
1 REFN Clinton-1
1 NOTE @N1@
1 _PHOTO @M31@
1 OBJE @M31@
1 FAMS @F1@
1 FAMC @F2@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I66@
2 _FREL Natural
2 _MREL Natural
1 MARR
2 DATE 11 OCT 1975
```

**FTM Mac (FTM-Mac)**:
```
1 CHIL @I1@
2 _FREL Step
2 _MREL Guardian
...
1 _WEIG 165lb
2 SOUR @S1@
3 PAGE p1
3 DATA
4 TEXT "John weighs 165 lbs."
3 QUAY 3
3 _JUST Because it was an awesome napkin.
3 _LINK http://gedcom4j.org
```

**RootsMagic source template (RM4, from Genea-Musings)**:
```
0 @S671@ SOUR
1 ABBR Westminster VRs
1 TITL Systematic History Fund, <i>Vital Records of Westminster, Massachusetts
2 CONC , to the end of year 1849</i> (Worcester, Mass.: F.P. Rice, 1908).
1 _SUBQ Fund, <i>Vital Records of Westminster, Massachusetts, to the end of yea
2 CONC r 1849</i>.
1 _BIBL Fund, Systematic History. <i>Vital Records of Westminster, Massachusett
...
1 _TMPLT
2 TID 372
2 FIELD
3 NAME Author
3 VALUE Systematic History Fund
```

**Synthetic Ancestry fixture to avoid copying blindly**: https://github.com/ggoosen/gedcom-mcp/blob/main/tests/fixtures/sample.ged uses `2 VERS (2010.3)` and `@I1@`-style ids with a `GEDC 5.5.1` header. This mixes old and new conventions and is **not** a real export.

---

## Open questions / unconfirmed
1. The name of the `.ged` file inside Ancestry's ZIP, and whether it has a BOM and CRLF line endings (gedcom-mcp says yes; not verified on raw bytes).
2. Whether Ancestry's `OBJE.FILE` is ever filled in (URL) in post-2022 exports. ANC-2024 has it empty and relies on the `RIN` GUID.
3. What the meanings of `_ORIG u`, `_ATL Y/N`, `_ENV prd` and `_ENCR 1` are, and what the `1,` prefix in `_APID` means.
4. Which INDI line points to a `_MTTAG` record in Ancestry exports.
5. The full value lists for `_FREL`/`_MREL` in FTM 2024 and RootsMagic 8–10, and the casing RM uses.
6. Whether FTM 2019/2024 writes `_MSTAT`, `_SCBK`, `_PRIM`, `_SDATE` or `_TYPE`. None were seen.
7. How RootsMagic 8–10 writes `FILE` paths (absolute, or `?`/`~`/`*` relative), and its header `VERS` format.
8. Hints, comments and record images in Ancestry exports: no official statement. Absent from the sample.
