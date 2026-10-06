"""Controlled vocabularies shared by the backend, the UI, and the recommender.

Keys are stable identifiers stored in the database; labels are for display.
"""
from __future__ import annotations

RECORD_TYPE_GROUPS: list[dict] = [
    {"key": "vital_religious", "label": "Vital and religious", "types": [
        ("births", "Births"), ("baptisms", "Baptisms / christenings"), ("marriages", "Marriages"),
        ("banns", "Banns / marriage intentions"), ("divorces", "Divorces"), ("deaths", "Deaths"),
        ("burials", "Burials / cemetery records"), ("congregational_registers", "Congregational & membership registers"),
    ]},
    {"key": "households", "label": "Households and residence", "types": [
        ("censuses", "Censuses"), ("population_registers", "Population registers"), ("electoral_rolls", "Electoral rolls / voter lists"),
        ("city_directories", "City directories"), ("address_books", "Address books"),
    ]},
    {"key": "migration", "label": "Migration and citizenship", "types": [
        ("passenger_lists", "Passenger lists"), ("border_crossings", "Border crossings"), ("passports", "Passports / passport applications"),
        ("naturalization", "Naturalization records"), ("citizenship_files", "Citizenship / alien files"),
    ]},
    {"key": "property_courts", "label": "Property and courts", "types": [
        ("deeds", "Deeds"), ("land_grants", "Land grants / patents"), ("mortgages", "Mortgages"), ("tax_lists", "Tax lists"),
        ("wills", "Wills"), ("probate", "Probate / estates"), ("guardianships", "Guardianships"), ("court_cases", "Court cases"),
    ]},
    {"key": "military", "label": "Military", "types": [
        ("military_service", "Service records"), ("military_pensions", "Pensions"), ("draft_registrations", "Draft registrations"),
        ("muster_rolls", "Muster rolls"), ("casualties", "Casualty lists"),
    ]},
    {"key": "newspapers", "label": "Newspapers", "types": [
        ("obituaries", "Obituaries"), ("announcements", "Birth / marriage announcements"), ("legal_notices", "Legal notices"),
        ("social_columns", "Social columns"), ("missing_persons", "Missing-person / information-wanted notices"),
        ("newspapers_general", "Newspapers (general)"),
    ]},
    {"key": "community", "label": "Community and institutions", "types": [
        ("school_registers", "School registers"), ("yearbooks", "Yearbooks"), ("employment", "Employment records"),
        ("poor_relief", "Poor relief / almshouse"), ("institutional_registers", "Institutional registers (hospitals, asylums, prisons, orphanages)"),
    ]},
    {"key": "published", "label": "Published research", "types": [
        ("family_histories", "Family histories"), ("local_histories", "Local / county histories"), ("journals", "Genealogical journals"),
        ("biographies", "Biographies"), ("transcriptions", "Published transcriptions / abstracts"),
    ]},
    {"key": "archival", "label": "Archival discovery", "types": [
        ("finding_aids", "Finding aids"), ("manuscript_catalogs", "Manuscript catalogs"), ("collection_descriptions", "Collection descriptions"),
        ("onsite_material", "Onsite-only material"),
    ]},
    {"key": "family_contributed", "label": "Family-contributed material", "types": [
        ("trees", "Contributed family trees"), ("letters", "Letters"), ("diaries", "Diaries"), ("photographs", "Photographs"),
        ("oral_histories", "Oral histories"),
    ]},
]

RECORD_TYPES: dict[str, str] = {k: label for g in RECORD_TYPE_GROUPS for k, label in g["types"]}
RECORD_TYPE_GROUP_OF: dict[str, str] = {k: g["key"] for g in RECORD_TYPE_GROUPS for k, _ in g["types"]}

SEARCH_CAPABILITIES = {
    "name_index": "Name index search",
    "full_text": "Full-text search",
    "catalog": "Catalog search",
    "browse_images": "Browse-only images",
    "onsite": "Onsite research",
    "request_only": "Request-only retrieval",
}

EVIDENCE_FORMS = {
    "original_image": "Original document image",
    "transcription": "Transcription",
    "index": "Index",
    "published_analysis": "Published analysis",
    "contributed_tree": "Contributed tree",
    "photograph": "Photograph",
    "finding_aid": "Finding aid",
}

ACCESS = {
    "free": "Free",
    "free_account": "Free account",
    "subscription": "Subscription",
    "library": "Library access",
    "onsite": "Onsite",
    "paid_retrieval": "Paid retrieval",
    "unknown": "Unknown",
}

INTEGRATION_METHODS = {
    "outbound_link": "Outbound link",
    "verified_search_link": "Verified parameterized search link",
    "documented_api": "Documented API (implemented)",
    "licensed_dataset": "Licensed dataset",
}

