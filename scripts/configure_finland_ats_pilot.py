#!/usr/bin/env python3
"""Stage an opt-in, read-only Finland public employer ATS pilot on an OVH host.

Reads only a reviewed repo-local source registry; does not poll, deploy, print
private environment values, or alter PostgreSQL/Cloudflare/ObumAI.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import tempfile


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "finland_public_ats_pilot.json"
IT_PORTFOLIO = ROOT / "config" / "finland_it_public_ats_portfolio.json"
NATIONWIDE_PORTFOLIO = ROOT / "config" / "finland_nationwide_ats_portfolio.json"
ENV = ROOT / "deploy" / "personal" / "env"
KEY = "SMARTPLOY_PUBLIC_ATS_SOURCES_JSON"
FILE_KEY = "SMARTPLOY_PUBLIC_ATS_SOURCES_FILE"


class PilotConfigurationError(ValueError):
    pass


def reviewed_sources(registry: Path = REGISTRY) -> list[dict]:
    payload = json.loads(registry.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or len(payload) != 5:
        raise PilotConfigurationError("Expected exactly five approved read-only pilot boards")
    source_ids: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            raise PilotConfigurationError("Pilot source must be an object")
        fields = {
            "provider", "tenant", "label", "stack", "employer_sector",
            "external_ai_forwarding_allowed", "location_terms",
        }
        if item.get("tenant") == "tsmg":
            fields |= {"request_timeout_seconds", "page_size"}
        if set(item) != fields:
            raise PilotConfigurationError("Pilot source registry contains unsupported fields")
        if item["provider"] != "lever" or item["stack"] != "global":
            raise PilotConfigurationError("Only reviewed public Lever boards can join this pilot")
        slug = item["tenant"]
        if not isinstance(slug, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,99}", slug):
            raise PilotConfigurationError("Invalid pilot tenant name")
        if slug in source_ids:
            raise PilotConfigurationError("Duplicate pilot tenant name")
        source_ids.add(slug)
        if slug == "tsmg" and (
            item["request_timeout_seconds"] != 45 or item["page_size"] != 50
        ):
            raise PilotConfigurationError("TSMG transport override differs from reviewed values")
        if item["external_ai_forwarding_allowed"] is not False:
            raise PilotConfigurationError("Public ATS pilot must not grant external AI forwarding")
        if item["employer_sector"] != "private":
            raise PilotConfigurationError("Public ATS pilot sector classification changed")
        terms = item["location_terms"]
        if not isinstance(terms, list) or not terms or len(terms) > 20:
            raise PilotConfigurationError("Explicit Finnish location terms are required")
        for term in terms:
            if not isinstance(term, str) or not (2 <= len(term.strip()) <= 80):
                raise PilotConfigurationError("Invalid pilot location term")
    return payload


def plan_env_update(env_contents: str, pilot_json: str) -> tuple[str, bool]:
    """Never overwrite a nonblank operator-defined source configuration."""
    lines = env_contents.splitlines(keepends=True)
    sources = [i for i, line in enumerate(lines) if line.startswith(KEY + "=")]
    files = [line for line in lines if line.startswith(FILE_KEY + "=")]
    if len(sources) > 1 or len(files) > 1:
        raise PilotConfigurationError("Duplicate ATS keys in private environment")
    if files and files[0][len(FILE_KEY) + 1:].strip():
        raise PilotConfigurationError("Refusing to override a configured ATS source registry file")
    if sources:
        original = lines[sources[0]][len(KEY) + 1:].strip()
        if original:
            if original == pilot_json:
                return env_contents, False
            raise PilotConfigurationError("Refusing to override the existing public ATS source selection")
        linebreak = "\r\n" if lines[sources[0]].endswith("\r\n") else "\n"
        lines[sources[0]] = KEY + "=" + pilot_json + linebreak
        return "".join(lines), True
    prefix = "" if not env_contents or env_contents.endswith(("\n", "\r")) else "\n"
    return env_contents + prefix + KEY + "=" + pilot_json + "\n", True


def plan_tsmg_transport_upgrade(
    env_contents: str, reviewed: list[dict], *, rollback: bool = False
) -> tuple[str, bool]:
    """Switch only the canonical old/reviewed pilot; refuse operator changes."""
    lines = env_contents.splitlines(keepends=True)
    found = [i for i, line in enumerate(lines) if line.startswith(KEY + "=")]
    file_values = [line[len(FILE_KEY) + 1:].strip() for line in lines if line.startswith(FILE_KEY + "=")]
    if len(found) != 1 or len(file_values) > 1 or any(file_values):
        raise PilotConfigurationError("Expected exactly one inline ATS pilot and no custom registry file")
    index = found[0]
    try:
        current = json.loads(lines[index][len(KEY) + 1:].strip())
    except (ValueError, TypeError) as exc:
        raise PilotConfigurationError("Current ATS source registry is not valid JSON") from exc

    old = []
    for item in reviewed:
        previous = dict(item)
        if previous.get("tenant") == "tsmg":
            previous.pop("request_timeout_seconds", None)
            previous.pop("page_size", None)
        old.append(previous)
    target = old if rollback else reviewed
    expected = reviewed if rollback else old
    if current == target:
        return env_contents, False
    if current != expected:
        raise PilotConfigurationError("Refusing to override an operator-modified ATS source selection")
    new_json = json.dumps(target, ensure_ascii=False, separators=(",", ":"))
    ending = "\r\n" if lines[index].endswith("\r\n") else "\n"
    lines[index] = KEY + "=" + new_json + ending
    return "".join(lines), True




def reviewed_it_portfolio(registry: Path = IT_PORTFOLIO) -> list[dict]:
    """Review the exact seven read-only ATS boards, not arbitrary web URLs.

    The official published Greenhouse GET APIs for Oura, Wolt and Smartly
    were checked; adding a new employer requires explicit code review.
    The previous TSMG driving-heavy source is retired from this
    IT-first portfolio, but the operator can restore the prior five.
    """
    # The OVH staging command runs on stock host Python, outside Docker.
    # Do NOT import app modules here: public_ats imports httpx, which is
    # installed in the API/worker images but is not required on the host.
    payload = json.loads(registry.read_text(encoding="utf-8"))
    expected = {
        ("lever", "uprightproject"), ("lever", "brightlyworks"),
        ("lever", "netlight"), ("lever", "rovio-2"),
        ("greenhouse", "oura"), ("greenhouse", "wolt"),
        ("greenhouse", "smartlyio"),
    }
    if not isinstance(payload, list) or len(payload) != 7:
        raise PilotConfigurationError("Expected seven reviewed IT-first ATS boards")
    source_ids: set[tuple[str, str]] = set()
    allowed = {
        "provider", "tenant", "label", "stack", "employer_sector",
        "external_ai_forwarding_allowed", "location_terms",
        "request_timeout_seconds", "page_size",
    }
    for item in payload:
        if not isinstance(item, dict):
            raise PilotConfigurationError("Portfolio source must be an object")
        provider, tenant = item.get("provider"), item.get("tenant")
        label = item.get("label")
        if (
            set(item) - allowed
            or provider not in {"lever", "greenhouse"}
            or not isinstance(tenant, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,99}", tenant)
            or not isinstance(label, str)
            or not label.strip()
            or len(label) > 200
            or not isinstance(item.get("stack", ""), str)
        ):
            raise PilotConfigurationError("Invalid public ATS board configuration")
        key = (provider, tenant)
        if key in source_ids:
            raise PilotConfigurationError("Duplicate IT portfolio employer")
        source_ids.add(key)
        if item.get("external_ai_forwarding_allowed") is not False:
            raise PilotConfigurationError("Public IT portfolio forbids external AI forwarding")
        locations = item.get("location_terms")
        if (
            item.get("employer_sector") != "private"
            or not isinstance(locations, list)
            or not 1 <= len(locations) <= 20
            or not all(
                isinstance(term, str)
                and 2 <= len(term.strip()) <= 80
                and not any(ord(ch) < 32 for ch in term)
                for term in locations
            )
        ):
            raise PilotConfigurationError("IT portfolio requires explicit Finland locations")
        if "finland" not in {term.strip().casefold() for term in locations}:
            raise PilotConfigurationError("Country term Finland must be present")
        if item.get("stack", "") != ("global" if provider == "lever" else ""):
            raise PilotConfigurationError("IT portfolio unexpected provider/stack")
        if item.get("page_size") is not None or item.get("request_timeout_seconds") is not None:
            raise PilotConfigurationError("IT portfolio cannot override network rate limits")

    if source_ids != expected:
        raise PilotConfigurationError("Unreviewed employer in IT portfolio")
    return payload


def plan_it_portfolio_upgrade(
    env_contents: str, former: list[dict], updated: list[dict], *,
    rollback: bool = False,
) -> tuple[str, bool]:
    """Compare full reviewed old/new sets and refuse unknown operator edits."""
    lines = env_contents.splitlines(keepends=True)
    indices = [i for i, row in enumerate(lines) if row.startswith(KEY + "=")]
    file_values = [row[len(FILE_KEY) + 1:].strip()
                   for row in lines if row.startswith(FILE_KEY + "=")]
    if len(indices) != 1 or len(file_values) > 1 or any(file_values):
        raise PilotConfigurationError("Expected exact inline source configuration and no custom registry file")
    index = indices[0]
    try:
        current = json.loads(lines[index][len(KEY) + 1:].strip())
    except (ValueError, TypeError) as exc:
        raise PilotConfigurationError("Existing public ATS settings are invalid JSON") from exc
    expected, target = (updated, former) if rollback else (former, updated)
    if current == target:
        return env_contents, False
    if current != expected:
        raise PilotConfigurationError("Refusing to override operator-modified ATS portfolio")
    ending = "\r\n" if lines[index].endswith("\r\n") else "\n"
    new_json = json.dumps(target, ensure_ascii=False, separators=(",", ":"))
    lines[index] = KEY + "=" + new_json + ending
    return "".join(lines), True


def reviewed_nationwide_portfolio(
    registry: Path = NATIONWIDE_PORTFOLIO,
) -> list[dict]:
    """Validate the curated 22-board wider-discovery roster before private staging.

    Source metadata is an ingestion hypothesis, not proof of current vacancies
    or a licence to submit applications. Keep the configured subset immutable
    and validate it through existing vetted Lever/Greenhouse/SmartRecruiters
    adapters. Every source remains Finland-scoped and local-only.
    """
    # This host-side staging tool must run on a stock Ubuntu Python 3
    # WITHOUT importing httpx or the application dependency tree. Strictly
    # validate the immutable registry here, while worker/CI also validates
    # each source with the original typed PublicATSSourceConfig.from_dict.
    expected = {
        ("lever", "global", "uprightproject"),
        ("lever", "global", "brightlyworks"),
        ("lever", "global", "netlight"),
        ("lever", "global", "rovio-2"),
        ("lever", "global", "alifsemi"),
        ("lever", "global", "dnb"),
        ("lever", "global", "jobgether"),
        ("lever", "global", "weloglobal"),
        ("lever", "eu", "quadcode"),
        ("greenhouse", "", "oura"),
        ("greenhouse", "", "wolt"),
        ("greenhouse", "", "smartlyio"),
        ("greenhouse", "", "alphasense"),
        ("greenhouse", "", "energyhub"),
        ("greenhouse", "", "yousician"),
        ("greenhouse", "", "pronto"),
        ("smartrecruiters", "", "AFRY"),
        ("smartrecruiters", "", "DeloitteNordic"),
        ("smartrecruiters", "", "Ramboll3"),
        ("smartrecruiters", "", "YIT1"),
        ("smartrecruiters", "", "Tieto2"),
        ("smartrecruiters", "", "TurnerTownsend"),
    }
    payload = json.loads(registry.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or len(payload) != len(expected):
        raise PilotConfigurationError("Expected the 22-source nationwide portfolio")
    observed = set()
    allowed_fields = {
        "provider", "tenant", "label", "stack", "employer_sector",
        "external_ai_forwarding_allowed", "location_terms",
    }
    for raw in payload:
        if not isinstance(raw, dict):
            raise PilotConfigurationError("Portfolio source must be an object")
        if set(raw) - allowed_fields:
            raise PilotConfigurationError("Unsupported nationwide ATS source fields")
        provider, tenant = raw.get("provider"), raw.get("tenant")
        stack = raw.get("stack", "")
        label = raw.get("label")
        if (
            not isinstance(provider, str)
            or not isinstance(tenant, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,99}", tenant)
            or not isinstance(label, str)
            or not label.strip()
            or len(label) > 200
            or not isinstance(stack, str)
            or (provider == "lever" and stack not in {"global", "eu"})
            or (provider != "lever" and stack != "")
        ):
            raise PilotConfigurationError("Invalid nationwide ATS source configuration")
        identity = (provider, stack, tenant)
        if identity in observed:
            raise PilotConfigurationError("Duplicate nationwide ATS board")
        observed.add(identity)
        locations = raw.get("location_terms")
        if (
            raw.get("external_ai_forwarding_allowed") is not False
            or raw.get("employer_sector") != "private"
            or not isinstance(locations, list)
            or not 1 <= len(locations) <= 20
            or not all(isinstance(term, str)
                       and 2 <= len(term.strip()) <= 80
                       and not any(ord(ch) < 32 for ch in term)
                       for term in locations)
            or "finland" not in {term.strip().casefold() for term in locations}
        ):
            raise PilotConfigurationError("Nationwide ATS sources must be Finland-scoped and private")
    if observed != expected:
        raise PilotConfigurationError("Unreviewed employer in nationwide ATS portfolio")
    return payload


def plan_nationwide_portfolio_upgrade(
    env_contents: str, legacy: list[dict], seven: list[dict],
    nationwide: list[dict], *, rollback_to: str = "",
) -> tuple[str, bool]:
    """Only replace an exact known 5/7/22-source roster; preserve all other env."""
    lines = env_contents.splitlines(keepends=True)
    indices = [i for i, row in enumerate(lines) if row.startswith(KEY + "=")]
    file_values = [row[len(FILE_KEY) + 1:].strip()
                   for row in lines if row.startswith(FILE_KEY + "=")]
    if len(indices) != 1 or len(file_values) > 1 or any(file_values):
        raise PilotConfigurationError("Expected exactly one inline ATS registry and no registry file")
    index = indices[0]
    try:
        current = json.loads(lines[index][len(KEY) + 1:].strip())
    except (ValueError, TypeError) as exc:
        raise PilotConfigurationError("Existing nationwide ATS settings are invalid JSON") from exc

    if rollback_to:
        if rollback_to not in {"five", "seven"}:
            raise PilotConfigurationError("Invalid portfolio rollback target")
        target = legacy if rollback_to == "five" else seven
        if current != nationwide and current != target:
            raise PilotConfigurationError("Refusing to roll back operator-modified ATS portfolio")
    else:
        target = nationwide
        if current not in (legacy, seven, nationwide):
            raise PilotConfigurationError("Refusing to overwrite operator-modified ATS portfolio")

    if current == target:
        return env_contents, False
    ending = "\r\n" if lines[index].endswith("\r\n") else "\n"
    lines[index] = KEY + "=" + json.dumps(
        target, ensure_ascii=False, separators=(",", ":")
    ) + ending
    return "".join(lines), True


def _validate_private_env(path: Path) -> os.stat_result:
    try:
        details = path.lstat()
    except FileNotFoundError as exc:
        raise PilotConfigurationError("Private SmartPloy env file does not exist") from exc
    if not stat.S_ISREG(details.st_mode) or stat.S_ISLNK(details.st_mode):
        raise PilotConfigurationError("Private SmartPloy env must be a non-symlink regular file")
    if stat.S_IMODE(details.st_mode) & 0o077:
        raise PilotConfigurationError("Private SmartPloy env must not be group/world readable")
    return details


def stage_pilot(
    env: Path = ENV,
    registry: Path = REGISTRY,
    *,
    apply: bool = False,
    upgrade_tsmg_transport: bool = False,
    rollback_tsmg_transport: bool = False,
    upgrade_it_portfolio: bool = False,
    rollback_it_portfolio: bool = False,
    upgrade_nationwide_portfolio: bool = False,
    rollback_nationwide_to_five: bool = False,
    rollback_nationwide_to_seven: bool = False,
) -> dict:
    nationwide_actions = sum((
        upgrade_nationwide_portfolio,
        rollback_nationwide_to_five,
        rollback_nationwide_to_seven,
    ))
    if nationwide_actions > 1 or (nationwide_actions and any((
        upgrade_tsmg_transport, rollback_tsmg_transport,
        upgrade_it_portfolio, rollback_it_portfolio,
    ))):
        raise PilotConfigurationError("Choose exactly one source portfolio operation")
    if upgrade_tsmg_transport and rollback_tsmg_transport:
        raise PilotConfigurationError("Choose upgrade or rollback, not both")
    if (upgrade_it_portfolio or rollback_it_portfolio) and (
        upgrade_tsmg_transport or rollback_tsmg_transport
    ):
        raise PilotConfigurationError("Choose only one ATS portfolio operation")
    sources = reviewed_sources(registry)
    former_sources = sources
    if nationwide_actions:
        sources = reviewed_nationwide_portfolio()
    elif upgrade_it_portfolio or rollback_it_portfolio:
        sources = reviewed_it_portfolio()
    elif registry != REGISTRY and (upgrade_tsmg_transport or rollback_tsmg_transport):
        raise PilotConfigurationError("Transport upgrade requires original reviewed pilot")
    env_stat = _validate_private_env(env)
    original = env.read_text(encoding="utf-8")
    pilot_json = json.dumps(sources, ensure_ascii=False, separators=(",", ":"))
    if nationwide_actions:
        seven = reviewed_it_portfolio()
        rollback_to = (
            "five" if rollback_nationwide_to_five
            else "seven" if rollback_nationwide_to_seven else ""
        )
        replacement, changed = plan_nationwide_portfolio_upgrade(
            original, former_sources, seven, sources, rollback_to=rollback_to,
        )
    elif upgrade_it_portfolio or rollback_it_portfolio:
        replacement, changed = plan_it_portfolio_upgrade(
            original, former_sources, sources, rollback=rollback_it_portfolio,
        )
    elif upgrade_tsmg_transport or rollback_tsmg_transport:
        replacement, changed = plan_tsmg_transport_upgrade(
            original, sources, rollback=rollback_tsmg_transport,
        )
    else:
        replacement, changed = plan_env_update(original, pilot_json)
    if apply and changed:
        descriptor, candidate = tempfile.mkstemp(prefix=".smartploy-env-", dir=str(env.parent))
        try:
            os.fchmod(descriptor, stat.S_IMODE(env_stat.st_mode))
            if hasattr(os, "fchown"):
                os.fchown(descriptor, env_stat.st_uid, env_stat.st_gid)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(replacement)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(candidate, env)
            directory = os.open(str(env.parent), os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(candidate):
                os.unlink(candidate)

    # Rollback receipts report the actual restored five employers rather
    # than the seven-source target still loaded for source validation.
    selected = (
        former_sources if rollback_it_portfolio or rollback_nationwide_to_five
        else seven if rollback_nationwide_to_seven
        else sources
    )
    return {
        "source_count": len(selected),
        "tenant_ids": [item["tenant"] for item in selected],
        "region_policy": "explicit Finland/Finnish locations only",
        "transport_scope": (
            "finland_nationwide_ats_portfolio_v3" if nationwide_actions
            else "finland_it_public_ats_portfolio_v2" if (upgrade_it_portfolio or rollback_it_portfolio)
            else "TSMG only" if (upgrade_tsmg_transport or rollback_tsmg_transport)
            else "initial approved pilot"
        ),
        "external_ai_forwarding": "disabled",
        "private_env": "updated" if changed and apply else "unchanged" if not changed else "change_ready",
        "next": "run production preflight and guarded deploy" if apply else "review and rerun with --apply",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Review or stage the opt-in public employer Finland job-source pilot"
    )
    parser.add_argument("--apply", action="store_true", help="stage pilot in the private host env")
    policy_action = parser.add_mutually_exclusive_group()
    policy_action.add_argument(
        "--upgrade-tsmg-transport",
        action="store_true",
        help="upgrade only unmodified existing five-source pilot with a bounded TSMG timeout",
    )
    policy_action.add_argument(
        "--rollback-tsmg-transport",
        action="store_true",
        help="restore only the original TSMG timeout/page-size settings",
    )
    policy_action.add_argument(
        "--upgrade-it-portfolio", action="store_true",
        help="replace exact current 5 ATS boards with 7 reviewed IT-first Lever/Greenhouse boards",
    )
    policy_action.add_argument(
        "--rollback-it-portfolio", action="store_true",
        help="restore old five-source pilot only if current selection equals reviewed IT portfolio",
    )
    policy_action.add_argument(
        "--upgrade-nationwide-portfolio", action="store_true",
        help="replace exactly 5 or 7 known ATS boards with 22 Finland/remote IT and planner boards",
    )
    policy_action.add_argument(
        "--rollback-nationwide-to-five", action="store_true",
        help="restore exact original five-source roster from reviewed 22-source roster",
    )
    policy_action.add_argument(
        "--rollback-nationwide-to-seven", action="store_true",
        help="restore exact IT-first seven-source roster from reviewed 22-source roster",
    )
    args = parser.parse_args()
    try:
        result = stage_pilot(
            apply=args.apply,
            upgrade_tsmg_transport=args.upgrade_tsmg_transport,
            rollback_tsmg_transport=args.rollback_tsmg_transport,
            upgrade_it_portfolio=args.upgrade_it_portfolio,
            rollback_it_portfolio=args.rollback_it_portfolio,
            upgrade_nationwide_portfolio=args.upgrade_nationwide_portfolio,
            rollback_nationwide_to_five=args.rollback_nationwide_to_five,
            rollback_nationwide_to_seven=args.rollback_nationwide_to_seven,
        )
    except (PilotConfigurationError, OSError, ValueError) as exc:
        raise SystemExit("ATS pilot: " + str(exc)) from exc
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
