# Copyright (c) 2026, Quantbit and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class TripSheet(Document):
	def autoname(self):
		self.name = self.trip_sheet