ENTRY_KINDS = {
    "search_service": "Search service",
    "collection": "Collection",
    "catalog": "Catalog",
    "guide": "Research guidance",
    "repository": "Repository",
    "directory": "Directory of resources",
}

REPOSITORY_TYPES = {
    "commercial_database": "Commercial database",
    "nonprofit_database": "Nonprofit database",
    "volunteer_project": "Volunteer project",
    "national_archive": "National archive",
    "national_library": "National library",
    "state_archive": "State / provincial archive",
    "county_clerk": "County clerk",
    "probate_court": "Probate court",
    "registry_of_deeds": "Registry of deeds",
    "public_library": "Public library",
    "historical_society": "Historical society",
    "religious_archive": "Religious archive",
    "university_library": "University library",
    "cemetery_index": "Cemetery index",
    "newspaper_archive": "Newspaper archive",
    "directory": "Directory / portal",
    "government_agency": "Government agency",
    "other": "Other",
}

VERIFICATION_STATUSES = {
    "verified": "Verified",
    "partial": "Partly verified",
    "needs_verification": "Needs verification",
    "broken": "Link problem",
}

CLAIM_TYPES = {
    "birth": "Birth", "baptism": "Baptism / christening", "marriage": "Marriage", "divorce": "Divorce",
    "death": "Death", "burial": "Burial", "residence": "Residence", "migration": "Migration / move",
    "immigration": "Immigration", "emigration": "Emigration", "naturalization": "Naturalization",
    "military": "Military service", "occupation": "Occupation", "religion": "Religious affiliation",
    "name": "Name", "relationship": "Relationship", "property": "Land / property", "other": "Other",
}

CLAIM_STATUSES = {
    "working": "Working assumption",
    "tentative": "Tentative",
    "confirmed": "Confirmed (by researcher)",
    "disputed": "Disputed",
    "rejected": "Rejected",
}

RELATIONSHIP_TYPES = {"parent": "Parent of", "child": "Child of", "spouse": "Spouse of", "sibling": "Sibling of", "other": "Other"}
RELATIONSHIP_QUALIFIERS = {"biological": "Biological", "adopted": "Adopted", "step": "Step", "foster": "Foster", "guardian": "Guardian",
                           "sealed": "Sealed (LDS)", "unknown": "Unknown", "other": "Other (see note)"}

DATE_QUALIFIERS = {
    "exact": "Exact", "about": "About", "before": "Before", "after": "After", "between": "Between",
    "estimated": "Estimated", "calculated": "Calculated", "unknown": "Unknown",
}

NAME_TYPES = {
    "birth": "Birth name", "married": "Married name", "maiden": "Maiden name", "alias": "Alias / nickname",
    "variant": "Spelling variant", "original_script": "Original-script name", "religious": "Religious name",
    "anglicized": "Anglicized name",
}

LOG_OUTCOMES = {
    "useful": "Useful finding",
    "possible_match": "Possible match",
    "no_result": "Searched — no result",
    "inaccessible": "Couldn't access (login, paywall, onsite)",
    "records_unavailable": "Records unavailable (lost, restricted, or never created)",
    "follow_up": "Follow-up needed",
}

RECORD_FORMATS = {
    "original_image": "Image of original record",
    "original_physical": "Original record (viewed in person)",
    "transcription": "Transcription",
    "abstract": "Abstract / extract",
    "index": "Index entry",
    "published_compilation": "Published compilation / book",
    "newspaper": "Newspaper item",
    "contributed_tree": "Contributed family tree",
    "cemetery_memorial": "Cemetery memorial / biography",
    "photograph": "Photograph",
    "oral": "Oral account / interview",
    "unknown": "Unknown / other",
}
# Formats that may hold useful clues but are never treated as proof of a relationship on their own.
CLUE_ONLY_FORMATS = {"contributed_tree", "cemetery_memorial"}

STANCES = {"supports": "Supports", "contradicts": "Contradicts", "mentions": "Mentions / context"}
IDENTITY_MATCH = {"certain": "Same person — certain", "probable": "Probably same person", "possible": "Possibly same person", "uncertain": "Identity uncertain"}
ASSESSMENTS = {"strong": "Strong", "moderate": "Moderate", "weak": "Weak", "unassessed": "Not yet assessed"}
INFORMANT_KNOWLEDGE = {"primary": "Primary (firsthand)", "secondary": "Secondary (hearsay)", "undetermined": "Undetermined"}

