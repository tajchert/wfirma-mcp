from urllib.parse import parse_qs

import httpx
import pytest
from test_parsing import TABLE

from wfirma_mcp.client import Settings, WFirmaClient, WFirmaError

LOGIN = """<form action="/logowanie" method="post">
<input name="data[User][login]"><input type="password" name="data[User][password]">
<input type="hidden" name="data[Invoice][id]" value="">
<input type="hidden" name="data[User][lock]" value="abc&amp;123"></form>"""
DASHBOARD = """<body data-token="dashboard-secret" data-company-context="company-demo">
<script type="text/json" data-fn="dashboardsIndex">{"companyId":"company-demo"}</script></body>"""
PAGE = f'<body data-token="page-secret" data-company-context="company-demo">{TABLE}</body>'


def scenario(final=None):
    seen = []

    def handler(request):
        seen.append(request)
        path = request.url.path
        if path == "/logowanie" and request.method == "GET":
            return httpx.Response(
                200, text=LOGIN, headers={"set-cookie": "session=demo; Path=/; Secure"}
            )
        if path == "/logowanie":
            fields = parse_qs(request.content.decode(), keep_blank_values=True)
            assert fields["data[User][login]"] == ["demo@example.invalid"]
            assert fields["data[User][password]"] == ["test-secret"]
            assert fields["data[User][lock]"] == ["abc&123"]
            assert fields["data[Invoice][id]"] == [""]
            assert request.headers["cookie"] == "session=demo"
            return httpx.Response(302, headers={"location": "/start?cookieCheck=login"})
        if path == "/start":
            assert request.method == "GET"
            return httpx.Response(200, text=DASHBOARD)
        if path == "/invoices/index/all":
            return httpx.Response(200, text=PAGE)
        return final(request) if final else httpx.Response(200, text=TABLE)

    return handler, seen


def client(handler, company="company-demo"):
    return WFirmaClient(
        Settings("demo@example.invalid", "test-secret", company),
        transport=httpx.MockTransport(handler),
    )


async def test_login_cookies_current_token_and_exact_month_form():
    handler, seen = scenario()
    async with client(handler) as api:
        result = await api.list_invoices(year=2031, month=7)
    request = seen[-1]
    assert request.url.path == "/invoices/indexTable/all/0/0/0/0/0/null/0/0"
    assert request.headers["x-wf-token"] == "page-secret"
    assert request.headers["referer"] == "https://wfirma.pl/invoices/index/all"
    assert parse_qs(request.content.decode()) == {
        "filters[year]": ["2031"],
        "filters[month]": ["7"],
        "filters[dateFrom]": ["0"],
        "filters[dateTo]": ["0"],
        "filters[dateRange]": ["0"],
        "setColumns": ["true"],
    }
    assert result["company_id"] == "company-demo"
    assert "secret" not in str(result)


async def test_range_form_excludes_stale_year_and_month():
    response = TABLE.replace(
        "<table>",
        """<div class="tab-range is-range-on">
    <input id="dateFrom" value="2031-07-03"><input id="dateTo" value="2031-09-29"></div><table>""",
    )
    handler, seen = scenario(lambda request: httpx.Response(200, text=response))
    async with client(handler) as api:
        await api.list_invoices(date_from="2031-07-03", date_to="2031-09-29")
    assert parse_qs(seen[-1].content.decode()) == {
        "filters[dateFrom]": ["2031-07-03"],
        "filters[dateTo]": ["2031-09-29"],
        "filters[dateRange]": ["1"],
        "setColumns": ["true"],
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"month": 7},
        {"year": 2031},
        {"year": 2031, "month": 13},
        {"date_from": "2031-09-29"},
        {"date_from": "2031-09-29", "date_to": "2031-07-01"},
        {"date_from": "2031-02-30", "date_to": "2031-07-01"},
        {"year": 2031, "month": 7, "date_from": "2031-07-01", "date_to": "2031-07-02"},
    ],
)
async def test_invalid_periods_fail_before_network(kwargs):
    handler, seen = scenario()
    async with client(handler) as api:
        with pytest.raises(WFirmaError):
            await api.list_invoices(**kwargs)
    assert seen == []


async def test_company_mismatch_prevents_accounting_read():
    handler, seen = scenario()
    async with client(handler, company="different") as api:
        with pytest.raises(WFirmaError, match="company"):
            await api.list_invoices()
    assert seen[-1].url.path == "/start"


async def test_foreign_redirect_does_not_receive_credentials():
    seen = []

    def handler(request):
        seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, text=LOGIN)
        return httpx.Response(307, headers={"location": "https://example.invalid/steal"})

    async with client(handler) as api:
        with pytest.raises(WFirmaError):
            await api.status()
    assert len(seen) == 2
    assert all(request.url.host == "wfirma.pl" for request in seen)


async def test_foreign_form_action_rejected_before_password_sent():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200, text=LOGIN.replace('action="/logowanie"', 'action="https://example.invalid"')
        )

    async with client(handler) as api:
        with pytest.raises(WFirmaError):
            await api.status()
    assert len(seen) == 1


async def test_expired_session_is_not_empty_result_or_retried_login():
    handler, seen = scenario(lambda request: httpx.Response(200, text=LOGIN))
    async with client(handler) as api:
        with pytest.raises(WFirmaError, match="session"):
            await api.list_invoices(year=2031, month=7)
    assert sum(r.method == "POST" and r.url.path == "/logowanie" for r in seen) == 1


async def test_ignored_period_filter_is_not_reported_as_requested_period():
    handler, _ = scenario()
    async with client(handler) as api:
        with pytest.raises(WFirmaError, match="period"):
            await api.list_invoices(year=2031, month=8)


@pytest.mark.parametrize("identifier", ["../delete", "abc?delete=1", "a/b", "https://other", ""])
async def test_detail_ids_cannot_change_route(identifier):
    handler, seen = scenario()
    async with client(handler) as api:
        with pytest.raises(WFirmaError):
            await api.invoice_detail(identifier)
    assert seen == []


async def test_http_error_does_not_leak_response_or_credentials():
    handler, seen = scenario(lambda request: httpx.Response(500, text="private-secret-response"))
    async with client(handler) as api:
        with pytest.raises(WFirmaError) as error:
            await api.list_invoices(year=2031, month=7)
    assert "private-secret" not in str(error.value)
    assert len(seen) == 5
