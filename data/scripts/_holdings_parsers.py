"""Parsers for issuer-published ETF holdings files (standard library only).

Downloaded files are untrusted input. These parsers:

* never extract an archive to disk (the .xlsx is read in memory),
* refuse XML that declares a DTD or entities,
* bound the size of every archive member they read,
* raise ``HoldingsFormatError`` on anything they do not recognise instead of
  guessing: an unknown line type or a changed layout stops the build.

Weights are kept as ``decimal.Decimal`` in the unit printed by the issuer
(percent). Conversion to fractions happens in ``build_processed.py``.
"""
from __future__ import annotations

import csv
import html
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

MAX_MEMBER_BYTES = 30_000_000
_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

_MONTHS = {name: idx + 1 for idx, name in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}

# Line kinds used downstream.
EQUITY, CASH, DERIVATIVE, OTHER = "equity", "cash", "derivative", "other"

# An exchange ticker as printed by the two issuers: letters/digits with an
# optional class or unit suffix (BRK.B, BF.B, RCI.B, BIP.UN, GIB.A).
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9]{0,5}(\.[A-Z]{1,2})?$")
# Placeholder identifiers the issuers print for unlisted lines such as
# contingent value rights or rights/warrants (e.g. 2602335D, 2299955D).
_PLACEHOLDER_RE = re.compile(r"^[0-9]{5,}[A-Z]?$")


class HoldingsFormatError(ValueError):
    """The file does not look like the layout this parser was written for."""


# --------------------------------------------------------------------- dates
def parse_printed_date(text: str) -> str:
    """'12-Nov-2026', 'Nov 12, 2026' or 'Nov 12 2026' -> '2026-11-12' (locale independent)."""
    cleaned = text.strip()
    match = re.fullmatch(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})", cleaned)
    if match:
        day, mon, year = match.group(1), match.group(2), match.group(3)
    else:
        match = re.fullmatch(r"([A-Za-z]{3})[a-z]*\.? (\d{1,2}),? (\d{4})", cleaned)
        if not match:
            raise HoldingsFormatError(f"unrecognised date text: {text!r}")
        mon, day, year = match.group(1), match.group(2), match.group(3)
    month = _MONTHS.get(mon.lower())
    if month is None:
        raise HoldingsFormatError(f"unrecognised month in date text: {text!r}")
    import datetime as _dt
    return _dt.date(int(year), month, int(day)).isoformat()


