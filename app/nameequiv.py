"""Given-name equivalents and surname spelling families, for searching records.

Clerks, census takers and indexers wrote names the way they heard them or abbreviated them:
"Wm" for William, "Maggie" for Margaret, "Andrew" for the Swedish "Anders", "Delia" for Bridget.
Searching only the name in the family tree misses those records (false negatives).

These lists describe how names were *written* in records. They say nothing about a person's
origin or identity, and a record using an equivalent name still has to be checked.
"""
from __future__ import annotations

import re
import unicodedata

# Each group is a set of names that were used interchangeably for one person in records
# (formal form first). Sources: common abbreviations in U.S. censuses and directories, and
# well-known Irish, Swedish and German forms and their usual American spellings.
GIVEN_GROUPS: list[list[str]] = [
    # English / Irish (abbreviations as written by clerks: Wm, Jas, Jno, Thos …)
    ["William", "Wm", "Will", "Willie", "Bill", "Billy", "Wilhelm"],
    ["James", "Jas", "Jim", "Jimmy", "Jamie", "Jemmy"],
    ["John", "Jno", "Jack", "Johnny", "Johann", "Johan", "Johannes", "Hans", "Jon", "Sean", "Jöns", "Jons"],
    ["Thomas", "Thos", "Tom", "Tommy", "Tomas"],
    ["Charles", "Chas", "Charlie", "Chas.", "Carl", "Karl"],
    ["George", "Geo", "Georg", "Göran", "Goran", "Jöran"],
    ["Joseph", "Jos", "Joe", "Josef", "Jozef"],
    ["Robert", "Robt", "Rob", "Bob", "Bobby", "Bert", "Rupert"],
    ["Richard", "Richd", "Rich", "Dick", "Rick"],
    ["Edward", "Edw", "Ed", "Eddie", "Ned", "Ted", "Eduard"],
    ["Patrick", "Patk", "Pat", "Patsy", "Paddy", "Padraig"],
    ["Michael", "Michl", "Mike", "Mick", "Mickey", "Michel", "Mikael"],
    ["Timothy", "Timy", "Tim", "Thady", "Tadhg", "Teague"],
    ["Daniel", "Danl", "Dan", "Danny", "Donal", "Donald"],
    ["Jeremiah", "Jere", "Jerry", "Diarmuid", "Dermot", "Darby", "Jeremy"],
    ["Cornelius", "Corns", "Con", "Connie", "Neil", "Conny", "Conor", "Connor"],
    ["Dennis", "Denis", "Dinny", "Denny", "Donnchadh"],
    ["Bartholomew", "Bart", "Batt", "Bat", "Bartley"],
    ["Francis", "Fras", "Frank", "Franz", "Fran", "Frans"],
    ["Frederick", "Fredk", "Fred", "Freddie", "Friedrich", "Fritz", "Fredrik", "Fredric", "Frederic"],
    ["Henry", "Hy", "Harry", "Hank", "Heinrich", "Henrik", "Hinrich"],
    ["Alexander", "Alexr", "Alex", "Sandy", "Alec", "Alick"],
    ["Benjamin", "Benj", "Ben", "Benny"],
    ["Samuel", "Saml", "Sam", "Sammy"],
    ["Nicholas", "Nichs", "Nick", "Nicolaus", "Niklas", "Klaus", "Claus", "Nils", "Nels", "Niels"],
    ["Andrew", "Andw", "Andy", "Anders", "Andreas", "Andres", "Andrea"],
    ["Peter", "Petr", "Pete", "Per", "Pehr", "Peder", "Pieter", "Petrus"],
    ["Lawrence", "Laurence", "Larry", "Lars", "Lorenz", "Laurentius", "Louis"],
    ["Lewis", "Louis", "Lou", "Ludwig", "Ludvig", "Lutz"],
    ["Olof", "Olaf", "Olav", "Ole", "Oliver", "Olle"],
    ["Eric", "Erik", "Erick", "Erich"],
    ["Gustave", "Gustaf", "Gustav", "Gust", "Gus", "Gösta", "Gosta", "Gustavus"],
    ["August", "Aug", "Gust", "Gus", "Augustus"],
    ["Matthew", "Matt", "Mats", "Mattias", "Matthias", "Mathias", "Matthäus"],
    ["Martin", "Mart", "Marty", "Mårten", "Marten"],
    ["Emil", "Emile", "Emiel"],
    ["Herbert", "Herb", "Bert", "Herbie"],
    ["Albert", "Albt", "Al", "Bert", "Albrecht", "Albrekt"],
    ["Alfred", "Alfd", "Alf", "Al", "Fred", "Alfie"],
    ["Ernest", "Ernst", "Ernie"],
    ["Leo", "Leon", "Leopold", "Lee"],
    ["Hugh", "Hugo", "Hughie", "Aodh"],
    ["Owen", "Eugene", "Eoghan", "Gene"],
    ["Terence", "Terrence", "Terry", "Turlough"],
    ["Morgan", "Murrough", "Morris", "Maurice"],
    ["Ignatius", "Ignaz", "Nace"],
    ["Stephen", "Steven", "Steve", "Stefan", "Steffen"],
    # Women
    ["Margaret", "Margt", "Marg", "Maggie", "Mag", "Peg", "Peggy", "Meg", "Madge", "Greta", "Gretchen", "Margareta", "Margaretha", "Margarete", "Margit", "Marget", "Daisy"],
    ["Mary", "Maria", "Marie", "Mamie", "Molly", "Mollie", "Polly", "May", "Mae", "Maire", "Maja"],
    ["Bridget", "Bridgt", "Biddy", "Bridie", "Delia", "Bedelia", "Bride", "Brigid", "Brigitta", "Britta", "Brita", "Britte", "Brigitte"],
    ["Catherine", "Cath", "Catharine", "Katherine", "Kathryn", "Katharina", "Katarina", "Karin", "Kate", "Katie", "Kitty", "Kit", "Cassie", "Kathleen", "Carrie"],
    ["Elizabeth", "Eliz", "Eliza", "Elisabet", "Elisabeth", "Lizzie", "Lizzy", "Liz", "Bessie", "Bess", "Betsy", "Betty", "Beth", "Libby", "Elsie", "Else", "Lisa", "Elise", "Lisette"],
    ["Ellen", "Ellie", "Nellie", "Nell", "Helen", "Helena", "Eleanor", "Elinor", "Ella", "Lena"],
    ["Honora", "Honor", "Nora", "Norah", "Hannah", "Onora", "Annie", "Nonie"],
    ["Johanna", "Joanna", "Hannah", "Jennie", "Jane", "Josie", "Hanna", "Johanne"],
    ["Hannah", "Anna", "Anne", "Ann", "Annie", "Nancy", "Hanna", "Nan"],
    ["Ann", "Anna", "Anne", "Annie", "Nancy", "Nan", "Nannie", "Antje"],
    ["Julia", "Judith", "Judy", "Julie", "Jule", "Sheila"],
    ["Sarah", "Sara", "Sally", "Sadie", "Sal"],
    ["Christina", "Kristina", "Christine", "Stina", "Tina", "Kirsten", "Kerstin", "Christiana", "Kristin"],
    ["Theresa", "Teresa", "Therese", "Tess", "Tessie", "Tracy"],
    ["Agnes", "Aggie", "Nessa", "Agnete"],
    ["Alice", "Allie", "Alicia", "Alis"],
    ["Augusta", "Gussie", "Gusta"],
    ["Mildred", "Millie", "Milly"],
    ["Clara", "Claire", "Clare", "Klara"],
    ["Barbara", "Babs", "Barb", "Bärbel"],
    ["Susan", "Susanna", "Susannah", "Sukey", "Sue", "Susie", "Zuzanna"],
    ["Ingrid", "Inga", "Ingeborg", "Inge"],
    ["Charlotta", "Charlotte", "Lotta", "Lottie", "Lotte"],
    ["Emma", "Emmy", "Em"],
    ["Wilhelmina", "Mina", "Minnie", "Wilma", "Helmi"],
    ["Crescentia", "Kreszenz", "Kreszentia", "Krescenzia", "Zenzi", "Cresence"],
    ["Frances", "Fanny", "Franziska", "Fran"],
    ["Louisa", "Louise", "Lou", "Lulu", "Luise", "Lovisa", "Lovise"],
    ["Dorothy", "Dorothea", "Dolly", "Dora", "Dot"],
    ["Rebecca", "Becky", "Reba"],
    ["Ida", "Idda"],
    ["Hulda", "Hilda", "Hildur"],
]

