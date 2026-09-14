# wFirma browser API reference: authentication, invoices, expenses, contractors, and taxes

This reference documents the requests and captured frontend code in
`wfirma_pl_login.har`, `wfirma_pl_przychody_wydatki.har`,
`wfirma_pl_company.har`, and `wfirma_pl_przychody_range.har`. It is intended as a starting point for a wFirma CLI using
the browser application's HTTP interface. It does not describe or establish the
contract of a separate official/public API. Section 16 adds live validation and
tax-accounting reads performed during live validation, with private local response
snapshots rather than a new HAR capture.

**Coverage:** logout, password re-login, dashboard, Przychody invoice lists and
month and date-range filtering, invoice and contractor detail dialogs,
contractor-scoped tables, Wydatki booked-expense and draft views, auxiliary JSON
calls, and MQTT event connections. Live validation additionally covers a fresh
password login, PIT calculations, JPK VAT XML, revenue and VAT registers, ZUS
declaration summaries, and forecast refresh responses. Authentication failures,
accounting-record mutations, and company switching remain untested. Examples
redact credentials and account identifiers.

**Privacy and examples:** Account-specific dates, record counts, financial
observations, and private snapshot names have been removed or replaced with
placeholders or explicitly synthetic examples. Example values are not captured
account data or proof that those particular values were tested. Evidence labels
identify the source of API behavior; they do not identify the source of sample
values. Empty/populated response shapes are retained to document parser behavior.

Sections 1–7 document the login capture; sections 8–12 extend that contract with
the invoice/expense capture. Section 13 covers contractor details and related
tables, section 14 documents date-range filtering, section 15 lists remaining
gaps, and section 16 documents the subsequent live validation.

## 1. Evidence and scope

| Property | Value |
| --- | --- |
| Source | `wfirma_pl_login.har` |
| JSON validity | Complete and parseable |
| HAR entries / page records | 196 / 3 |
| Requests to `wfirma.pl` | 88 |
| Requests to `events-9.wfirma.pl` | 1 |
| Remaining requests | 107; third-party services |
| Statuses on `wfirma.pl` | 43 × 200, 43 × 304, 2 × 302 |

Evidence references such as **E148** mean the one-based position in
`log.entries`, not a line number. **Observed** means an actual request/response
or captured HTML value. **Frontend-derived** means behavior found in downloaded
JavaScript, without necessarily observing that request. **Recommendation** is
implementation guidance, not a tested server requirement.

Analysis grouped traffic by host, method, path, and response type, then decoded
only relevant HTML and application JavaScript, including base64-encoded bodies.
Images, fonts, CSS, and vendor bundles were not exhaustively inspected. No
requests were replayed and no external documentation was substituted for evidence.

The earlier `wfirma_pl.har` is truncated at exactly 100,000 bytes and supplies no
complete wFirma application requests. This complete login capture supersedes the
initial blocked report. Invoice and expense routes mentioned in the earlier
file's page titles still do not establish their API contracts. These captures
do not establish behavior across all business types or account configurations.

## 2. Endpoint index

Application HTTP origin: `https://wfirma.pl`.

| Evidence | Method | Path / query | Status | Observed result |
| --- | --- | --- | --- | --- |
| E1 | GET | `/wylogowanie` | 302 | Redirect to `https://wfirma.pl` |
| E2 | GET | `/` | 200 | Public HTML landing page |
| E83 | GET | `/logowanie` | 200 | HTML login form |
| E148 | POST | `/logowanie` | 302 | Redirect to `/start?cookieCheck=login`; cookies set |
| E149 | GET | `/start?cookieCheck=login` | 200 | Authenticated dashboard HTML and bootstrap data |
| E189 | POST | `/settings/checkViewStyle` | 200 | JSON string `"compact"` |
| E190 | GET | `/dashboard_start_modules/getConfig/md?_=<CACHE_BUSTER>` | 200 | JSON dashboard layout |
| E191 | POST | `/virtual_assistant/getHintsCount` | 200 | JSON status and hint count |
| E192 | GET / WebSocket upgrade | `wss://events-9.wfirma.pl/ws` | 101 | MQTT connection and subscriptions |

Additional non-JSON resources:

| Evidence | Method | Path | Observed result |
| --- | --- | --- | --- |
| E91 | GET | `/images/get/{image_id}/empty/1` | Login-page image; `image/png` |
| E180 | GET | `/users/avatarView` | `image/png` |
| E181 | GET | `/common_files/view/{file_id}/0/0/1` | `image/png` |
| E52, E96, E167 | GET | `/manifest.json` | `application/manifest+json` |

Identifier placeholders replace literal captured values. Each image route has
only one observed example; parameter meanings, accepted ranges, and the meaning
of the trailing flags are unknown. `/common_files/view/...` is not established
as an invoice PDF endpoint by this capture.

## 3. Authentication flow

```text
Existing browser cookie jar
  GET /wylogowanie
    <- 302 Location: https://wfirma.pl
  GET /
    <- 200 public HTML
  GET /logowanie
    <- 200 login form with hidden fields
  POST /logowanie (URL-encoded form + same cookie jar)
    <- 302 Location: /start?cookieCheck=login + Set-Cookie headers
  GET /start?cookieCheck=login (updated cookie jar)
    <- 200 dashboard HTML
       body[data-token]              -> X-Wf-Token for AJAX requests
       body[data-company-context]    -> active company identifier
       rabbitmqsSubscribe JSON        -> separate MQTT credentials
  Dashboard AJAX requests + MQTT connection
```

This records a **re-login using an existing browser session**. A
`SESSION_WFIRMA_PL` cookie already exists at E1, E83, and E148. The login response
sets that cookie, but its value is unchanged in this particular capture and is
sent again at E149. The same is true of `node` and `part` across E148–E149.
Session creation from an empty jar was not verified by this HAR. A later live
empty-jar password login succeeded (section 16.1); session-ID rotation on other
login paths remains unverified.

### 3.1 Logout: `GET /wylogowanie`

Observed request: E1, with existing cookies. No query or request body.

```http
GET /wylogowanie HTTP/1.1
Host: wfirma.pl
Cookie: SESSION_WFIRMA_PL=<SESSION>; ...
```

```http
HTTP/1.1 302 Found
Location: https://wfirma.pl
Set-Cookie: referrerPromotionId=...; Max-Age=-1; path=/; domain=.wfirma.pl
```

The response body is empty. No deletion of `SESSION_WFIRMA_PL` appears in this
response. This does not prove that server-side authentication remains valid:
logout can invalidate server state independently of retaining a cookie. The
capture does not probe a protected route immediately after logout.

**CLI recommendation:** implement logout as an explicit state-changing command,
despite its GET method, and remove locally stored authentication material after
the logout attempt. Logout is not shown to be a prerequisite for login.

### 3.2 Load form: `GET /logowanie`

E83 returns `text/html; charset=UTF-8`, with no `Set-Cookie` header. The form has
`action="/logowanie"` and `method="post"`. The login input is `type="email"`; the
password input is `type="password"`.

Parse the current form and its hidden fields before submission. Six ancillary
fields in E148 exactly match their values in E83. No named CSRF/token input was
observed in this login form. The dashboard's `X-Wf-Token` is not present on the
login POST; this observation does not establish the absence of all login protection.

### 3.3 Submit credentials: `POST /logowanie`

Observed request: E148.

```http
POST /logowanie HTTP/1.1
Host: wfirma.pl
Content-Type: application/x-www-form-urlencoded
Origin: https://wfirma.pl
Referer: https://wfirma.pl/logowanie
Cookie: <COOKIE_JAR>
```

Decoded form fields:

| Field | Captured value / shape | Interpretation and handling |
| --- | --- | --- |
| `data[User][login]` | Nonempty; redacted | User login; form presents an email input |
| `data[User][password]` | Nonempty; redacted | Password |
| `data[Invoice][id]` | Empty string | Hidden field; preserve current form value; purpose unverified |
| `data[Invoice][hash]` | Empty string | Hidden field; preserve current form value; purpose unverified |
| `data[User][googleClientId]` | Nonempty OAuth client identifier; redacted | Hidden configuration value; also submitted on password login |
| `data[User][cookiePolicy]` | `https://wfirma.pl` | Hidden configuration value |
| `data[User][lock]` | Empty string | Hidden field; purpose not established by the successful request |
| `data[User][lockBottomMessage]` | Empty string | Hidden field; purpose not established by the successful request |

All eight fields were sent. Their presence does not prove that each is required.
E8 (`/_public/app.js`) also uses `googleClientId` and `cookiePolicy` to initialize
Google sign-in. Password login is the only completed login flow documented here.

Schematic wire body, with placeholders that must be form-encoded:

```text
data%5BUser%5D%5Blogin%5D=<ENCODED_LOGIN>&data%5BUser%5D%5Bpassword%5D=<ENCODED_PASSWORD>&data%5BInvoice%5D%5Bid%5D=&data%5BInvoice%5D%5Bhash%5D=&data%5BUser%5D%5BgoogleClientId%5D=<ENCODED_FORM_VALUE>&data%5BUser%5D%5BcookiePolicy%5D=https%3A%2F%2Fwfirma.pl&data%5BUser%5D%5Block%5D=&data%5BUser%5D%5BlockBottomMessage%5D=
```

