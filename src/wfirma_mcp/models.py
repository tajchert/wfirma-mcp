"""Explicit tool schemas; strings preserve identifiers and monetary precision."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Year = Annotated[int, Field(ge=1900, le=9999, strict=True, description="Calendar year")]
Month = Annotated[int, Field(ge=1, le=12, strict=True, description="Calendar month, 1–12")]
RecordID = Annotated[
    str,
    Field(
        pattern=r"^[A-Za-z0-9_-]+$",
        min_length=1,
        max_length=256,
        description="Opaque ID from a previously returned record/link",
    ),
]
ISODate = Annotated[
    str,
    Field(
        pattern=r"^\d{4}-\d{2}-\d{2}$", max_length=10, description="ISO calendar date YYYY-MM-DD"
    ),
]
DecimalString = Annotated[str, Field(pattern=r"^[+-]?\d+(?:\.\d+)?$")]


class ResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Cell(ResultModel):
    text: str
    value: DecimalString | None
    links: list[str]
    lines: list[str] | None = None
    components: dict[str, DecimalString | None] | None = None


class Row(ResultModel):
    id: str | None
    type: str | None
    cells: dict[str, Cell]


class Pagination(ResultModel):
    page: int = Field(ge=1)
    show: int = Field(ge=1)
    total: int = Field(ge=0)
    pages: int = Field(ge=0)


class Period(ResultModel):
    mode: Literal["range", "selected"]
    year: str | None = None
    month: str | None = None
    quarter: str | None = None
    date_from: str | None = None
    date_to: str | None = None


class TableResult(ResultModel):
    company_id: str
    model: str
    table_url: str | None
    rows: list[Row]
    pagination: Pagination
    returned_count: int = Field(ge=0)
    complete: bool = Field(description="True only when all rows of the filtered table are returned")
    period: Period
    filters: dict[str, str | list[str]]
    warnings: list[str]


class SessionStatus(ResultModel):
    authenticated: bool
    company_id: str
    company_pinned: bool
    accounting_access: Literal["read-only"]


class ContractorResult(ResultModel):
    company_id: str
    id: str
    fields: dict[str, str]


class DetailTable(ResultModel):
    rows: list[Row]


class XMLNode(ResultModel):
    tag: str
    text: str
    attributes: dict[str, str]
    children: list["XMLNode"]


class XMLDocument(ResultModel):
    namespace: str | None
    document: XMLNode


class DetailResult(ResultModel):
    company_id: str
    id: str
    tables: list[DetailTable]
    text: str
    xml: XMLDocument | None = None
