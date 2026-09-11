# Copyright (c) 2026, Quantbit and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class TripSheet(Document):
	def autoname(self):
		if not self.season:
			frappe.throw("Season is required .")
		if not self.slip_no:
			frappe.throw("Slip No is required.")
			
		season_abbr = frappe.db.get_value("Season", self.season, "abbr")
		slip_no = str(self.slip_no)
		self.name = f"TS/{season_abbr}/{slip_no}"