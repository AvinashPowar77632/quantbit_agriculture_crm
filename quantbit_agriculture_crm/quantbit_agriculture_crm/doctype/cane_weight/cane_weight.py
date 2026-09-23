# Copyright (c) 2026, Quantbit and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate,to_timedelta,flt
from datetime import timedelta
import json
from typing import List


class CaneWeight(Document):
	@frappe.whitelist()
	def actual_weight(self):
		gross_weight = self.gross_weight or 0
		tare_weight = self.tare_weight or 0
		self.cane_weight = gross_weight - tare_weight
		self.binding_weight=self.cane_weight * (self.binding_weight_percentage()/100)
		self.net_weight=self.cane_weight - self.binding_weight
		self.transporter_weight=self.net_weight
		self.harvester_weight=self.net_weight
		self.farmer_weight=self.net_weight


	def calculate_penalty_weights(self):
		gross = flt(self.gross_weight)
		tare = flt(self.tare_weight)
		binding = flt(self.binding_weight)

		if gross <= 0 or tare <= 0:
			return

		cane_weight = gross - tare
		net_weight = cane_weight - binding
		adj_farmer_weight = cane_weight - binding

		farmer_weight = adj_farmer_weight
		water_supplier_weight = 0
		cane_deduction_weight = 0

		deduction = 0

		for row in self.penalty_charges or []:
			if row.entity_type != "Farmer":
				continue
			if row.deduction_method == "Percentage":
				deduction = flt(row.deduction_rate)
			else:
				deduction = 0
			break

		water_share = flt(self.water_share)
		if water_share > 0:
			supplier_percent = water_share
			farmer_percent = 100 - supplier_percent
			water_supplier_weight = (adj_farmer_weight * supplier_percent) / 100
			farmer_weight = (adj_farmer_weight * farmer_percent) / 100

		if deduction > 0:
			cane_deduction_weight = (farmer_weight * deduction) / 100
			farmer_weight = farmer_weight - cane_deduction_weight
		frappe.log_error(f"Debug: deduction={deduction}, cane_deduction_weight={cane_deduction_weight}, farmer_weight={farmer_weight}")
		self.cane_weight = round(cane_weight, 3)
		self.net_weight = round(net_weight, 3)
		self.farmer_weight = round(farmer_weight, 3)
		self.water_supplier_weight = round(water_supplier_weight, 3)
		self.cane_deduction_weight = round(cane_deduction_weight, 3)
		self.transporter_weight = round(net_weight, 3)
		self.harvester_weight = round(net_weight, 3)

	@frappe.whitelist()
	def binding_weight_percentage(self):
		weight = frappe.get_value("Weight Settings Details",{"vehicle_type":self.transporter_vehicle_type},"percentage")
		return weight or 1

	def before_submit(self):
		if self.gross_weight <= 0:
			frappe.throw("Gross Weight must be greater than zero.")
		if self.tare_weight <= 0:
			frappe.throw("Tare Weight must be greater than zero.")
		if self.gross_weight < self.tare_weight:
			frappe.throw("Gross Weight must be greater than Tare Weight.")
		if not self.cane_weight or self.cane_weight <= 0:
			frappe.throw("Cane Weight must be greater than zero.")

	def on_submit(self):
		self.on_submit_status_change()
	
	def on_cancel(self):
		self.on_cancel_status_change()
	
	def on_cancel_status_change(self):
		trip_id= [self.trip_sheet]
		status_change(doctype="Trip Sheet",docnames=trip_id,status_field="status",status="Submitted Token")

	def on_submit_status_change(self):
		trip_id= [self.trip_sheet]
		status_change(doctype="Trip Sheet",docnames=trip_id,status_field="status",status="Weight Done")


@frappe.whitelist()
def status_change(doctype: str, docnames: List[str], status_field: str, status: str):
    if not doctype:
        frappe.throw("Doctype is required")
    if not docnames:
        frappe.throw("List of document names is required")
    if not status_field:
        frappe.throw("Fieldname is required")
    if status is None:
        frappe.throw("Status value is required")

    placeholders = ", ".join(["%s"] * len(docnames))

    frappe.db.sql(
        f"""
        UPDATE `tab{doctype}`
        SET `{status_field}` = %s
        WHERE name IN ({placeholders})
        """,
        tuple([status] + list(docnames)),
    )
    frappe.db.commit()