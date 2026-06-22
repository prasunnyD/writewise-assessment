"""Enumerations for contract extraction schema values."""

from enum import Enum


class PricingModel(str, Enum):
    """Pricing model variants in a PBM contract."""

    TRADITIONAL = "traditional"
    APPLIED_REBATES = "applied_rebates"


class TermCategory(str, Enum):
    """Category of a contract term row."""

    ADMIN_FEE = "admin_fee"
    NETWORK_DISCOUNT = "network_discount"
    DISPENSING_FEE = "dispensing_fee"
    REBATE = "rebate"


class SourceSection(str, Enum):
    """Origin section for an included service or fee row."""

    INCLUDED_SERVICES = "included_services"
    ALLOWANCES_FEES = "allowances_fees"


class FeeType(str, Enum):
    """Fee classification within Allowances and Ancillary Charges."""

    ALLOWANCE = "allowance"
    ANCILLARY_FEE = "ancillary_fee"


class DrugType(str, Enum):
    """Drug type for network discount grid rows."""

    BRAND = "brand"
    GENERIC = "generic"
    LDD = "ldd"
    NEW_TO_MARKET = "new_to_market"


class RebateChannel(str, Enum):
    """Rebate payment channel."""

    RETAIL_30 = "retail_30"
    RETAIL_90 = "retail_90"
    MAIL = "mail"
    SPECIALTY = "specialty"


class PaymentSchedule(str, Enum):
    """Rebate payment timing schedule."""

    QUARTERLY_150D = "quarterly_150d"
    MONTHLY_60D = "monthly_60d"


class ValueType(str, Enum):
    """How a contract value should be interpreted."""

    NUMERIC = "numeric"
    INCLUDED = "included"
    QUOTED_UPON_REQUEST = "quoted_upon_request"
    PASS_THROUGH = "pass_through"
    TEXT = "text"


class BasisType(str, Enum):
    """Unit or basis for a numeric contract value."""

    AWP_MINUS_PERCENT = "awp_minus_percent"
    DOLLAR_PER_CLAIM = "dollar_per_claim"
    PMPM = "pmpm"
    PMPY = "pmpy"
    PER_RECORD = "per_record"
    PER_AUDIT = "per_audit"
    PER_HOUR = "per_hour"
    FLAT_ANNUAL = "flat_annual"
    PER_MEMBER = "per_member"
    PER_MEMBER_PER_YEAR = "per_member_per_year"
    PER_BRAND_DRUG = "per_brand_drug"
    OTHER = "other"
