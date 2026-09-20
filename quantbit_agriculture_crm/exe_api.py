import frappe
from frappe.utils import getdate, to_timedelta
from datetime import timedelta
import json
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import traceback
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3
from frappe.model.document import Document
import json
from frappe.utils import getdate, to_timedelta
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

# Suppress SSL warnings when using verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

@frappe.whitelist()
def get_data(trip_sheet, season, posting_date, posting_time):
    trip_data = frappe.db.sql("""
        SELECT
            *
        FROM 
            `tabTrip Sheet`
        WHERE name = %s
        LIMIT 1
    """, (trip_sheet,), as_dict=True)

    penalty_charges = frappe.db.sql("""
        SELECT
            *
        FROM 
            `tabTrip Sheet Penalty Charges`
        WHERE 
            parent = %s
    """, (trip_sheet,), as_dict=True)
    

    if not trip_data:
        frappe.throw(f"No Trip Sheet found with name {trip_sheet}")

    t = trip_data[0]
    data_key = {}

    ll_names = {}
    if t.get('json'):
        try:
            ll_names = json.loads(t.json)
        except (json.JSONDecodeError, TypeError) as e:
            frappe.log_error(f"Error parsing json JSON: {str(e)}", "Trip Sheet JSON Parse Error")
            ll_names = {}

    shift_data = get_shift_season_factory_day(
        posting_date=posting_date,
        posting_time=posting_time,
        season=season
    )

    data_key["shift"] = shift_data.get("shift")
    data_key["season_day"] = shift_data.get("season_day")
    data_key["factory_day"] = shift_data.get("factory_day")
    data_key["effective_date"] = shift_data.get("effective_date")

    diesel_allocation = diesel_allocation_method(
        season=season,
        vehicle_type=t.transporter_vehicle_type,
        distance=t.distance or 0
    )
    data_key["diesel_allocation"] = diesel_allocation
    auto_token_details= get_auto_token_details_form_trip_sheet(t.name)

    data_key["cart_no"] = t.cart_no
    data_key["json"] = t.json
    data_key["binding_weight_percent"] = get_binding_weight_percentage(t.transporter_vehicle_type) or 1

    data_key["trip_sheet"] = t.name
    data_key["season"] = t.season
    data_key["branch"] = t.branch
    data_key["company"] = t.company
    data_key["cane_registration"] = t.cane_registration
    data_key["crop_variety"] = t.crop_variety
    data_key["route"] = t.route
    data_key["farmer"] = t.farmer
    data_key["crop_type"] = t.crop_type
    data_key["distance"] = t.distance
    data_key["is_flat_rate"] = t.is_flat_rate
    data_key["farmer_name"] = t.farmer_name
    data_key["area_in_acrs"] = t.area_in_acrs
    data_key["circle_office"] = t.circle_office
    data_key["survey_number"] = t.survey_number
    data_key["is_kisan_card"] = t.is_kisan_card
    data_key["village"] = t.village
    data_key["transporter_contract"] = t.transporter_contract
    data_key["transporter"] = t.transporter
    data_key["harvester_contract"] = t.harvester_contract
    data_key["harvester"] = t.harvester
    data_key["transporter_name"] = t.transporter_name
    data_key["transporter_vehicle_type"] = t.transporter_vehicle_type
    data_key["transporter_gang_type"] = t.transporter_gang_type
    data_key["vehicle_no"] = t.vehicle_no
    data_key["trolly_1"] = t.trolly_1
    data_key["trolly_2"] = t.trolly_2
    data_key["ht_driver"] = t.ht_driver
    data_key["cart_no"] = t.cart_no
    data_key["harvester_name"] = t.harvester_name
    data_key["harvester_vehicle_type"] = t.harvester_vehicle_type
    data_key["harvester_gang_type"] = t.harvester_gang_type
    data_key["cane_deduction_type"] = t.cane_deduction_type
    data_key["deduction"] = t.deduction
    data_key["water_supplier_code"] = t.water_supplier_code
    data_key["water_supplier_name"] = t.water_supplier_name
    data_key["water_share"] = t.water_share
    data_key["rope_placement"] = t.rope_placement
    data_key["slip_boy"] = t.slip_boy
    data_key["slip_boy_name"] = t.slip_boy_name 
    data_key["token_time"] = t.token_time or auto_token_details.get("token_time") if auto_token_details else None
    data_key["auto_token_no"] = t.auto_token_no or auto_token_details.get("auto_token_no") if auto_token_details else None
    data_key["token_date"] = t.token_date or auto_token_details.get("token_date") if auto_token_details else None
    data_key["token_user"] = t.token_user or auto_token_details.get("token_user") if auto_token_details else None
    data_key["token_no"] = t.token_no or auto_token_details.get("token_no") if auto_token_details else None

    data_key["rope_placement_ll_name"] = ll_names.get("rope_placement_ll_name")
    data_key["seed_type_ll_name"] = ll_names.get("seed_type_ll_name")
    data_key["taluka_ll_name"] = ll_names.get("taluka_ll_name")
    data_key["cane_deduction_type_ll_name"] = ll_names.get("cane_deduction_type_ll_name")
    data_key["harvester_vehicle_type_ll_name"] = ll_names.get("harvester_vehicle_type_ll_name")
    data_key["water_supplier_ll_name"] = ll_names.get("water_supplier_ll_name")
    data_key["crop_variety_ll_name"] = ll_names.get("crop_variety_ll_name")
    data_key["crop_seed_ll_name"] = ll_names.get("crop_seed_ll_name")
    data_key["district_ll_name"] = ll_names.get("district_ll_name")
    data_key["harvester_gang_type_ll_name"] = ll_names.get("harvester_gang_type_ll_name")
    data_key["crop_type_ll_name"] = ll_names.get("crop_type_ll_name")
    data_key["irrigation_method_ll_name"] = ll_names.get("irrigation_method_ll_name")
    data_key["state_ll_name"] = ll_names.get("state_ll_name")
    data_key["farmer_ll_name"] = ll_names.get("farmer_ll_name")
    data_key["transporter_ll_name"] = ll_names.get("transporter_ll_name")
    data_key["transporter_vehicle_type_ll_name"] = ll_names.get("transporter_vehicle_type_ll_name")
    data_key["soil_type_ll_name"] = ll_names.get("soil_type_ll_name")
    data_key["circle_office_ll_name"] = ll_names.get("circle_office_ll_name")
    data_key["route_ll_name"] = ll_names.get("route_ll_name")
    data_key["harvester_ll_name"] = ll_names.get("harvester_ll_name")
    data_key["transporter_gang_type_ll_name"] = ll_names.get("transporter_gang_type_ll_name")
    data_key["penalty_charges"] = []
    
    for penalty_charge in penalty_charges:
        data_key["penalty_charges"].append({
            "entity_code": penalty_charge.entity_code,
            "entity_name": penalty_charge.entity_name,
            "entity_type": penalty_charge.entity_type,
            "deduction_type": penalty_charge.deduction_type,
            "deduction_method": penalty_charge.deduction_method,
            "deduction_rate": penalty_charge.deduction_rate,
        })

    return data_key

