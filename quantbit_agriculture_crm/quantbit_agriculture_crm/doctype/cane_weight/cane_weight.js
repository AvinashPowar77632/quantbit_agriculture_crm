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

		// Make token_no in red color
		if (frm.fields_dict.token_no) {
			frm.fields_dict.token_no.$wrapper.find("input, .control-value").css({
				"color": "#dc2626",
				"font-weight": "bold"
			});
			frm.fields_dict.token_no.$wrapper.find("label").css({
				"color": "#dc2626",
				"font-weight": "bold"
			});
		}
	},
	trip_sheet(frm) {
		if (frm.doc.trip_sheet) {
			// Clear existing weight entries when trip sheet is changed
			frm.set_value("gross_weight", 0);
			frm.set_value("tare_weight", 0);
			frm.set_value("net_weight", 0);
			frm.set_value("cane_weight", 0);
			frm.set_value("binding_weight", 0);
		}
	}
});

