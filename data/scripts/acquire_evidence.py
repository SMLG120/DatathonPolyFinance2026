#!/usr/bin/env python3
"""Acquire the official documents behind the controversy registry and the
terms-of-use pages quoted in docs/data-sources.md (standard library only).

    # every item that may be fetched automatically (one GET each, 1 s apart)
    python3 -I data/scripts/acquire_evidence.py

    # BlackRock's terms forbid automated copying without permission: open the
    # page in a web browser, save it, then register the saved file
    python3 -I data/scripts/acquire_evidence.py --item BLACKROCK_CA_TERMS \
        --from-file <saved page> --retrieved-at 2026-11-14T22:34:58Z

    # no network: re-check the registered pages against the current
    # configuration (after editing must_contain, terms or limitations below)
    python3 -I data/scripts/acquire_evidence.py --reverify

    # correct the free-text retrieval_method of an already registered file
    python3 -I data/scripts/acquire_evidence.py --item <ITEM> --from-file <same file> \
        --retrieved-at <UTC ISO> --method "<corrected text>" --amend-method

What it guarantees
* Raw pages go to data/raw/<subdir>/<ITEM>_<retrieval-date>.html (UTC date),
  are written atomically, set read-only and never overwritten. data/raw/ is
  git-ignored; data/manifests/raw_files_manifest.json keeps URL, HTTP status,
  retrieval timestamp (UTC), byte size and SHA-256.
* A page is accepted only if every sentence this project relies on
  (``must_contain``) is literally present in its visible text and the date
  printed on the page parses to the configured document date. The sentences
  found are stored in the manifest as ``verified_phrases``: each statement in
  the controversy registry and each terms-of-use quotation traces to a hashed
  file. A bot-challenge page, a moved page or an edited page therefore fails.
* All or nothing: any failure aborts the run with a non-zero exit code and
  nothing is written.
* An item already retrieved on the current UTC date is kept and NOT requested
  again (pages are dynamic; raw files are never replaced).

Record kinds written: ``controversy_evidence`` (used by build_processed.py for
controversies.json and sources.json), ``terms_of_use`` (documentation, and the
check of the quotations in _terms.py) and ``regulatory_reference`` (the dated
listing behind the "Regulatory claim check" in docs/data-sources.md).
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import os
import re
import stat
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (RAW_DIR, RAW_MANIFEST, REPO_ROOT, SCHEMA_VERSION, dump_json, load_json, rel,  # noqa: E402
                     sha256_bytes, sha256_file, write_bytes_atomic)
from _terms import REUSE_STATEMENTS, TERMS_ITEM_FOR, quotations  # noqa: E402
from acquire_holdings import USER_AGENT, AcquisitionError, fetch, iso_z, utc_now  # noqa: E402

KINDS = ("controversy_evidence", "terms_of_use", "regulatory_reference")
_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
           "november", "december"]

EPA = "United States Environmental Protection Agency (EPA), epa.gov"
AER = "Alberta Energy Regulator (AER), aer.ca"
TERMS_PAGE = "Not applicable: this record is itself a terms-of-use page."

BLACKROCK_NOTICE = (
    "BlackRock Canada terms ('Prohibited Uses') forbid using \"any robot, spider, intelligent agent, other automatic\n"
    "  device, or manual process to search, monitor or copy this Website\" without permission, \"provided that generally\n"
    "  available third-party web browsers may be used without such permission\".\n"
    "  -> Open https://www.blackrock.com/ca/investors/en/terms-and-conditions in a web browser, save the page, then:\n"
    "     python3 -I data/scripts/acquire_evidence.py --item BLACKROCK_CA_TERMS --from-file <path> --retrieved-at <UTC ISO>"
)

ITEMS = {
    # ------------------------------------------------------------ controversy evidence
    "EPA_EXXONMOBIL_CAA": {
        "kind": "controversy_evidence",
        "publisher": EPA,
        "title": "Exxon Mobil Corporation/Exxonmobil Oil Corporation Clean Air Act Settlement (EPA enforcement case page)",
        "url": ("https://www.epa.gov/enforcement/"
                "exxon-mobil-corporationexxonmobil-oil-corporation-clean-air-act-settlement"),
        "raw_subdir": "controversy_evidence",
        "source_id_prefix": "epa_exxonmobil_caa_settlement",
        "automated_download": True,
        "document_date": "2017-10-31",
        "document_date_marker": "October 31, 2017",
        "must_contain": [
            "EPA, the U.S. Department of Justice, and the Louisiana Department of Environmental Quality announced a "
            "settlement today with Exxon Mobil Corp. and ExxonMobil Oil Corp.",
            "petrochemical manufacturing facilities in Texas and Louisiana",
            "The settlement resolves allegations that ExxonMobil violated the Clean Air Act by failing to properly "
            "operate and monitor industrial flares at their petrochemical facilities",
            "The owners and/or operators of the eight plants subject to this settlement are Exxon Mobil Corporation "
            "and its subsidiary ExxonMobil Oil Corporation",
            "Exxon Mobil Corporation is a publicly traded company headquartered in Irving, Texas.",
            "The complaint alleges that Exxon violated Clean Air Act (CAA) and regulatory requirements",
            "Exxon will pay a civil penalty of $2.5 million.",
            "is subject to a 30-day public comment period and final court approval",
        ],
        "limitations": (
            "A regulator's summary of a negotiated settlement of allegations, written on the day the proposed consent "
            "decree was lodged (subject to public comment and final court approval). The page does not say whether the "
            "court entered the decree and records no admission or finding of liability. The consent decree itself and "
            "the court docket were not retrieved. The page names Exxon Mobil Corporation; whether today's listed "
            "company behind ticker XOM (printed 'EXXONMOBIL HOLDINGS CORP' in the SPY file) is the same legal entity "
            "was not researched."),
    },
    "EPA_ENBRIDGE_CWA": {
        "kind": "controversy_evidence",
        "publisher": EPA,
        "title": "Enbridge Clean Water Act Settlement (EPA enforcement case page)",
        "url": "https://www.epa.gov/enforcement/enbridge-clean-water-act-settlement",
        "raw_subdir": "controversy_evidence",
        "source_id_prefix": "epa_enbridge_cwa_settlement",
        "automated_download": True,
        "document_date": "2016-07-20",
        "document_date_marker": "July 20, 2016",
        "must_contain": [
            "The U.S. Environmental Protection Agency (EPA) and the Department of Justice today announced a settlement "
            "with Enbridge Energy Limited Partnership and several related Enbridge companies to resolve claims "
            "stemming from its 2010 oil spills in Marshall, Mich. and Romeoville, Ill.",
            "Enbridge has agreed to spend at least $110 million on a series of measures to prevent spills",
            "Enbridge will also pay civil penalties totaling $62 million for Clean Water Act violations",
            "On January 19, 2017, the United States filed a motion to enter as a final judgment a revised consent decree.",
            "The discharge was the result of a pipeline rupture",
            "Enbridge paid a civil penalty of $61 million for the Marshall spill and $1 million for the Romeoville spill.",
        ],
        "limitations": (
            "A regulator's summary of a negotiated settlement. The settling parties are described as 'Enbridge Energy "
            "Limited Partnership and several related Enbridge companies'; the page does not list them and does not "
            "name Enbridge Inc., the listed company. It reports a motion to enter a revised consent decree (January "
            "19, 2017) but not the court's decision on it. The consent decree and the court docket were not retrieved."),
    },
    "EPA_ENBRIDGE_ORDER": {
        "kind": "controversy_evidence",
        "publisher": EPA,
        "title": ("Case Summary: EPA Orders Enbridge Inc. to Perform Additional Dredging to Remove Oil from Kalamazoo "
                  "River, Mich. (EPA enforcement case page)"),
        "url": ("https://www.epa.gov/enforcement/"
                "case-summary-epa-orders-enbridge-inc-perform-additional-dredging-remove-oil-kalamazoo"),
        "raw_subdir": "controversy_evidence",
        "source_id_prefix": "epa_enbridge_dredging_order",
        "automated_download": True,
        "document_date": "2013-03-14",
        "document_date_marker": "March 14, 2013",
        "must_contain": [
            "EPA Orders Enbridge Inc. to Perform Additional Dredging to Remove Oil from Kalamazoo River, Mich.",
            "EPA issued an administrative order that requires Enbridge Inc. to do additional dredging in",
            "July 2010 pipeline spill",
            "The order was issued under the authority of section 311(c) of the Clean Water Act.",
            "Enbridge reported that a 30-inch oil pipeline ruptured near Marshall, Michigan.",
        ],
        "limitations": (
            "A regulator's case summary of a clean-up order; it is not a finding of a violation. Used here only "
            "because it names Enbridge Inc. as the company ordered to clean up the July 2010 spill near Marshall, "
            "Michigan that the 2016 settlement also concerns. The order (PDF) itself was not retrieved."),
    },
    "AER_CNRL_PENALTY": {
        "kind": "controversy_evidence",
        "publisher": AER,
        "title": ("News Release 2024-07-15: Alberta Energy Regulator penalizes CNRL for contravening the Environmental "
                  "Protection and Enhancement Act"),
        "url": "https://www.aer.ca/about-aer/media-centre/news-releases/news-release-2024-07-15",
        "raw_subdir": "controversy_evidence",
        "source_id_prefix": "aer_cnrl_penalty_news_release",
        "automated_download": True,
        "document_date": "2024-07-15",
        "document_date_marker": "July 15, 2024",
        "must_contain": [
            "The Alberta Energy Regulator (AER) has fined Canadian Natural Resources Limited (CNRL) for contravening "
            "section 155 of the Environmental Protection and Enhancement Act (EPEA)",
            "The AER has ordered CNRL to pay $278 000.",
            "Following an investigation, the AER has determined that between May 21, 2022, and August 4, 2022, CNRL "
            "contravened section 155 of EPEA by failing to prevent a hazardous substance that contained bitumen from "
            "coming into contact with birds and other wildlife, resulting in bird fatalities.",
        ],
        "limitations": (
            "A regulator's news release about its own administrative decision. It does not say whether the decision "
            "was appealed or paid, and does not name the site. The enforcement decision on the AER Compliance "
            "Dashboard was not retrieved."),
    },
    # ------------------------------------------- regulatory claim check (documentation)
    "CNW_CIRO_RELEASE_LISTING": {
        "kind": "regulatory_reference",
        "publisher": "CNW Group / Cision (newswire.ca): press releases issued by the Canadian Investment Regulatory "
                     "Organization (CIRO)",
        "title": "Canadian Investment Regulatory Organization (CIRO) Press Releases - listing, page 2 at 100 per page",
        "url": "https://www.newswire.ca/news/canadian-investment-regulatory-organization-%28ciro%29/?page=2&pagesize=100",
        "raw_subdir": "regulatory_reference",
        "source_id_prefix": "cnw_ciro_release_listing",
        "automated_download": True,
        "document_date": "2026-03-12",
        "document_date_marker": "Mar 12, 2026",
        "must_contain": [
            "Canadian Investment Regulatory Organization (CIRO) Press Releases",
            "Mar 12, 2026, 11:00 ET",
            "CIRO Publishes New Guidance for Order Execution Only Dealers",
            "Greater access to educational resources from OEO dealers will empower DIY investors to make confident, "
            "informed investment decisions",
        ],
        "terms": ("The terms of use of newswire.ca were not retrieved. The page is used only to cite the title, the "
                  "time stamp and the first sentence of CIRO's own press release, with a link; the raw page is kept "
                  "out of git."),
        "limitations": (
            "A wire-service LISTING: it proves the title, the time stamp and the opening sentence of the release, "
            "not its body. The release page itself and ciro.ca answered automated requests with a bot challenge "
            "(HTTP 403) and were not bypassed; the body was read through a web-fetch tool only (no raw copy, no "
            "hash). The listing is paginated: the entry moves to another page as CIRO publishes new releases, and "
            "this item then fails instead of recording a different page."),
    },
    # ------------------------------------------------------------------ terms of use
    "SSGA_TERMS": {
        "kind": "terms_of_use",
        "publisher": "State Street Investment Management (State Street Global Advisors), ssga.com",
        "title": "Terms and Conditions | State Street",
        "url": "https://www.ssga.com/us/en/intermediary/footer/terms-and-conditions",
        "raw_subdir": "terms_of_use",
        "source_id_prefix": "ssga_terms_and_conditions",
        "automated_download": True,
        "document_date": None,
        "document_date_marker": None,
        "must_contain": [
            "You may not copy, reproduce, duplicate, modify, adopt or lend, sell, disseminate or otherwise transfer, in "
            "whole or in part, any of the information contained in this Site, except for the purpose of accessing the "
            "Site and producing print-outs for your own personal use, or making a reasonable number of copies of such "
            "pages for internal use within your organization in accordance with this Agreement.",
            "to be published, redistributed or retransmitted for other than use for or on behalf of yourself",
        ],
        "limitations": ("Read for the reuse conditions only. The page prints no revision date. The words 'robot', "
                        "'automated', 'scrap', 'crawl' and 'data mining' do not occur in its visible text."),
    },
    "BLACKROCK_CA_TERMS": {
        "kind": "terms_of_use",
        "publisher": "BlackRock Asset Management Canada Limited, blackrock.com/ca",
        "title": "Terms and Conditions | BlackRock (Canada, investors site)",
        "url": "https://www.blackrock.com/ca/investors/en/terms-and-conditions",
        "raw_subdir": "terms_of_use",
        "source_id_prefix": "blackrock_ca_terms_and_conditions",
        "automated_download": False,  # see BLACKROCK_NOTICE
        "document_date": None,
        "document_date_marker": None,
        "must_contain": [
            "February 2020",
            "Such content is solely for your personal, non-commercial use.",
            "You may download material displayed on this Website for your personal use provided you also retain all "
            "copyright and other proprietary notices contained on the materials.",
            "You may not distribute, modify, transmit, reuse, repost, or use the content of this Website for public or "
            "commercial purposes",
            "without BlackRock's written permission",
            "Use any robot, spider, intelligent agent, other automatic device, or manual process to search, monitor or "
            "copy this Website or the reports, data, information, content, software, products services, or other "
            "materials on, generated by or obtained from this Website",
            "provided that generally available third-party web browsers may be used without such permission",
        ],
        "limitations": "Read for the reuse conditions only. The page prints 'February 2020' as its date.",
    },
    "EPA_DISCLAIMERS": {
        "kind": "terms_of_use",
        "publisher": EPA,
        "title": "EPA Disclaimers",
        "url": "https://www.epa.gov/web-policies-and-procedures/epa-disclaimers",
        "raw_subdir": "terms_of_use",
        "source_id_prefix": "epa_disclaimers",
        "automated_download": True,
        "document_date": None,
        "document_date_marker": None,
        "must_contain": [
            "The disclaimers provided on this page represent a catalogue of options listed here for convenience and do "
            "not necessarily apply to any particular work or other information unless the Agency has explicitly "
            "stated so",
            "These documents may be freely distributed and used for non-commercial, scientific and educational purposes.",
            "Commercial use of the documents available from the EPA websites may be protected under the U.S. and "
            "Foreign Copyright Laws.",
        ],
        "limitations": "A catalogue of disclaimers; EPA says each applies only where it states so.",
    },
    "AER_COPYRIGHT": {
        "kind": "terms_of_use",
        "publisher": AER,
        "title": "Copyright and Disclaimer | Alberta Energy Regulator",
        "url": "https://www.aer.ca/copyright-and-disclaimer",
        "raw_subdir": "terms_of_use",
        "source_id_prefix": "aer_copyright_and_disclaimer",
        "automated_download": True,
        "document_date": None,
        "document_date_marker": None,
        "must_contain": [
            "Information on this site has been posted with the intent that it be readily available for personal and "
            "public non-commercial (educational) use.",
            "the information may be reproduced, in whole or in part and by any means, without charge or further "
            "permission from the AER.",
            "the AER be identified as the source of the materials",
            "the reproduction not be presented as an official version of the AER material",
        ],
        "limitations": "Read for the reuse conditions only.",
    },
}


def terms_for(item_key: str) -> str:
    item = ITEMS[item_key]
    if item["kind"] == "terms_of_use":
        return TERMS_PAGE
    if item["kind"] == "regulatory_reference":
        return item["terms"]
    return REUSE_STATEMENTS[TERMS_ITEM_FOR[item_key]]


def normalise(text: str) -> str:
    """Collapse whitespace and drop the space that tag removal leaves before punctuation."""
    return re.sub(r" ([.,;:)])", r"\1", re.sub(r"\s+", " ", text).strip())


def visible_text(body: bytes) -> str:
    text = body.decode("utf-8", errors="replace")
    text = re.sub(r"(?is)<(script|style|noscript|svg)\b.*?</\1\s*>", " ", text)
    text = re.sub(r"(?s)<!--.*?-->", " ", text)
    return normalise(html.unescape(re.sub(r"<[^>]+>", " ", text)))


def long_date_to_iso(text: str) -> str:
    """'October 31, 2017' or 'Mar 12, 2026' -> ISO date (full month name or its first three letters)."""
    match = re.fullmatch(r"([A-Za-z]+)\.? (\d{1,2}), (\d{4})", text.strip())
    name = match.group(1).lower() if match else ""
    months = [m for m in _MONTHS if m == name or (len(name) == 3 and m.startswith(name))]
    if len(months) != 1:
        raise AcquisitionError(f"unrecognised date text {text!r}")
    return dt.date(int(match.group(3)), _MONTHS.index(months[0]) + 1, int(match.group(2))).isoformat()


def validate(item_key: str, body: bytes, retrieval_date: str) -> dict:
    """Check that the page is the document we cite; return the facts recorded in the manifest."""
    item = ITEMS[item_key]
    head = body[:4000].lower()
    if b"<html" not in head and b"<!doctype html" not in head:
        raise AcquisitionError(f"{item_key}: not an HTML page; first bytes {body[:80]!r}")
    text = visible_text(body)
    missing = [phrase for phrase in item["must_contain"] if normalise(phrase) not in text]
    if missing:
        raise AcquisitionError(
            f"{item_key}: the page does not contain {len(missing)} of the {len(item['must_contain'])} sentences this "
            f"project relies on (challenge page, moved or edited page?). First missing: {missing[0]!r}")
    facts = {"document_date": None, "document_date_text": None}
    marker = item["document_date_marker"]
    if marker:
        if marker not in text:
            raise AcquisitionError(f"{item_key}: date text {marker!r} not found on the page")
        iso = long_date_to_iso(marker)
        if iso != item["document_date"]:
            raise AcquisitionError(f"{item_key}: {marker!r} parses to {iso}, configured document_date is "
                                   f"{item['document_date']}")
        if iso > retrieval_date:
            raise AcquisitionError(f"{item_key}: document date {iso} is after the retrieval date {retrieval_date}")
        facts = {"document_date": iso, "document_date_text": marker}
    title = re.search(rb"(?is)<title[^>]*>(.*?)</title>", body)
    updated = re.search(r"Last updated on ([A-Za-z]+ \d{1,2}, \d{4})", text)
    facts["page_title"] = normalise(html.unescape(title.group(1).decode("utf-8", errors="replace"))) if title else None
    facts["page_last_updated"] = long_date_to_iso(updated.group(1)) if updated else None
    facts["verified_phrases"] = list(item["must_contain"])
    return facts


def self_check() -> None:
    """Configuration errors are bugs: fail before any network request."""
    for key, statement in REUSE_STATEMENTS.items():
        for quote in quotations(statement):
            if quote not in ITEMS[key]["must_contain"]:
                raise AcquisitionError(f"configuration: quotation {quote!r} in _terms.py is not verified by item {key}")
    for key, item in ITEMS.items():
        if item["kind"] not in KINDS:
            raise AcquisitionError(f"configuration: {key} has an unknown kind")
        if item["kind"] == "controversy_evidence" and key not in TERMS_ITEM_FOR:
            raise AcquisitionError(f"configuration: no terms page is mapped to {key}")
    prefixes = [item["source_id_prefix"] for item in ITEMS.values()]
    if len(set(prefixes)) != len(prefixes):
        raise AcquisitionError("configuration: duplicate source_id_prefix")


def reverify(manifest: dict) -> int:
    """No network. Re-check each registered page against the current configuration and refresh the
    descriptive fields of its manifest record. URL, timestamps, size and hash are never touched."""
    errors, changed, checked = [], 0, 0
    refreshed = []
    for entry in manifest["files"]:
        key = entry.get("item")
        if entry["kind"] not in KINDS or key not in ITEMS:
            refreshed.append(entry)
            continue
        item = ITEMS[key]
        try:
            body = (REPO_ROOT / entry["path"]).read_bytes()
            if sha256_bytes(body) != entry["sha256"]:
                raise AcquisitionError(f"{key}: {entry['path']} no longer matches the SHA-256 in the manifest")
            facts = validate(key, body, entry["retrieval_date"])
        except (AcquisitionError, OSError) as exc:
            errors.append(str(exc))
            continue
        new = dict(entry, publisher=item["publisher"], title=item["title"], **facts)
        new["terms"] = terms_for(key)
        new["limitations"] = item["limitations"]
        checked += 1
        changed += new != entry
        refreshed.append(new)
        print(f"{key}: {entry['path']}: hash ok, {len(facts['verified_phrases'])} of {len(facts['verified_phrases'])} "
              f"sentences found{'  (manifest record refreshed)' if new != entry else ''}")
    if errors:
        print("RE-VERIFICATION FAILED - the manifest was not changed.", file=sys.stderr)
        for message in errors:
            print(f"  - {message}", file=sys.stderr)
        return 2
    if changed:
        manifest["files"] = refreshed
        write_bytes_atomic(RAW_MANIFEST, dump_json(manifest), overwrite=True)
    print(f"re-verified {checked} page(s) without any network request; manifest "
          f"{'updated (' + str(changed) + ' record(s))' if changed else 'unchanged'}: {rel(RAW_MANIFEST)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--item", action="append", choices=sorted(ITEMS),
                        help="default: every item that may be fetched automatically")
    parser.add_argument("--from-file", metavar="PATH",
                        help="register a page saved by hand from a web browser (exactly one --item)")
    parser.add_argument("--retrieved-at", metavar="UTC_ISO",
                        help="with --from-file: when the page was retrieved, e.g. 2026-11-14T22:34:58Z")
    parser.add_argument("--http-status", type=int, help="with --from-file: HTTP status observed, if known")
    parser.add_argument("--method", help="with --from-file: how the page was obtained (free text)")
    parser.add_argument("--reverify", action="store_true",
                        help="no network: re-check the registered pages against the current configuration")
    parser.add_argument("--amend-method", action="store_true",
                        help="with --from-file and --method, for a file that is already registered with the same "
                             "SHA-256: correct the free-text retrieval_method of its manifest record, nothing else")
    args = parser.parse_args()

    items = args.item or [key for key, item in ITEMS.items() if item["automated_download"]]
    if len(set(items)) != len(items):
        parser.error("duplicate --item")
    if args.reverify and (args.item or args.from_file):
        parser.error("--reverify takes no other option")
    if args.from_file and len(items) != 1:
        parser.error("--from-file needs exactly one --item")
    if args.from_file and not args.retrieved_at:
        parser.error("--from-file needs --retrieved-at (UTC time of the retrieval)")
    if (args.retrieved_at or args.http_status or args.method) and not args.from_file:
        parser.error("--retrieved-at/--http-status/--method only apply to --from-file")
    if args.amend_method and not (args.from_file and args.method):
        parser.error("--amend-method needs --from-file and --method")

    try:
        self_check()
    except AcquisitionError as exc:
        print(f"ACQUISITION FAILED - nothing was requested or written.\n  - {exc}", file=sys.stderr)
        return 2
    if args.reverify:
        if not RAW_MANIFEST.exists():
            print("RE-VERIFICATION FAILED - no manifest.", file=sys.stderr)
            return 2
        return reverify(load_json(RAW_MANIFEST))
    if not args.from_file:
        blocked = [key for key in items if not ITEMS[key]["automated_download"]]
        if blocked:
            print("ACQUISITION FAILED - nothing was requested or written.", file=sys.stderr)
            print(f"  - automated download is disabled for: {', '.join(blocked)}\n{BLACKROCK_NOTICE}", file=sys.stderr)
            return 2

    manifest = load_json(RAW_MANIFEST) if RAW_MANIFEST.exists() else {
        "schema_version": SCHEMA_VERSION,
        "note": ("One record per raw file retrieved by data/scripts/acquire_*.py. Raw files live under data/raw/ "
                 "(git-ignored) and are never modified after retrieval; this manifest is the committed record "
                 "of their URL, retrieval time, size and SHA-256."),
        "files": [],
    }
    by_id = {entry["source_id"]: entry for entry in manifest["files"]}
    today = utc_now().date().isoformat()

    staged, kept, errors = [], [], []
    requests_made = 0
    for key in items:
        item = ITEMS[key]
        try:
            if args.from_file:
                body = Path(args.from_file).expanduser().read_bytes()
                try:
                    moment = dt.datetime.fromisoformat(args.retrieved_at.replace("Z", "+00:00"))
                except ValueError:
                    raise AcquisitionError(f"--retrieved-at is not an ISO timestamp: {args.retrieved_at!r}") from None
                if moment.tzinfo is None:
                    raise AcquisitionError("--retrieved-at must carry a timezone (use a trailing Z for UTC)")
                if moment > utc_now() + dt.timedelta(minutes=5):
                    raise AcquisitionError("--retrieved-at is in the future")
                meta = {"http_status": args.http_status, "url_final": None, "content_type": None,
                        "http_last_modified": None, "http_date": None,
                        "retrieval_method": args.method or "page saved from a web browser, registered with --from-file"}
            else:
                previous = by_id.get(f"{item['source_id_prefix']}_{today}")
                if previous is not None:
                    path = REPO_ROOT / previous["path"]
                    if path.exists() and sha256_file(path) == previous["sha256"]:
                        kept.append((key, previous))
                        continue
                if requests_made:
                    time.sleep(1.0)
                requests_made += 1
                response = fetch(item["url"])
                body = response.pop("body")
                moment = utc_now()
                meta = dict(response, retrieval_method=f"HTTP GET by acquire_evidence.py (User-Agent: {USER_AGENT})")
            retrieval_date = moment.astimezone(dt.timezone.utc).date().isoformat()
            facts = validate(key, body, retrieval_date)
            target = RAW_DIR / item["raw_subdir"] / f"{key}_{retrieval_date}.html"
            digest = sha256_bytes(body)
            already = target.exists()
            if already and sha256_file(target) != digest:
                raise AcquisitionError(
                    f"{key}: {rel(target)} already exists with different content. Raw files are never "
                    "modified; a second, different snapshot on the same UTC date is refused.")
            record = {
                "source_id": f"{item['source_id_prefix']}_{retrieval_date}",
                "kind": item["kind"],
                "item": key,
                "publisher": item["publisher"],
                "title": item["title"],
                "path": rel(target),
                "url_requested": item["url"],
                "url_final": meta["url_final"],
                "http_status": meta["http_status"],
                "content_type": meta["content_type"],
                "http_last_modified": meta["http_last_modified"],
                "http_date": meta["http_date"],
                "retrieval_method": meta["retrieval_method"],
                "retrieved_at_utc": iso_z(moment),
                "retrieval_date": retrieval_date,
                "bytes": len(body),
                "sha256": digest,
            }
            record.update(facts)
            record["terms"] = terms_for(key)
            record["limitations"] = item["limitations"]
            staged.append((key, target, body, record, already))
        except (AcquisitionError, OSError) as exc:
            errors.append(str(exc))

    if errors:
        print("ACQUISITION FAILED - nothing was written.", file=sys.stderr)
        for message in errors:
            print(f"  - {message}", file=sys.stderr)
        return 2

    for key, previous in kept:
        print(f"{key}: kept (already retrieved on this UTC date, not requested again): {previous['path']}")
        print(f"    source_id={previous['source_id']}  sha256={previous['sha256']}")
    for key, target, body, record, already in staged:
        if not already:
            write_bytes_atomic(target, body, overwrite=False)
            os.chmod(target, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        previous = by_id.get(record["source_id"])
        if previous and previous["sha256"] == record["sha256"] and args.amend_method:
            previous["retrieval_method"] = record["retrieval_method"]
            state = "retrieval_method amended (same file, same hash; every other field kept as first recorded)"
        elif previous and previous["sha256"] == record["sha256"]:
            state = "unchanged (already in the manifest; manifest record kept as first recorded)"
        else:
            by_id[record["source_id"]] = record
            state = "registered" if already else "written"
        print(f"{key}: {state}: {record['path']}")
        print(f"    source_id={record['source_id']}  kind={record['kind']}  http_status={record['http_status']}  "
              f"bytes={record['bytes']}")
        print(f"    sha256={record['sha256']}")
        print(f"    retrieved_at_utc={record['retrieved_at_utc']}  document date printed on page="
              f"{record['document_date']}  page last updated={record['page_last_updated']}")
        print(f"    sentences verified in the page: {len(record['verified_phrases'])} of {len(record['verified_phrases'])}")
    manifest["files"] = sorted(by_id.values(), key=lambda entry: (entry["kind"], entry["source_id"]))
    if staged:
        write_bytes_atomic(RAW_MANIFEST, dump_json(manifest), overwrite=True)
    print(f"manifest {'updated' if staged else 'unchanged'}: {rel(RAW_MANIFEST)} ({len(manifest['files'])} record(s)); "
          f"network requests made: {requests_made}")

    registered = {entry["item"] for entry in manifest["files"]}
    if "BLACKROCK_CA_TERMS" not in registered:
        print("\nNOTE: the BlackRock Canada terms page is not registered yet.\n" + BLACKROCK_NOTICE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
