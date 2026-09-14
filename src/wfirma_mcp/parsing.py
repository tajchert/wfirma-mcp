"""Parse documented HTML structures without executing application scripts."""

import json
import re
from decimal import Decimal, InvalidOperation
from xml.etree.ElementTree import ParseError as XMLParseError

from bs4 import BeautifulSoup, Tag
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException


class ParseError(ValueError):
    """The response no longer matches the documented interface."""


def soup(source: str) -> BeautifulSoup:
    return BeautifulSoup(source, "html.parser")


def display(node: Tag) -> str:
    return " ".join(node.stripped_strings)


def decimal_text(value: str) -> str | None:
    compact = re.sub(r"\s", "", value).replace("−", "-")
    compact = re.sub(r"(?:PLN|EUR|USD|zł)$", "", compact).replace(",", ".")
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", compact):
        return None
    try:
        return format(Decimal(compact), "f")
    except InvalidOperation:
        return None


def _cell(node: Tag, field: str) -> dict:
    text = display(node)
    raw = node.get("data-value")
    value = decimal_text(raw) if raw is not None else None
    # Only known monetary fields get locale normalization. Identifiers stay text.
    suffix = field.rsplit(".", 1)[-1]
    if raw is None and (
        suffix
        in {"netto", "tax", "vat", "brutto", "total", "total_composed", "alreadypaid", "remaining"}
        or suffix.startswith("rate")
    ):
        value = decimal_text(text)
    links = list(
        dict.fromkeys(
            a["href"]
            for a in node.select("a[href]")
            if re.fullmatch(
                r"/(?:invoices|contractors|declaration_headers|expense_drafts)/view/[A-Za-z0-9_-]+",
                a["href"],
            )
        )
    )
    result = {"text": text, "value": value, "links": links}
    if node.select_one(".declaration-header-zusdra-details"):
        result["lines"] = node.get_text("\n", strip=True).splitlines()
        result["value"] = None
    components = {}
    for match in re.finditer(
        r"(Społeczne|Zdrowotne|FP i FGŚP|Razem)\s*:?\s*([−+-]?\d[\d\s]*,\d+)", text
    ):
        components[match[1]] = decimal_text(match[2])
    if components:
        result["components"] = components
        result["value"] = None
    return result


def table_rows(table: Tag, *, records_only: bool, columns=None) -> list[dict]:
    columns = dict(columns or {})
    for header in table.select("[data-colname][data-column]"):
        if header.find_parent("tr") and header.find_parent("tr").find_parent("thead"):
            columns[header["data-column"]] = header["data-colname"]
    rows = []
    selector = "tr.tab-data[data-row-id]" if records_only else "tr"
    for row in table.select(selector):
        # Keep independent nested tables and responsive copies out of the current table.
        if row.find_parent("table") is not table:
            continue
        if set(row.get("class", [])) & {"tab-sum", "child"}:
            continue
        cells = {}
        for index, cell in enumerate(row.find_all(["td", "th"], recursive=False)):
            if (
                not cell.has_attr("data-column")
                and not cell.has_attr("data-colname")
                and records_only
            ):
                continue
            field = (
                cell.get("data-colname")
                or columns.get(cell.get("data-column"))
                or cell.get("data-column")
                or str(index)
            )
            cells[field] = _cell(cell, field)
        if cells:
            labels = cells.get("DeclarationHeader.zusdra", {}).get("lines", [])
            if labels:
                for name in ("alreadypaid", "remaining", "total"):
                    amount = cells.get(f"DeclarationHeader.{name}", {})
                    lines = amount.get("lines", [])
                    if len(labels) == len(lines):
                        amount["components"] = {
                            label: decimal_text(value) for label, value in zip(labels, lines)
                        }
                        amount["value"] = None
            rows.append(
                {"id": row.get("data-row-id"), "type": row.get("data-row-type"), "cells": cells}
            )
    return rows


def parse_table(source: str, model: str) -> dict:
    doc = soup(source)
    wrappers = doc.select(f'.table-wrapper[data-model="{model}"]')
    if len(wrappers) != 1:
        raise ParseError("Expected one documented table wrapper; the interface may have changed.")
    wrapper = wrappers[0]
    params = wrapper.select_one("#tab-params[data-params]")
    try:
        meta = json.loads(params["data-params"]) if params else None
        if not isinstance(meta, dict) or any(
            type(meta.get(key)) is not int or meta[key] < minimum
            for key, minimum in {"page": 1, "show": 1, "total": 0, "pages": 0}.items()
        ):
            raise ValueError
    except (ValueError, TypeError, KeyError):
        raise ParseError("Missing or invalid pagination metadata.") from None
    columns = {
        h["data-column"]: h["data-colname"]
        for h in wrapper.select("thead [data-colname][data-column]")
        if h.find_parent(class_="table-wrapper") is wrapper
    }
    rows = []
    for table in wrapper.find_all("table"):
        if table.find_parent(class_="table-wrapper") is wrapper:
            rows.extend(table_rows(table, records_only=True, columns=columns))
    if (meta["total"] > 0 and not rows) or len(rows) > meta["total"]:
        raise ParseError(
            "Parsed records contradict the table metadata; row markup may have changed."
        )
    filters = {}
    for control in wrapper.select("select[id], input[id]"):
        key = control["id"]
        if key not in {
            "year",
            "month",
            "quarter",
            "dateFrom",
            "dateTo",
            "dateRange",
            "email",
            "type",
            "paymentstate",
            "deliverystate",
            "ksef",
            "accepted",
            "source",
        }:
            continue
        if control.name == "select":
            options = control.select("option[selected]")
            if control.has_attr("multiple"):
                filters[key] = [option.get("value", "") for option in options]
            else:
                options = options or control.select("option")[:1]
                filters[key] = options[0].get("value", "") if options else ""
        else:
            filters[key] = control.get("value", "")
    active_range = wrapper.select_one(".tab-range.is-range-on")
    if active_range:
        start = active_range.select_one('[id="dateFrom"]')
        end = active_range.select_one('[id="dateTo"]')
        period = {
            "mode": "range",
            "date_from": start.get("value") if start else None,
            "date_to": end.get("value") if end else None,
        }
    else:
        period = {
            "mode": "selected",
            **{k: v for k, v in filters.items() if k in {"year", "month", "quarter"}},
        }
    complete = meta["page"] == 1 and meta["pages"] <= 1 and len(rows) == meta["total"]
    warnings = (
        []
        if complete
        else ["Only the returned page is available; pagination beyond this page is not validated."]
    )
    if meta.get("insertIdFilterConflict") or meta.get("insertIdSearchConflict"):
        warnings.append("wFirma reports a filter/search conflict.")
    return {
        "model": model,
        "table_url": wrapper.get("data-url"),
        "rows": rows,
        "pagination": {k: meta[k] for k in ("page", "show", "total", "pages")},
        "returned_count": len(rows),
        "complete": complete,
        "period": period,
        "filters": filters,
        "warnings": warnings,
    }


def parse_contractor(source: str) -> dict:
    basics = soup(source).select_one("#tab-basics")
    if not basics:
        raise ParseError("Missing contractor basics section.")
    fields = {}
    for group in basics.select(".mat-group"):
        label = group.select_one("label.label-bg")
        value = group.select_one(".mat-text.form-control-plaintext")
        if label and value:
            fields[display(label)] = display(value)
    return {"fields": fields}


def _xml_node(node) -> dict:
    return {
        "tag": node.tag,
        "text": (node.text or "").strip(),
        "attributes": dict(node.attrib),
        "children": [_xml_node(child) for child in node],
    }


def parse_detail(source: str) -> dict:
    doc = soup(source)
    root = doc.select_one(".dialogbox") or doc.select_one("fieldset#print-preview")
    if root is None:
        raise ParseError("Missing documented detail dialog.")
    result = {"tables": []}
    preview = doc.select_one("fieldset#print-preview")
    if preview and preview.get_text().strip():
        xml = preview.get_text().strip()
        try:
            element = ElementTree.fromstring(xml)
            result["xml"] = {
                "namespace": element.tag[1:].split("}")[0] if element.tag.startswith("{") else None,
                "document": _xml_node(element),
            }
        except (XMLParseError, DefusedXmlException, RecursionError):
            raise ParseError("Invalid or unsafe XML in declaration preview.") from None
        preview.decompose()
    for unwanted in doc.select("script, style, input, button, noscript"):
        unwanted.decompose()
    for table in root.find_all("table"):
        if table.find_parent("table") is None:
            result["tables"].append({"rows": table_rows(table, records_only=False)})
    result["text"] = display(root) if root.name else ""
    return result
