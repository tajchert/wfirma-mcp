"""All records, amounts, identifiers, counts, and periods here are synthetic."""

import html

import pytest

from wfirma_mcp.parsing import ParseError, parse_contractor, parse_detail, parse_table

TABLE = """<div class="table-wrapper" data-model="Invoice"
 data-url="/invoices/indexTable/all/0/0/0/0/0/null/0/0">
 <select id="year"><option selected value="2031">2031</option></select>
 <select id="month"><option selected value="7">July</option></select>
 <table><thead><tr>
 <th data-colname="Invoice.fullnumber" data-column="Nr dokumentu">Nr dokumentu</th>
 <th data-colname="InvoiceKsef.ksef_reference_number" data-column="Numer w  KSeF">KSeF</th>
 <th data-colname="Invoice.total_composed" data-column="Razem">Razem</th>
 </tr></thead><tbody id="tab-params" data-params='{"page":1,"show":10,"total":23,"pages":3}'>
 <tr class="tab-data" data-row-id="inv-demo" data-row-type="normal_draft">
 <td data-column="Nr dokumentu"><a href="/invoices/view/inv-demo">DEMO/1</a></td>
 <td data-column="Numer w  KSeF"></td>
 <td data-column="Razem" data-value="1234.123456">1 234,12 EUR</td></tr>
 <tr class="tab-sum"><td>Total</td></tr><tr class="child"><td>duplicate</td></tr>
 </tbody></table></div>"""


def test_exact_column_labels_decimal_precision_drafts_and_partial_results():
    result = parse_table(TABLE, "Invoice")
    assert result["complete"] is False
    assert result["pagination"]["total"] == 23
    assert result["filters"]["month"] == "7"
    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["id"] == "inv-demo"
    assert row["type"] == "normal_draft"
    assert row["cells"]["Invoice.fullnumber"]["links"] == ["/invoices/view/inv-demo"]
    assert row["cells"]["InvoiceKsef.ksef_reference_number"]["value"] is None
    assert row["cells"]["Invoice.total_composed"]["value"] == "1234.123456"
    assert row["cells"]["Invoice.total_composed"]["text"] == "1 234,12 EUR"


def test_valid_empty_result_without_table():
    result = parse_table(
        """<div class="table-wrapper" data-model="Expense">
    <div id="tab-params" data-params='{"page":1,"show":10,"total":0,"pages":0}'></div>
    </div>""",
        "Expense",
    )
    assert result["complete"] is True
    assert result["rows"] == []


@pytest.mark.parametrize(
    "source", ["<form>Login</form>", '<div class="table-wrapper" data-model="Invoice"></div>']
)
def test_missing_context_is_not_an_empty_list(source):
    with pytest.raises(ParseError):
        parse_table(source, "Invoice")


def test_active_range_overrides_stale_month():
    source = TABLE.replace(
        "<table>",
        """<div class="tab-term tab-range is-range-on">
    <input id="dateFrom" value="2031-07-03"><input id="dateTo" value="2031-09-29">
    </div><table>""",
    )
    result = parse_table(source, "Invoice")
    assert result["period"] == {"mode": "range", "date_from": "2031-07-03", "date_to": "2031-09-29"}


def test_localized_negative_vat_and_zus_components_are_not_flattened():
    source = """<div class="table-wrapper" data-model="Vatregister"><table>
    <thead><tr><th data-colname="Vatregister.tax" data-column="VAT">VAT</th>
    <th data-colname="DeclarationHeader.total" data-column="Razem">Razem</th></tr></thead>
    <tbody id="tab-params" data-params='{"page":1,"show":10,"total":1,"pages":1}'>
    <tr class="tab-data" data-row-id="demo">
    <td data-column="VAT">−1&nbsp;234,56</td>
    <td data-column="Razem"><div>Społeczne: 100,00</div><div>Zdrowotne: 200,00</div></td>
    </tr></tbody></table></div>"""
    cells = parse_table(source, "Vatregister")["rows"][0]["cells"]
    assert cells["Vatregister.tax"]["value"] == "-1234.56"
    assert cells["DeclarationHeader.total"]["value"] is None
    assert cells["DeclarationHeader.total"]["text"] == "Społeczne: 100,00 Zdrowotne: 200,00"


def test_contractor_fields_are_scoped_and_identifiers_stay_strings():
    source = """<div class="dialogbox" data-token="SECRET"><div id="tab-basics">
    <div class="mat-group"><div class="mat-text form-control-plaintext">0012345678</div>
    <label class="label-bg">NIP</label></div></div>
    <div class="mat-group"><label class="label-bg">Wrong</label><div class="mat-text">x</div></div></div>"""
    assert parse_contractor(source) == {"fields": {"NIP": "0012345678"}}


