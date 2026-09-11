
import frappe
import requests
import json
from datetime import datetime, date, time, timedelta
from requests.adapters import HTTPAdapter, Retry
import requests
from frappe.utils import getdate, to_timedelta
from datetime import timedelta

@frappe.whitelist()
def sync_trip_sheet_remote_to_local():
    """Optimized: fetch Trip Sheet data from remote API and insert/update locally one by one."""
    local_doctype = "Trip Sheet"
    total_synced, total_failed = 0, 0
    sync_details = []

    try:
        sites = frappe.get_all("Site Configuration", fields=["name", "site", "user", "password"])
        if not sites:
            return {"success": False, "message": "No site configurations found"}

        frappe.log_error("Sync Start", f"Found {len(sites)} remote sites")

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
                    frappe.log_error("Auth Failed", f"{site.name}: {resp.text[:200]}")
                    continue
                frappe.log_error("Auth OK", f"Logged into {site.name}")
            except Exception as e:
                frappe.log_error("Auth Exception", f"{site.name}: {str(e)}")
                continue

            # --- Fetch pre-cleaned remote Trip Sheet data ---
            try:
                remote_response = session.get(
                    f"{base_url}/api/method/quantbit_agriculture_crm.exe_api.sync_trip_sheets",
                    timeout=30,
                )
                # Log the raw response for debugging
                frappe.log_error("Raw API Response", f"{site.name}: {remote_response.text[:500]}")
                
                # Check status code and parse JSON
                if remote_response.status_code != 200:
                    frappe.log_error("API Error", f"{site.name}: Status code {remote_response.status_code}")
                    continue
                
                response_json = remote_response.json()
                
                # Handle different possible response structures
                if "message" in response_json and isinstance(response_json["message"], dict):
                    remote_data = response_json["message"].get("data", [])
                else:
                    remote_data = response_json.get("data", [])
                
                if not isinstance(remote_data, list):
                    frappe.log_error("Invalid Data Format", f"{site.name}: Expected list, got {type(remote_data)}")
                    continue
                
                if not remote_data:
                    frappe.log_error("No Data", f"{site.name}: No trip sheets to sync")
                    continue

                frappe.log_error("Remote Fetch", f"{site.name}: {len(remote_data)} records found")
            except Exception as e:
                frappe.log_error("Remote Fetch Error", f"{site.name}: {str(e)}")
                continue

            # --- Iterate through all Trip Sheets ---
            for doc in remote_data:
                name = doc.get("name")
                if not name:
                    frappe.log_error("Missing Name", f"{site.name}: Skipping document with no name")
                    continue

                # Clean system fields
                for f in [
                    "creation", "modified", "modified_by", "owner", "docstatus",
                    "_liked_by", "_assign", "_comments", "_user_tags", "idx","diesel_allocated"
                ]:
                    doc.pop(f, None)

                # Handle json field
                # Keep the json field but still parse it
                json_field = doc.get("json")  # don't pop it

                if json_field:
                    try:
                        json_data = json.loads(json_field)
                        for k, v in json_data.items():
                            if isinstance(v, list):
                                frappe.log_error("JSON List Detected", f"{name}: Field {k} contains list: {v}")
                                doc[k] = v[0] if v else None
                            else:
                                doc[k] = v
                    except json.JSONDecodeError as e:
                        frappe.log_error("JSON Parse Error", f"{name}: Invalid JSON: {str(e)}")
                        continue
                try:
                    json_data = json.loads(json_field) if json_field else {}
                    for k, v in json_data.items():
                        if isinstance(v, list):
                            frappe.log_error("JSON List Detected", f"{name}: Field {k} contains list: {v}")
                            doc[k] = v[0] if v else None
                        else:
                            doc[k] = v
                except json.JSONDecodeError as e:
                    frappe.log_error("JSON Parse Error", f"{name}: Invalid JSON: {str(e)}")
                    continue

                # Convert list values to single values
                for k, v in doc.items():
                    if isinstance(v, list):
                        frappe.log_error("List Detected", f"{name}: Field {k} contains list: {v}")
                        doc[k] = v[0] if v else None

                # Safe date conversion
                def safe_convert(obj):
                    if isinstance(obj, dict):
                        return {k: safe_convert(v) for k, v in obj.items()}
                    elif isinstance(obj, list):
                        frappe.log_error("Unexpected List in safe_convert", f"{name}: List detected: {obj}")
                        return obj[0] if obj else None
                    elif isinstance(obj, (datetime, date)):
                        return obj.isoformat()
                    elif isinstance(obj, time):
                        return obj.strftime("%H:%M:%S")
                    elif isinstance(obj, timedelta):
                        sec = int(obj.total_seconds())
                        return f"{sec//3600:02d}:{(sec%3600)//60:02d}:{sec%60:02d}"
                    return obj

                doc = safe_convert(doc)

                try:
                    if frappe.db.exists(local_doctype, name):
                        # --- Update existing ---
                        local_doc = frappe.get_doc(local_doctype, name)
                        for k, v in doc.items():
                            if hasattr(local_doc, k):
                                try:
                                    local_doc.set(k, v)
                                except Exception as e:
                                    frappe.log_error("Field Set Error", f"{name}: Field {k} with value {v} caused error: {str(e)}")
                                    continue
                        local_doc.save(ignore_permissions=True)
                        action = "Updated"
                    else:
                        # --- Insert new ---
                        new_doc = frappe.new_doc(local_doctype)
                        for k, v in doc.items():
                            if k != "name":
                                try:
                                    new_doc.set(k, v)
                                except Exception as e:
                                    frappe.log_error("Field Set Error", f"{name}: Field {k} with value {v} caused error: {str(e)}")
                                    continue
                        new_doc.name = name
                        new_doc.insert(ignore_permissions=True)
                        action = "Inserted"

                    frappe.db.commit()

                    # --- Mark remote as synced ---
                    try:
                        session.put(
                            f"{base_url}/api/resource/Trip Sheet/{name}",
                            json={"is_sync": 1},
                            timeout=10
                        )
                    except Exception as e:
                        frappe.log_error("Remote Update Error", f"{name}: Failed to mark as synced: {str(e)}")

                    total_synced += 1
                    sync_details.append({"site": site.name, "name": name, "action": action, "status": "OK"})

                except Exception as e:
                    frappe.log_error("Local Save Error", f"{name}: {str(e)[:300]}")
                    total_failed += 1
                    sync_details.append({"site": site.name, "name": name, "status": "Failed", "error": str(e)[:100]})
                    frappe.db.rollback()
                    continue

        msg = f"Sync done: {total_synced} OK, {total_failed} failed"
        frappe.log_error("Sync Complete", msg)
        return {"success": True, "message": msg, "synced": total_synced, "failed": total_failed, "details": sync_details}

    except Exception as e:
        frappe.log_error("Critical Error", str(e))
        frappe.db.rollback()
        return {"success": False, "message": str(e)}