@frappe.whitelist()
def diesel_allocation_method(season, vehicle_type, distance):
	ds_alloc = frappe.db.get_value("Fuel Station Criteria",
		{"season": season, "criteria": "Per Km", "vehicle_type": vehicle_type, "parent": season},
		["allocated_quantity"]
	)
	if not ds_alloc:
		return 0

	if distance <= 10:
		return 10
	else:
		final_d = distance - 10
		value = ds_alloc * final_d
		return int(value + 10)

@frappe.whitelist()
def get_shift_season_factory_day(posting_date=None, posting_time=None, season=None):
    posting_date = getdate(posting_date) if posting_date else None
    shift = None
    shift_previous_day = False 

    # === Determine Shift ===
    if posting_time:	
        shift_data = frappe.db.sql("""
            SELECT name as shift_name, start_time, end_time
            FROM `tabFactory Shift`
            WHERE disabled = 0
            ORDER BY start_time
        """, as_dict=True)

        posting_seconds = to_timedelta(posting_time).total_seconds()
        
        for s in shift_data:
            start = s.start_time.total_seconds()
            end = s.end_time.total_seconds()

            # Detect night shift (crosses midnight when end < start)
            if end < start:
                if posting_seconds >= start or posting_seconds <= end:
                    shift = s.shift_name
                    
                    if posting_seconds <= end:
                        shift_previous_day = True
                    break
            else:
                if start <= posting_seconds <= end:
                    shift = s.shift_name
                    shift_previous_day = False
                    break

        shift = shift

    # === Adjust posting date for night shift ===
    effective_posting_date = posting_date
    if shift_previous_day and posting_date:
        effective_posting_date = posting_date - timedelta(days=1)

    season_day = 0
    factory_day = 0

    if effective_posting_date and season:
        season_data = frappe.db.sql("""
            SELECT factory_start_date, factory_end_date
            FROM `tabSeason`
            WHERE disabled = 0 AND name = %s
        """, (season,), as_dict=True)

        if season_data:
            data = season_data[0]
            factory_start = getdate(data.factory_start_date)
            factory_end = getdate(data.factory_end_date)

            if factory_start <= effective_posting_date <= factory_end:
                factory_day = (effective_posting_date - factory_start).days + 1
                season_day = factory_day  # Both based on factory start
            else:
                factory_day = 0
                season_day = 0

    return {
        "shift": shift or "",
        "season_day": season_day or 0,
        "factory_day": factory_day or 0,
        "factory_date": effective_posting_date,
        "season":season
    }


