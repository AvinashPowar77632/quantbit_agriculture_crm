# Copyright (c) 2026, Quantbit and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from quantbit_agriculture_crm.exe_api import get_auto_token_trip_sheets


def execute(filters=None):
    if not filters:
        filters = {}

    columns = get_columns()
    data = []

    transporter_contract = (filters.get("transporter_contract") or "").strip()
    trip_sheet_no = (filters.get("trip_sheet") or filters.get("trip_sheet_no") or "").strip()
    cane_registration = (filters.get("cane_registration") or "").strip()
    farmer = (filters.get("farmer") or "").strip()

    try:
        res = get_auto_token_trip_sheets(
            transporter_contract=transporter_contract,
            trip_sheet_no=trip_sheet_no,
            cane_registration=cane_registration,
            farmer=farmer,
        )
        data = res.get("trip_sheets") or res.get("sheets") or []
    except Exception as e:
        frappe.msgprint(str(e))
        return columns, []

    return columns, data


def get_columns():
    return [
        {
            "label": _("Trip Sheet"),
            "fieldname": "name",
            "fieldtype": "Link",
            "options": "Trip Sheet",
            "width": 140,
        },
        {
            "label": _("Slip No"),
            "fieldname": "slip_no",
            "fieldtype": "Int",
            "width": 90,
        },
        {
            "label": _("Trolly Trailer 1"),
            "fieldname": "trolly_trailer_1",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": _("Trolly Trailer 2"),
            "fieldname": "trolly_trailer_2",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": _("Rope Placement"),
            "fieldname": "rope_placement",
            "fieldtype": "Data",
            "width": 140,
        },
        {
            "label": _("Transporter Vehicle Type"),
            "fieldname": "transporter_vehicle_type",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": _("HT Driver"),
            "fieldname": "ht_driver",
            "fieldtype": "Data",
            "width": 140,
        },
        {
            "label": _("Farmer"),
            "fieldname": "farmer",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": _("Cane Registration"),
            "fieldname": "cane_registration",
            "fieldtype": "Link",
            "options": "Cane Registration",
            "width": 140,
        },
        {
            "label": _("Transporter Contract Name"),
            "fieldname": "transporter_contract_name",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": _("Harvestor Contract Name"),
            "fieldname": "harvester_contract_name",
            "fieldtype": "Data",
            "width": 180,
        },
    ]
