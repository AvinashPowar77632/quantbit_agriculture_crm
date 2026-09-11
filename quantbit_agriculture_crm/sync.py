import frappe
import requests
import json
from datetime import datetime, date, time, timedelta
from requests.adapters import HTTPAdapter, Retry
from frappe.utils import getdate, to_timedelta, now_datetime, add_days
from requests.packages.urllib3.util.retry import Retry

def _log(title, message):
    """Helper to prefix every log with a timestamp."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    frappe.log_error(title, f"[{ts}] {message}")


CHILD_ROW_SYSTEM_FIELDS = [
    "name", "creation", "modified", "modified_by", "owner",
    "docstatus", "idx", "parent", "parentfield", "parenttype",
    "_liked_by", "_assign", "_comments", "_user_tags"
]

# Scalar-field system keys stripped from the top-level remote doc (not from table fields).
TRIP_SHEET_SCALAR_FIELDS_TO_STRIP = [
    "creation", "modified", "modified_by", "owner", "docstatus",
    "_liked_by", "_assign", "_comments", "_user_tags", "idx", "diesel_allocated"
]

# How many local writes to batch into a single frappe.db.commit(). Each record still gets
# its own savepoint, so one bad record only rolls back that record, not the whole batch.
TRIP_SHEET_COMMIT_BATCH_SIZE = 20


def _clean_child_rows(rows):
    """Strip system/meta fields from child table rows so Frappe can re-create them
    under the new parent instead of colliding with remote names."""
    cleaned = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row = dict(row)  # don't mutate original
        for f in CHILD_ROW_SYSTEM_FIELDS:
            row.pop(f, None)
        cleaned.append(row)
    return cleaned


def _safe_convert(obj, table_fields, unexpected_lists, is_table_list=False):
    """Recursively coerce date/time types to strings while preserving legitimate
    child-table lists; any other stray list is flagged via `unexpected_lists`."""
    if isinstance(obj, dict):
        return {
            k: _safe_convert(v, table_fields, unexpected_lists, is_table_list=(k in table_fields))
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        if is_table_list:
            # Legitimate child table data — recurse into each row, keep as list
            return [_safe_convert(row, table_fields, unexpected_lists) for row in obj]
        unexpected_lists.append(obj)
        return obj[0] if obj else None
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, time):
        return obj.strftime("%H:%M:%S")
    elif isinstance(obj, timedelta):
        sec = int(obj.total_seconds())
        return f"{sec//3600:02d}:{(sec%3600)//60:02d}:{sec%60:02d}"
    return obj


def _mark_trip_sheet_synced_on_remote(session, base_url, name):
    """Best-effort notify the remote site that a Trip Sheet was pulled in successfully."""
    try:
        session.put(
            f"{base_url}/api/resource/Trip Sheet/{name}",
            json={"is_sync": 1},
            timeout=10
        )
    except Exception as e:
        _log("Remote Update Error", f"{name}: Failed to mark as synced: {str(e)}")


@frappe.whitelist()
def sync_trip_sheet_remote_to_local():
    """Optimized: fetch Trip Sheet data from remote API and insert/update locally one by one."""
    local_doctype = "Trip Sheet"
    total_synced, total_failed = 0, 0
    sync_details = []

    # Dynamically detect which fields on Trip Sheet are child tables
    meta = frappe.get_meta(local_doctype)
    table_fields = {df.fieldname for df in meta.get_table_fields()}

    try:
        sites = frappe.get_all("Site Configuration", fields=["name", "site", "user", "password"])
        if not sites:
            return {"success": False, "message": "No site configurations found"}

        _log("Sync Start", f"Found {len(sites)} remote sites")

        for site in sites:
            base_url = site.site.rstrip("/")
            session = requests.Session()

            # --- Authenticate ---
            try:
                resp = session.post(
                    f"{base_url}/api/method/login",
                    data={"usr": site.user, "pwd": site.password},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=10,
                )
                if resp.status_code != 200 or "message" not in resp.json():
                    _log("Auth Failed", f"{site.name}: status {resp.status_code}, body: {resp.text[:200]}")
                    continue
            except Exception as e:
                _log("Auth Exception", f"{site.name}: {str(e)}")
                continue

            # --- Fetch remote Trip Sheet data ---
            try:
                remote_response = session.get(
                    f"{base_url}/api/method/quantbit_agriculture_crm.exe_api.sync_trip_sheets",
                    timeout=30,
                )

                if remote_response.status_code != 200:
                    _log("API Error", f"{site.name}: status {remote_response.status_code}, "
                                       f"raw: {remote_response.text[:300]}")
                    continue

                response_json = remote_response.json()

                if "message" in response_json and isinstance(response_json["message"], dict):
                    remote_data = response_json["message"].get("data", [])
                else:
                    remote_data = response_json.get("data", [])

                if not isinstance(remote_data, list):
                    _log("Invalid Data Format", f"{site.name}: expected list, got {type(remote_data)}, "
                                                 f"raw: {remote_response.text[:300]}")
                    continue

                if not remote_data:
                    _log("No Data", f"{site.name}: No trip sheets to sync")
                    continue

                _log("Remote Fetch", f"{site.name}: {len(remote_data)} records found")
            except Exception as e:
                _log("Remote Fetch Error", f"{site.name}: {str(e)}")
                continue

            # One query for the whole batch instead of a per-record frappe.db.exists() call
            remote_names = [d.get("name") for d in remote_data if d.get("name")]
            existing_names = set(
                frappe.get_all(local_doctype, filters={"name": ["in", remote_names]}, pluck="name")
            ) if remote_names else set()

            pending_remote_updates = []  # (name,) staged for "mark as synced" after the next commit

            # --- Iterate through all Trip Sheets ---
            for doc in remote_data:
                name = doc.get("name")
                if not name:
                    _log("Missing Name", f"{site.name}: Skipping document with no name")
                    continue

                # Clean system fields (but never touch table fields like penalty_charges)
                for f in TRIP_SHEET_SCALAR_FIELDS_TO_STRIP:
                    if f not in table_fields:
                        doc.pop(f, None)

                # Handle json field
                json_field = doc.get("json")
                list_fields_found = []
                if json_field:
                    try:
                        json_data = json.loads(json_field)
                        for k, v in json_data.items():
                            if isinstance(v, list) and k not in table_fields:
                                list_fields_found.append((k, v))
                                doc[k] = v[0] if v else None
                            else:
                                doc[k] = v
                    except json.JSONDecodeError as e:
                        _log("JSON Parse Error", f"{name}: Invalid JSON: {str(e)}")
                        continue

                # Flatten stray scalar-field lists ONLY — never touch table fields
                for k, v in list(doc.items()):
                    if isinstance(v, list) and k not in table_fields:
                        list_fields_found.append((k, v))
                        doc[k] = v[0] if v else None

                if list_fields_found:
                    _log("List Fields Detected", f"{name}: {list_fields_found}")

                # Safe date conversion — preserves table-field lists as lists of dicts
                unexpected_lists = []
                doc = {
                    k: _safe_convert(v, table_fields, unexpected_lists, is_table_list=(k in table_fields))
                    for k, v in doc.items()
                }
                if unexpected_lists:
                    _log("Unexpected List in safe_convert", f"{name}: {unexpected_lists}")

                # Clean child table rows (strip name/parent/creation etc so Frappe re-creates them)
                for tf in table_fields:
                    if isinstance(doc.get(tf), list):
                        doc[tf] = _clean_child_rows(doc[tf])

                save_point = f"trip_sheet_sync_{frappe.generate_hash(length=10)}"
                frappe.db.savepoint(save_point)
                try:
                    field_errors = []
                    if name in existing_names:
                        # --- Update existing ---
                        local_doc = frappe.get_doc(local_doctype, name)
                        for k, v in doc.items():
                            if hasattr(local_doc, k):
                                try:
                                    if k in table_fields:
                                        local_doc.set(k, [])  # clear existing rows first
                                        for row in v:
                                            local_doc.append(k, row)
                                    else:
                                        local_doc.set(k, v)
                                except Exception as e:
                                    field_errors.append(f"{k}={v}: {str(e)}")
                                    continue
                        local_doc.save(ignore_permissions=True)
                        action = "Updated"
                    else:
                        # --- Insert new ---
                        new_doc = frappe.new_doc(local_doctype)
                        for k, v in doc.items():
                            if k == "name":
                                continue
                            try:
                                if k in table_fields:
                                    for row in v:
                                        new_doc.append(k, row)
                                else:
                                    new_doc.set(k, v)
                            except Exception as e:
                                field_errors.append(f"{k}={v}: {str(e)}")
                                continue
                        new_doc.name = name
                        new_doc.insert(ignore_permissions=True)
                        action = "Inserted"
                        existing_names.add(name)

                    if field_errors:
                        _log("Field Set Error", f"{name}: {field_errors}")

                    pending_remote_updates.append(name)
                    total_synced += 1
                    sync_details.append({"site": site.name, "name": name, "action": action, "status": "OK"})

                    # Batch commits: one round trip per N records instead of every record.
                    # The savepoint above still isolates a bad record from a good one.
                    if len(pending_remote_updates) >= TRIP_SHEET_COMMIT_BATCH_SIZE:
                        frappe.db.commit()
                        for synced_name in pending_remote_updates:
                            _mark_trip_sheet_synced_on_remote(session, base_url, synced_name)
                        pending_remote_updates = []

                except Exception as e:
                    _log("Local Save Error", f"{name}: {str(e)[:300]}")
                    total_failed += 1
                    sync_details.append({"site": site.name, "name": name, "status": "Failed", "error": str(e)[:100]})
                    frappe.db.rollback(save_point=save_point)
                    continue

            # Flush whatever is left in the batch for this site
            if pending_remote_updates:
                frappe.db.commit()
                for synced_name in pending_remote_updates:
                    _mark_trip_sheet_synced_on_remote(session, base_url, synced_name)

        msg = f"Sync done: {total_synced} OK, {total_failed} failed"
        _log("Sync Complete", msg)
        return {"success": True, "message": msg, "synced": total_synced, "failed": total_failed, "details": sync_details}

    except Exception as e:
        _log("Critical Error", str(e))
        frappe.db.rollback()
        return {"success": False, "message": str(e)}

def delete_old_error_logs():
    """Delete Error Log entries older than 20 days. Runs every 6 hours via cron."""
    ts = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    cutoff_date = add_days(now_datetime(), -20)

    try:
        old_logs = frappe.get_all(
            "Error Log",
            filters={"creation": ["<", cutoff_date]},
            pluck="name"
        )

        if not old_logs:
            return

        batch_size = 500
        total_deleted = 0

        for i in range(0, len(old_logs), batch_size):
            batch = old_logs[i:i + batch_size]
            frappe.db.delete("Error Log", {"name": ["in", batch]})
            frappe.db.commit()
            total_deleted += len(batch)

        frappe.log_error(
            "Error Log Cleanup",
            f"[{ts}] Deleted {total_deleted} Error Log records older than {cutoff_date}"
        )

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            "Error Log Cleanup Failed",
            f"[{ts}] {str(e)}"
        )


def delete_old_activity_logs():
    """Delete Activity Log entries older than 20 days. Runs every 6 hours via cron."""
    ts = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    cutoff_date = add_days(now_datetime(), -20)

    try:
        old_logs = frappe.get_all(
            "Activity Log",
            filters={"creation": ["<", cutoff_date]},
            pluck="name"
        )

        if not old_logs:
            return

        batch_size = 500
        total_deleted = 0

        for i in range(0, len(old_logs), batch_size):
            batch = old_logs[i:i + batch_size]
            frappe.db.delete("Activity Log", {"name": ["in", batch]})
            frappe.db.commit()
            total_deleted += len(batch)

        frappe.log_error(
            "Activity Log Cleanup",
            f"[{ts}] Deleted {total_deleted} Activity Log records older than {cutoff_date}"
        )

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error("Activity Log Cleanup Failed",
            f"[{ts}] {str(e)}"
        )


def _convert_dates_for_json(obj):
    """Recursively convert datetime/date/time/timedelta values to JSON-serializable strings."""
    if isinstance(obj, dict):
        return {k: _convert_dates_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_dates_for_json(item) for item in obj]
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat() if hasattr(obj, "isoformat") else str(obj)
    elif isinstance(obj, time):
        return obj.strftime("%H:%M:%S") if obj else None
    elif isinstance(obj, timedelta):
        total_seconds = int(obj.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return obj


def _sync_cane_weight_to_site(doc, doc_dict, child_fields, site):
    """Push one Cane Weight document to a single remote site.
    Returns None on success, or a short error string on failure.
    Logs at every call so each step is traceable in the Error Log."""
    remote_url = site.site.rstrip("/")
    _log("Cane Weight Sync", f"Syncing {doc.name} to site: {site.name} ({remote_url})")
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
    session.mount("http://", HTTPAdapter(max_retries=retries))
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})

    try:
        login_response = session.post(
            f"{remote_url}/api/method/login",
            data={"usr": site.user, "pwd": site.password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        _log("Login Response", f"{remote_url}: status {login_response.status_code}, body: {login_response.text[:200]}")
        if login_response.status_code != 200 or "Logged In" not in login_response.text:
            _log("Authentication Failed", f"{remote_url}: status {login_response.status_code}")
            return f"authentication failed (status {login_response.status_code})"

        doctype_check = session.get(f"{remote_url}/api/resource/DocType/Cane Weight", timeout=30)
        if doctype_check.status_code != 200:
            _log("Doctype Check Failed", f"'Cane Weight' may not exist on {remote_url}: status {doctype_check.status_code}")
            return "remote 'Cane Weight' doctype not found"

        # Prepare data for remote sync (strip local-only flags, incl. from child rows)
        sync_data = doc_dict.copy()
        sync_data.pop("is_sync", None)
        sync_data.pop("moved", None)
        sync_data = _convert_dates_for_json(sync_data)
        for child_field in child_fields:
            for row in sync_data.get(child_field) or []:
                row.pop("is_sync", None)
                row.pop("moved", None)

        check_response = session.get(f"{remote_url}/api/resource/Cane Weight/{doc.name}", timeout=30)
        if check_response.status_code == 200:
            _log("Updating Remote", f"Updating Cane Weight {doc.name} on {remote_url}")
            resp = session.put(f"{remote_url}/api/resource/Cane Weight/{doc.name}", json=sync_data, timeout=30)
        else:
            _log("Inserting Remote", f"Inserting Cane Weight {doc.name} on {remote_url}")
            resp = session.post(f"{remote_url}/api/resource/Cane Weight", json=sync_data, timeout=30)

        if resp.status_code not in (200, 201):
            _log("Remote Save Failed", f"{doc.name} on {remote_url}: status {resp.status_code}, body: {resp.text[:200]}")
            return f"remote save failed (status {resp.status_code}): {resp.text[:200]}"

        _log("Remote Save Success", f"{doc.name} synced to {remote_url}")
        return None
    except Exception as e:
        _log("Remote Sync Error", f"{doc.name} on {remote_url}: {str(e)}"[:300])
        return str(e)[:200]


@frappe.whitelist(allow_guest=False)
def sync_cane_weight_to_remote():
    """
    Sync submitted Cane Weight documents from the local Frappe instance to all
    configured remote Frappe instances. Once a document is pushed to every remote
    site successfully, it is marked synced, archived into Cane Weight History,
    then cancelled and deleted locally.

    Logs at every call/step (not just on failure) so a run's progress can be
    traced in the Error Log.
    """
    _log("Cane Weight Sync", "Starting Cane Weight sync (Local to Remote)")

    if not frappe.db.exists("DocType", "Cane Weight"):
        _log("Cane Weight Sync", "Local 'Cane Weight' doctype does not exist")
        return

    local_cane_weights = frappe.get_all("Cane Weight", filters={"docstatus": 1}, fields=["name"])
    _log("Cane Weight Sync", f"Found {len(local_cane_weights)} local Cane Weight records to sync")
    if not local_cane_weights:
        return

    sites = frappe.get_all("Site Configuration", fields=["name", "site", "user", "password"])
    _log("Cane Weight Sync", f"Found {len(sites)} site configurations: {[s.name for s in sites]}")
    if not sites:
        _log("Cane Weight Sync", "No site configurations found in 'Site Configuration' doctype")
        return

    try:
        meta = frappe.get_meta("Cane Weight")
        child_fields = [f.fieldname for f in meta.get_table_fields()]
    except Exception as e:
        _log("Cane Weight Sync Error", f"Error fetching Cane Weight metadata: {str(e)}"[:2000])
        return

    synced, failed = 0, 0

    for local_cw in local_cane_weights:
        try:
            doc = frappe.get_doc("Cane Weight", local_cw.name)
            doc_dict = doc.as_dict()
            _log("Cane Weight Sync", f"Processing Cane Weight: {doc.name}")

            site_errors = [
                f"{site.name}: {err}"
                for site in sites
                if (err := _sync_cane_weight_to_site(doc, doc_dict, child_fields, site))
            ]
            if site_errors:
                failed += 1
                _log("Cane Weight Sync Error", f"{doc.name} - sync failed: {'; '.join(site_errors)}"[:2000])
                continue

            # Synced to every site: mark synced, archive, then remove locally.
            # db_set bypasses the "not allowed to change after submission" check,
            # since is_sync/moved are not user-editable, submit-time fields.
            doc.db_set("is_sync", 1, update_modified=False)
            _log("Cane Weight Sync", f"Marked {doc.name} as synced (is_sync=1)")

            history_doc = frappe.new_doc("Cane Weight History")
            for field, value in doc_dict.items():
                if field not in ("name", "moved"):
                    history_doc.set(field, value)
            history_doc.insert(ignore_permissions=True)
            _log("Cane Weight Sync", f"Inserted {doc.name} into Cane Weight History")

            doc.db_set("moved", 1, update_modified=False)
            _log("Cane Weight Sync", f"Marked {doc.name} as moved (moved=1)")

            if frappe.db.exists("Cane Weight", doc.name):
                doc_to_delete = frappe.get_doc("Cane Weight", doc.name)
                if doc_to_delete.docstatus == 1:
                    doc_to_delete.cancel()
                    _log("Cane Weight Sync", f"Canceled Cane Weight: {doc.name}")
                frappe.delete_doc("Cane Weight", doc.name, ignore_permissions=True, ignore_missing=True)
                _log("Cane Weight Sync", f"Deleted Cane Weight: {doc.name}")

            synced += 1
            _log("Cane Weight Sync", f"Successfully synced, moved, and deleted Cane Weight: {doc.name}")

        except Exception as e:
            failed += 1
            _log("Cane Weight Sync Error", f"{local_cw.name} - failed to move to history or delete: {str(e)}"[:300])
            frappe.db.rollback()
            continue

    frappe.db.commit()
    _log("Cane Weight Sync", f"Sync job complete: {synced} synced, {failed} failed out of {len(local_cane_weights)}")