@frappe.whitelist()
def get_binding_weight_percentage(vehicale_type):
	binding_weight_percentage_setting = frappe.db.get_value("Weight Settings Details",
        {"vehicle_type": vehicale_type},"percentage")
	return binding_weight_percentage_setting or 1

@frappe.whitelist(allow_guest=False)
def get_trip_sheet_data(trip_sheet, season=None, posting_date=None, posting_time=None):
   
	try:
		data = get_data(trip_sheet, season, posting_date, posting_time)
		return {
			"success": True,
			"data": data
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "get_trip_sheet_data API Error")
		return {
			"success": False,
			"error": str(e)
		}
    
@frappe.whitelist(allow_guest=False)
def get_cane_weight_data(trip_sheet, season , posting_date , posting_time):
    """Fetch Cane Weight + Trip Sheet + Auto Token details with penalty structure."""
    if not trip_sheet:
        return {"status": "error", "message": "Trip Sheet Number is required"}

    try:
        data = {}
        status = ""
        
        trip_sheet_doc = frappe.db.get_value("Trip Sheet",{"name": trip_sheet,"season": season},
            ["name", "status"],
            as_dict=True
        )

        if not trip_sheet_doc:
            frappe.throw(f"Trip Sheet {trip_sheet} not found for season {season}.")

        # Trip Sheet must be Submitted Token before Cane Weight
        if trip_sheet_doc.status != "Submitted Token":
            frappe.throw(
                f"Trip Sheet {trip_sheet} is not in 'Submitted Token' status. "
                f"Current status is '{trip_sheet_doc.status or 'Not Set'}'. "
                f"Please complete the Auto Token process first."
            )

        if trip_sheet_doc.status == "Weight Done":
            frappe.throw(
                f"Trip Sheet {trip_sheet} is already in 'Weight Done' status."
                f"Weight is already done for this trip sheet."
            )

        # === 1️⃣ Check if Cane Weight Already Exists ===
        is_exists = frappe.db.exists("Cane Weight", {
            "trip_sheet": trip_sheet,
            "season": season,
            "docstatus": ["!=", 2]
        })

        if is_exists:
            # === 2️⃣ Fetch Existing Cane Weight Document ===
            cw_doc = frappe.get_doc("Cane Weight", {
                "trip_sheet": trip_sheet,
                "season": season,
                "docstatus": ["!=", 2]
            })

            excluded_fields = [
                'doctype', 'owner', 'creation', 'modified', 'modified_by',
                'docstatus', 'idx', 'column_break', 'section_break', 'amended_from',
                '__islocal', '__unsaved', '__onload',

            ]

            for field in cw_doc.meta.fields:
                if (field.fieldname not in excluded_fields and
                    field.fieldtype not in ['Column Break', 'Section Break', 'Tab Break']):
                    data[field.fieldname] = cw_doc.get(field.fieldname)

            data["binding_weight_percent"] = get_binding_weight_percentage(cw_doc.transporter_vehicle_type) or 1

            status = "Draft" if cw_doc.docstatus == 0 else "Submitted"

        else:
            data = get_data(trip_sheet, season, posting_date, posting_time)

        return {
            "status": "success",
            "message": f"Cane Weight Data {status}",
            "doc_status": status,
            "data": data,
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "get_cane_weight_data_with_token API Failed")
        return {"status": "error", "message": str(e)}

