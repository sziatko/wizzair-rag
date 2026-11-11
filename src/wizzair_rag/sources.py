"""Registry of source documents: what we download and how we cite it.

Download date and file hash are not here: download.py writes them to
data/raw/manifest.json, because they change on every run.
"""

from dataclasses import dataclass
from typing import Literal

CARRIER = "Wizz Air Hungary"
HELP_CENTRE = "https://www.wizzair.com/en-gb/help-centre"
WIZZ = "https://www.wizzair.com"


@dataclass(frozen=True)
class Source:
    id: str  # stable slug, used in file names and chunk ids
    url: str
    kind: Literal["pdf", "html", "json"]
    title: str
    # JSON body for sources fetched with POST (only the fees API so far).
    post_json: dict | None = None
    # Date the document says it is effective from. None: the page shows no date,
    # so the download date in the manifest is the only version we have.
    effective_from: str | None = None
    carrier: str = CARRIER


SOURCES: list[Source] = [
    Source(
        id="gcc-wah-2023-03-01",
        url=f"{WIZZ}/cms/api/docs/default-source/downloadable-documents/general-conditions-of-carriage/gcc-wah/gcc-wah-1-march-2023/gcc-w6_en_final_010323-clean_26d02e3b-cf3a-465d-a27d-84336897b630.pdf",
        kind="pdf",
        title="General Conditions of Carriage, Wizz Air Hungary Ltd.",
        effective_from="2023-03-01",
    ),
    Source(
        # Still linked on wizzair.com; kept to answer open question 1 (which GCC is current).
        id="gcc-wah-2020-07-01",
        url=f"{WIZZ}/cms/api/docs/default-source/downloadable-documents/general-conditions-of-carriage/gcc-wah/wah-gccs---2020---en_271dff70-51a7-497a-afa8-77c93d1af396.pdf",
        kind="pdf",
        title="General Conditions of Carriage, Wizz Air Hungary Ltd. (2020)",
        effective_from="2020-07-01",
    ),
    Source(
        id="gcc-list",
        url=f"{WIZZ}/en-gb/legal/general-conditions-of-carriage-for-passengers-and-baggage",
        kind="html",
        title="General Conditions of Carriage for passengers and baggage",
    ),
    Source(
        id="hc-cabin-baggage",
        url=f"{HELP_CENTRE}/booking-information-and-services/baggage/baggage-allowance/cabin-baggage",
        kind="html",
        title="Cabin baggage",
    ),
    Source(
        id="hc-checked-in-baggage",
        url=f"{HELP_CENTRE}/booking-information-and-services/baggage/baggage-allowance/checked-in-baggage",
        kind="html",
        title="Checked-in baggage",
    ),
    Source(
        id="hc-special-baggage",
        url=f"{HELP_CENTRE}/booking-information-and-services/baggage/special-baggage",
        kind="html",
        title="Special baggage",
    ),
    Source(
        id="hc-childrens-baggage",
        url=f"{HELP_CENTRE}/booking-information-and-services/with-children/childrens-baggage",
        kind="html",
        title="Children's baggage",
    ),
    Source(
        id="hc-restricted-items",
        url=f"{HELP_CENTRE}/restricted-items",
        kind="html",
        title="Restricted items",
    ),
    Source(
        # The parent page "damaged-delayed-and-lost-bags" is only a list of links.
        id="hc-bags-reporting-procedure",
        url=f"{HELP_CENTRE}/damaged-or-lost-bags-and-items/damaged-delayed-and-lost-bags/reporting-procedure",
        kind="html",
        title="Damaged, delayed and lost bags: reporting procedure",
    ),
    Source(
        # Question titles only: their answer links 301 to Help Centre hubs (checked 2026-11-09).
        # Real passenger wording for eval questions, not for the index.
        id="hc-faq",
        url=f"{HELP_CENTRE}/frequently-asked-questions",
        kind="html",
        title="Frequently asked questions",
    ),
    Source(
        # Page text only (intro notes); the fee table itself comes from fees-api below.
        id="fees-all-services",
        url=f"{WIZZ}/en-gb/information-and-services/prices-discounts/all-services-fees",
        kind="html",
        title="All services and fees",
    ),
    Source(
        # The API the fees page calls in the browser. Numbers only, with code names
        # (e.g. "baggage-max23" is shown as "max. 20 kg"), so citations use fees-table.txt:
        # the rendered page text, saved by hand into each snapshot (see its manifest note).
        # The version in the path changes with site deploys; a 404 here means: take the
        # new one from the page HTML.
        id="fees-api",
        url="https://be.wizzair.com/29.24.0/Api/asset/serviceFees",
        kind="json",
        title="All services and fees (fee table)",
        post_json={"currencyCodes": ["EUR"]},
    ),
    Source(
        id="fees-fares-bundles",
        url=f"{WIZZ}/en-gb/information-and-services/prices-discounts/fares-bundles",
        kind="html",
        title="Fares and bundles",
    ),
]
