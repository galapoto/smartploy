"""SP81 exact approved-contact fingerprint for employer review and final action.

The reviewed job's CV/PDF and the user's approved profile contact are separate
snapshot components. No employer or remote AI interaction occurs here.
"""
from __future__ import annotations

import re

from .browser_handoff import _approved_contact, approved_fields_sha256
from .identity import UserProfileBinding
from .profile import CandidateProfile, ProfileFact


class ApprovedContactUnavailable(ValueError):
    pass


def approved_fields_fingerprint_locked(
    cur, binding: UserProfileBinding, letter: str, *, require_contact: bool,
) -> str:
    """Hash current, row-locked owner-approved contact facts and saved letter.

    Internal review fixtures without approved contact may persist an empty
    fingerprint, which remains unusable for real final-action consent.
    """
    cur.execute(
        """SELECT fact_type,value FROM smartploy_profile_facts
           WHERE profile_id=%s AND approved=true
           ORDER BY fact_type,value FOR SHARE""",
        (binding.profile_id,),
    )
    facts = tuple(
        ProfileFact(str(row[0]), str(row[1]), "reviewed-storage", approved=True)
        for row in cur.fetchall()
    )
    approved = _approved_contact(CandidateProfile(binding.profile_id, facts))
    if not approved["full_name"] or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", approved["email"]):
        if require_contact:
            raise ApprovedContactUnavailable("Approved applicant name and email are required")
        return ""
    return approved_fields_sha256({**approved, "cover_letter": letter[:10000]})