Use a form encoder on decoded names such as `data[User][login]`. The HAR's
`postData.params` names already contain `%5B` and `%5D`; feeding those names
unchanged into another encoder would double-encode them. `postData.text` is the
captured wire representation. This is not a JSON request.

Observed success: empty response body, status 302, and
`Location: /start?cookieCheck=login`. Follow this as GET, retaining every
`Set-Cookie` header. Do not force the credential POST method onto the redirect.

### 3.4 Cookies set on login

E148 sets the following cookies. All have `Path=/` and `Domain=.wfirma.pl`.
Values are intentionally omitted.

| Cookie | Observed lifetime | Other observed attributes | Role |
| --- | --- | --- | --- |
| `SESSION_WFIRMA_PL` | No `Expires` or `Max-Age` | `Secure; HttpOnly` | Session identifier, inferred from name and use |
| `node` | `Max-Age=2592000` | No additional flags captured | Possible routing state; purpose unverified |
| `part` | `Max-Age=31536000` | No additional flags captured | Possible routing/partition state; purpose unverified |
| `wasLogged` | `Max-Age=2592000` | No additional flags captured | Login-history marker, inferred |
| `isClient` | `Max-Age=5184000` | No additional flags captured | Client marker, inferred |
| `referrerPromotionId` | `Max-Age=-1` | No additional flags captured | Deleted cookie |

No `SameSite` attribute is explicitly present on these captured Set-Cookie
headers. A session cookie's browser lifetime does not establish the server's
session timeout. E2 also sets `dropDownActiveLink` with `Max-Age=2592000`.

**CLI recommendation:** use a domain/path-aware cookie jar and process repeated
Set-Cookie headers individually. Preserve application cookies rather than
assuming `SESSION_WFIRMA_PL` alone is sufficient. The browser also sends consent
and analytics cookies; their necessity for application authentication is not
established. Keep password, cookie, AJAX-token, and MQTT-JWT values out of logs.

## 4. Dashboard bootstrap: `GET /start?cookieCheck=login`

E149 returns `text/html; charset=utf-8`. The only observed query value is
`cookieCheck=login`; its necessity on later dashboard loads is unknown.

The HTML is part of the application interface: there is no separate captured
JSON response containing all dashboard business data.

### 4.1 AJAX token and company context

Redacted HTML shape:

```html
<body
  class="wf-scope-normal"
  data-token="<AJAX_TOKEN>"
  data-company-context="<COMPANY_ID>"
  ...>
```

The `data-token` value exactly matches the `x-wf-token` header sent in E189,
E190, and E191. E154 (`/app.js`) configures jQuery AJAX headers from
`$("body").data("token")`. Header names are case-insensitive; the code spells it
`X-Wf-Token`, while the HAR records lowercase.

Frontend code also replaces the AJAX token when dialogs/drawers supply a token,
and adds a hidden `token` field to certain dialog forms. Those flows are
**frontend-derived** in the login capture; section 8.2 adds an observed invoice
dialog token change. Token lifetime, mandatory
validation, and behavior when missing or stale have not been tested. Treat it as
application request-protection state, not as a public API key or an independently
usable bearer credential.

`body[data-company-context]` equals the `companyId` in the `dashboardsIndex`
bootstrap JSON. None of the three dashboard AJAX requests explicitly sends a
company ID in its path, query, or body. Session-selected company context is a
reasonable inference; the company-switching mechanism is unknown.

### 4.2 Embedded JSON

The HTML contains scripts such as:

```html
<script type="text/json" data-fn="__init__">...</script>
<script type="text/json" data-fn="dashboardsIndex">...</script>
<script type="text/json" data-fn="rabbitmqsSubscribe">...</script>
```

Parse their contents as JSON; do not execute the page scripts to extract them.
The relevant observed fields are:

| Script `data-fn` | Fields / types |
| --- | --- |
| `__init__` | `packFree`: boolean; `vatPayer`: boolean; `userId`: string; `here`: string; `responseMessage`: string; `responseStatus`: string; `newMessages`: integer; `warehouse`: object |
| `__init__.warehouse` | `id`: integer; `enabled`: boolean; `type`: string; `defaultUnitId`: integer |
| `dashboardsIndex` | `companyId`: string; `controller`: string; `showCompanySettings`, `showMojoGreetingScreen`, `showCakGreetingScreen`: booleans |
| `dashboardStartModulesReadyForAccounting` | `status`: null in this capture; `lastMonthName`: string |
| `dashboardStartModulesForecastVatNew` | `vatPayer`: boolean |
| `rabbitmqsSubscribe` | Event connection configuration; see section 6 |

The observed `__init__.here` is `/dashboards/index`, although the requested URL
is `/start?cookieCheck=login`. This is an internal bootstrap value, not evidence
of a separate HTTP request to `/dashboards/index`. `responseStatus` is `"OK"`;
`responseMessage` is nonempty and omitted here. `dashboardsIndex.controller` is
`"dashboard_start_modules"`. Other `dashboardsIndex` fields are present with
null values: `commonFileFromLink`, `showEcommerceWarningNew`, `loginTime`,
`showSubscriptionWarning`, `userLastLogin`, and `showImplementationInvitation`.
Their non-null schemas are unknown.

The HTML contains module elements named `ready_for_accounting`, `magic_box`,
`recent_invoices`, `invoice_drafts`, `forecast`, and `shortcuts`. Presence in
markup does not prove visibility, available data, or a separate module API.
Do not interpret the layout response below as invoice or forecast data.

## 5. Observed dashboard JSON requests

All three calls send the current cookie jar, `X-Requested-With: XMLHttpRequest`,
`X-Wf-Token: <AJAX_TOKEN>`, and `Referer:
https://wfirma.pl/start?cookieCheck=login`. The two POSTs also send
`Origin: https://wfirma.pl`. Their captured `Accept` value is `*/*`.

These headers are observed, not individually proven mandatory. HTTP/2 pseudo
headers, browser fingerprint headers, and static asset requests need not be
copied as an HTTP contract. Let the HTTP library manage transport headers.

All three responses have status 200, `Content-Type: application/json`, and
`Cache-Control: no-store, no-cache, must-revalidate`. Each repeats the deletion
of `referrerPromotionId`. There is **no shared JSON envelope** across these calls.

### 5.1 View style: `POST /settings/checkViewStyle`

Evidence: E189. Body is empty (`Content-Length: 0`), with no request Content-Type
header or `postData` object. Do not invent a `{}` body.

```http
POST /settings/checkViewStyle HTTP/1.1
Host: wfirma.pl
Cookie: <COOKIE_JAR>
Origin: https://wfirma.pl
Referer: https://wfirma.pl/start?cookieCheck=login
X-Requested-With: XMLHttpRequest
X-Wf-Token: <AJAX_TOKEN>
Content-Length: 0
```

Exact observed JSON response:

```json
"compact"
```

The response is a **JSON string**, not an object. E154 applies this value as a
CSS class in the UI. Other allowed styles and any side effects are unknown.

### 5.2 Layout: `GET /dashboard_start_modules/getConfig/md`

Evidence: E190. Query contains `_`, with a numeric value, consistent with a
client cache-buster. Omission has not been tested. No request body.

```http
GET /dashboard_start_modules/getConfig/md?_=<CACHE_BUSTER> HTTP/1.1
Host: wfirma.pl
Cookie: <COOKIE_JAR>
Referer: https://wfirma.pl/start?cookieCheck=login
X-Requested-With: XMLHttpRequest
X-Wf-Token: <AJAX_TOKEN>
```

Synthetic layout example; coordinates and preference values are illustrative:

```json
{
  "ready_for_accounting": {"x": "0", "y": "0"},
  "ocr": {"x": "4", "y": "0"},
  "recent_invoices": {"x": "0", "y": "4"},
  "forecast": {"x": "12", "y": "2"},
  "shortcuts": {"x": "16", "y": "0"},
  "is_default": true
}
```

Module entries contain string-valued `x` and `y` layout coordinates;
`is_default` is a boolean. Preserve these observed types. The name `md` suggests
a responsive layout breakpoint, but accepted alternatives are not established.
The `ocr` key in the JSON does not exactly mirror the module names in the HTML;
clients must not assume those sets are identical.

**Frontend-derived edge case:** E154 checks for an empty array from the config
request and handles it as no configuration in one branch. No empty-array
response was observed, so do not present it as a verified response schema.

### 5.3 Hint count: `POST /virtual_assistant/getHintsCount`

Evidence: E191.

```http
POST /virtual_assistant/getHintsCount HTTP/1.1
Host: wfirma.pl
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
Cookie: <COOKIE_JAR>
Origin: https://wfirma.pl
Referer: https://wfirma.pl/start?cookieCheck=login
X-Requested-With: XMLHttpRequest
X-Wf-Token: <AJAX_TOKEN>

urls%5B%5D=%2Fstart
```

Decoded field: `urls[]=/start`. Its array notation supports representing repeated
values in a form encoder; the login capture contains only one value. The value is `/start`,
without `cookieCheck=login`, even though the Referer includes that query.

Exact observed JSON response:

```json
{"status": "OK", "count": 0}
```

`status` is a string and `count` is an integer. The login capture has no error,
nonzero count, or multi-URL example. Section 12 adds nonzero and multi-URL
examples; the aggregation rule remains unknown.

## 6. Event connection: MQTT over WebSocket

E192 upgrades to `wss://events-9.wfirma.pl/ws` with status 101. The request Origin
is `https://wfirma.pl`; the negotiated `Sec-WebSocket-Protocol` is `mqtt`.
No Cookie or X-Wf-Token header is present on this captured handshake.

E149 embeds configuration in
`script[type="text/json"][data-fn="rabbitmqsSubscribe"]`:

```json
{
  "host": "events-9.wfirma.pl",
  "port": 443,
  "vhost": "wfirma.pl",
  "clientId": "<SERVER_PROVIDED_CLIENT_ID>",
  "topics": {
    "0": "<SERVER_PROVIDED_PREFIX>.wfirma.expense.ocr",
    "1": "<SERVER_PROVIDED_PREFIX>.wfirma.common.progress"
  },
  "jwt": "<MQTT_JWT>"
}
```

Use returned host, client ID, and topic strings; do not construct account prefixes
from guesses or assume the numbered event host is stable across accounts.

**Observed in binary WebSocket frames:** the CONNECT packet contains protocol
name `MQTT`, protocol level 4, keepalive 60 seconds, and clean-session flag false.
Its username is `wfirma.pl:Bearer`. Its client ID and password exactly match the
HTML `clientId` and `jwt`. The CONNACK return code is 0. Two subscriptions are
acknowledged with QoS 1. Five WebSocket message records are captured; no published
business event payload appears in them. A WebSocket message can contain multiple
MQTT packets.

**Frontend-derived behavior (E154):** the client builds the WebSocket URL from
`host` and `port`, uses `vhost + ":Bearer"` as username, and the JWT as password.
It subscribes to all supplied topics at QoS 1. The connection options also include
`connectTimeout: 4000` and `sessionExpiryInterval: 1800`; the latter is a code
setting, not proof of broker-negotiated session lifetime in the captured
protocol-level-4 connection.

The MQTT JWT is distinct from both the session cookie and AJAX token. This
optional event channel is not needed to interpret the three HTTP JSON responses.
An OCR topic alone does not establish an upload or OCR submission API.

### 6.1 Token refresh: code evidence only

E154 contains a `$.getJSON("/rabbitmqs/refreshToken", ...)` call. No corresponding
network entry exists in this capture.

| Item | Frontend-derived behavior; not network-verified |
| --- | --- |
| Candidate request | `GET /rabbitmqs/refreshToken` |
| Successful result consumed by code | Object with a truthy `jwt` field; replace password and reconnect |
| Auth-related result consumed by code | Missing JWT with `status === "AUTH"` leads to navigation to `/` |
| Refresh interval | 600,000 ms |
| Retry delay after a failed refresh | 10,000 ms |

These intervals are client behavior, not measured JWT expiry or server retry
requirements. No HTTP status, complete response schema, or standalone refresh
example has been verified. The code's `AUTH` branch must not be generalized to
all wFirma endpoints.

## 7. CLI implementation guidance

The capture supports designing an authentication client, but does not prove a
minimal independently working login request. Recommended sequence:

1. Create a persistent HTTP session with a cookie jar. Load `/logowanie` and parse
   the form action and current named fields. A later empty-jar bootstrap succeeded
   in live validation (section 16.1); minimal field/cookie requirements remain untested.
2. Fill only the login and password fields; preserve the current hidden values.
   Encode once as `application/x-www-form-urlencoded` and submit to the same origin.
3. Process every Set-Cookie header and inspect the redirect. Follow the observed
   successful redirect as GET with the updated jar.
4. Verify the response is the expected dashboard, not merely HTTP 200. Extract
   `body[data-token]`, `body[data-company-context]`, and relevant JSON scripts.
   Their presence is a candidate success check supported by this capture.
5. Store the session state and active company context. Send the current token and
   observed AJAX headers for the documented JSON calls. Decode each endpoint's
   response according to its own shape.
6. On unexpected HTML, redirects, or missing bootstrap data, surface an
   authentication/context error instead of assuming an empty JSON result. These
   are defensive checks; actual failure responses remain uncaptured.
7. Keep event credentials separate if adding live notifications. Implement explicit
   logout; do not run it automatically at the start of every command.

Never infer company scope from an unrelated numeric URL segment. Validate the
active company extracted from the dashboard before future accounting commands.
Do not blindly retry POSTs or copy retry rules from the event-token client to
accounting operations; idempotency and mutation behavior are not established.

Suggested CLI-facing capabilities and their current evidence:

| Capability | Available evidence |
| --- | --- |
| `auth login` | Form, submitted fields, cookies, redirect, token extraction; fresh session subsequently validated in section 16.1 |
| `auth logout` | GET and redirect; post-logout protected access not tested |
| `auth status` | Candidate dashboard bootstrap check; no dedicated status endpoint captured |
| `dashboard layout` | One verified request and response shape |
| `dashboard view-style` | One verified empty POST returning a JSON string |
| `assistant hints-count` | One verified form POST for `/start` |
| `events watch` | MQTT handshake/authentication/subscriptions; no event payload schema |

The CLI names above are proposals, not existing commands or wFirma route names.

## 8. Invoice/expense capture and session continuity

### 8.1 Source and request inventory

| Property | Value |
| --- | --- |
| Source | `wfirma_pl_przychody_wydatki.har` |
| JSON validity | Complete and parseable |
| HAR entries / page records | 148 / 3 |
| Hosts | `wfirma.pl`: 115; `events-9.wfirma.pl`: 3; third parties: 30 |
| Page navigation | `/invoices/index/all`, `/expenses/index`, `/expense_drafts/index` |

**PWn** references entry `n` in this new capture; **En** continues to reference
`wfirma_pl_login.har`. Do not mix the two numbering schemes. PW106 contains the
captured `/app.js` body used for frontend-derived table behavior below. Earlier
copies of the bundle in this capture have no body, so the populated copy was
inspected once. No live requests were made.

| Evidence | Method | Path | Status / content | Purpose |
| --- | --- | --- | --- | --- |
| PW1 | GET | `/invoices/index/all` | 200 HTML | Przychody list, initially empty for selected period |
| PW47, PW48 | POST | `/invoices/indexTable/all/0/0/0/0/0/null/0/0` | 200 HTML | Invoice table after month changes |
| PW50 | GET | `/invoices/view/{invoice_id}?_=<CACHE_BUSTER>` | 200 HTML | Invoice detail dialog |
| PW55 | GET | `/expenses/index` | 200 HTML | Booked-expenses view, empty for selected period |
| PW101 | GET | `/expense_drafts/index` | 200 HTML | Expense-drafts list, first page populated |
| PW42 | POST | `/invoices/numberOfIncomeDrafts` | 200 JSON number | Income-draft badge count |
| PW95, PW143 | POST | `/expense_drafts/numberOfExpenseDrafts` | 200 JSON number | Expense-draft badge count |
| PW41, PW94, PW142 | POST | `/settings/checkViewStyle` | 200 JSON string | Same view-style helper as section 5.1 |
| PW43, PW53, PW54, PW96, PW144, PW147 | POST | `/virtual_assistant/getHintsCount` | 200 JSON object | Page/dialog help counts |
| PW141 | GET | `/new_column/manageNewColumnTooltip/{x}/{y}/ExpenseKsef.ksef_reference_number/ExpensesDrafts?_=<CACHE_BUSTER>` | 200 HTML | New-column UI tooltip; not list data |

The `x`/`y` placeholders in the tooltip route replace observed screen-position-like
numbers; their exact semantics are unverified. It is not necessary for extracting
list records. Static assets and event connections are omitted from this index.

### 8.2 Same session, different page and dialog tokens

The `SESSION_WFIRMA_PL` cookie on PW1, PW47, PW48, PW50, PW55, and PW101 matches
the cookie used on the successful dashboard request E149. No new login was
needed in this captured sequence.

The AJAX token is **not a single fixed value for the whole session**:

| Token source | Requests verified to use it |
| --- | --- |
| PW1 `body[data-token]` | PW41, PW47, PW48, PW50 |
| PW50 `.dialogbox[data-token]` | PW53 and PW54 |
| PW55 `body[data-token]` | PW94, PW95 |
| PW101 `body[data-token]` | PW141, PW143 |

The three page-body tokens differ from each other. PW53/PW54 use the dialog's
token rather than PW1's page-body token. This confirms the token replacement
behavior previously found only in frontend code. It does not establish whether
older tokens remain valid or what the server validates.

For a CLI, parse the token from each full page and from any dialog response that
supplies one, and keep it with the active cookie jar. Table-fragment requests
PW47/PW48 continue using the original invoice-page token. Normal page navigation
GETs PW1/PW55/PW101 do not send `X-Wf-Token`; their AJAX requests do.

## 9. Przychody: invoice listing and detail

### 9.1 Load invoice page: `GET /invoices/index/all`

PW1 returns a full HTML page with the familiar session bootstrap and:

```html
<div class="table-wrapper responsive"
     data-url="/invoices/indexTable/all/0/0/0/0/0/null/0/0"
     data-model="Invoice">
  ...
</div>
```

Its actual wrapper ID is generated and should not be hard-coded. The page
selects a year/month. A successful HTML response
without `<table>` elements can represent an empty list: the wrapper still has
`#tab-params` metadata reporting `total: 0` and `pages: 0`.

The path segment `all` does not mean all dates. The initial view is period-filtered,
and results can include both `normal` and `normal_draft` row types. Do not
present every row as a finalized invoice or an empty month as an empty account.

### 9.2 Refresh/filter: `POST /invoices/indexTable/all/0/0/0/0/0/null/0/0`

PW47 and PW48 use the same literal route. The roles of the positional zero and
`null` segments are unknown. In particular, they are not established page numbers
or company IDs. Obtain this route from the page's `data-url` when possible.

Observed request headers:

```http
POST /invoices/indexTable/all/0/0/0/0/0/null/0/0 HTTP/1.1
Host: wfirma.pl
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
Accept: text/html, */*; q=0.01
Origin: https://wfirma.pl
Referer: https://wfirma.pl/invoices/index/all
Cookie: <COOKIE_JAR>
X-Requested-With: XMLHttpRequest
X-Wf-Token: <CURRENT_AJAX_TOKEN>
```

Decoded request fields, with account-specific period values replaced:

| Field | PW47 | PW48 | Interpretation |
| --- | --- | --- | --- |
| `filters[year]` | `<YEAR>` | `<YEAR>` | Selected year |
| `filters[month]` | `<MONTH_A>` | `<MONTH_B>` | Selected months; integers 1–12 |
| `filters[dateFrom]` | `0` | `0` | Captured sentinel; no explicit date bound supplied |
| `filters[dateTo]` | `0` | `0` | Captured sentinel; no explicit date bound supplied |
| `filters[dateRange]` | `0` | `0` | Captured sentinel; range mode not exercised in PW47/PW48; see section 14 |
| `setColumns` | `true` | `true` | Literal form string; UI also recalculates columns when truthy |

Schematic PW48 wire body; substitute and form-encode the placeholders:

```text
filters%5Byear%5D=<YEAR>&filters%5Bmonth%5D=<MONTH>&filters%5BdateFrom%5D=0&filters%5BdateTo%5D=0&filters%5BdateRange%5D=0&setColumns=true
```

Neither request sends `page`, `show`, sorting, search, or an explicit company ID.
Section 14 documents explicit dates on this same route.
Both responses return HTML containing a `.table-wrapper`, headers, rows, filters,
and pagination metadata. Account-specific row counts are omitted. There is no JSON
`items` or `invoices` array. A response can contain substantial UI markup beyond
the rows; scope extraction to the desired wrapper.

### 9.3 Invoice row schema in HTML

Observed in PW47/PW48. Data rows are `tr.tab-data[data-row-id]`; the row ID matches
the `/invoices/view/{invoice_id}` link for that row. `data-row-type` is `normal`
or `normal_draft` in this capture. IDs should be treated as opaque strings.

Header cells expose `data-colname` and a localized `data-column` label:

| Header field | Display label | Row extraction |
| --- | --- | --- |
| `Invoice.lp` | Lp. | Display ordinal; not the invoice ID |
| `Invoice.fullnumber` | Nr dokumentu | Text of invoice-view link |
| `InvoiceKsef.ksef_reference_number` | Numer w KSeF | Cell text; may include a log link or be empty |
| `Contractor.altname` | Kontrahent | Contractor link text; cell `title` also supplies a name |
| `Invoice.type` | Rodzaj | Display text; retain `data-row-type` separately |
| `Invoice.date` | Data wystawienia | Display date; column marked `desc` in these responses |
| `Invoice.paymentdate` | Termin płatności | Display date |
| `Invoice.alreadypaid` | Zapłacono | Cell `data-value` decimal string |
| `Invoice.remaining` | Pozostało | Cell `data-value` decimal string |
| `Invoice.total_composed` | Razem | Cell `data-value` decimal string; preserve display/currency context |
| `Invoice.netto` | Kwota netto | Cell `data-value` decimal string |
| `Invoice.paymentmethod` | Metoda płatności | Display text |

Not every body cell has `data-colname`. Monetary cells do; other cells expose
`data-column` matching a header's localized label. Match within the same wrapper,
using its header mapping, rather than assuming `td:nth-child(...)` is stable.
Keep the exact attribute label for matching: the captured invoice KSeF label has
two spaces between `w` and `KSeF`, though the table above normalizes it for reading.

### 9.4 Additional invoice filters: markup and code evidence

These controls are present in PW1/PW47/PW48 but only year/month changes were sent
in the capture. The generic frontend handler wraps selected filter IDs under
`filters`; its select-change branch can produce arrays. The exact wire encoding
and server semantics for these unexercised filters need validation.

| Control ID | Observed option values / labels |
| --- | --- |
| `year` | `<YEAR>`, other available years, and empty; read options from the page |
| `month` | `1`–`12`, and empty |
| `email` | Empty; `1` = Tak; `0` = Nie |
| `type` | `\|normal\|` = Faktura; `\|draft\|` = Wersja robocza faktury; literal pipe delimiters |
| `paymentstate` | Empty; `paid` = rozliczona; `unpaid` = nierozliczona; `undefined` = nieokreślona |
| `deliverystate` | Empty; `2` = zrealizowana; `3` = niezrealizowana; `4` = nieokreślona |
| `ksef` | Empty; `0` = wysłane; `1` = niewysłane; `2` = odrzucone; `3` = offline |

Do not replace these values with guessed booleans or translated strings.
The effect of empty choices is not generally established; section 13.4 provides
a contractor-invoice example with an empty month. The list has
search-scope options for document number, contractor names/NIP/email, invoice
text/date, item names, and KSeF number. No search request was captured; see
section 11.3 for the frontend request object.

### 9.5 Invoice detail: `GET /invoices/view/{invoice_id}`

PW50 follows a link from a listed invoice, sending cookies, `X-Wf-Token`,
`X-Requested-With: XMLHttpRequest`, `Accept: */*`, and a numeric `_` query
cache-buster. The response is an HTML dialog, not JSON or a PDF.

The response supplies `.dialogbox[data-token]` and a JSON script with
`data-fn="invoicesView"` containing `invoiceId` as a string. It also contains
multiple independent tables. Important observed header fields include:

| Table | Fields |
| --- | --- |
| Invoice lines | `InvoiceContent.lp`, `InvoiceContent.name`, `Unit.name`, `InvoiceContent.unit_count`, `InvoiceContent.price`, `VatCode.label`, `InvoiceContent.netto`, `InvoiceContent.brutto`, `InvoiceContent.gtu`, and a `Ryczałt` column whose `data-colname` is literally `0` |
| VAT breakdown | `VatCode.label`, `VatContent.netto`, `VatContent.tax`, `VatContent.brutto` |
| KSeF log | `InvoiceKsefLog.response_status`, `InvoiceKsefLog.response_text`, `InvoiceKsefLog.created` |

The response establishes the presence of those tables, not an exhaustive detail
schema for all invoice types. Scope table parsing carefully; selecting every
`tr.tab-data` in the dialog would mix unrelated records.

## 10. Wydatki: booked expenses and expense drafts

### 10.1 Booked expenses: `GET /expenses/index`

PW55 returns full HTML for a selected period. Synthetic empty-list metadata example:

```json
{
  "page": 1,
  "show": 10,
  "total": 0,
  "pages": 0,
  "scrollable": true,
  "insertIdFilterConflict": false,
  "insertIdSearchConflict": false
}
```

The page exposes `.table-wrapper[data-model="Expense"]` with
`data-url="/expenses/indexTable"`, but **no request to that URL was captured**.
There are no booked-expense data rows or table headers in this empty result.
Section 13.3 adds a requested contractor-scoped expense-table route, also empty.
The draft column schema below must not be represented as a verified
booked-expense row schema.

Observed controls include year/month and `paymentstate` values `paid`, `unpaid`,
`undefined`, and `split_payment` (podzielona płatność). No booked-expense filter,
sort, detail, or pagination action was exercised.

**Frontend-derived candidate:** the generic table loader would submit a data
object to `/expenses/indexTable` when a control changes. This is a useful route
for subsequent verification; its response to a nonempty or filtered request is
not documented by this capture.

### 10.2 Draft list: `GET /expense_drafts/index`

PW101 returns full HTML with a populated `Expense` table. The controls expose a
selected year and an optional month. Its wrapper points to:

```text
/expenses/indexTable/normal/0/0/0/1
```

This URL is observed in **HTML metadata only**. It was not requested. The draft
page therefore reuses an expenses table route in its UI configuration; there is
no evidence for a guessed `/expense_drafts/indexTable` endpoint. The meanings of
the positional arguments are unverified; preserve the returned route.

PW101 captures only the first page of a multi-page result. **Synthetic example:**
10 visible rows, 23 total records, and 3 pages leave 13 records on later pages.
A CLI must distinguish visible records
from the total and must not report a complete list after reading only this page.

