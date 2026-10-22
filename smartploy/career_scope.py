"""Conservative title-only career scope for Finland-wide IT and planning discovery.

No user profile, CV, AI service or employer content is needed to label a
published job *title*. This is a browse aid, not an assertion of skills fit,
seniority, availability or permission to apply. All jobs remain stored.
"""
from __future__ import annotations

import re


# Independent domain families deliberately not inferred from description:
# driver ads often mention apps, smartphones, AI, data or planning tools.
_IT_TITLE = (
    r"(?<!\w)(?:it|ict|tieto[- ]?tekn|tieto[- ]?järjestelm|software|"
    r"ohjelmist|ohjelmoi|kooda|kehittäj|developer|devops|frontend|"
    r"backend|full[- ]?stack|web[- ]?develop|sovellus|"
    r"data[- /]?(?:engineer|analy|scient|architect|specialist|"
    r"steward|platform|quality|consultant|kehittäj|insinöör|"
    r"analyyt|asiantuntij)|tietokanta|database|data[- ]?analy|"
    r"analyytikko|analyst|business intelligence|power bi|"
    r"pilvi(?:palvel|asiantuntij)|cloud[- ]?(?:engineer|architect|"
    r"specialist|developer|consultant)|cyber|kyber|tietoturva|"
    r"information security|infosec|machine learning|"
    r"tekoäly|artificial intelligence|"
    r"testaaja|testaus|software[- ]?test|quality assurance|"
    r"qa[- ]?(?:engineer|tester|analyst)|test automation|"
    r"järjestelmäasiantuntij|system[s]?[- ]?(?:admin|engineer|analyst)|"
    r"network[- ]?(?:engineer|administrator)|verkkoasiantuntij|"
    r"it[- /]?(?:support|tuki|asiantuntij)|technical support|"
    r"service desk|helpdesk|product[- ]?(?:owner|analyst)|"
    r"tekninen[- ]?projekt|automation[- ]?(?:engineer|developer))"
)

_PLANNING_TITLE = (
    r"(?<!\w)(?:suunnittelij\w*|hankesuunnittelij\w*|projektisuunnittelij\w*|suunnitteluinsinöör\w*|"
    r"projektikoordinaattor\w*|hankekoordinaattor\w*|"
    r"projektiassistent\w*|project[- ]?(?:planner|coordinator|"
    r"assistant)|planning[- ]?(?:officer|specialist|engineer|"
    r"coordinator)|urban[- ]?planner|environmental[- ]?engineer|"
    r"ympäristöinsinöör\w*|"
    r"toimistopalvelu(?:jen)?[- ]?suunnittelij\w*|toimistokoordinaattor\w*|"
    r"hallinto[- ]?(?:suunnittelij|koordinaattor|asiantuntij)\w*|"
    r"kehittämis(?:suunnittelij|koordinaattor|asiantuntij)\w*|"
    r"viestintä(?:suunnittelij|koordinaattor|asiantuntij)\w*|"
    r"verkkoviestintä\w*|verkkosisältö\w*|"
    r"sisältö(?:suunnittelij|koordinaattor|asiantuntij)\w*|"
    r"intranet[- ]?(?:koordinaattor|asiantuntij|suunnittelij)\w*|"
    r"tiedonhallin\w*|tietoasiantuntij\w*|"
    r"palvelu(?:suunnittelij|koordinaattor)\w*|"
    r"project[- ]?specialist|office[- ]?(?:planner|coordinator|administrator)|"
    r"administrative[- ]?(?:planner|coordinator|specialist)|"
    r"(?:digital|content|website|web[- ]?content|communications|intranet|"
    r"documentation|knowledge[- ]?management)[- ]?(?:planner|coordinator|specialist)|"
    r"technical[- ]?writer|document[- ]?controller)(?!\w)"
)

_REJECT_TRANSPORT_TITLE = (
    r"(?<!\w)(?:driver|chauffeur|courier|"
    r"kuljettaj\w*|taksikuski|autonkuljettaj\w*|"
    r"lähetti|delivery[- ]?rider)(?!\w)"
)
# Also catch a compound formed by concatenating words to "kuljettaja".
# Otherwise "Suunnittelijamyymäläkuljettaja" looks like a planning role
# despite explicitly being a driver; reject it before the planning check.
_TRANSPORT_COMPOUND = r"(?<!\w)[a-zåäö]*kuljettaj\w*(?!\w)"
_SENIOR = r"(?<!\w)(?:senior|principal|lead|staff|head|director|johtava|vanhempi|päällikkö)(?!\w)"
_ENTRY = r"(?<!\w)(?:junior|entry[- ]?level|graduate|trainee|intern|internship|harjoittelij\w*|juniori|nuorempi|kesätyö|kesäharjoittelij\w*)(?!\w)"


def career_area(title: str) -> str:
    """Return 'it_data', 'planning', or 'other' from a job title ONLY."""
    lowered = str(title or "").casefold()
    # Prevent promoted driver titles that also mention app/data tooling
    # in their title. True IT jobs do not generally advertise driving.
    if re.search(_REJECT_TRANSPORT_TITLE, lowered) or re.search(_TRANSPORT_COMPOUND, lowered):
        return "other"
    if re.search(_IT_TITLE, lowered):
        return "it_data"
    if re.search(_PLANNING_TITLE, lowered):
        return "planning"
    return "other"


def title_experience(title: str) -> str:
    """Report only an explicitly stated title-level marker, never infer."""
    lowered = str(title or "").casefold()
    if re.search(_SENIOR, lowered):
        return "senior"
    if re.search(_ENTRY, lowered):
        return "entry"
    return "unspecified"


def relevant_career_title(title: str) -> bool:
    return career_area(title) in {"it_data", "planning"}
