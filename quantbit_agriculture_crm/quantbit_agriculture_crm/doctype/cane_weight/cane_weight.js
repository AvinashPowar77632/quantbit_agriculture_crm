// Copyright (c) 2026, Quantbit and contributors
// For license information, please see license.txt

frappe.ui.form.on("Cane Weight", {
	refresh(frm) {
		frm.add_custom_button(__("See Slip Details"), function () {
			let filters = {};
			if (frm.doc.transporter_contract) {
				filters.transporter_contract = frm.doc.transporter_contract;
			}
			if (frm.doc.trip_sheet) {
				filters.trip_sheet = frm.doc.trip_sheet;
			}
			frappe.set_route("query-report", "Slip Details", filters);
		});
	},
});