_INDEX: dict[str, list[str]] = {}
for _g in GIVEN_GROUPS:
    for _n in _g:
        lst = _INDEX.setdefault(_n.lower().rstrip("."), [])
        lst += [x for x in _g if x not in lst]


def fold(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(ch)).lower().strip()


ABBREVIATIONS = {"wm", "jas", "jno", "thos", "chas", "geo", "jos", "robt", "richd", "edw", "patk", "michl", "danl", "fredk", "alexr", "benj",
                 "saml", "nichs", "andw", "alfd", "albt", "hy", "fras", "timy", "corns", "margt", "bridgt", "cath", "eliz", "petr", "jere", "aug"}


def is_abbreviation(name: str) -> bool:
    return (name or "").lower().rstrip(".") in ABBREVIATIONS


def nickname_in_quotes(given: str) -> str | None:
    """'Anders "Andrew" Gustav' → 'Andrew' (the name the person went by, as Ancestry trees often record it)."""
    m = re.search(r"[\"“”']([^\"“”']{2,20})[\"“”']", given or "")
    return m.group(1).strip() if m else None


def strip_quoted(given: str) -> str:
    return " ".join(re.sub(r"[\"“”'][^\"“”']{2,20}[\"“”']", " ", given or "").split())


def given_equivalents(given: str) -> list[str]:
    """Names that records may use for this given name (excluding itself)."""
    given = strip_quoted(given)
    first = (given or "").split()[0] if (given or "").split() else ""
    out: list[str] = []
    for key in {first.lower().rstrip("."), fold(first).rstrip(".")}:
        for n in _INDEX.get(key, ()):
            if n.lower() != first.lower() and n not in out:
                out.append(n)
    # Keep the list focused: formal + common forms before rarer ones
    return out