def test_detail_separates_tables_strips_scripts_and_decodes_namespaced_xml():
    xml = '<JPK xmlns="urn:example:v2"><Naglowek><Rok>2031</Rok></Naglowek></JPK>'
    source = f"""<div class="dialogbox" data-token="SECRET"><script>secret()</script>
    <table><tr><th>Lines</th></tr><tr><td>Demo item</td></tr></table>
    <table><tr><th>VAT</th></tr><tr><td>2,30</td></tr></table>
    <fieldset id="print-preview">{html.escape(xml)}</fieldset></div>"""
    result = parse_detail(source)
    assert len(result["tables"]) == 2
    assert result["xml"]["namespace"] == "urn:example:v2"
    assert result["xml"]["document"]["children"][0]["children"][0]["text"] == "2031"
    assert "SECRET" not in str(result)
    assert "secret()" not in str(result)


def test_xml_entities_are_rejected():
    xml = '<!DOCTYPE JPK [<!ENTITY x SYSTEM "file:///etc/passwd">]><JPK>&x;</JPK>'
    with pytest.raises(ParseError):
        parse_detail(f'<fieldset id="print-preview">{html.escape(xml)}</fieldset>')


def test_header_and_body_can_be_separate_tables_in_same_wrapper():
    source = TABLE.replace("</thead><tbody", "</thead></table><table><tbody")
    result = parse_table(source, "Invoice")
    assert result["rows"][0]["cells"]["Invoice.fullnumber"]["text"] == "DEMO/1"


def test_zus_components_keep_labels_and_column_association():
    source = TABLE.replace(
        'data-colname="Invoice.total_composed"', 'data-colname="DeclarationHeader.total"'
    )
    source = source.replace(
        'data-value="1234.123456">1 234,12 EUR',
        ">Społeczne: 100,00<br>Zdrowotne: 200,00<br>FP i FGŚP: 30,00<br><b>Razem: 330,00</b>",
    )
    result = parse_table(source, "Invoice")
    cell = result["rows"][0]["cells"]["DeclarationHeader.total"]
    assert cell["components"] == {
        "Społeczne": "100.00",
        "Zdrowotne": "200.00",
        "FP i FGŚP": "30.00",
        "Razem": "330.00",
    }
    assert cell["value"] is None


@pytest.mark.parametrize(
    "selection, expected",
    [
        (
            '<option selected value="paid">Paid</option><option selected value="unpaid">Unpaid</option>',
            ["paid", "unpaid"],
        ),
        ('<option value="paid">Paid</option>', []),
    ],
)
def test_saved_multiselect_filters_preserve_all_selected_values(selection, expected):
    source = TABLE.replace(
        "<table>", f'<select id="paymentstate" multiple>{selection}</select><table>'
    )
    assert parse_table(source, "Invoice")["filters"]["paymentstate"] == expected


def test_nonempty_metadata_with_unrecognized_rows_fails_closed():
    with pytest.raises(ParseError):
        parse_table(TABLE.replace('class="tab-data"', 'class="changed-row-markup"'), "Invoice")


def test_zus_labels_in_separate_blank_header_column_map_to_each_amount_column():
    source = """<div class="table-wrapper" data-model="DeclarationHeader"><table><thead><tr>
    <th data-colname="DeclarationHeader.zusdra" data-column=""></th>
    <th data-colname="DeclarationHeader.total" data-column="Razem">Razem</th>
    </tr></thead></table><table>
    <tbody id="tab-params" data-params='{"page":1,"show":10,"total":1,"pages":1}'>
    <tr class="tab-data" data-row-id="demo"><td data-column="">
    <div class="declaration-header-zusdra-details">Społeczne<br>Zdrowotne<br>FP i FGŚP</div>
    <div><b>Razem</b></div></td><td data-column="Razem">
    <div class="declaration-header-zusdra-details">100,00<br>200,00<br>30,00<br></div>
    <div><b>330,00</b></div></td></tr></tbody></table></div>"""
    result = parse_table(source, "DeclarationHeader")
    cell = result["rows"][0]["cells"]["DeclarationHeader.total"]
    assert cell["components"] == {
        "Społeczne": "100.00",
        "Zdrowotne": "200.00",
        "FP i FGŚP": "30.00",
        "Razem": "330.00",
    }
    assert cell["value"] is None