Rows use `tr.tab-data[data-row-id]`, with `data-row-type="invoice"` in this
example and links to `/expense_drafts/view/{expense_id}`. These detail links were
not followed, so their response schemas and required method/headers are unverified.

| Header field | Display label | Row extraction |
| --- | --- | --- |
| `Expense.lp` | Lp. | Display ordinal |
| `Expense.fullnumber` | Nr dokumentu | Draft-view link text |
| `ExpenseKsef.ksef_reference_number` | Numer w KSeF | Cell text; preserve missing values |
| `Contractor.altname` | Kontrahent | Contractor link text / cell title |
| `Expense.date` | Data wystawienia | Display date; column marked `asc` |
| `Expense.alreadypaid` | Zapłacono | Cell `data-value` decimal string |
| `Expense.remaining` | Pozostało | Cell `data-value` decimal string |
| `Expense.total_composed` | Razem | Cell `data-value`; retain display/currency context |
| `Expense.netto` | Kwota netto | Cell `data-value` decimal string |
| `Expense.vat` | Kwota VAT | Cell `data-value` decimal string |

Do not assume two decimal places: captured draft `data-value` attributes include
values with up to six fractional digits. Preserve them as decimal strings or
arbitrary-precision decimals. Read each record's currency label;
do not infer a monetary field's currency from a global default or confuse a
converted amount with an original-currency amount. This document intentionally
omits actual document numbers, counterparties, tax IDs, and amounts.

### 10.3 Draft filters: metadata only

In addition to year/month and the expense payment-state options:

| Control ID | Observed option values / labels |
| --- | --- |
| `accepted` | Empty; `2` = niewysłane do akceptacji; `0` = do akceptacji; `1` = zaakceptowane |
| `source` | Empty; `magic_box` = import Magic Box; `ksef` = import KSeF; `manual` = dodane ręcznie |

These options are not a record of filter requests. Search-scope options include
expense number, contractor names, description, amounts, KSeF number, and purchase
item names. The default empty month does not establish unrestricted dates beyond
the selected year or absence of other saved filters.

## 11. Shared HTML table contract and pagination

### 11.1 Metadata and row extraction

Find the desired `.table-wrapper` by its `data-model` and `data-url`. Within that
wrapper, parse the JSON in `#tab-params[data-params]`. The element is a `<tbody>`
for populated results and a `<div class="no-results">` for empty results.
Do not require it to be a tbody or treat the missing `<table>` as a login failure.

The following values are synthetic examples, not counts from the account:

| Example result | `page` | `show` | `total` | `pages` | Visible data rows |
| --- | --- | --- | --- | --- | --- |
| Empty invoice period | 1 | 50 | 0 | 0 | 0 |
| Populated invoice period A | 1 | 50 | 4 | 1 | 4 |
| Populated invoice period B | 1 | 50 | 9 | 1 | 9 |
| Empty booked-expense period | 1 | 10 | 0 | 0 | 0 |
| Expense drafts, partial result | 1 | 10 | 23 | 3 | 10 |

All five metadata objects also include `scrollable: true`,
`insertIdFilterConflict: false`, and `insertIdSearchConflict: false`. Their
conflict flags were not exercised. Different page sizes already exist in the
same session; the client should read them rather than assuming one global limit.

Practical extraction procedure:

1. Parse HTML using an HTML parser; HTML-decode the `data-params` attribute before
   JSON parsing. Do not regex the whole response into rows.
2. Read metadata even when the list is empty. Verify the expected page context
   and wrapper to distinguish a valid empty response from a login page.
3. Extract only `tr.tab-data[data-row-id]` within the relevant body table. Exclude
   header/footer rows, selection controls, and responsive `tr.child` duplicates.
4. Build a column map from the header's `data-colname` and `data-column`. Use
   matching body labels for cells lacking `data-colname`; preserve exact labels
   for matching and normalize whitespace only for display.
5. Preserve IDs, row types, detail links, missing values, decimal strings, and
   currency context. Footer totals are not additional records.
6. Return rows together with `page`, `show`, `total`, `pages`, and completeness.
   PW101 is a partial result even though its first-page HTTP request succeeded.

### 11.2 Pagination controls: frontend-derived, not replayed

PW106's `tableScripts` implementation calls the wrapper's `data-url` through
jQuery `.load(url + " .table-wrapper > *", data, callback)`. The CSS suffix is a
client-side response selector: **do not append ` .table-wrapper > *` to the
network URL**. Data objects use the form-style table interface; this is confirmed
on the wire for the two invoice filter POSTs.

The following request objects are produced by frontend controls. Their use for
paging/sorting/search is not captured on the wire here:

| Control | Data object sent to table loader |
| --- | --- |
| Specific page | `{page: 2}` (example next page) |
| Next / previous buttons | `{page: "next"}` / `{page: "previous"}` |
| Page-size change | `{page: 1, show: <SELECTED_VALUE>}` |
| Sort column | `{sorting: {"Invoice.date": "asc"}}` (example field/direction) |
| Search | `{search: <TEXT>}`; UI truncates input to 100 characters |
| Search scopes | `{searchInValues: <SELECTED_VALUES>}` |
| Non-period filter | `{filters: {<CONTROL_ID>: <SELECTED_VALUES>}, setColumns: true}` |

The UI offers page sizes 5, 10, 15, 20, 50, and 100. That is a list of visible
choices, not a verified server maximum. The "last" button starts with a placeholder
`data-value="10000000"`, which JavaScript replaces with metadata `pages`; it is
not evidence of ten million pages or a special API page value.

A candidate form-encoded sort field is `sorting[Invoice.date]=asc`; a candidate
next-page body is `page=2`. These are code-derived examples, not recorded requests.
Do not claim pagination or filter combinations are verified until a subsequent
capture or deliberate test exercises them. The second draft page is the most
useful missing read request.

### 11.3 Saved state and filter resets

The successful month POSTs omit page size and sorting, yet their responses retain
`show: 50` and an invoice-date descending marker. This is consistent with
server-side/default view state; it does not identify its persistence mechanism.
Do not assume an omitted field resets its previous value or that concurrent CLI
list operations sharing a session are independent.

PW106's reset handler sends `"__reset__"` for selected filter controls, sorting,
and search-scope values, and sets `dateRange`, `dateFrom`, and `dateTo` to zero.
The reset-sentinel requests remain unverified. Explicit date ranges are now
observed in section 14; inspect the active mode as well as returned controls
before claiming a result covers a requested period.

## 12. Additional JSON helpers and CLI coverage

### 12.1 Draft badge counts

`POST /invoices/numberOfIncomeDrafts` (PW42) and
`POST /expense_drafts/numberOfExpenseDrafts` (PW95/PW143) have empty request bodies
(`Content-Length: 0`), no request Content-Type, and the same cookie, Origin,
Referer, `X-Requested-With`, and current `X-Wf-Token` pattern as other AJAX calls.

Their `application/json` responses are **bare numbers**, not objects. The following
income-draft and expense-draft counts are synthetic examples:

```json
2
```

```json
23
```

The first illustrates an income-draft count; the second illustrates an
expense-draft count. A badge matching a table total does not prove that it is
filtered identically to every table view. The income count must not be used to
discard `normal_draft` rows in another period.

### 12.2 Hint-count extension

The section 5.3 form interface now has these additional observations:

| Evidence | Decoded `urls[]` values | JSON result |
| --- | --- | --- |
| PW43, PW54 | `/invoices/index/all` | `{"status":"OK","count":8}` |
| PW53 | `/invoices/view/{invoice_id}` and `/invoices/index/all` | `{"status":"OK","count":8}` |
| PW96 | `/expenses/index` | `{"status":"OK","count":0}` |
| PW144, PW147 | `/expense_drafts/index` | `{"status":"OK","count":0}` |

PW53 sends repeated `urls[]` fields in one form, establishing a multi-value wire
example. Counts are help hints, not invoice or expense totals. The aggregation
rule across multiple URLs remains unknown.

### 12.3 Proposed CLI listing behavior

| Proposed capability | Implementation supported by evidence | Remaining limitation |
| --- | --- | --- |
| `invoices list --year ... --month ...` | Load invoice page, extract token/route, submit observed period form, parse HTML table and metadata | Search/sort/pagination requests are frontend-derived only; date-range mode is documented in section 14 |
| `invoices show <id>` | Fetch observed invoice detail route with current AJAX state; parse scoped dialog sections and update token | One invoice type/example; no PDF download contract |
| `expenses list` | Load `/expenses/index`; parse current-period empty-state metadata | Populated booked-expense rows and table-refresh response not captured |
| `expense-drafts list` | Load `/expense_drafts/index`; parse draft rows and metadata | Only first page of a multi-page result captured |
| Draft-count helpers | Empty POST returning a JSON integer | Scope relative to saved filters and periods is unverified |

These are proposed command names, not implemented commands. A future CLI should
surface partial results and the active period/company, preserve the distinction
between invoices and drafts, and avoid silent loss of monetary precision.

## 13. Contractor details and contractor-scoped records

### 13.1 Capture and identity

