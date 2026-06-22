"""Minimal markdown/text snippets for unit tests."""

COVER_PAGE = """\
Northwind PBM
Pricing Proposal
Acme Corporation
January 15, 2026
"""

TRADITIONAL_PRICING_SECTION = """\
Traditional Pricing
Administrative Fee
2026 $1.50 per approved paid claim
2027 $1.75 per approved paid claim
Network Guarantees
Broad National Retail 30 Retail 90
Brand Effective Discount 2026: AWP - 18.5 % 2026: AWP - 20.0 % 2026: AWP - 22.0 %
Generic Effective Rate 2026: AWP - 75.0 % 2026: AWP - 78.0 % 2026: AWP - 80.0 %
Mail Order
Brand Effective Discount 2026: AWP - 25.0 %
"""

REBATE_GUARANTEES_SECTION = """\
Rebate Guarantees
Northwind exclusionary formulary
Per Brand Drug — Rebates paid 150 days after the quarter
2026 1.50 2.00 3.00 4.00
2027 1.75 2.25 3.25 4.25
"""

APPLIED_REBATES_SECTION = """\
Traditional Pricing — Applied Rebates
Administrative Fee
2026 $2.00 per approved paid claim
Network Guarantees
Broad National Retail 30 Retail 90
Brand Effective Discount 2026: AWP - 20.0 % 2026: AWP - 22.0 % 2026: AWP - 24.0 %
"""

INCLUDED_SERVICES_SECTION = """\
Clinical Services (Included Services)
• Prior authorization review
• Step therapy management
Member Services
• 24/7 nurse hotline
"""

ALLOWANCES_FEES_SECTION = """\
Allowances and Ancillary Charges
Implementation Allowances
Setup and conversion $5,000 per year
Eligibility Maintenance
Monthly eligibility file Included
Additional Administrative Services
Clinical prior authorization with physician review $25.00 per claim
"""

ASSUMPTIONS_SECTION = """\
Assumptions and Caveats
General Assumptions
• Pricing assumes 50,000 covered lives.
• Rebates subject to manufacturer participation.
"""

FULL_DOCUMENT_MARKDOWN = (
    COVER_PAGE
    + "\n"
    + TRADITIONAL_PRICING_SECTION
    + "\n"
    + REBATE_GUARANTEES_SECTION
    + "\n"
    + APPLIED_REBATES_SECTION
    + "\n"
    + INCLUDED_SERVICES_SECTION
    + "\n"
    + ALLOWANCES_FEES_SECTION
    + "\n"
    + ASSUMPTIONS_SECTION
)

VALIDATOR_SOURCE = """\
Brand Effective Discount 2026: AWP - 18.5 %
Clinical prior authorization with physician review $25.00 per claim
Prior authorization review
"""