# Research question types → record types to prioritise (ordered by usefulness).
QUESTION_TYPES: dict[str, dict] = {
    "identify_parents": {
        "label": "Identify parents",
        "record_types": ["probate", "wills", "baptisms", "births", "censuses", "marriages", "deeds", "obituaries",
                          "deaths", "guardianships", "court_cases", "family_histories", "local_histories", "congregational_registers", "tax_lists"],
    },
    "find_birth": {"label": "Find birth or baptism", "record_types": ["births", "baptisms", "censuses", "deaths", "marriages", "military_pensions", "draft_registrations", "congregational_registers", "announcements"]},
    "find_marriage": {"label": "Find marriage", "record_types": ["marriages", "banns", "announcements", "congregational_registers", "censuses", "probate", "military_pensions", "social_columns"]},
    "find_death": {"label": "Find death or burial", "record_types": ["deaths", "burials", "obituaries", "probate", "wills", "censuses", "military_pensions", "legal_notices"]},
    "find_origin": {"label": "Find place of origin / overseas origin", "record_types": ["naturalization", "passenger_lists", "obituaries", "citizenship_files", "passports", "congregational_registers", "censuses", "draft_registrations", "local_histories", "border_crossings"]},
    "find_immigration": {"label": "Find immigration / arrival", "record_types": ["passenger_lists", "naturalization", "border_crossings", "censuses", "citizenship_files", "passports"]},
    "trace_residence": {"label": "Trace residence / movements", "record_types": ["censuses", "city_directories", "tax_lists", "deeds", "electoral_rolls", "population_registers", "address_books", "land_grants"]},
    "find_military": {"label": "Find military service", "record_types": ["military_service", "military_pensions", "draft_registrations", "muster_rolls", "casualties", "obituaries"]},
    "find_land": {"label": "Find land / property", "record_types": ["deeds", "land_grants", "mortgages", "tax_lists", "probate", "court_cases"]},
    "find_children": {"label": "Identify children / household", "record_types": ["censuses", "probate", "wills", "baptisms", "births", "obituaries", "guardianships", "population_registers"]},
    "life_context": {"label": "Understand life & community context", "record_types": ["newspapers_general", "social_columns", "local_histories", "city_directories", "school_registers", "employment", "congregational_registers", "photographs"]},
    "other": {"label": "Other / general", "record_types": ["censuses", "births", "marriages", "deaths", "obituaries", "probate", "newspapers_general", "family_histories"]},
}

# Which claim types define the time/place window for a question type.
QUESTION_ANCHORS: dict[str, list[str]] = {
    "identify_parents": ["birth", "baptism", "residence", "marriage"],
    "find_birth": ["birth", "baptism", "residence"],
    "find_marriage": ["marriage", "residence", "birth"],
    "find_death": ["death", "burial", "residence"],
    "find_origin": ["immigration", "emigration", "naturalization", "birth", "residence", "migration"],
    "find_immigration": ["immigration", "naturalization", "residence", "migration"],
    "trace_residence": ["residence", "migration", "census"],
    "find_military": ["military", "residence", "birth"],
    "find_land": ["property", "residence"],
    "find_children": ["marriage", "residence", "death"],
    "life_context": ["residence", "occupation", "migration"],
    "other": ["residence", "birth", "death", "marriage"],
}


def vocabularies() -> dict:
    """Everything the UI needs to render pickers and labels."""
    return {
        "record_type_groups": [
            {"key": g["key"], "label": g["label"], "types": [{"key": k, "label": l} for k, l in g["types"]]}
            for g in RECORD_TYPE_GROUPS
        ],
        "record_types": RECORD_TYPES,
        "search_capabilities": SEARCH_CAPABILITIES,
        "evidence_forms": EVIDENCE_FORMS,
        "access": ACCESS,
        "integration_methods": INTEGRATION_METHODS,
        "entry_kinds": ENTRY_KINDS,
        "repository_types": REPOSITORY_TYPES,
        "verification_statuses": VERIFICATION_STATUSES,
        "claim_types": CLAIM_TYPES,
        "claim_statuses": CLAIM_STATUSES,
        "relationship_types": RELATIONSHIP_TYPES,
        "relationship_qualifiers": RELATIONSHIP_QUALIFIERS,
        "date_qualifiers": DATE_QUALIFIERS,
        "name_types": NAME_TYPES,
        "log_outcomes": LOG_OUTCOMES,
        "record_formats": RECORD_FORMATS,
        "clue_only_formats": sorted(CLUE_ONLY_FORMATS),
        "stances": STANCES,
        "identity_match": IDENTITY_MATCH,
        "assessments": ASSESSMENTS,
        "informant_knowledge": INFORMANT_KNOWLEDGE,
        "question_types": {k: v["label"] for k, v in QUESTION_TYPES.items()},
    }