def get_auto_token_details_form_trip_sheet(trip_sheet):
    token_parent = frappe.db.get_value(
        "Auto Token Trip sheet Details",
        {"trip_sheet_no": trip_sheet},
        "parent"
    )
    token = frappe.db.get_value(
        "Auto Token",
        {"name": token_parent},
        ["name", "token_no", "posting_time", "posting_date","creator"],
        as_dict=True
    )
    if token:
        return {
            "auto_token_no": token.name,
            "token_no": token.token_no,
            "token_date": token.posting_date,
            "token_time": token.posting_time,
            "token_user": token.creator
        }
    return None



def _find_existing_cane_weight(trip_sheet):
    """Look up a non-cancelled Cane Weight for a Trip Sheet, if any."""
    return frappe.db.get_value(
        "Cane Weight",
        {"trip_sheet": trip_sheet, "docstatus": ["!=", 2]},
        "name"
    )


def _apply_actual_weight(doc, data):
    """Load posted data onto a Cane Weight doc and recompute its weight fields."""
    doc.update(data)
    doc.actual_weight()
    doc.calculate_penalty_weights()
    return doc


@frappe.whitelist()
def save_cane_weight_form(data):
    try:
        data = frappe.parse_json(data)
        frappe.log_error(title="save_cane_weight_form called", message=f"save_cane_weight_form called {str(data)}")

        slip_no = data.get("trip_sheet")
        existing_doc = _find_existing_cane_weight(slip_no) if slip_no else None

        if existing_doc:
            doc = frappe.get_doc("Cane Weight", existing_doc)
            _apply_actual_weight(doc, data)
            doc.docstatus = 0  # Ensure it stays as draft
            doc.save()
            return {
                "success": True,
                "message": "Cane Weight updated successfully (found by slip_no)",
                "data": {"name": doc.name}
            }

        # Create new document
        doc = frappe.new_doc("Cane Weight")
        _apply_actual_weight(doc, data)
        doc.docstatus = 0  # Save as draft
        doc.insert()
        return {
            "success": True,
            "message": "Cane Weight saved successfully",
            "data": {"name": doc.name}
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "save_cane_weight_form Error")
        return {
            "success": False,
            "error": str(e)
        }

@frappe.whitelist()
def submit_cane_weight_form(data):
    """Submit Cane Weight form (docstatus=1).
    Checks if document exists based on slip_no, then updates and submits or creates and submits accordingly."""
    try:
        data = frappe.parse_json(data)
        frappe.log_error(title="submit_cane_weight_form called", message=f"submit_cane_weight_form called {str(data)}")

        slip_no = data.get("trip_sheet")
        if not slip_no:
            return {
                "success": False,
                "message": "Cane Weight data Must be with Slip No Detailes",
                "data": None
            }

        existing_doc = _find_existing_cane_weight(slip_no)

        if existing_doc:
            doc = frappe.get_doc("Cane Weight", existing_doc)
            _apply_actual_weight(doc, data)
            doc.submit()
            return {
                "success": True,
                "message": "Cane Weight updated and submitted successfully (found by slip_no)",
                "data": {"name": doc.name}
            }

        # No draft exists yet for this trip sheet - create and submit in one go
        doc = frappe.new_doc("Cane Weight")
        _apply_actual_weight(doc, data)
        doc.insert()
        doc.submit()
        return {
            "success": True,
            "message": "Cane Weight created and submitted successfully",
            "data": {"name": doc.name}
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "submit_cane_weight_form Error")
        return {
            "success": False,
            "error": str(e)
        }


def _find_existing_other_weight(name):
    """Look up a non-cancelled Other Weight by name, if any (the EXE sends
    `name` back once a document has been saved/loaded, so re-saving or
    submitting updates that same document instead of creating a duplicate)."""
    if not name:
        return None
    return frappe.db.get_value(
        "Other Weight",
        {"name": name, "docstatus": ["!=", 2]},
        "name"
    )


def _apply_other_weight_data(doc, data):
    """Load posted data onto an Other Weight doc. doctype/name/docstatus are
    managed by the caller, not by the posted data itself."""
    doc.update({k: v for k, v in data.items() if k not in ("doctype", "name", "docstatus")})
    return doc