@frappe.whitelist(allow_guest=False)
def sync_cane_weight_to_remote():
    """
    Sync Cane Weight documents from local Frappe instance to remote Frappe instances.
    Only syncs documents where is_sync is 0 and moved is 0 locally.
    Sets is_sync to 1 after successful sync to prevent re-syncing.
    Moves synced records to Cane Weight History, cancels, and deletes from Cane Weight.
    """
    frappe.log_error("Starting Cane Weight sync (Local to Remote)")
    try:
        # Check local doctype existence
        if not frappe.db.exists("DocType", "Cane Weight"):
            frappe.log_error("Local 'Cane Weight' doctype does not exist")
            return

        # Fetch local Cane Weight records that need syncing
        local_cane_weights = frappe.get_all(
            "Cane Weight",
            filters={"docstatus": 1},
            fields=["name"]
        )
        
        frappe.log_error(f"Found {len(local_cane_weights)} local Cane Weight records to sync")
        
        if not local_cane_weights:
            frappe.log_error("No local Cane Weight records found with is_sync=0 and moved=0")
            return

        # Get site configurations
        sites = frappe.get_all("Site Configuration", fields=["name", "site", "user", "password"])
        frappe.log_error(f"Found {len(sites)} site configurations: {[s.name for s in sites]}")
        
        if not sites:
            frappe.log_error("No site configurations found in 'Site Configuration' doctype")
            return

        # Get local metadata
        try:
            meta = frappe.get_meta("Cane Weight")
            child_fields = [f.fieldname for f in meta.get_table_fields()]
            local_fields = [f.fieldname for f in meta.get("fields") if f.fieldtype not in ["Table", "Section Break", "Column Break", "Read Only", "Button"]]
            frappe.log_error("Local Metadata", f"Local Cane Weight fields: {local_fields}, Child fields: {child_fields}")
        except Exception as e:
            frappe.log_error("Metadata Error", f"Error fetching local Cane Weight metadata: {str(e)}"[:100])
            return

        # Sync each local Cane Weight to all remote sites
        for local_cw in local_cane_weights:
            try:
                # Get full document data
                doc = frappe.get_doc("Cane Weight", local_cw.name)
                doc_dict = doc.as_dict()
                
                frappe.log_error("Processing Local Cane Weight", f"Processing Cane Weight: {doc.name}")
                
                sync_successful = True  # Track if sync succeeds for all sites
                
                # Sync to each remote site
                for site in sites:
                    remote_url = site.site.rstrip("/")
                    username = site.user
                    password = site.password
                    frappe.log_error(f"Syncing to site: {site.name} ({remote_url})")
                
                    # Initialize session with retries
                    session = requests.Session()
                    retries = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
                    session.mount("http://", HTTPAdapter(max_retries=retries))
                    session.mount("https://", HTTPAdapter(max_retries=retries))
                    session.headers.update({
                        "Accept": "application/json",
                        "Content-Type": "application/json"
                    })
                
                    # Authenticate
                    try:
                        login_response = session.post(
                            f"{remote_url}/api/method/login",
                            data={"usr": username, "pwd": password},
                            headers={"Content-Type": "application/x-www-form-urlencoded"}
                        )
                        log_message = f"Login response for {remote_url}: Status {login_response.status_code}\nResponse: {login_response.text[:100]}"
                        frappe.log_error("Login Response", log_message)
                        
                        if login_response.status_code != 200 or "Logged In" not in login_response.text:
                            frappe.log_error("Authentication Failed", f"Authentication failed for {remote_url}")
                            sync_successful = False
                            continue
                    except Exception as e:
                        frappe.log_error("Authentication Error", f"Error for {remote_url}: {str(e)}"[:100])
                        sync_successful = False
                        continue
                
                    # Verify doctype exists on remote site
                    try:
                        doctype_check_url = f"{remote_url}/api/resource/DocType/Cane Weight"
                        doctype_check = session.get(doctype_check_url)
                        
                        if doctype_check.status_code != 200:
                            frappe.log_error("Doctype Check Failed", f"Doctype 'Cane Weight' may not exist on {remote_url}")
                            sync_successful = False
                            continue
                    except Exception as e:
                        frappe.log_error("Doctype Check Error", f"Error for {remote_url}: {str(e)}"[:100])
                        sync_successful = False
                        continue
                
                    # Prepare data for remote sync (remove local-only fields)
                    sync_data = doc_dict.copy()
                    sync_data.pop("is_sync", None)
                    sync_data.pop("moved", None)
                    
                    # Convert datetime and timedelta objects to strings for JSON serialization
                    from datetime import datetime, date, time, timedelta
                    def convert_dates(obj):
                        if isinstance(obj, dict):
                            return {k: convert_dates(v) for k, v in obj.items()}
                        elif isinstance(obj, list):
                            return [convert_dates(item) for item in obj]
                        elif isinstance(obj, (datetime, date)):
                            return obj.isoformat() if hasattr(obj, 'isoformat') else str(obj)
                        elif isinstance(obj, time):
                            return obj.strftime('%H:%M:%S') if obj else None
                        elif isinstance(obj, timedelta):
                            # Convert timedelta to total seconds or string format
                            total_seconds = int(obj.total_seconds())
                            hours, remainder = divmod(total_seconds, 3600)
                            minutes, seconds = divmod(remainder, 60)
                            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                        return obj
                    
                    sync_data = convert_dates(sync_data)
                    
                    # Remove is_sync and moved from child tables
                    for child_field in child_fields:
                        if child_field in sync_data and sync_data[child_field]:
                            for row in sync_data[child_field]:
                                row.pop("is_sync", None)
                                row.pop("moved", None)
                    
                    # Check if document exists on remote
                    try:
                        check_url = f"{remote_url}/api/resource/Cane Weight/{doc.name}"
                        check_response = session.get(check_url)
                        
                        if check_response.status_code == 200:
                            # Update existing document
                            frappe.log_error("Updating Remote", f"Updating Cane Weight {doc.name} on {remote_url}")
                            update_url = f"{remote_url}/api/resource/Cane Weight/{doc.name}"
                            update_response = session.put(update_url, json=sync_data)
                            
                            if update_response.status_code != 200:
                                frappe.log_error("Update Failed", f"Failed to update {doc.name} on {remote_url}: {update_response.text[:100]}")
                                sync_successful = False
                                continue
                            else:
                                frappe.log_error("Update Success", f"Successfully updated {doc.name} on {remote_url}")
                        else:
                            # Insert new document
                            frappe.log_error("Inserting Remote", f"Inserting Cane Weight {doc.name} on {remote_url}")
                            insert_url = f"{remote_url}/api/resource/Cane Weight"
                            insert_response = session.post(insert_url, json=sync_data)
                            
                            if insert_response.status_code not in [200, 201]:
                                frappe.log_error("Insert Failed", f"Failed to insert {doc.name} on {remote_url}: {insert_response.text[:10000]}")
                                sync_successful = False
                                continue
                            else:
                                frappe.log_error("Insert Success", f"Successfully inserted {doc.name} on {remote_url}")
                    except Exception as e:
                        frappe.log_error("Remote Sync Error", f"Error syncing {doc.name} to {remote_url}: {str(e)}"[:100])
                        sync_successful = False
                        continue
                
                # If sync successful to all sites, mark as synced and move to history
                if sync_successful:
                    try:
                        # Mark as synced
                        doc.is_sync = 1
                        doc.flags.ignore_permissions = True
                        doc.save()
                        frappe.log_error("Mark Synced", f"Marked Cane Weight {doc.name} as synced (is_sync=1)")
                        
                        # Move to Cane Weight History
                        history_doc = frappe.new_doc("Cane Weight History")
                        
                        # Copy all fields except name and moved
                        for field in doc_dict:
                            if field not in ["name", "moved"]:
                                history_doc.set(field, doc_dict.get(field))
                        
                        history_doc.insert(ignore_permissions=True)
                        frappe.log_error("History Insert", f"Inserted {doc.name} into Cane Weight History")
                        
                        # Mark as moved
                        doc.moved = 1
                        doc.save(ignore_permissions=True)
                        frappe.log_error("Mark Moved", f"Marked Cane Weight {doc.name} as moved (moved=1)")
                        
                        # Cancel and delete from Cane Weight
                        if frappe.db.exists("Cane Weight", doc.name):
                            doc_to_delete = frappe.get_doc("Cane Weight", doc.name)
                            
                            # Cancel if submitted
                            if doc_to_delete.docstatus == 1:
                                doc_to_delete.cancel()
                                frappe.log_error("Cancel Success", f"Canceled Cane Weight: {doc.name}")
                            
                            # Delete the document
                            frappe.delete_doc("Cane Weight", doc.name, ignore_permissions=True, ignore_missing=True)
                            frappe.log_error("Delete Success", f"Deleted Cane Weight: {doc.name}")
                        
                        frappe.log_error("Sync Complete", f"Successfully synced, moved, and deleted Cane Weight: {doc.name}")
                        
                    except Exception as e:
                        error_msg = f"Failed to move {doc.name} to history or delete: {str(e)}"[:100]
                        frappe.log_error("Post-Sync Error", error_msg)
                        frappe.db.rollback()
                        continue
                else:
                    frappe.log_error("Sync Incomplete", f"Skipping history move for {doc.name} - sync failed for one or more sites")
                
            except Exception as e:
                error_msg = f"Error processing Cane Weight {local_cw.name}: {str(e)}"[:100]
                frappe.log_error("Processing Error", error_msg)
                continue

        frappe.db.commit()
        frappe.log_error("Sync Job Complete", f"Completed sync job for {len(local_cane_weights)} local Cane Weight records")

    except Exception as e:
        frappe.log_error("Unexpected Error", f"Unexpected error in sync_cane_weight_two: {str(e)}"[:100])
        frappe.db.rollback()

