// Copyright (c) 2026, Quantbit and contributors
// For license information, please see license.txt

frappe.query_reports["Slip Details"] = {
	filters: [
		{
			fieldname: "transporter_contract",
			label: __("Transporter Contract"),
			fieldtype: "Autocomplete",
			reqd: 0,
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "trip_sheet",
			label: __("Trip Sheet"),
			fieldtype: "Autocomplete",
			reqd: 0,
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "cane_registration",
			label: __("Cane Registration"),
			fieldtype: "Data",
			reqd: 0,
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "farmer",
			label: __("Farmer"),
			fieldtype: "Data",
			reqd: 0,
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
	],

	onload: function (report) {
		window.load_trip_sheet_report_filter_options = function () {
			frappe.call({
				method: "quantbit_agriculture_crm.exe_api.get_trip_sheet_filter_options",
				callback: function (r) {
					if (r.message && r.message.success) {
						let cur_tc = report.get_filter_value("transporter_contract");
						let cur_ts = report.get_filter_value("trip_sheet");

						let contracts = ["", ...(r.message.transporter_contract_options || r.message.transporter_contracts || [])];
						let sheets = ["", ...(r.message.trip_sheet_options || r.message.trip_sheets || [])];

						if (cur_tc && !contracts.includes(cur_tc)) {
							contracts.push(cur_tc);
						}
						if (cur_ts && !sheets.includes(cur_ts)) {
							sheets.push(cur_ts);
						}

						let tc_filter = report.get_filter("transporter_contract");
						let ts_filter = report.get_filter("trip_sheet");

						if (tc_filter) {
							tc_filter.df.options = contracts.join("\n");
							tc_filter.refresh();
							if (cur_tc) {
								tc_filter.set_input(cur_tc);
							}
						}
						if (ts_filter) {
							ts_filter.df.options = sheets.join("\n");
							ts_filter.refresh();
							if (cur_ts) {
								ts_filter.set_input(cur_ts);
							}
						}
					}
				},
			});
		};

		window.load_trip_sheet_report_filter_options();

		report.page.add_inner_button(__("Show Options from Trip Sheet List"), function () {
			window.load_trip_sheet_report_filter_options();
		});
	},
};