@frappe.whitelist()
def save_other_weight_form(data):
    """Save Other Weight form (docstatus=0). Updates the existing document
    when `data.name` refers to a non-cancelled draft, otherwise creates one."""
    try:
        data = frappe.parse_json(data)
        frappe.log_error(title="save_other_weight_form called", message=f"save_other_weight_form called {str(data)}")

        existing_doc = _find_existing_other_weight(data.get("name"))

        if existing_doc:
            doc = frappe.get_doc("Other Weight", existing_doc)
            _apply_other_weight_data(doc, data)
            doc.docstatus = 0  # Ensure it stays as draft
            doc.save()
            return {
                "success": True,
                "message": "Other Weight updated successfully",
                "data": {"name": doc.name}
            }

        # Create new document
        doc = frappe.new_doc("Other Weight")
        _apply_other_weight_data(doc, data)
        doc.docstatus = 0  # Save as draft
        doc.insert()
        return {
            "success": True,
            "message": "Other Weight saved successfully",
            "data": {"name": doc.name}
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "save_other_weight_form Error")
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist()
def submit_other_weight_form(data):
    """Submit Other Weight form (docstatus=1). Updates and submits the
    existing document when `data.name` refers to a non-cancelled draft,
    otherwise creates and submits it in one go."""
    try:
        data = frappe.parse_json(data)
        frappe.log_error(title="submit_other_weight_form called", message=f"submit_other_weight_form called {str(data)}")

        existing_doc = _find_existing_other_weight(data.get("name"))

        if existing_doc:
            doc = frappe.get_doc("Other Weight", existing_doc)
            _apply_other_weight_data(doc, data)
            doc.submit()
            return {
                "success": True,
                "message": "Other Weight updated and submitted successfully",
                "data": {"name": doc.name}
            }

        doc = frappe.new_doc("Other Weight")
        _apply_other_weight_data(doc, data)
        doc.insert()
        doc.submit()
        return {
            "success": True,
            "message": "Other Weight created and submitted successfully",
            "data": {"name": doc.name}
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "submit_other_weight_form Error")
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist(allow_guest=False)
def get_other_weight_records(limit_page_length=50):
    """List submitted (docstatus=1) Other Weight records, for the EXE's
    'View Submitted Records' dialog."""
    try:
        records = frappe.get_all(
            "Other Weight",
            filters={"docstatus": 1},
            fields=["name", "season", "party_name", "vehicle_no", "weight_in", "actual_weight", "modified"],
            order_by="modified desc",
            limit_page_length=limit_page_length,
        )
        return {"success": True, "data": records}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "get_other_weight_records Error")
        return {"success": False, "error": str(e)}


@frappe.whitelist(allow_guest=False)
def get_other_weight_record(name):
    """Fetch one full Other Weight document, for 'load selected record' in
    the EXE's View Submitted Records dialog."""
    try:
        doc = frappe.get_doc("Other Weight", name)
        return {"success": True, "data": doc.as_dict()}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "get_other_weight_record Error")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def sync_trip_sheets():
    try:
        trip_sheets = frappe.get_all(
            "Trip Sheet",
            filters={"status": "Submitted Token", "is_sync": 0},
            fields=["*"]
        )
        clean_fields = {
            "creation",
            "modified",
            "modified_by",
            "owner",
            "docstatus",
            "idx",
            "_user_tags",
            "_comments",
            "_assign",
            "_liked_by"
        }

        cleaned_data = []

        for ts in trip_sheets:
            ts["trip_sheet"] = ts.name
            # Add Auto Token details
            token_parent = frappe.db.get_value(
                "Auto Token Trip sheet Details",
                {"trip_sheet_no": ts.name},
                "parent"
            )
            token = frappe.db.get_value(
                "Auto Token",
                {"name": token_parent},
                ["name", "token_no", "posting_time", "posting_date","creator"],
                as_dict=True
            )
            penalty_charges = frappe.db.sql("""SELECT
                                *
                            FROM 
                                `tabTrip Sheet Penalty Charges`
                            WHERE 
                                parent = %s
                        """, (ts.name,), as_dict=True)

            if penalty_charges:
                ts["penalty_charges"] = penalty_charges
            
            if token:
                ts["auto_token_no"] = token.name
                ts["token_no"] = token.token_no
                ts["token_date"] = token.posting_date
                ts["token_time"] = token.posting_time
                ts["token_user"]= token.creator

            # Remove unwanted fields
            for field in clean_fields:
                ts.pop(field, None)

            cleaned_data.append(ts)

        return {
            "success": True,
            "data": cleaned_data
        }

    except Exception as e:
        frappe.log_error(f"Error in sync_trip_sheets: {str(e)}")
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }
