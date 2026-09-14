"""Serialized, in-memory sessions for the documented wFirma browser reads."""

import asyncio
import json
import re
import time
from datetime import date
from urllib.parse import urljoin, urlsplit

import httpx

from .credentials import Settings, WFirmaError
from .parsing import ParseError, parse_contractor, parse_detail, parse_table, soup

ORIGIN = "https://wfirma.pl"
JPK_TYPES = "jpkewp,jpkfa,jpkmag,jpkpkpir,jpkkr,jpkkrpd,jpkvat,jpkv7m,jpkv7k"


def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise WFirmaError("Invalid record identifier; use an ID from a returned record.")
    return value


def period_fields(year=None, month=None, date_from=None, date_to=None) -> dict:
    if date_from is not None or date_to is not None:
        if year is not None or month is not None or not date_from or not date_to:
            raise WFirmaError("Supply both dates or a year and month, without combining modes.")
        try:
            if not all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) for v in (date_from, date_to)):
                raise ValueError
            if date.fromisoformat(date_from) > date.fromisoformat(date_to):
                raise ValueError
        except (ValueError, TypeError):
            raise WFirmaError("Invalid date range; use ordered ISO dates YYYY-MM-DD.") from None
        return {
            "filters[dateFrom]": date_from,
            "filters[dateTo]": date_to,
            "filters[dateRange]": "1",
            "setColumns": "true",
        }
    if year is None and month is None:
        return {}
    if (
        type(year) is not int
        or not 1900 <= year <= 9999
        or type(month) is not int
        or not 1 <= month <= 12
    ):
        raise WFirmaError("Supply a valid year and a month from 1 to 12.")
    return {
        "filters[year]": str(year),
        "filters[month]": str(month),
        "filters[dateFrom]": "0",
        "filters[dateTo]": "0",
        "filters[dateRange]": "0",
        "setColumns": "true",
    }