| Property | Value |
| --- | --- |
| Source | `wfirma_pl_company.har` |
| Evidence prefix | **Cn** = one-based entry `n` in this HAR |
| JSON validity / entries / pages | Complete / 34 / 1 |
| Hosts | `wfirma.pl`: 33; `fonts.gstatic.com`: 1 |
| Coverage | Two contractor dialogs, their related tables, and two contractor-invoice year-filter POSTs |

Here “company” means the **contractor/customer receiving invoices**, represented
by `contractorId`. It is distinct from the user's active accounting company,
represented by `body[data-company-context]` or `companyId` in dashboard bootstrap.
Do not substitute one identifier for the other.

C1 and C19 open two different contractor IDs. The dialog's `contractorsView`
bootstrap `contractorId` equals the ID in its request path. The associated table
URLs carry that same contractor ID. Existing invoice rows expose these IDs in
`/contractors/view/{contractor_id}` links, so they can be followed without deriving
an ID from a name or NIP. Contractor directory listing and lookup by NIP were not
captured.

### 13.2 Details: `GET /contractors/view/{contractor_id}`

Observed in C1 and C19, with a numeric `_` cache-buster query, no body, status 200,
and `text/html` response content. Both requests originate from the invoice page:

```http
GET /contractors/view/<CONTRACTOR_ID>?_=<CACHE_BUSTER> HTTP/1.1
Host: wfirma.pl
Accept: */*
Referer: https://wfirma.pl/invoices/index/all
Cookie: <COOKIE_JAR>
X-Requested-With: XMLHttpRequest
X-Wf-Token: <CURRENT_AJAX_TOKEN>
```

The response is an HTML dialog with `.dialogbox[data-token]` and:

```html
<script type="text/json" data-fn="contractorsView">
  {"contractorId":"<CONTRACTOR_ID>","tab":null}
</script>
```

The session cookie matches the previous login capture. The token from C1 is used
on C5–C17; the token from C19 is used on C20–C34. Retain the updated dialog token
for related requests. The Referer on those requests remains the top-level invoice
page; it is not changed to the dialog URL.

The basic details are in `#tab-basics`. They are display values rather than named
form inputs or a structured contractor JSON object. For each `label.label-bg`,
read the sibling `.mat-text.form-control-plaintext` in the same `.mat-group`:

```html
<div class="mat-group used">
  <div class="mat-text used form-control-plaintext">&lt;FULL_NAME&gt;</div>
  <label class="label-bg">Pełna nazwa</label>
</div>
```

| Observed label | Suggested CLI field | Observed representation |
| --- | --- | --- |
| Pełna nazwa | `full_name` | Text |
| Skrócona nazwa | `short_name` | Text |
| NIP | `tax_id` | Text identifier; may include an adjacent icon/link |
| Adres | `address_display` | Combined display address; no verified separate street/city/postcode fields |
| Rabat | `discount_display` | Formatted display text; do not assume an unobserved numeric API schema |
| Nr konta | `bank_account_display` | Optional block; identifier text with an adjacent icon/link |

The CLI field names above are proposed normalization names, not wFirma response
keys. Preserve NIP and account numbers as strings. An absent bank-account block
means “not supplied in this response,” not proof that the contractor has no bank
account anywhere in wFirma. No email/phone field is established by these detail
examples. Keep the full name and short name distinct, even when they match.

Scope extraction to `#tab-basics` to avoid calendar and other labels elsewhere in
the dialog. Read only the value block, not the entire parent group's text, which
also includes the label. Ignore adjacent action icons when extracting NIP/account
text. The VAT/bank verification-history links were not followed and do not
establish a tax-status or bank-verification API contract.

The basic tab also contains financial-summary tables with headings such as
Należności przeterminowane, Odsetki, Ilość przeterminowanych faktur, Średnie
przeterminowanie, Do 3 miesięcy, Do 2 lat, and Powyżej 2 lat. Their values are
formatted display data; this capture does not establish calculation rules or
currency/rounding semantics. Actual names, addresses, NIP values, bank accounts,
and financial amounts are omitted from this reference.

### 13.3 Related tables: observed GET requests

The dialog exposes tabs Ogólne, Przychody, Wydatki, Płatności, CRM, and Dokumenty.
Its `script[data-fn="frameworkLibsTableViewsAjax"]` blocks contain `{"url": ...}`
objects for related tables. These are not merely route hints: the following
requests actually occur for both contractors.

All are **GET** requests with a numeric `_` cache-buster, no body, cookies, the
current dialog token, `X-Requested-With: XMLHttpRequest`, and
`Accept: text/html, */*; q=0.01`. All return 200 HTML. This extends the earlier
POST-only invoice refresh examples: the table interface also supports observed
GET initial loads in contractor context.

| Evidence: first / second contractor | Requested path | Observed result |
| --- | --- | --- |
| C6 / C21 | `/invoices/indexTable/all/{contractor_id}` | Invoice rows; first page only for first contractor |
| C7 / C22 | `/invoices/indexTable/proforma/{contractor_id}` | Empty table metadata |
| C8 / C23 | `/invoices/indexTable/interest_note/{contractor_id}` | Empty table metadata |
| C9 / C24 | `/invoices/indexTable/auto/{contractor_id}` | Empty table metadata |
| C10 / C25 | `/invoices/indexTable/income/{contractor_id}` | Empty table metadata |
| C11 / C26 | `/contractor_services/indexTable/{contractor_id}` | Empty table metadata |
| C12 / C27 | `/expenses/indexTable/contractor/{contractor_id}` | Empty table metadata |
| C13 / C28 | `/payments/indexTable/all/0/{contractor_id}` | Payment table rows; account-specific counts omitted |
| C14 / C29 | `/contact_logs/indexTable/{contractor_id}` | Empty table metadata |
| C15 / C30 | `/contacts/indexTable/{contractor_id}` | Empty table metadata |
| C16 / C31 | `/crm_task_lists/indexTable/0/{contractor_id}` | Empty table metadata |
| C17 / C32 | `/documents/indexTable/crm,book,warehouse/contractor/{contractor_id}` | Empty table metadata |

Treat literal route segments as observed values, not a complete enum of accepted
record types. Empty responses establish the route and empty-state format, not the
populated row schema. All listed empty results report page 1, show 10, total 0,
and pages 0, using the shared `#tab-params[data-params]` convention.

The captures cover complete single-page and partial multi-page invoice results.
Account-specific totals are omitted. Later pages of the multi-page result were
not captured.

The contractor invoice table uses these header fields:

```text
Invoice.lp
Invoice.fullnumber
InvoiceKsef.ksef_reference_number
Invoice.type
Invoice.date
Invoice.paymentdate
Invoice.alreadypaid
Invoice.remaining
Invoice.total_composed
Invoice.paymentmethod
```

It omits `Contractor.altname` and `Invoice.netto` present in the earlier main
invoice list. A parser must tolerate context-specific columns rather than
requiring a fixed schema. Row IDs/detail links and monetary `data-value` extraction
follow section 9.3.

C13/C28 expose payment columns `Payment.payment_method`, `Payment.value`,
`Payment.date`, and `Payment.id`. This is read-only evidence of a related payment
list, not a contract for creating, editing, or reconciling payments.

### 13.4 Contractor invoice filters: observed POST requests

C33 and C34 POST to `/invoices/indexTable/all/{contractor_id}` for the **second**
contractor. They use the current dialog token, the invoice-page Referer,
`Origin: https://wfirma.pl`, and
`Content-Type: application/x-www-form-urlencoded; charset=UTF-8`.

| Field | C33 | C34 |
| --- | --- | --- |
| `filters[year]` | `<YEAR_A>` | `<YEAR_B>` |
| `filters[month]` | Empty string | Empty string |
| `filters[dateFrom]` | `0` | `0` |
| `filters[dateTo]` | `0` | `0` |
| `filters[dateRange]` | `0` | `0` |
| `setColumns` | `true` | `true` |

This supplies an observed year selection with no month selected. Encode an empty
month as `filters%5Bmonth%5D=` rather than dropping the field. Responses cover
populated and empty table shapes; account-specific periods and totals are omitted.
The filter route remains scoped to the contractor. This does not prove that
arbitrary empty filter fields have the same clearing behavior or that this
contractor route accepts all main-list filter combinations.

**Proposed CLI flow:** `contractors show <id>` can request only the detail dialog
when basic company information is needed. It need not fetch every related table.
A separate `invoices list --contractor <id> --year ...` can load the observed
contractor route and submit the year form using its dialog token. These command
names are proposals; no CLI code has been added.

## 14. Explicit date-range filtering on Przychody invoices

### 14.1 Capture

| Property | Value |
| --- | --- |
| Source | `wfirma_pl_przychody_range.har` |
| Evidence prefix | **Rn** = one-based entry `n` in this HAR |
| JSON validity / entries / pages | Complete / 47 / 1 |
| Hosts | `wfirma.pl`: 39; `fonts.googleapis.com`: 4; `fonts.gstatic.com`: 2; `static.hotjar.com`: 1; `events-9.wfirma.pl`: 1 |
| Relevant requests | R1: main invoice-page GET; R47: date-range table POST |

The session cookie matches E149's session. R47 uses the token from R1's
`body[data-token]`. R1 initially uses month mode; its period and row count are omitted.

### 14.2 Observed range request

