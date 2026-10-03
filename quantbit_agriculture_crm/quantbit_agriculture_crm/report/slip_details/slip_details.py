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
            "label": _("Status"),
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": _("Farmer"),
            "fieldname": "farmer",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": _("Trolly Trailer 1 LL Name"),
            "fieldname": "trolly_trailer_1_ll_name",
            "fieldtype": "Data",
            "width": 140,
        },
        {
            "label": _("Trolly Trailer 2 LL Name"),
            "fieldname": "trolly_trailer_2_ll_name",
            "fieldtype": "Data",
            "width": 140,
        },
        {
            "label": _("Rope Placement LL Name"),
            "fieldname": "rope_placement_ll_name",
            "fieldtype": "Data",
            "width": 140,
        },
        {
            "label": _("Vehicle Type LL Name"),
            "fieldname": "transporter_vehicle_type_ll_name",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": _("HT Driver LL Name"),
            "fieldname": "ht_driver_ll_name",
            "fieldtype": "Data",
            "width": 140,
        },
        {
            "label": _("Transporter"),
            "fieldname": "transporter",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": _("Harvester LL Name"),
            "fieldname": "harvester_ll_name",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": _("Village LL Name"),
            "fieldname": "village_ll_name",
            "fieldtype": "Data",
            "width": 130,
        },
        {
            "label": _("Route LL Name"),
            "fieldname": "route_ll_name",
            "fieldtype": "Data",
            "width": 140,
        },
        {
            "label": _("Cane Registration"),
            "fieldname": "cane_registration",
            "fieldtype": "Link",
            "options": "Cane Registration",
            "width": 140,
        },
    ]