class WFirmaClient:
    def __init__(self, settings: Settings, *, transport=None):
        self.settings = settings
        self.http = httpx.AsyncClient(
            transport=transport,
            timeout=30,
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": "wfirma-mcp/0.1"},
        )
        self.lock = asyncio.Lock()
        self.token = None
        self.company_id = None
        self.authenticated = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def close(self):
        await self.http.aclose()
        self.token = None
        self.http.cookies.clear()
        self.authenticated = False

    def _url(self, path: str) -> str:
        url = urljoin(ORIGIN, path)
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "wfirma.pl"
            or parsed.username
            or parsed.password
            or parsed.fragment
            or "\\" in path
        ):
            raise WFirmaError("Blocked a destination outside the wFirma origin.")
        return url

    async def _request(self, method, path, *, data=None, ajax=False, referer=None):
        url = self._url(path)
        headers = {}
        if ajax:
            if not self.token:
                raise WFirmaError("Missing authenticated session token.")
            headers.update(
                {
                    "X-Wf-Token": self.token,
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "text/html, */*; q=0.01",
                }
            )
        if referer:
            headers["Referer"] = self._url(referer)
        if method == "POST":
            headers["Origin"] = ORIGIN
        for _ in range(6):
            try:
                response = await self.http.request(method, url, data=data, headers=headers)
            except httpx.HTTPError:
                raise WFirmaError(
                    "wFirma network request failed; no automatic retry was attempted."
                ) from None
            if response.is_redirect:
                next_url = self._url(urljoin(url, response.headers.get("location", "")))
                if self.authenticated and urlsplit(next_url).path == "/logowanie":
                    self.authenticated = False
                    self.token = None
                    raise WFirmaError(
                        "wFirma session expired. Call session_status to log in again."
                    )
                if response.status_code not in {301, 302, 303} or urlsplit(next_url).path not in {
                    "/start",
                    "/logowanie",
                }:
                    raise WFirmaError(
                        "Unexpected redirect; request stopped without replaying credentials."
                    )
                method, data, url = "GET", None, next_url
                continue
            if response.status_code >= 400:
                if response.status_code in {401, 403}:
                    self.authenticated = False
                    self.token = None
                raise WFirmaError(
                    f"wFirma returned HTTP {response.status_code}; no automatic retry was attempted."
                )
            return response.text
        raise WFirmaError("Too many wFirma redirects.")

    def _context(self, source: str, *, full=False, dashboard=False):
        doc = soup(source)
        if doc.select_one('[name="data[User][login]"]'):
            self.authenticated = False
            self.token = None
            raise WFirmaError(
                "wFirma session is unauthenticated or expired; MFA/CAPTCHA may require browser login."
            )
        body = doc.select_one("body[data-token][data-company-context]")
        if full and body is None:
            raise WFirmaError(
                "Missing authenticated company context; the browser interface may have changed."
            )
        if body:
            company = body["data-company-context"]
            expected = self.settings.company_id or self.company_id
            if not company or (expected and company != expected):
                self.authenticated = False
                self.token = None
                raise WFirmaError("Active company does not match the expected company.")
            if dashboard:
                bootstrap = doc.select_one('script[data-fn="dashboardsIndex"]')
                try:
                    parsed = json.loads(bootstrap.get_text()) if bootstrap else {}
                    if str(parsed.get("companyId", "")) != company:
                        raise ValueError
                except (ValueError, TypeError):
                    raise WFirmaError(
                        "Missing or inconsistent dashboard company context."
                    ) from None
            self.company_id = company
        token_node = doc.select_one(".dialogbox[data-token]") or body
        if token_node:
            self.token = token_node["data-token"]

    async def _login(self):
        if self.authenticated:
            return
        if not self.settings.login or not self.settings.password:
            raise WFirmaError(
                "Configure macOS Keychain with --setup-keychain, supply --login/--password, "
                "or set WFIRMA_LOGIN and WFIRMA_PASSWORD in the environment or an explicit --env-file."
            )
        source = await self._request("GET", "/logowanie")
        login = soup(source).select_one('[name="data[User][login]"]')
        form = login.find_parent("form") if login else None
        if form is None or form.get("method", "").lower() != "post":
            raise WFirmaError(
                "Expected password login form was not found; MFA/CAPTCHA is not supported."
            )
        action = self._url(form.get("action", "/logowanie"))
        if action != ORIGIN + "/logowanie":
            raise WFirmaError("Unexpected login form action; credentials were not sent.")
        fields = {
            node["name"]: node.get("value", "")
            for node in form.select('input[type="hidden"][name]')
        }
        fields.update(
            {
                "data[User][login]": self.settings.login,
                "data[User][password]": self.settings.password,
            }
        )
        source = await self._request("POST", action, data=fields, referer="/logowanie")
        self._context(source, full=True, dashboard=True)
        self.authenticated = True

    async def _page(self, path):
        await self._login()
        source = await self._request("GET", path)
        self._context(source, full=True)
        return source

    async def status(self):
        async with self.lock:
            await self._login()
            source = await self._request("GET", "/start?cookieCheck=login")
            self._context(source, full=True, dashboard=True)
            return {
                "authenticated": True,
                "company_id": self.company_id,
                "company_pinned": bool(self.settings.company_id),
                "accounting_access": "read-only",
            }

    def _result(self, result):
        return {"company_id": self.company_id, **result}

    async def _table(self, path, model, fields=None, route_prefix=None):
        source = await self._page(path)
        parsed = parse_table(source, model)
        if fields:
            route = parsed["table_url"]
            if not route or not route_prefix or not route.startswith(route_prefix):
                raise WFirmaError("Unexpected table refresh route.")
            self._url(route)
            if "?" in route or ".." in route or "%" in route:
                raise WFirmaError("Unexpected table refresh route.")
            source = await self._request("POST", route, data=fields, ajax=True, referer=path)
            self._context(source)
            parsed = parse_table(source, model)
            if fields.get("filters[dateRange]") == "1":
                expected = {
                    "mode": "range",
                    "date_from": fields["filters[dateFrom]"],
                    "date_to": fields["filters[dateTo]"],
                }
                valid = parsed["period"] == expected
            else:
                valid = parsed["period"]["mode"] != "range" and all(
                    parsed["filters"].get(key) == fields[f"filters[{key}]"]
                    for key in ("year", "month")
                )
            if not valid:
                raise WFirmaError("Returned period does not match the requested period.")
        parsed["warnings"].append(
            "Completeness applies to this filtered table only, not all accounting activity."
        )
        return self._result(parsed)

    async def list_invoices(self, year=None, month=None, date_from=None, date_to=None):
        fields = period_fields(year, month, date_from, date_to)
        async with self.lock:
            return await self._table(
                "/invoices/index/all", "Invoice", fields, "/invoices/indexTable/all/"
            )

    async def list_expenses(self, drafts=False):
        async with self.lock:
            return await self._table(
                "/expense_drafts/index" if drafts else "/expenses/index", "Expense"
            )

    async def list_declarations(self, kind="tax"):
        routes = {
            "tax": "/declaration_headers/index/tax",
            "vat": "/declaration_headers/index/vat",
            "jpk": f"/declaration_headers/index/{JPK_TYPES}",
            "zus": "/declaration_headers/zusdra",
        }
        if kind not in routes:
            raise WFirmaError("Unknown declaration type.")
        async with self.lock:
            return await self._table(routes[kind], "DeclarationHeader")

    async def revenue_register(self, year=None, month=None):
        fields = period_fields(year, month)
        if fields:
            fields = {key: fields[key] for key in ("filters[year]", "filters[month]", "setColumns")}
        async with self.lock:
            return await self._table(
                "/lumpregisters/index", "Lumpregister", fields, "/lumpregisters/indexTable"
            )

    async def vat_register(self, kind="sale"):
        if kind not in {"sale", "purchase"}:
            raise WFirmaError("VAT register must be sale or purchase.")
        async with self.lock:
            return await self._table(f"/vatregisters/{kind}", "Vatregister")

    async def _detail(self, kind, record_id, page):
        record_id = identifier(record_id)
        async with self.lock:
            await self._page(page)
            source = await self._request(
                "GET",
                f"/{kind}/view/{record_id}?_={time.time_ns() // 1_000_000}",
                ajax=True,
                referer=page,
            )
            self._context(source)
            parser = parse_contractor if kind == "contractors" else parse_detail
            try:
                return self._result({"id": record_id, **parser(source)})
            except ParseError as error:
                raise WFirmaError(str(error)) from None

    async def invoice_detail(self, invoice_id):
        return await self._detail("invoices", invoice_id, "/invoices/index/all")

    async def contractor_detail(self, contractor_id):
        return await self._detail("contractors", contractor_id, "/invoices/index/all")

    async def declaration_detail(self, declaration_id):
        return await self._detail(
            "declaration_headers", declaration_id, "/declaration_headers/index/tax"
        )