R47 posts to the same main invoice-table route as PW47/PW48:

```http
POST /invoices/indexTable/all/0/0/0/0/0/null/0/0 HTTP/1.1
Host: wfirma.pl
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
Accept: text/html, */*; q=0.01
Origin: https://wfirma.pl
Referer: https://wfirma.pl/invoices/index/all
Cookie: <COOKIE_JAR>
X-Requested-With: XMLHttpRequest
X-Wf-Token: <CURRENT_AJAX_TOKEN>
```

| Field | Value (private dates replaced) | Meaning supported by the request |
| --- | --- | --- |
| `filters[dateFrom]` | `<START_DATE>` | Explicit lower date, `YYYY-MM-DD` |
| `filters[dateTo]` | `<END_DATE>` | Explicit upper date, `YYYY-MM-DD` |
| `filters[dateRange]` | `1` | Range mode enabled |
| `setColumns` | `true` | Same literal form flag used on month changes |

Schematic body; substitute and form-encode the date placeholders:

```text
filters%5BdateFrom%5D=<START_DATE>&filters%5BdateTo%5D=<END_DATE>&filters%5BdateRange%5D=1&setColumns=true
```

**No `filters[year]` or `filters[month]` fields are sent in range mode.** The
request also omits pagination, sorting, and search fields. Do not convert these
date strings to timestamps or invent a JSON body. Encode bracketed names once.

### 14.3 Result and active-mode detection

R47 returns status 200 and `text/html`, with the established invoice column/row
format. Metadata indicates a complete single-page result; its row count is omitted.
Both `normal` and `normal_draft` row types occur.

The response's date inputs contain the requested start/end values. It marks the
range controls with `.tab-term.tab-range.is-range-on` and hides the ordinary
`.tab-term.tab-selects` container with `style="display: none;"`. Desktop/mobile
copies of the controls can occur, so scope or deduplicate them.

**The old year/month selects retain their previous values in the range response.**
Those retained values do not describe the active filter while range mode is on.
Prefer the active range container and its date inputs over the hidden selectors
when reporting the list's period.

The rendered `Invoice.date` values parse as ISO dates and lie inside the
requested interval. None equals either endpoint. Therefore the capture supports
a date-range result but does **not** establish inclusive/exclusive boundary rules,
maximum range length, invalid-date behavior, or conclusively distinguish issue
date from other potentially correlated accounting dates.

### 14.4 CLI use and remaining range tests

For a proposed command such as
`invoices list --from <START_DATE> --to <END_DATE>`:

1. Load `/invoices/index/all` with the existing session; extract the current page
   token and invoice-table `data-url`.
2. POST the four observed range fields, using date-only strings and
   `filters[dateRange]=1`. Keep year/month out of this request.
3. Parse the returned table, active range controls, and pagination metadata.
   Preserve drafts and decimal precision as described in sections 9 and 11.
4. Report completeness from metadata; range mode does not disable pagination.

The previously observed month forms use `dateRange=0`, zero date sentinels, and
explicit year/month. They provide a candidate way to select month mode again,
but this capture does not contain a **range-to-month transition**. It also does
not test combining range mode with contractor scope, search, sorting, pagination,
or other filters. These combinations must remain distinct from the verified
standalone range request.

## 15. Remaining capture needs

| Area | What remains unknown |
| --- | --- |
| Fresh authentication | Minimal cookie/field requirements, session-ID rotation, redirect alternatives; one empty-jar password login succeeded in section 16.1 |
| Authentication failures | Incorrect password, expired tokens/session, lockout, MFA, CAPTCHA, social login |
| Token lifecycle | Server validation and lifetime of page/dialog tokens; MQTT refresh responses |
| Accounting-company selection | Listing/switching the user's companies, permission boundaries, account variants |
| Contractor operations | Directory listing/search, lookup by NIP, structured address fields, edits, contacts, verification-history responses |
| Invoice listing | Actual paging, search, sort, non-period filters, reset behavior; contractor second page |
| Date ranges | Endpoint inclusion, date-field semantics, validation/limits, switching back to month, combined filters |
| Invoice operations | Other detail variants, creation/editing, payments, PDFs, KSeF actions |
| Booked expenses | Populated general/contractor results and an actual unscoped `/expenses/indexTable` refresh |
| Expense drafts | Second-page request/response, filters, detail view, attachments, OCR and booking |
| Tax records | Multi-page tax/register results, explicit declaration-list year changes, corrections and their supersession rules, export actions, declaration creation/submission and payment recording |
| Forecasts | Retrieval of numerical forecasts, accepted path parameters, cache/state behavior beyond the observed refresh response |
| Operational behavior | Error envelopes, rate limits, idempotency, concurrent list-state interactions |

Menu links to creation, editing, deletion, payment, or export actions are not
validated API contracts. No accounting mutation was replayed or inferred as a
listing prerequisite. The four complete captures were analyzed locally; the
original truncated HAR remains excluded from endpoint claims. Preserve the
source-specific evidence labels when extending this reference.

## 16. Live validation: authentication and tax-accounting reads

### 16.1 Evidence and fresh login

The following requests were made during authorized live validation.
These are **live observations**, distinct from the HAR
evidence in sections 1–14. Private snapshots under `.private/` support this
section; they contain account data and authentication state and must not be
published or committed. Examples below contain no actual credentials, company
IDs, declaration IDs, invoice IDs, counterparties, financial amounts, or
account-specific periods and totals. Snapshot descriptions below are generic
labels, not filenames; private filenames can themselves reveal financial details.

| Evidence | Snapshot category (generic label) | API coverage |
| --- | --- | --- |
| L1 | Dashboard | Successful fresh password login and authenticated company context |
| L2 | PIT listing and calculation details | PIT calculations and calculation-table structure |
| L3 | VAT and JPK listings and details | VAT-UE listing, JPK listing and quarterly VAT XML |
| L4 | Revenue-register page and filtered tables | Revenue-register page and actual month-filter POST responses |
| L5 | VAT register pages and JPK detail | Quarterly VAT registers and interim monthly JPK XML |
| L6 | ZUS declaration page | ZUS declaration list and contribution components |
| L7 | PIT and VAT forecast responses | Forecast refresh acknowledgments, without numerical tax estimates |
| L8 | Invoice tables and detail dialog | Live invoice month/range filtering and line-level ryczałt rate fields |

Fresh login succeeded with an initially empty local HTTP cookie jar:

1. GET `/logowanie` using a cookie-aware client.
2. Parse the form containing `data[User][login]`; preserve its named hidden inputs.
3. Read credentials locally, populate `data[User][login]` and
   `data[User][password]`, and POST URL-encoded fields to the same-origin action.
4. Follow redirects through the same client, retaining cookies.
5. Confirm an authenticated dashboard using both `body[data-token]` and
   `body[data-company-context]`, plus `script[data-fn="dashboardsIndex"]`.
6. Verify the displayed company against the intended business before retrieving
   accounting records.

No logout, imported HAR cookies, MQTT connection, or browser automation was
needed. This validates one empty-jar login, not the minimal required fields,
all login alternatives, or server-side session rotation. The client restricted
redirects to `https://wfirma.pl`; it did not test cross-origin authentication.

Credentials were read from `.env` fields `WFIRMA_LOGIN` and `WFIRMA_PASSWORD`
without printing them. Cookie persistence supported subsequent reads. Keep
`.env` and cookie/token files owner-readable only, use an owner-only private
directory, and exclude credentials, HARs and snapshots from version control.
A successful local HTTP session does not log the user into their browser.

### 16.2 Live endpoint index

Use the same cookie jar and current `X-Wf-Token` for AJAX reads. Top-level pages
are HTML; dialog reads were made with `X-Requested-With: XMLHttpRequest`.
Actual row links and wrapper `data-url` values should supply opaque routes.

| Method | Path | Observed result |
| --- | --- | --- |
| GET | `/declaration_headers/index/tax` | PIT calculation listing |
| GET | `/declaration_headers/view/{declaration_id}` | HTML detail; content depends on declaration type |
| GET | `/declaration_headers/index/vat` | VAT-UE information listing in validation; do not assume this is a quarterly payable-VAT list |
| GET | `/declaration_headers/index/jpkewp,jpkfa,jpkmag,jpkpkpir,jpkkr,jpkkrpd,jpkvat,jpkv7m,jpkv7k` | JPK listing, including JPK_V7K monthly records |
| GET | `/declaration_headers/zusdra` | ZUS DRA listing with contribution breakdowns |
| GET | `/lumpregisters/index` | Ryczałt revenue register |
| POST | `/lumpregisters/indexTable` | Actual year/month-filtered revenue-register response |
| GET | `/vatregisters/sale` | Quarterly VAT sales register |
| GET | `/vatregisters/purchase` | Quarterly VAT purchase register |
| GET | `/dashboard_start_modules/forecastPitNew/0/0/1` | HTML with embedded JSON acknowledging PIT forecast refresh |
| GET | `/dashboard_start_modules/forecastVatNew/0/0/1` | HTML with embedded JSON acknowledging VAT forecast refresh |

