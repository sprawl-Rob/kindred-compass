"""AI-assisted document reading: consent, sensitive-document warnings, number masking, applying the reading."""
import time

import pytest

from app import ocr
from tests.test_ai import ai, enable, wait_run  # noqa: F401  (fixture)
from tests.test_documents import _pdf, _wait

pytestmark = pytest.mark.skipif(not ocr.available(), reason="page previews need macOS Quartz")

DD214 = ["CERTIFICATE OF RELEASE OR DISCHARGE FROM ACTIVE DUTY (DD FORM 214)", "1. NAME: HARTLEY PAUL A",
         "3. SOCIAL SECURITY NUMBER 123-45-6789", "smudged boxes"]
READING = {
    "transcription": "1. NAME (Last, First, Middle): HARTLEY, PAUL A\n3. SOCIAL SECURITY NUMBER: 123-45-6789\n2. DEPARTMENT, COMPONENT AND BRANCH: ARMY/RA\n"
                     "4a. GRADE, RATE OR RANK: SP4\n12a. DATE ENTERED AD THIS PERIOD: 1966 06 14\n12b. SEPARATION DATE THIS PERIOD: 1968 06 13",
    "doc_type": "military", "title": "DD-214 — Paul A. Hartley — 1968",
    "fields": [{"label": "Name", "value": "Paul A Hartley"}, {"label": "Branch of Service", "value": "Army"}, {"label": "Rank", "value": "SP4"},
               {"label": "Date Entered Service", "value": "14 Jun 1966"}, {"label": "Separation Date", "value": "13 Jun 1968"},
               {"label": "Character of Service", "value": "Honorable"}, {"label": "Service Number", "value": "123-45-6789"}],
    "people": [{"name": "Paul A Hartley", "role": "veteran", "details": ""}],
    "uncertainties": ["Box 13 decorations partly illegible"],
}


def test_reading_a_dd214_with_ai(ai):
    c = ai.client
    enable(c)
    pid = c.ok("post", "/api/projects", json={"name": "Vet"})["id"]
    paul = c.ok("post", f"/api/projects/{pid}/persons", json={"names": [{"given": "Paul", "surname": "Hartley"}], "sex": "M", "living_status": "deceased"})["id"]
    r = c.c.post(f"/api/projects/{pid}/documents", files=[("files", ("dd214.pdf", _pdf(DD214), "application/pdf"))], headers={"X-Kindred": "1"})
    d = _wait(c, r.json()["documents"][0]["id"])
    assert any("Social Security" in w for w in d["sensitivity"])
    # images aren't sent until the user allows attachments
    pv = c.ok("post", "/api/ai/preview", json={"task": "document_reading", "inputs": {"document_id": d["id"]}})
    assert not pv["can_run"] and any("off in AI Settings" in b for b in pv["blockers"])
    c.ok("post", "/api/ai/consent", json={"acknowledge": True, "allow_attachments": True})
    pv = c.ok("post", "/api/ai/preview", json={"task": "document_reading", "inputs": {"document_id": d["id"]}})
    assert pv["can_run"] and pv["sent"]["images"] == 1 and any("Social Security" in w for w in pv["sent"]["warnings"])
    ai.anthropic.output = READING
    run = c.ok("post", "/api/ai/runs", json={"task": "document_reading", "inputs": {"document_id": d["id"]},
                                             "confirmed_model": f"{pv['selection']['provider']}:{pv['selection']['model']}"})
    assert wait_run(c, run["id"])["status"] == "succeeded"
    call = ai.anthropic.calls[-1]
    assert any(part.get("type") == "image" for m in call["messages"] for part in m["content"] if isinstance(part, dict))
    d = c.ok("get", f"/api/documents/{d['id']}")
    assert "123-45-6789" not in str(d["ai"]) and "[number withheld]" in d["ai"]["transcription"]
    d = c.ok("post", f"/api/documents/{d['id']}/ai/apply")
    assert d["doc_type"] == "military" and d["title"] == "DD-214 — Paul A. Hartley — 1968" and "123-45-6789" not in d["text"]
    assert d["detected"]["fields"]["branch"] == "Army" and d["detected"]["fields"]["service_separation"] == "13 Jun 1968"
    pv = c.ok("get", f"/api/documents/{d['id']}/attach-preview", params={"person_id": paul})
    mil = next(f for f in pv["facts"] if f["claim_type"] == "military")
    assert mil["date_text"] == "14 Jun 1966 – 13 Jun 1968" and "Army" in mil["value_text"] and "Honorable" in mil["value_text"]