# Surname spelling families: how the same surname was written in U.S. records.
def surname_variants(surname: str) -> list[str]:
    s = (surname or "").strip()
    if not s:
        return []
    out: list[str] = []

    def add(v: str):
        v = v.strip()
        if v and v.lower() != s.lower() and v.lower() not in (x.lower() for x in out):
            v = v[:1].upper() + v[1:]
            if v[:2] == "Mc" and len(v) > 2:
                v = "Mc" + v[2:3].upper() + v[3:]
            if v[:3] == "Mac" and len(v) > 3 and s[3:4].isupper():
                v = "Mac" + v[3:4].upper() + v[4:]
            if v[:2] == "O'" and len(v) > 2:
                v = "O'" + v[2:3].upper() + v[3:]
            out.append(v)

    low = s.lower()
    # Irish O'/Mc/Mac prefixes were often dropped or added in America
    m = re.match(r"^o[’'\s]?(\w+)$", low)
    if m and low.startswith(("o'", "o’", "o ")):
        add(m.group(1))
    elif re.match(r"^(shaughnessy|brien|connor|neil|neill|donnell|sullivan|leary|keefe|reilly|rourke|hara|malley|dea|dwyer|grady|connell|toole|mahony|driscoll|callaghan|halloran|shea|hare|meara|flaherty|kelly|riordan|donoghue|donohue|regan|gorman|loughlin|mara|day)", low):
        add("O'" + s)
    if low.startswith("mc"):
        add("Mac" + s[2:])
    elif low.startswith("mac") and len(low) > 5:
        add("Mc" + s[3:])
    # Scandinavian letters and endings written the American way
    f = fold(s)
    if f != low:
        add(f)
    for a, b in [("ö", "oe"), ("ä", "ae"), ("å", "aa"), ("ü", "ue")]:
        if a in low:
            add(low.replace(a, b))
    for a, b in [("strom", "strum"), ("strom", "strem"), ("strom", "ström"), ("quist", "qvist"), ("qvist", "quist"), ("quist", "kvist"),
                 ("berg", "burg"), ("burg", "berg"), ("son", "sen"), ("sen", "son"), ("sson", "son"), ("gren", "green"),
                 ("lund", "land"), ("dahl", "dal"), ("holm", "home"), ("ck", "k"), ("a", "e")]:
        if a in fold(low) and (a not in ("a",) or re.search(r"(?<=^b)a(?=ck)", fold(low))):
            add(fold(low).replace(a, b, 1))
    # German forms
    for a, b in [("ie", "e"), ("ie", "ei"), ("ei", "ie"), ("sch", "sh"), ("tz", "z"), ("mann", "man"), ("dt", "t"), ("th", "t"), ("ch", "ck")]:
        if a in low and len(low) > 5:
            add(low.replace(a, b, 1))
    # Common Irish spellings: doubled consonants / -ey / -y / -ie
    for a, b in [("ssy", "ssey"), ("ssey", "ssy"), ("ssy", "sy"), ("nn", "n"), ("ss", "s"), ("y$", "ey"), ("ey$", "y"), ("y$", "ie")]:
        if re.search(a, low):
            add(re.sub(a, b.replace("$", ""), low, count=1))
    return out[:14]


def abbreviations(given: str) -> list[str]:
    g = strip_quoted(given or "").split()
    if not g:
        return []
    out = [g[0][0] + "."]
    if len(g) > 1:
        out.append(f"{g[0][0]}. {g[1][0]}.")
        if len(g[1].strip(".")) > 2:
            out.append(g[1])  # people often went by their middle name
    return out