Declaration wrappers expose `/declaration_headers/indexTable/{type}`; observed
types include `tax`, `zusdra`, and the comma-separated JPK types above. VAT
wrappers expose `/vatregisters/indexTable/sale` and
`/vatregisters/indexTable/purchase`. These wrapper URLs were discovered in live
HTML, but direct refresh/filter requests to them were **not** tested. Do not
describe them as independently validated request contracts.

### 16.3 PIT and JPK lists: periods, amounts and completeness

Both use `.table-wrapper[data-model="DeclarationHeader"]`, the shared
`#tab-params[data-params]` metadata, and `tr.tab-data[data-row-id]` rows.
Observed row types are `tax` and `jpkv7k`. Details are linked through
`/declaration_headers/view/{declaration_id}`.

Relevant headers and cells:

| Header field | Display / extraction |
| --- | --- |
| `DeclarationHeader.sequence` | `Okres`, period label and detail link |
| `DeclarationHeader.type` | `Typ`, declaration type or calculation-detail link |
| `DeclarationTax.type` | `Rodzaj opodatkowania`, present in the PIT list |
| `DeclarationHeader.submit_date` | `Termin złożenia`, present in the JPK list |
| `DeclarationHeader.payment_date` | `Termin zapłaty` |
| `DeclarationHeader.alreadypaid` | `Zapłacono`; scalar monetary cells have decimal `data-value` |
| `DeclarationHeader.remaining` | `Pozostało`; scalar monetary cells have decimal `data-value` |
| `DeclarationHeader.total` | `Razem`; scalar monetary cells have decimal `data-value` |

Match body `data-column` labels to header fields when body `data-colname` is
missing. Blank JPK monetary cells must remain absent, not turn into zero.
Period labels can be Polish month names or quarter names with Roman numerals.

Read selected periods and pagination metadata from each response; account-specific
years and row counts are omitted here. Distinguish monthly JPK records from
records containing a quarterly declaration. Do not sum a quarterly liability
once for each monthly record or interpret an interim monthly record as a
completed quarter.

These initial pages inherited selected periods from the live account. Verify
the selected controls and returned document periods; defaults are not a
contract. Explicit year-changing requests and multi-page tax lists were not
tested. No correction example was available, so selecting a latest effective
declaration among originals/corrections remains unresolved.

### 16.4 PIT calculation detail and VAT XML

PIT details in L2 contain a calculation table in HTML, not a stable numeric
JSON object. It displays:

- The period and taxation method.
- Revenue separately for each applicable ryczałt rate and its revenue share.
- Social and health contribution deductions, including unused prior amounts.
- Other deductions, rounded taxable bases, tax per rate and final payable tax.

Preserve rate-specific calculations and associate line-level ryczałt fields with
the corresponding calculation buckets; do not assume one business-wide rate.
Health amounts labeled as deductible contributions are already deductions:
do not halve them again.
Displayed revenue percentages may be rounded; recomputing with exact revenue
fractions can affect reconciliation of saved bases and final taxes.
These are parsing considerations, not a complete tax-law specification.

JPK detail responses in L3/L5 embed escaped XML inside
**`fieldset#print-preview`**. Extract its decoded text with an HTML parser and
parse that as XML, without executing scripts. The neighboring
`#print-preview-pdf` element was empty and does not establish a PDF endpoint.

Inspect namespace-qualified XML by namespace-aware or local-name matching.
Namespace URIs and form versions are versioned; do not hardcode one across all
periods. Read the document's actual version and namespace first.

| XML element(s) | Use |
| --- | --- |
| `JPK/Naglowek/Rok`, `Miesiac` | Monthly reporting period |
| `Naglowek/CelZlozenia` | Submission purpose; read the value from the document |
| `Deklaracja/Naglowek/Kwartal` | Quarter, when a quarterly declaration is present |
| `Deklaracja/PozycjeSzczegolowe/P_38` | Total output VAT |
| `P_39`, `P_48`, `P_49`, `P_50`, `P_51` | Prior credit, deductible VAT, relevant reductions, and declared payable VAT |
| `SprzedazWiersz`, `ZakupWiersz` | Monthly ledger records, with `K_*` amounts |

Do not sum every `P_*` or `K_*` field: some overlap or are subtotals.
Preserve signs and correction classifications, including negative adjustments.
Rounding individual declaration fields can differ from rounding one net ledger total.
Use the actual form schema and applicable rules when computing, rather than
treating `P_38 - P_48` as universal; other relevant adjustments may affect the result.

### 16.5 Revenue and VAT registers

The revenue wrapper is `.table-wrapper[data-model="Lumpregister"]` with
`data-url="/lumpregisters/indexTable"`. L4 validates month-filter POST requests.
The following is their decoded form shape, with private period values replaced:

```text
filters[year]=<YEAR>
filters[month]=<MONTH>
setColumns=true
```

Names above are decoded form names: URL-encode once. Send cookies, the current
AJAX headers, and `/lumpregisters/index` as the Referer. No date-range fields
were submitted in these register requests. Parse populated and empty response
metadata using the same contract. This validates month filtering only.

Headers include `Lumpregister.lp`, `.date`, `.fullnumber`, `.description`,
`.rate3`, `.rate5_5`, `.rate8_5`, `.rate10`, `.rate12`, `.rate12_5`, `.rate14`,
`.rate15`, `.rate17`, `.ratenp`, and `.total`, plus `ContractorDetail.nip`.
This is the observed column set, not an exhaustive list of legal tax rates.

VAT wrappers use model `Vatregister` and row types `sale` / `purchase`.
Read the selected year, quarter, and pagination metadata from the response.
Headers include:

```text
Vatregister.lp                 ContractorDetail.name
Vatregister.date               Vatregister.name
Vatregister.ksef_reference_number
ContractorDetail.nip           Vatregister.description
Vatregister.vat_code_label     Vatregister.netto
Vatregister.tax                Vatregister.brutto
```

The VAT body's amount cells lacked decimal `data-value` attributes in these
responses. Parse localized text as decimal values, handling grouping spaces,
nonbreaking spaces, decimal commas and negative signs. Exclude `tr.tab-sum`
and other footer rows from records; their totals can serve as cross-checks.
Preserve exact column labels such as the double space in `Numer w  KSeF`.

### 16.6 ZUS summaries and payment semantics

L6 uses a `DeclarationHeader` wrapper and row type `zusdra`.
Headers include `.sequence`, `.type`, `.form_of_taxation`, `.submit_date`,
`.zusdra`, `.alreadypaid`, `.remaining`,
and `.total`. The last three contain component breakdowns rather than one
interchangeable scalar:

```text
Społeczne
Zdrowotne
FP i FGŚP
Razem
```

Extract each component and associate it with its paid/remaining/total column;
do not flatten the whole row into one monetary value. A ZUS declaration's
period is not necessarily the quarter in which its contribution was paid.
Actual bank-payment timing and component eligibility matter for PIT deductions.
Bank transfers matching the total do not independently prove ZUS allocation.

More generally, wFirma's `alreadypaid` and `remaining` fields are bookkeeping
state, not an authoritative bank or tax-office balance. Reconciliation should
compare each source independently. Preserve declared liability, recorded payments,
actual bank debits, tax-office allocation and interest as distinct evidence.

### 16.7 Forecast endpoints refresh state; they do not return estimates

The two exact `/forecastPitNew/0/0/1` and `/forecastVatNew/0/0/1` routes in the
endpoint index were followed from dashboard links. Each returned an HTML
`div#response-message` containing a
`script[type="text/json"][data-fn="elementsDialogboxResponse"]` JSON object.
Parse the script's text as JSON, not the complete HTML response body. The object
contains `responseStatus: "OK"` and a message saying the respective forecast was
successfully refreshed. Other observed fields include `redirect: null`,
`insertId: {"0":""}`, `reloadPage: false`, and `reload: null`.

**Neither response contained numerical PIT or VAT amounts.** Treat these as
state-refresh operations despite their GET method, not pure numerical forecast
reads. The meaning of the path parameters, cache effects, and the request that
retrieves forecast amounts remain unverified. No declaration was generated as
part of this work, and refreshing a forecast is not proof of a computed tax due.

### 16.8 Data freshness and reconciliation boundaries

The following are general implementation considerations, not a report of the
account's finances or bookkeeping status:

- Pagination completeness does not establish accounting completeness or month
  coverage. Compare the requested period with the periods represented in the rows.
- Reconcile invoices, drafts, internal documents, and tax registers before
  aggregating income. Avoid double-counting representations of the same activity
  or interpreting an empty register as proof of no taxable activity.
- Keep invoice issue dates and register dates distinct. A range on
  `Invoice.date` is not proof of the correct PIT/VAT recognition period.
- Distinguish internal transfers from tax payments and revenue. Associate receipts
  with the relevant invoices and periods. A transaction export without an opening
  balance cannot establish a current account balance.
- Current-quarter estimates must identify issued-but-unbooked items,
  provisional tax rates, payment-based deductions and missing months. Keep
  them separate from saved declarations and from forecasts of future sales.

The temporary client and calculations were analysis helpers, not a supported
CLI implementation. Login errors, MFA/CAPTCHA, pagination beyond one page,
company switching, declaration corrections, and accounting mutations still
require separate validation. No credentials or private snapshots belong in
public examples or automated test fixtures.