def _decimal(text, what: str) -> Decimal:
    try:
        value = Decimal(str(text).replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        raise HoldingsFormatError(f"{what}: not a number: {text!r}") from None
    if not value.is_finite():
        raise HoldingsFormatError(f"{what}: not finite: {text!r}")
    return value


# ---------------------------------------------------------------------- xlsx
def _safe_xml(payload: bytes, member: str) -> ET.Element:
    if b"<!DOCTYPE" in payload or b"<!ENTITY" in payload:
        raise HoldingsFormatError(f"{member}: XML with a DTD/entity declaration is refused")
    return ET.fromstring(payload)


def _read_member(archive: zipfile.ZipFile, member: str) -> bytes:
    try:
        info = archive.getinfo(member)
    except KeyError:
        raise HoldingsFormatError(f"xlsx member missing: {member}") from None
    if info.file_size > MAX_MEMBER_BYTES:
        raise HoldingsFormatError(f"xlsx member too large: {member} ({info.file_size} bytes)")
    data = archive.read(member)
    if len(data) > MAX_MEMBER_BYTES:
        raise HoldingsFormatError(f"xlsx member too large after inflation: {member}")
    return data


def _text_of(si: ET.Element) -> str:
    """Concatenate <t> runs of a shared-string item, skipping phonetic runs."""
    parts = []
    for node in si.iter():
        if node.tag == f"{{{_MAIN_NS}}}rPh":
            continue
        if node.tag == f"{{{_MAIN_NS}}}t":
            parts.append(node.text or "")
    return "".join(parts)


def read_xlsx_first_sheet(payload: bytes) -> list[tuple[int, dict[str, str]]]:
    """Return [(row_number, {column_letters: cell_text})] for the first worksheet.

    Numeric cells keep the exact text stored in the file (e.g. '7.904389',
    '3.0E-6') so no precision is lost before Decimal conversion.
    """
    if payload[:4] != b"PK\x03\x04":
        raise HoldingsFormatError("not an .xlsx (zip) file: bad magic bytes")
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise HoldingsFormatError(f"not a readable .xlsx: {exc}") from None
    with archive:
        workbook = _safe_xml(_read_member(archive, "xl/workbook.xml"), "xl/workbook.xml")
        sheets = workbook.findall(f"{{{_MAIN_NS}}}sheets/{{{_MAIN_NS}}}sheet")
        if not sheets:
            raise HoldingsFormatError("workbook has no sheets")
        rel_id = sheets[0].get(f"{{{_REL_NS}}}id")
        rels = _safe_xml(_read_member(archive, "xl/_rels/workbook.xml.rels"), "workbook rels")
        target = None
        for rel_node in rels.findall(f"{{{_PKG_REL_NS}}}Relationship"):
            if rel_node.get("Id") == rel_id:
                target = rel_node.get("Target")
        if not target:
            raise HoldingsFormatError("cannot resolve the first worksheet")
        member = target.lstrip("/") if target.startswith("/") else "xl/" + target
        if ".." in member.split("/"):
            raise HoldingsFormatError(f"suspicious worksheet path: {target!r}")

        strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = _safe_xml(_read_member(archive, "xl/sharedStrings.xml"), "sharedStrings")
            strings = [_text_of(si) for si in shared.findall(f"{{{_MAIN_NS}}}si")]

        sheet = _safe_xml(_read_member(archive, member), member)
    data = sheet.find(f"{{{_MAIN_NS}}}sheetData")
    if data is None:
        raise HoldingsFormatError("worksheet has no sheetData")
    rows: list[tuple[int, dict[str, str]]] = []
    for row in data.findall(f"{{{_MAIN_NS}}}row"):
        cells: dict[str, str] = {}
        for cell in row.findall(f"{{{_MAIN_NS}}}c"):
            ref = cell.get("r") or ""
            col = re.match(r"[A-Z]+", ref)
            if not col:
                raise HoldingsFormatError(f"cell without a reference in row {row.get('r')}")
            kind = cell.get("t")
            value_node = cell.find(f"{{{_MAIN_NS}}}v")
            if kind == "inlineStr":
                inline = cell.find(f"{{{_MAIN_NS}}}is")
                text = _text_of(inline) if inline is not None else None
            elif value_node is None or value_node.text is None:
                text = None
            elif kind == "s":
                text = strings[int(value_node.text)]
            else:
                text = value_node.text
            if text is not None:
                cells[col.group(0)] = text
        rows.append((int(row.get("r")), cells))
    return rows


# ------------------------------------------------------- State Street (SSGA)
SSGA_COLUMNS = ["Name", "Ticker", "Identifier", "SEDOL", "Weight", "Sector", "Shares Held", "Local Currency"]


def _classify_ssga_line(name: str, ticker: str, identifier: str, sedol: str) -> str:
    if ticker == "-" and sedol == "-" and "DOLLAR" in name.upper():
        return CASH
    if sedol == "-" and _PLACEHOLDER_RE.match(ticker):
        # Unlisted placeholder line (e.g. a contingent value right): not an index constituent.
        return OTHER
    if sedol != "-" and _TICKER_RE.match(ticker):
        return EQUITY
    raise HoldingsFormatError(
        f"SSGA line not recognised (name={name!r}, ticker={ticker!r}, identifier={identifier!r}, sedol={sedol!r})")


def parse_ssga_daily_holdings(payload: bytes, expected_ticker: str) -> dict:
    """Parse State Street's 'holdings-daily-us-en-<fund>.xlsx'."""
    rows = read_xlsx_first_sheet(payload)
    by_number = dict(rows)
    meta = {(cells.get("A") or "").strip(): (cells.get("B") or "").strip()
            for number, cells in rows if number <= 4 and cells.get("A")}
    for label in ("Fund Name:", "Ticker Symbol:", "Holdings:"):
        if label not in meta:
            raise HoldingsFormatError(f"SSGA header line {label!r} not found (have {sorted(meta)})")
    if meta["Ticker Symbol:"] != expected_ticker:
        raise HoldingsFormatError(f"file is for {meta['Ticker Symbol:']!r}, expected {expected_ticker!r}")
    date_text = meta["Holdings:"]
    match = re.fullmatch(r"As of (\S+)", date_text)
    if not match:
        raise HoldingsFormatError(f"unrecognised 'Holdings:' text: {date_text!r}")
    holdings_date = parse_printed_date(match.group(1))

    header_row = None
    for number, cells in rows:
        if [cells.get(col) for col in "ABCDEFGH"] == SSGA_COLUMNS:
            header_row = number
            break
    if header_row is None:
        raise HoldingsFormatError(f"SSGA column header row {SSGA_COLUMNS} not found")

    lines = []
    footers = []
    in_table = True
    for number, cells in rows:
        if number <= header_row:
            continue
        has_weight = cells.get("E") is not None
        if in_table and cells.get("A") and has_weight:
            name = cells["A"].strip()
            ticker = (cells.get("B") or "").strip()
            identifier = (cells.get("C") or "").strip()
            sedol = (cells.get("D") or "").strip()
            sector_raw = (cells.get("F") or "").strip()
            currency = (cells.get("H") or "").strip()
            lines.append({
                "kind": _classify_ssga_line(name, ticker, identifier, sedol),
                "ticker": ticker,
                "name": name,
                "weight_percent": _decimal(cells["E"], f"SSGA row {number} weight"),
                "sector_raw": sector_raw,
                "asset_class_raw": None,
                "currency": currency,
                "exchange": None,
                "identifier": identifier,
                "sedol": sedol,
                "market_value": None,
                "source_row": number,
            })
            continue
        in_table = False
        if has_weight:
            raise HoldingsFormatError(f"SSGA row {number}: weight found after the end of the holdings table")
        if cells.get("A"):
            footers.append(cells["A"].strip())
    if not lines:
        raise HoldingsFormatError("SSGA file has no holdings rows")
    return {
        "issuer_format": "ssga_daily_holdings_xlsx",
        "fund_id": expected_ticker,
        "fund_name_in_file": meta["Fund Name:"],
        "holdings_date": holdings_date,
        "holdings_date_text": date_text,
        "publication_date": None,  # not printed in the file
        "weight_unit": "percent",
        "columns": SSGA_COLUMNS,
        "lines": lines,
        "footers": footers,
    }


# ------------------------------------------------------ BlackRock (iShares)
ISHARES_COLUMNS = ["Ticker", "Name", "Sector", "Asset Class", "Market Value", "Weight (%)", "Notional Value",
                   "Shares", "Price", "Location", "Exchange", "Currency", "FX Rate", "Market Currency"]
_ISHARES_KIND = {
    "Equity": EQUITY,
    "Cash": CASH,
    "Cash Collateral and Margins": CASH,
    "Money Market": CASH,
    "Futures": DERIVATIVE,
    "FX": DERIVATIVE,
}


def parse_ishares_holdings_csv(payload: bytes, expected_ticker: str) -> dict:
    """Parse the iShares (BlackRock Canada) '<FUND>_holdings.csv' download."""
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HoldingsFormatError(f"iShares CSV is not UTF-8: {exc}") from None
    if "<html" in text[:2000].lower():
        raise HoldingsFormatError("iShares download is an HTML page, not a CSV")
    records = list(csv.reader(io.StringIO(text)))
    if not records or len(records[0]) < 2 or records[0][0].strip() != "Fund Holdings as of":
        raise HoldingsFormatError(f"iShares first line not recognised: {records[:1]!r}")
    date_text = records[0][1].strip()
    holdings_date = parse_printed_date(date_text)

    header_idx = next((i for i, rec in enumerate(records) if [c.strip() for c in rec] == ISHARES_COLUMNS), None)
    if header_idx is None:
        raise HoldingsFormatError(f"iShares column header {ISHARES_COLUMNS} not found")

    lines = []
    footers = []
    in_table = True
    for offset, rec in enumerate(records[header_idx + 1:], start=header_idx + 2):
        stripped = [c.replace(" ", " ").strip() for c in rec]
        if in_table and len(stripped) == len(ISHARES_COLUMNS):
            row = dict(zip(ISHARES_COLUMNS, stripped))
            asset_class = row["Asset Class"]
            if asset_class not in _ISHARES_KIND:
                raise HoldingsFormatError(f"iShares line {offset}: unknown Asset Class {asset_class!r} ({row['Name']!r})")
            kind = _ISHARES_KIND[asset_class]
            ticker = row["Ticker"]
            if kind == EQUITY:
                if _PLACEHOLDER_RE.match(ticker):
                    kind = OTHER  # unlisted placeholder line (rights/warrants), reported separately
                elif not _TICKER_RE.match(ticker):
                    raise HoldingsFormatError(f"iShares line {offset}: unexpected equity ticker {ticker!r}")
            lines.append({
                "kind": kind,
                "ticker": ticker,
                "name": row["Name"],
                "weight_percent": _decimal(row["Weight (%)"], f"iShares line {offset} weight"),
                "sector_raw": row["Sector"],
                "asset_class_raw": asset_class,
                "currency": row["Market Currency"],
                "exchange": row["Exchange"],
                "identifier": None,
                "sedol": None,
                "market_value": _decimal(row["Market Value"], f"iShares line {offset} market value"),
                "source_row": offset,
            })
            continue
        in_table = False
        if any(stripped):
            if len(stripped) == len(ISHARES_COLUMNS):
                raise HoldingsFormatError(f"iShares line {offset}: holdings row after the end of the table")
            footers.append(" ".join(c for c in stripped if c))
    if not lines:
        raise HoldingsFormatError("iShares file has no holdings rows")
    return {
        "issuer_format": "ishares_ca_holdings_csv",
        "fund_id": expected_ticker,
        "fund_name_in_file": None,  # the CSV does not print the fund name
        "holdings_date": holdings_date,
        "holdings_date_text": date_text,
        "publication_date": None,  # not printed in the file
        "weight_unit": "percent",
        "columns": ISHARES_COLUMNS,
        "lines": lines,
        "footers": footers,
    }


# --------------------------- State Street product page: fund sector breakdown
def parse_ssga_fund_sector_breakdown(payload: bytes) -> dict:
    """Extract the 'Fund Sector Breakdown' table embedded in an SSGA ETF product page.

    These are fund-level totals published by the issuer. They say nothing
    about which constituent belongs to which sector.
    """
    text = payload.decode("utf-8", errors="replace")
    match = re.search(r'<input[^>]*\bid="fund-sector-breakdown"[^>]*\bvalue="([^"]*)"', text)
    if not match:
        raise HoldingsFormatError("fund-sector-breakdown block not found in the product page")
    try:
        block = json.loads(html.unescape(match.group(1)))
        label = block["label"]
        as_of_text = block["asOfDateSimple"]
        entries = [(item["name"]["value"], item["weight"]["originalValue"]) for item in block["attrArray"]]
    except (KeyError, TypeError, ValueError) as exc:
        raise HoldingsFormatError(f"fund-sector-breakdown block not understood: {exc!r}") from None
    if label != "Fund Sector Breakdown" or not entries:
        raise HoldingsFormatError(f"unexpected sector block label {label!r} or empty block")
    title = re.search(r"<title>([^<]*)</title>", text)
    return {
        "issuer_format": "ssga_product_page_html",
        "page_title": html.unescape(title.group(1)).strip() if title else None,
        "as_of_date": parse_printed_date(as_of_text),
        "as_of_text": block.get("asOfDate", as_of_text),
        "weight_unit": "percent",
        "sectors": [{"sector": name.strip(), "weight_percent": _decimal(weight, f"sector {name!r} weight")}
                    for name, weight in entries],
    }


def summarize(parsed: dict) -> dict:
    """Totals in percent by line kind, used for validation and reporting."""
    totals: dict[str, Decimal] = {}
    counts: dict[str, int] = {}
    for line in parsed["lines"]:
        totals[line["kind"]] = totals.get(line["kind"], Decimal(0)) + line["weight_percent"]
        counts[line["kind"]] = counts.get(line["kind"], 0) + 1
    return {"total_percent": sum(totals.values(), Decimal(0)), "percent_by_kind": totals, "count_by_kind": counts}
