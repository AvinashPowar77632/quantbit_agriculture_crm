import sys
import serial
import serial.tools.list_ports
from datetime import datetime
import requests
import json
import re # Added for regex operations
import time
import socket
import threading
import select
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QLineEdit, QTextEdit, QMessageBox,
    QFrame, QSplitter, QGroupBox, QGridLayout, QSpacerItem,
    QSizePolicy, QCheckBox, QSpinBox, QTabWidget, QProgressBar,
    QDateEdit, QDateTimeEdit, QScrollArea, QTableWidget, QTableWidgetItem,
    QTimeEdit , QDoubleSpinBox , QHeaderView, QDialog, QAbstractItemView
)
from PySide6.QtCore import QThread, Signal, Qt, QTimer, QDate, QDateTime, QTime
from PySide6.QtGui import QFont, QPalette, QColor, QIcon, QPixmap, QDoubleValidator, QTextCursor
from urllib.parse import quote

class SerialReader(QThread):
    data_received = Signal(str)
    connection_status = Signal(bool, str)
    
    def __init__(self, port, baud, timeout=1):
        super().__init__()
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.ser = None
        self.running = True
    
    def run(self):
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                timeout=self.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
            self.connection_status.emit(True, f"Connected to {self.port}")
            
            while self.running and self.ser.is_open:
                try:
                    # Read data continuously (readline will wait for timeout if no data)
                    data = self.ser.readline().decode('ascii', errors='replace').strip()
                    if data:
                        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        formatted_data = f"[{timestamp}] {data}"
                        self.data_received.emit(formatted_data)
                    else:
                        # Small sleep when no data to prevent tight loop
                        time.sleep(0.01)
                except (UnicodeDecodeError, ValueError) as e:
                    self.data_received.emit(f"[ERROR] Failed to decode received data: {str(e)}")
                    time.sleep(0.1)
                except Exception as e:
                    self.data_received.emit(f"[ERROR] Read error: {str(e)}")
                    time.sleep(0.1)
                        
        except serial.SerialException as e:
            self.connection_status.emit(False, f"Connection failed: {str(e)}")
        except Exception as e:
            self.connection_status.emit(False, f"Unexpected error: {str(e)}")
    
    def stop(self):
        self.running = False
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except:
                pass
    
    def send_data(self, data):
        if self.ser and self.ser.is_open:
            try:
                self.ser.write((data + '\n').encode('utf-8'))
                return True
            except Exception as e:
                self.connection_status.emit(False, f"Send failed: {str(e)}")
                return False
        return False

class CaneWeightSaveWorker(QThread):
    """Runs the Cane Weight save/submit POST off the UI thread so clicking
    Save/Submit doesn't freeze the app for the duration of the request."""
    finished_ok = Signal(dict)
    finished_error = Signal(str)

    def __init__(self, session, url, send_payload):
        super().__init__()
        self.session = session
        self.url = url
        self.send_payload = send_payload

    def run(self):
        try:
            response = self.session.post(
                self.url, json={"data": self.send_payload},
                headers={"Accept": "application/json"}, timeout=30
            )
            response.raise_for_status()
            self.finished_ok.emit(response.json())
        except requests.exceptions.HTTPError as e:
            try:
                error_detail = e.response.json()
                error_msg = f"HTTP {e.response.status_code}: {error_detail}"
            except Exception:
                error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            self.finished_error.emit(error_msg)
        except requests.exceptions.RequestException as e:
            self.finished_error.emit(f"Network error: {str(e)}")
        except Exception as e:
            import traceback
            self.finished_error.emit(f"Unexpected error: {str(e)}\n{traceback.format_exc()}")


class StatusIndicator(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(20, 20)
        self.connected = False
    
    def set_status(self, connected):
        self.connected = connected
        self.update()
    
    # def paintEvent(self, event):
        # from PySide6.QtGui import QPainter
        # painter = QPainter(self)
        # painter.setRenderHint(QPainter.Antialiasing)
        
        # color = QColor(46, 204, 113) if self.connected else QColor(231, 76, 60)
        # painter.setBrush(color)
        # painter.setPen(Qt.NoPen)
        # painter.drawEllipse(2, 2, 16, 16)


class CollapsibleSection(QWidget):
    """Accordion-style collapsible section: click the header to expand/collapse the content."""
    def __init__(self, title, content_widget, expanded=False, parent=None):
        super().__init__(parent)
        self.title = title

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.toggle_button = QPushButton()
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(expanded)
        self.toggle_button.setCursor(Qt.PointingHandCursor)
        self.toggle_button.setMinimumHeight(42)
        self.toggle_button.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding-left: 14px;
                font-size: 13px;
                font-weight: 600;
                color: #2c3e50;
                background-color: #f4f6f8;
                border: 1px solid #dbe1e8;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #eaeff4;
                border: 1px solid #c7d0da;
            }
            QPushButton:checked {
                background-color: #e8f0fe;
                border: 1px solid #aac6f5;
                color: #1a56c4;
            }
        """)
        self.toggle_button.clicked.connect(self._on_toggled)

        self.content_widget = content_widget
        self.content_widget.setVisible(expanded)

        outer_layout.addWidget(self.toggle_button)
        outer_layout.addWidget(self.content_widget)

        self._update_button_text()

    def _on_toggled(self):
        checked = self.toggle_button.isChecked()
        self.content_widget.setVisible(checked)
        self._update_button_text()

    def _update_button_text(self):
        arrow = "▼" if self.toggle_button.isChecked() else "▶"  # down-/right-pointing triangle (escaped: immune to file-encoding corruption)
        self.toggle_button.setText(f"  {arrow}  {self.title}")

    def set_expanded(self, expanded):
        if self.toggle_button.isChecked() != expanded:
            self.toggle_button.setChecked(expanded)
            self._on_toggled()


class MainWindow(QWidget):
    # Matches the "Cane Weight Penalty Charges" child DocType's Deduction
    # Method Select field options exactly.
    PENALTY_DEDUCTION_METHODS = ["Percentage", "Amount", "Amount Per Ton"]

    def _make_penalty_readonly_item(self, text=""):
        """A QTableWidgetItem for the penalty charges table that the user
        can't edit (used for Entity Code/Name/Type)."""
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def _make_penalty_deduction_method_combo(self, current_text=""):
        """A QComboBox cell widget for the penalty charges table's Deduction
        Method column, restricted to the DocType's Select options."""
        combo = QComboBox()
        combo.addItems(self.PENALTY_DEDUCTION_METHODS)
        if current_text in self.PENALTY_DEDUCTION_METHODS:
            combo.setCurrentText(current_text)
        return combo

    def _populate_compact_grid(self, grid, items, slots_per_row=4, start_row=0):
        """Lay out (label, widget) pairs into `grid`, `slots_per_row`
        label+field slots per row (2 grid columns per slot) instead of one
        pair per row, so a group box stays compact. `start_row` lets several
        calls share one grid (e.g. one logical group per row) without
        overlapping - each call returns the next free row, to pass as the
        following call's start_row."""
        last_row = start_row
        for i, (label, widget) in enumerate(items):
            row, slot = divmod(i, slots_per_row)
            row += start_row
            col = slot * 2
            grid.addWidget(QLabel(label), row, col)
            grid.addWidget(widget, row, col + 1)
            last_row = max(last_row, row)
        for c in range(1, slots_per_row * 2, 2):
            grid.setColumnStretch(c, 1)
        return last_row + 1

    def __init__(self, primary_site_url, primary_username, primary_password, primary_session):
        super().__init__()
        self.setWindowTitle("RS232 Communication Terminal")
        self.setGeometry(100, 100, 900, 700)
        self.setMinimumSize(800, 600)
        
        # Initialize variables
        self.reader = None
        self.connected = False
        self.bytes_received = 0
        self.bytes_sent = 0
        self.current_weight = None  # Store current weight from serial port
        self.form_fields = {}
        self.fuel_sale_fields = {}  # Initialize fuel sale form fields
        self.auto_token_fields = {}  # Initialize auto token form fields
        self.diesel_sale_fields = {}  # Initialize diesel sale form fields
        self.cane_inward_slip_fields = {}  # Initialize cane inward slip form fields
        self.other_weight_fields = {}  # Initialize other weight form fields
        self.current_cane_weight_doc = None # To store the Cane Weight document if fetched for update
        self.current_trip_sheet_doc = None  # To store last selected Trip Sheet document for Cane Weight
        self.current_fuel_sale_doc = None
        self.current_auto_token_doc = None
        self.current_diesel_sale_doc = None
        self.current_other_weight_doc = None
        
        # RFID Connection variables
        self.rfid_api_endpoint = "http://deverpvppl.erpdata.in/api/resource/Rfid tag Reading/1"
        self.rfid_api_token = "1c90597bb0a9a7b:d469fa05aee8daf"
        self.rfid_hex_string = None
        self.rfid_socket = None
        self.rfid_port = 6000
        self.rfid_ip = '192.168.10.244'
        self.rfid_local_ip = socket.gethostbyname(socket.gethostname())
        self.rfid_read_thread = None
        self.rfid_send_thread = None
        self.rfid_running = False
        
        # Primary Frappe Instance Settings (received from LoginPage)
        self.primary_frappe_username = primary_username
        self.primary_frappe_password = primary_password
        self.primary_frappe_site_url = primary_site_url
        self.primary_frappe_session = primary_session # Use requests.Session
        self.primary_frappe_logged_in = True # Already logged in via LoginPage
        
        # Secondary Frappe Instance Settings
        self.secondary_frappe_username = ""
        self.secondary_frappe_password = ""
        self.secondary_site_url = ""
        self.secondary_frappe_session = requests.Session() # Use requests.Session
        self.secondary_frappe_logged_in = False
        
        # Third Frappe Instance Settings (new source for auto-sync)
        self.third_frappe_username = "administrator"
        self.third_frappe_password = "Erpd@t@123$"
        self.third_frappe_site_url = "http://103.219.1.138:4412/"
        self.third_frappe_session = requests.Session() # Use requests.Session
        self.third_frappe_logged_in = False
        
        # Trip Sheet Frappe Instance Settings (new) - Auto-login on startup
        self.trip_sheet_frappe_username = "serversync@gmail.com"
        self.trip_sheet_frappe_password = "Admin@123$"
        self.trip_sheet_frappe_site_url = "https://erpbharati.m.frappe.cloud"
        self.trip_sheet_frappe_session = requests.Session()
        self.trip_sheet_frappe_logged_in = False
        self.trip_sheets_data = [] # To store fetched trip sheets
        self.auto_trip_sheet_login_completed = False  # Flag to track auto-login
        
        # Trip Sheet ERP API (token-based) for utility methods (e.g., branches)
        self.trip_sheet_api_base = "https://erpbharati.m.frappe.cloud"
        self.trip_sheet_api_key = "7e8f882588bc8ff"
        self.trip_sheet_api_secret = "ac1506700a4120d"

        # Cane Weight API integration: operator types only the numeric Trip Sheet No.
        # (e.g. "134") - this prefix is added automatically to form the full document
        # name ("TS/2526/134") sent to quantbit_agriculture_crm.exe_api.get_data.
        self.TRIP_SHEET_PREFIX = "TS/2627/"

        # Auto-sync timer (Primary to Secondary)
        self.primary_to_secondary_auto_sync_timer = QTimer(self)
        self.primary_to_secondary_auto_sync_timer.timeout.connect(self.sync_primary_to_secondary_data)
        self.primary_to_secondary_auto_sync_enabled = False # Will be controlled by a checkbox
        
        # Auto-sync timer (Third to Primary)
        self.third_to_primary_auto_sync_timer = QTimer(self)
        self.third_to_primary_auto_sync_timer.timeout.connect(self.sync_third_to_primary_data)
        self.third_to_primary_auto_sync_enabled = False # Will be controlled by a checkbox
        
        # Set up the UI
        self.setup_ui()
        self.setup_styles()
        self.setWindowIcon(self.load_logo_icon())
        
        # Start RFID connection in a separate thread
        QTimer.singleShot(500, self.start_rfid_connection_thread)  # Delay to ensure UI is ready
        
        # Timer for updating statistics
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_stats)
        self.stats_timer.start(1000)

        # Keep Posting Date/Time live - always the current system date/time, never
        # hard-coded - unless the operator has ticked "Edit Posting Date & Time" to
        # manually override them (see _on_edit_posting_datetime_toggled). Posting
        # Date/Time is the only field kept live-ticking; Token Date/Time and
        # Gross/Tare Weight Timestamp are set once (at form creation/clear, or at
        # the actual capture moment) instead of continuously updating - see
        # _tick_weight_timestamps/_tick_token_datetime, no longer wired to this timer.
        self._refresh_posting_datetime_now()
        self._gross_weight_captured = False
        self._tare_weight_captured = False
        # Binding Weight % for the current trip sheet's vehicle type - set from
        # Get Data's "binding_weight_percent" (see _populate_cane_weight_form_from_exe_api)
        self._cane_weight_binding_percent = 1
        self._base_diesel_allocation = 0.0
        self.posting_datetime_timer = QTimer(self)
        self.posting_datetime_timer.timeout.connect(self._tick_posting_datetime)
        self.posting_datetime_timer.start(1000)

    def start_rfid_connection_thread(self):
        """Start RFID connection in a background thread."""
        rfid_connection_thread = threading.Thread(target=self.start_rfid_connection, daemon=True)
        rfid_connection_thread.start()
    
    def auto_login_trip_sheet(self):
        if self.auto_trip_sheet_login_completed:
            return
    
        site_url = self.trip_sheet_frappe_site_url
        username = self.trip_sheet_frappe_username
        password = self.trip_sheet_frappe_password
    
        if not site_url or not username or not password:
            self.output.append("[Trip Sheet Auto-Login] Credentials not configured, skipping auto-login")
            return
        
        try:
            self.output.append(f"[Trip Sheet Auto-Login] Attempting to login to {site_url}...")
            response = self.trip_sheet_frappe_session.post(
                f"{site_url}/api/method/login",
                json={"usr": username, "pwd": password}
            )
            response.raise_for_status()
            
            self.trip_sheet_frappe_logged_in = True
            self.auto_trip_sheet_login_completed = True
            
            # Update UI elements (if they exist)
            if hasattr(self, 'trip_sheet_login_btn'):
                self.trip_sheet_login_btn.setEnabled(False)
            if hasattr(self, 'trip_sheet_logout_btn'):
                self.trip_sheet_logout_btn.setEnabled(True)
            
            self.output.append(f"[Trip Sheet Auto-Login] Successfully logged in to Trip Sheet instance!")
            
            # Automatically fetch trip sheets after successful login
            QTimer.singleShot(500, self.fetch_trip_sheets)
        
        except requests.exceptions.HTTPError as e:
            error_msg = f"[Trip Sheet Auto-Login Error] HTTP {e.response.status_code}: {e.response.text}"
            self.output.append(error_msg)
            self.auto_trip_sheet_login_completed = True  # Mark as completed even on error to avoid retry loop
            QMessageBox.warning(self, "Trip Sheet Auto-Login Warning", 
                            f"Failed to auto-login to Trip Sheet: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = f"[Trip Sheet Auto-Login Error] Network error: {str(e)}"
            self.output.append(error_msg)
            self.auto_trip_sheet_login_completed = True
            QMessageBox.warning(self, "Trip Sheet Auto-Login Warning", 
                            f"Network error during Trip Sheet auto-login: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Trip Sheet Auto-Login Error] {error_msg}")
            self.auto_trip_sheet_login_completed = True
            QMessageBox.warning(self, "Trip Sheet Auto-Login Warning", 
                            f"Unexpected error during Trip Sheet auto-login: {error_msg}")

    def load_logo_icon(self):
        """Load the logo image from URL and create a QIcon for the window."""
        logo_url = "https://media.licdn.com/dms/image/v2/D560BAQEMpaC_iBLQyw/company-logo_200_200/company-logo_200_200/0/1719257928420/quantbit_technologies_logo?e=2147483647&v=beta&t=B5LgukVqoYKt0Pls_rXBAjLhnqrHmi5yTxX1k9cKcz0"
        logo_pixmap = QPixmap()
        
        try:
            response = requests.get(logo_url)
            response.raise_for_status()  # Raise error for bad status codes
            if logo_pixmap.loadFromData(response.content):
                # Scale for icon (window icons are small; 32x32 or 64x64 works well)
                logo_pixmap = logo_pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                icon = QIcon(logo_pixmap)
                return icon
            else:
                raise ValueError("Failed to load pixmap from data")
        except Exception as e:
            # Fallback: Create a simple colored icon with text "QT" (Quantbit)
            fallback_pixmap = QPixmap(64, 64)
            fallback_pixmap.fill(QColor("#667eea"))  # Blue background
            # painter = QPainter(fallback_pixmap)
            # painter.setPen(QColor("white"))
            # painter.setFont(QFont("Arial", 24, QFont.Bold))
            # painter.drawText(fallback_pixmap.rect(), Qt.AlignCenter, "QT")
            # painter.end()
            fallback_icon = QIcon(fallback_pixmap)
            
            # Log error if output is available
            if hasattr(self, 'output'):
                self.output.append(f"[Window Icon] Failed to load logo from {logo_url}: {str(e)}. Using fallback icon.")
            
            return fallback_icon
    
    def setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # Header
        header_frame = self.create_header()
        main_layout.addWidget(header_frame)

        # Main content area with tabs - only Communication / Settings / Cane Weight shown
        tab_widget = QTabWidget()

        # --- Communication tab ---
        comm_tab = QWidget()
        comm_layout = QVBoxLayout(comm_tab)
        settings_group = self.create_connection_settings()
        comm_layout.addWidget(settings_group)
        splitter = QSplitter(Qt.Vertical)
        receive_group = self.create_receive_area()
        splitter.addWidget(receive_group)
        send_group = self.create_send_area()
        splitter.addWidget(send_group)
        splitter.setSizes([400, 200])
        comm_layout.addWidget(splitter)
        tab_widget.addTab(comm_tab, "Communication")

        # --- Settings tab ---
        settings_tab = self.create_settings_tab()
        tab_widget.addTab(settings_tab, "Settings")

        # --- Cane Weight tab (its sub-sections are collapsible, see create_cane_form_tab) ---
        cane_form_tab = self.create_cane_form_tab()
        tab_widget.addTab(cane_form_tab, "Cane Weight")

        # --- Cane Inward Slip tab ---
        self.cane_inward_slip_tab = self.create_cane_inward_slip_tab()
        tab_widget.addTab(self.cane_inward_slip_tab, "Cane Inward Slip")

        # --- Other Weight tab ---
        self.other_weight_tab = self.create_other_weight_tab()
        tab_widget.addTab(self.other_weight_tab, "Other Weight")

        # The following forms are built (so their fields/signals still work in the
        # background, e.g. RFID auto-fill) but are hidden from the main interface for now.
        self.fuel_sale_tab = self.create_fuel_sale_tab()
        self.auto_token_tab = self.create_auto_token_tab()
        self.diesel_sale_tab = self.create_diesel_sale_tab()

        main_layout.addWidget(tab_widget)
        self.setLayout(main_layout)
    
    def create_header(self):
        header_frame = QFrame()
        header_frame.setObjectName("headerFrame")
        header_layout = QHBoxLayout(header_frame)
        # header_layout.setContentsMargins(15, 10, 15, 10)
        # header_layout.setSpacing(10)
        
        # List of image URLs to display side by side
        image_urls = [
            "https://media.licdn.com/dms/image/v2/D560BAQEMpaC_iBLQyw/company-logo_200_200/company-logo_200_200/0/1719257928420/quantbit_technologies_logo?e=2147483647&v=beta&t=B5LgukVqoYKt0Pls_rXBAjLhnqrHmi5yTxX1k9cKcz0"  # Example second image (Quantbit logo from previous request)
        ]
        
        # Add multiple images side by side
        for index, url in enumerate(image_urls):
            logo_label = QLabel()
            logo_label.setFixedSize(50, 50)  # Fixed size for each logo
            logo_pixmap = QPixmap()
            
            try:
                if logo_pixmap.loadFromData(requests.get(url).content):  # Download and load the image
                    logo_pixmap = logo_pixmap.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    logo_label.setPixmap(logo_pixmap)
                    logo_label.setStyleSheet("border: none;")  # No border for clean look
                else:
                    # Fallback: Set placeholder text if image fails to load
                    logo_label.setText(f"IMG{index+1}")
                    logo_label.setStyleSheet(
                        "background-color: #667eea; color: white; border-radius: 25px; "
                        "font-weight: bold; font-size: 16px; text-align: center;"
                    )
                    logo_label.setAlignment(Qt.AlignCenter)
            except Exception as e:
                # Handle network or other errors
                logo_label.setText(f"IMG{index+1}")
                logo_label.setStyleSheet(
                    "background-color: #667eea; color: white; border-radius: 25px; "
                    "font-weight: bold; font-size: 16px; text-align: center;"
                )
                logo_label.setAlignment(Qt.AlignCenter)
                self.output.append(f"[Header] Failed to load image {url}: {str(e)}")
            
            header_layout.addWidget(logo_label)
        
        # Title layout
        title_layout = QVBoxLayout()
        title_label = QLabel("Quantbit Cane Weighbridge System")
        title_label.setObjectName("titleLabel")
        title_label.setStyleSheet("font-size: 20px; font-weight: bold; color: Blue; margin: 0;")
        subtitle_label = QLabel("RS232 Communication Terminal - Professional serial tool")
        subtitle_label.setObjectName("subtitleLabel")
        subtitle_label.setStyleSheet("font-size: 12px; color: rgba(8, 178, 221, 0.8); margin: 0;")
        title_layout.addWidget(title_label)
        title_layout.addWidget(subtitle_label)
        header_layout.addLayout(title_layout, 1)  # Stretch to fill spac

        # Logged-in user name (top-right corner), with a live clock beside it -
        # every date/time field in this app tracks the live system clock, so
        # the header shows one too (ticked every second by update_stats(),
        # same timer that already drives RX/TX/Connected).
        user_container = QVBoxLayout()
        user_top_row = QHBoxLayout()
        self.logged_in_user_label = QLabel(f"👤 {self.primary_frappe_username}")
        self.logged_in_user_label.setObjectName("loggedInUserLabel")
        self.logged_in_user_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #2c3e50;")
        self.logged_in_user_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.header_clock_label = QLabel(datetime.now().strftime("%H:%M:%S"))
        self.header_clock_label.setObjectName("headerClockLabel")
        self.header_clock_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #3498db;")
        self.header_clock_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        user_top_row.addWidget(self.logged_in_user_label)
        user_top_row.addWidget(self.header_clock_label)
        role_label = QLabel(self.primary_frappe_site_url)
        role_label.setStyleSheet("font-size: 10px; color: #7f8c8d;")
        role_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        user_container.addLayout(user_top_row)
        user_container.addWidget(role_label)
        header_layout.addLayout(user_container)

        return header_frame
    
    def create_connection_settings(self):
        settings_group = QGroupBox("Connection Settings")
        settings_group.setObjectName("settingsGroup")
        layout = QGridLayout(settings_group)
        
        layout.addWidget(QLabel("Port:"), 0, 0)
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(120)
        self.refresh_ports()
        layout.addWidget(self.port_combo, 0, 1)
        
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setMaximumWidth(100)
        self.refresh_btn.clicked.connect(self.refresh_ports)
        layout.addWidget(self.refresh_btn, 0, 2)
        
        layout.addWidget(QLabel("Baud Rate:"), 0, 3)
        self.baud_combo = QComboBox()
        self.baud_combo.setEditable(True)
        common_bauds = ["2400", "4800", "9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"]
        self.baud_combo.addItems(common_bauds)
        self.baud_combo.setCurrentText("2400")
        layout.addWidget(self.baud_combo, 0, 4)
        
        self.connect_btn = QPushButton("🔌 Connect")
        self.connect_btn.setObjectName("connectBtn")
        self.connect_btn.setMinimumHeight(35)
        self.connect_btn.setProperty("connected", "false")
        self.connect_btn.clicked.connect(self.toggle_connection)
        layout.addWidget(self.connect_btn, 0, 5)

        # Live connection statistics (updated once per second by update_stats)
        self.rx_label = QLabel("RX: 0 bytes")
        layout.addWidget(self.rx_label, 1, 0, 1, 2)
        self.tx_label = QLabel("TX: 0 bytes")
        layout.addWidget(self.tx_label, 1, 2, 1, 2)
        self.time_label = QLabel("Connected: 00:00:00")
        layout.addWidget(self.time_label, 1, 4, 1, 2)

        return settings_group
    
    def create_receive_area(self):
        receive_group = QGroupBox("Received Data")
        receive_group.setObjectName("dataGroup")
        layout = QVBoxLayout(receive_group)
        
        controls_layout = QHBoxLayout()
        self.timestamp_check = QCheckBox("Show timestamps")
        self.timestamp_check.setChecked(True)
        controls_layout.addWidget(self.timestamp_check)
        self.autoscroll_check = QCheckBox("Auto-scroll")
        self.autoscroll_check.setChecked(True)
        controls_layout.addWidget(self.autoscroll_check)
        controls_layout.addStretch()
        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("clearBtn")
        clear_btn.clicked.connect(self.clear_received_data)
        controls_layout.addWidget(clear_btn)
        save_btn = QPushButton("Save Log")
        save_btn.setObjectName("saveBtn")
        save_btn.clicked.connect(self.save_log)
        controls_layout.addWidget(save_btn)
        layout.addLayout(controls_layout)
        
        self.output = QTextEdit()
        self.output.setObjectName("dataOutput")
        self.output.setReadOnly(True)
        self.output.setFont(QFont("Consolas", 10))
        layout.addWidget(self.output)
        
        return receive_group
    
    def create_send_area(self):
        send_group = QGroupBox("Send Data")
        send_group.setObjectName("dataGroup")
        layout = QVBoxLayout(send_group)
        
        send_layout = QHBoxLayout()
        self.send_input = QLineEdit()
        self.send_input.setPlaceholderText("Enter data to send...")
        self.send_input.returnPressed.connect(self.send_data)
        send_layout.addWidget(self.send_input)
        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("sendBtn")
        self.send_btn.clicked.connect(self.send_data)
        self.send_btn.setMinimumWidth(80)
        send_layout.addWidget(self.send_btn)
        layout.addLayout(send_layout)
        
        history_label = QLabel("Send History:")
        layout.addWidget(history_label)
        self.send_history = QTextEdit()
        self.send_history.setObjectName("sendHistory")
        self.send_history.setReadOnly(True)
        self.send_history.setMaximumHeight(80)
        self.send_history.setFont(QFont("Consolas", 9))
        layout.addWidget(self.send_history)
        
        return send_group
    
    def create_settings_tab(self):
        # Outer widget just hosts a scroll area, so the settings tab never gets cut off
        # as more setting groups (Frappe instances, RFID, ...) are added over time.
        settings_tab = QWidget()
        outer_layout = QVBoxLayout(settings_tab)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Tab header
        settings_header = QLabel("⚙️  Application Settings")
        settings_header.setStyleSheet("font-size: 18px; font-weight: 700; color: #2c3e50; background: transparent;")
        layout.addWidget(settings_header)
        settings_subheader = QLabel("Serial/hardware options and the RFID reader.")
        settings_subheader.setStyleSheet("color: #7f8c8d; font-size: 11px; background: transparent;")
        layout.addWidget(settings_subheader)

        # Serial Settings Group
        serial_group = QGroupBox("🔌  Advanced Serial Settings")
        serial_group.setObjectName("serialSettingsGroup")
        serial_layout = QGridLayout(serial_group)
        serial_layout.setContentsMargins(14, 18, 14, 14)
        serial_layout.setHorizontalSpacing(12)
        serial_layout.setVerticalSpacing(10)

        serial_layout.addWidget(QLabel("Data Bits:"), 0, 0)
        self.databits_combo = QComboBox()
        self.databits_combo.addItems(["5", "6", "7", "8"])
        self.databits_combo.setCurrentText("8")
        serial_layout.addWidget(self.databits_combo, 0, 1)
        
        serial_layout.addWidget(QLabel("Parity:"), 0, 2)
        self.parity_combo = QComboBox()
        self.parity_combo.addItems(["None", "Even", "Odd", "Mark", "Space"])
        serial_layout.addWidget(self.parity_combo, 0, 3)
        
        serial_layout.addWidget(QLabel("Stop Bits:"), 1, 0)
        self.stopbits_combo = QComboBox()
        self.stopbits_combo.addItems(["1", "1.5", "2"])
        serial_layout.addWidget(self.stopbits_combo, 1, 1)
        
        serial_layout.addWidget(QLabel("Timeout (s):"), 1, 2)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 60)
        self.timeout_spin.setValue(1)
        serial_layout.addWidget(self.timeout_spin, 1, 3)
        
        layout.addWidget(serial_group)

        # Secondary/Third Frappe Instance settings, the Trip Sheet Frappe
        # instance (Auto-Login) and the Primary->Secondary Auto Sync toggle
        # have been removed from this tab (per request) - their credential
        # inputs and status widgets no longer exist. The backing session
        # objects, __init__ defaults and sync/login methods are left in
        # place (now unused) rather than removed.

        # RFID Reader Settings Group - lets the weighbridge/reader IP, port and the
        # Frappe "Rfid tag Reading" API endpoint/token be changed at runtime instead of
        # only via the hardcoded defaults in __init__. Saving tears down the current
        # socket/threads and reconnects with the new values - no app restart needed.
        rfid_group = QGroupBox("📡  RFID Reader Settings")
        rfid_group.setObjectName("rfidSettingsGroup")
        rfid_layout = QGridLayout(rfid_group)
        rfid_layout.setContentsMargins(14, 18, 14, 14)
        rfid_layout.setHorizontalSpacing(12)
        rfid_layout.setVerticalSpacing(10)

        rfid_layout.addWidget(QLabel("Reader IP:"), 0, 0)
        self.rfid_ip_input = QLineEdit()
        self.rfid_ip_input.setText(self.rfid_ip)
        self.rfid_ip_input.setPlaceholderText("e.g., 192.168.10.244")
        rfid_layout.addWidget(self.rfid_ip_input, 0, 1)

        rfid_layout.addWidget(QLabel("Reader Port:"), 0, 2)
        self.rfid_port_input = QLineEdit()
        self.rfid_port_input.setText(str(self.rfid_port))
        self.rfid_port_input.setPlaceholderText("e.g., 6000")
        rfid_layout.addWidget(self.rfid_port_input, 0, 3)

        rfid_layout.addWidget(QLabel("API Endpoint:"), 1, 0)
        self.rfid_api_endpoint_input = QLineEdit()
        self.rfid_api_endpoint_input.setText(self.rfid_api_endpoint)
        self.rfid_api_endpoint_input.setPlaceholderText("e.g., http://<site>/api/resource/Rfid tag Reading/1")
        rfid_layout.addWidget(self.rfid_api_endpoint_input, 1, 1, 1, 3)

        rfid_layout.addWidget(QLabel("API Token:"), 2, 0)
        self.rfid_api_token_input = QLineEdit()
        self.rfid_api_token_input.setText(self.rfid_api_token)
        self.rfid_api_token_input.setEchoMode(QLineEdit.Password)
        self.rfid_api_token_input.setPlaceholderText("Frappe API key:secret")
        rfid_layout.addWidget(self.rfid_api_token_input, 2, 1, 1, 3)

        self.rfid_status_label = QLabel("Status: Connecting...")
        self.rfid_status_label.setObjectName("settingsStatusPill")
        rfid_layout.addWidget(self.rfid_status_label, 3, 0, 1, 2)

        save_rfid_btn = QPushButton("💾  Save && Reconnect")
        save_rfid_btn.setObjectName("saveApiBtn")
        save_rfid_btn.clicked.connect(self.save_rfid_settings)
        rfid_layout.addWidget(save_rfid_btn, 3, 2, 1, 2, alignment=Qt.AlignRight)

        layout.addWidget(rfid_group)

        layout.addStretch()

        scroll_area.setWidget(content)
        outer_layout.addWidget(scroll_area)

        return settings_tab

    def _unwrap_scrollable_tab(self, tab_widget):
        """Several create_*_tab() builders wrap their content in their own QScrollArea
        (needed when they filled a whole QTabWidget page). Inside an accordion section
        that inner QScrollArea would otherwise collapse to a small fixed-height box with
        its own scrollbar, cutting fields off. Instead of moving widgets around (risky -
        can corrupt the layout tree), just size that inner scroll area to fit its content
        and turn its own scrollbar off, so only the one outer accordion scroll area scrolls."""
        inner_scroll = tab_widget.findChild(QScrollArea)
        if inner_scroll is not None:
            inner_widget = inner_scroll.widget()
            if inner_widget is not None:
                inner_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                inner_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                inner_scroll.setMinimumHeight(inner_widget.sizeHint().height() + 12)
        return tab_widget

    # ------------------------------------------------------------------
    # Live Posting Date / Posting Time (always the current system clock)
    # ------------------------------------------------------------------
    def _refresh_posting_datetime_now(self):
        """Force Posting Date and Posting Time to the current system date/time."""
        now = datetime.now()
        posting_date = self.form_fields.get("posting_date")
        if posting_date is not None:
            posting_date.setDate(QDate(now.year, now.month, now.day))
        posting_time = self.form_fields.get("posting_time")
        if posting_time is not None:
            posting_time.setTime(QTime(now.hour, now.minute, now.second))

    def _tick_posting_datetime(self):
        """Called every second. Keeps Posting Date/Time locked to the live system
        clock unless the operator ticked 'Edit Posting Date & Time' to override them."""
        edit_checkbox = self.form_fields.get("edit")
        if edit_checkbox is not None and edit_checkbox.isChecked():
            return
        self._refresh_posting_datetime_now()

    def _tick_weight_timestamps(self):
        """No longer wired to posting_datetime_timer (Posting Date/Time is now the
        only field kept live-ticking) - kept here unused in case it's needed again.
        Gross/Tare Weight Timestamp are set once at form creation/clear instead, and
        get_gross_weight()/get_tare_weight() stamp the real capture moment directly."""
        now = datetime.now()
        if not self._gross_weight_captured:
            field = self.form_fields.get("gross_weight_timestamp")
            if field is not None:
                field.setDateTime(now)
        if not self._tare_weight_captured:
            field = self.form_fields.get("tare_weight_timestamp")
            if field is not None:
                field.setDateTime(now)

    def _tick_token_datetime(self):
        """No longer wired to posting_datetime_timer (Posting Date/Time is now the
        only field kept live-ticking) - kept here unused in case it's needed again.
        Token Date/Token Time are set once at form creation/clear instead."""
        now = datetime.now()
        token_date = self.form_fields.get("token_date")
        if token_date is not None:
            token_date.setDate(QDate(now.year, now.month, now.day))
        token_time = self.form_fields.get("token_time")
        if token_time is not None:
            token_time.setTime(QTime(now.hour, now.minute, now.second))

    def _on_edit_posting_datetime_toggled(self, state):
        """'Edit Posting Date & Time' checkbox: unchecked (default) = fields are
        locked to the live clock; checked = operator can manually set a backdated
        Posting Date/Time. Turning it back off snaps the fields back to 'now'."""
        edit_checkbox = self.form_fields.get("edit")
        editable = bool(edit_checkbox.isChecked()) if edit_checkbox is not None else False
        posting_date = self.form_fields.get("posting_date")
        if posting_date is not None:
            posting_date.setEnabled(editable)
        posting_time = self.form_fields.get("posting_time")
        if posting_time is not None:
            posting_time.setEnabled(editable)
        if not editable:
            self._refresh_posting_datetime_now()

    def _default_weight_bridge_users(self):
        """Gross/Tare Weight Bridge User default to the currently logged-in user.
        Only fills them when empty - once a value is present (typed by the operator,
        or otherwise set), it is left alone."""
        username = self.primary_frappe_username or ""
        for key in ("gross_weight_bridge_user", "tare_weight_bridge_user"):
            field = self.form_fields.get(key)
            if field is not None and not field.text().strip():
                field.setText(username)

    # ------------------------------------------------------------------
    # Cane Weight API integration (quantbit_agriculture_crm.exe_api.get_cane_weight_data)
    # ------------------------------------------------------------------
    def _trip_sheet_prefix_for_season(self, season_text):
        """Derive the 'TS/xxxx/' prefix from a season string like '2026-2027' -> 'TS/2627/',
        so this keeps working automatically every new season instead of needing a hardcoded
        prefix update each year. Falls back to self.TRIP_SHEET_PREFIX if parsing fails."""
        try:
            start, end = (season_text or "").split("-")
            code = start[-2:] + end[-2:]
            if len(code) == 4 and code.isdigit():
                return f"TS/{code}/"
        except (ValueError, AttributeError):
            pass
        return self.TRIP_SHEET_PREFIX

    def fetch_cane_weight_data_from_trip_sheet_no(self):
        """Operator types only the numeric Trip Sheet No. (e.g. "1258"). We add the
        "TS/xxxx/" prefix automatically (derived from the selected Season), call
        exe_api.get_cane_weight_data with the full document name, and auto-populate
        the Cane Weight form from the response."""
        if not self.primary_frappe_logged_in:
            QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance!")
            return

        trip_sheet_field = self.form_fields.get("trip_sheet")
        if trip_sheet_field is None:
            return
        raw_no = trip_sheet_field.text().strip()
        if not raw_no:
            QMessageBox.warning(self, "Warning", "Please enter a Trip Sheet No. (e.g. 134)!")
            return

        # get_cane_weight_data requires trip_sheet, season, posting_date and posting_time -
        # pull season/posting_date/posting_time straight from the live form fields so they
        # always match what's actually on screen (posting_date/time track the system clock).
        season_field = self.form_fields.get("season")
        posting_date_field = self.form_fields.get("posting_date")
        posting_time_field = self.form_fields.get("posting_time")
        season_value = season_field.currentText() if season_field is not None else ""
        posting_date_value = posting_date_field.date().toString("yyyy-MM-dd") if posting_date_field is not None else ""
        posting_time_value = posting_time_field.time().toString("HH:mm:ss") if posting_time_field is not None else ""

        # If the operator already typed the full "TS/2627/1258" form, don't double-prefix it.
        # Otherwise derive the "TS/xxxx/" prefix from the currently selected Season (e.g.
        # "2026-2027" -> "TS/2627/") so this keeps working automatically every new season.
        prefix = self._trip_sheet_prefix_for_season(season_value)
        full_trip_sheet_no = raw_no if raw_no.upper().startswith("TS/") else f"{prefix}{raw_no}"

        try:
            url = f"{self.primary_frappe_site_url}/api/method/quantbit_agriculture_crm.exe_api.get_cane_weight_data"
            headers = {"Accept": "application/json"}
            params = {
                "trip_sheet": full_trip_sheet_no,
                "season": season_value,
                "posting_date": posting_date_value,
                "posting_time": posting_time_value,
            }
            self.output.append(f"[Cane Weight API] Fetching data for Trip Sheet: {full_trip_sheet_no}, season={season_value}, posting_date={posting_date_value}, posting_time={posting_time_value}")
            response = self.primary_frappe_session.get(url, headers=headers, params=params, timeout=20)
            response.raise_for_status()
            result = response.json()

            # Response shape: {"message": {"status": ..., "message": ..., "doc_status": ..., "data": {...actual fields...}}}
            message_obj = result.get("message") or {}
            status = message_obj.get("status")
            status_text = message_obj.get("message", "")
            doc_status = message_obj.get("doc_status", "")
            data = message_obj.get("data") or {}

            if status != "success" or not data:
                QMessageBox.warning(self, "Not Found", status_text or f"No data found for Trip Sheet No.: {full_trip_sheet_no}")
                return

            self._populate_cane_weight_form_from_exe_api(data, full_trip_sheet_no)
            self.output.append(f"[Cane Weight API] {status_text} (doc_status={doc_status}) - form populated from {full_trip_sheet_no}")
            QMessageBox.information(self, "Success", f"{status_text or 'Cane Weight form populated'} from Trip Sheet {full_trip_sheet_no}")

        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            self.output.append(f"[Cane Weight API Error] {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to fetch Trip Sheet data:\n\n{error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error: {str(e)}"
            self.output.append(f"[Cane Weight API Error] {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to fetch Trip Sheet data:\n\n{error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Cane Weight API Error] {error_msg}")
            QMessageBox.critical(self, "Error", f"Unexpected error while fetching Trip Sheet data:\n\n{error_msg}")

    def _set_form_field_value(self, field_key, value):
        """Safely set a value onto a form_fields widget by key - skips silently if the
        field doesn't exist on this form or the API didn't return a value for it."""
        widget = self.form_fields.get(field_key)
        if widget is None or value is None:
            return
        try:
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QComboBox):
                text = str(value)
                if widget.findText(text) == -1:
                    widget.addItem(text)
                widget.setCurrentText(text)
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setValue(float(value) if value != "" else 0)
            elif isinstance(widget, QDateEdit):
                date = QDate.fromString(str(value), "yyyy-MM-dd")
                if date.isValid():
                    widget.setDate(date)
            elif isinstance(widget, QTimeEdit):
                time_val = QTime.fromString(str(value), "HH:mm:ss")
                if time_val.isValid():
                    widget.setTime(time_val)
            elif isinstance(widget, QLineEdit):
                widget.setText(str(value))
        except Exception as e:
            self.output.append(f"[Cane Weight API] Could not set field '{field_key}': {e}")

    def _recalculate_diesel_allocation(self):
        """Dynamically recalculate diesel_allocation = base + heavy_vehicle_allowance + extra_fuel_allocation"""
        try:
            extra_widget = self.form_fields.get("extra_fuel_allocation")
            extra_val = float(extra_widget.text().strip() or 0.0) if extra_widget else 0.0
        except (ValueError, AttributeError):
            extra_val = 0.0
        try:
            heavy_widget = self.form_fields.get("heavy_vehicle_fuel_allowance")
            heavy_val = float(heavy_widget.text().strip() or 0.0) if heavy_widget else 0.0
        except (ValueError, AttributeError):
            heavy_val = 0.0
        base_val = getattr(self, "_base_diesel_allocation", 0.0)
        total = round(base_val + heavy_val + extra_val, 2)
        diesel_widget = self.form_fields.get("diesel_allocation")
        if diesel_widget is not None:
            diesel_widget.setText(str(total))

    def _populate_cane_weight_form_from_exe_api(self, data, full_trip_sheet_no):
        """Populate the Cane Weight form from a quantbit_agriculture_crm.exe_api.get_data
        response. Posting Date/Time are deliberately never touched here - they always
        track the live system clock (see _refresh_posting_datetime_now)."""
        field_keys = [
            "company", "season", "branch", "shift", "season_day", "factory_day",
            "cane_registration", "crop_variety", "route", "farmer", "crop_type",
            "distance", "is_flat_rate", "farmer_name", "area_in_acrs", "circle_office",
            "survey_number", "is_kisan_card", "village", "transporter_contract",
            "transporter", "harvester_contract", "harvester", "transporter_name",
            "transporter_vehicle_type", "transporter_gang_type", "vehicle_no",
            "trolly_1", "trolly_2", "ht_driver", "harvester_name",
            "harvester_vehicle_type", "harvester_gang_type", "cane_deduction_type",
            "deduction", "water_share", "rope_placement",
            "auto_token_no", "token_user", "token_no",
            # Weight Information - present when this trip sheet already has a saved
            # draft Cane Weight entry (doc_status "Draft"), so re-fetching resumes it.
            "gross_weight", "gross_weight_bridge", "gross_weight_bridge_user",
            "tare_weight", "tare_weight_bridge", "tare_weight_bridge_user",
            "cane_weight", "binding_weight", "net_weight",
            "farmer_weight", "transporter_weight", "harvester_weight",
            # token_date/token_time deliberately excluded - they always track the live
            # system clock now, same as posting_date/posting_time (see _tick_token_datetime).
            # Local Language (LL) Name fields - Read Only, display-only.
            "village_ll_name", "route_ll_name", "sub_village_ll_name",
            "circle_office_ll_name", "taluka_ll_name", "district_ll_name",
            "state_ll_name", "crop_type_ll_name", "crop_seed_ll_name",
            "soil_type_ll_name", "seed_type_ll_name", "irrigation_method_ll_name",
            "crop_variety_ll_name", "farmer_ll_name", "transporter_ll_name",
            "cane_deduction_type_ll_name", "rope_placement_ll_name", "harvester_ll_name",
            "ht_driver_ll_name",
            # Field Slip tab
            "slip_boy_name",
            # Fuel fields
            "heavy_vehicle_fuel_allowance", "extra_fuel_allocation", "diesel_allocation",
        ]
        for key in field_keys:
            if key in data:
                self._set_form_field_value(key, data.get(key))

        base_alloc = data.get("base_allocation")
        if base_alloc is not None:
            self._base_diesel_allocation = float(base_alloc)
        else:
            d_alloc = float(data.get("diesel_allocation") or 0.0)
            h_alloc = float(data.get("heavy_vehicle_fuel_allowance") or 0.0)
            e_alloc = float(data.get("extra_fuel_allocation") or 0.0)
            self._base_diesel_allocation = max(0.0, d_alloc - h_alloc - e_alloc)

        # Needed by _build_cane_weight_payload to recompute cane_weight/binding_weight/
        # net_weight the same way CaneWeight.actual_weight() does server-side.
        self._cane_weight_binding_percent = data.get("binding_weight_percent") or 1

        # Gross/Tare Weight Timestamp are QDateTimeEdit fields (not handled by the generic
        # setter above) that normally live-tick until captured. If the draft already has a
        # real timestamp, apply it directly and mark that weight "captured" so it freezes
        # there instead of being overwritten by the next tick.
        gross_ts = data.get("gross_weight_timestamp")
        if gross_ts:
            dt = QDateTime.fromString(str(gross_ts), "yyyy-MM-dd HH:mm:ss")
            field = self.form_fields.get("gross_weight_timestamp")
            if dt.isValid() and field is not None:
                field.setDateTime(dt)
                self._gross_weight_captured = True
        tare_ts = data.get("tare_weight_timestamp")
        if tare_ts:
            dt = QDateTime.fromString(str(tare_ts), "yyyy-MM-dd HH:mm:ss")
            field = self.form_fields.get("tare_weight_timestamp")
            if dt.isValid() and field is not None:
                field.setDateTime(dt)
                self._tare_weight_captured = True

        # Show the fully-resolved Trip Sheet No. (with prefix) back to the operator
        # so the field submits the correct document name.
        if "trip_sheet" in self.form_fields:
            self.form_fields["trip_sheet"].setText(full_trip_sheet_no)

        # Penalty charges come back pre-computed from the backend - populate the
        # table directly instead of re-deriving them client-side.
        self._populate_penalty_charges_table_from_api(data.get("penalty_charges") or [])

        # Posting Date/Time always track the live system clock - never from API data.
        self._refresh_posting_datetime_now()

    def _populate_penalty_charges_table_from_api(self, penalty_rows):
        penalty_table = self.form_fields.get("penalty_charges")
        if penalty_table is None:
            return
        penalty_table.setRowCount(0)
        for row_data in penalty_rows:
            row = penalty_table.rowCount()
            penalty_table.insertRow(row)
            penalty_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            penalty_table.setItem(row, 1, self._make_penalty_readonly_item(str(row_data.get("entity_code") or "")))
            penalty_table.setItem(row, 2, self._make_penalty_readonly_item(str(row_data.get("entity_name") or "")))
            penalty_table.setItem(row, 3, self._make_penalty_readonly_item(str(row_data.get("entity_type") or "")))
            penalty_table.setItem(row, 4, QTableWidgetItem(str(row_data.get("deduction_type") or "")))
            penalty_table.setCellWidget(row, 5, self._make_penalty_deduction_method_combo(str(row_data.get("deduction_method") or "")))
            deduction_rate_val = row_data.get("deduction_rate")
            penalty_table.setItem(row, 6, QTableWidgetItem("" if deduction_rate_val is None else str(deduction_rate_val)))
            penalty_table.setItem(row, 7, QTableWidgetItem(""))
            penalty_table.setItem(row, 8, QTableWidgetItem(""))
        self.output.append(f"[Cane Weight API] Populated {len(penalty_rows)} penalty charge row(s) from API")

    def create_cane_form_tab(self):
        cane_form_tab = QWidget()
        outer_layout = QVBoxLayout(cane_form_tab)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # Cane Weight has two inner tabs: "Field Slip" (tab 1, a compact
        # quick-entry view - see create_field_slip_tab) and "Detailed Entry"
        # (tab 2, built below). Each field lives in exactly one of the two
        # tabs - Field Slip's fields (plus the Submit/Save/Clear/View
        # Submitted Records actions) have been removed from the Detailed
        # Entry sections below to avoid duplicating them.
        cane_inner_tabs = QTabWidget()

        detailed_entry_tab = self._build_detailed_entry_tab()

        field_slip_tab = self.create_field_slip_tab()
        cane_inner_tabs.addTab(field_slip_tab, "Field Slip")
        cane_inner_tabs.addTab(detailed_entry_tab, "Detailed Entry")

        outer_layout.addWidget(cane_inner_tabs)

        self._lock_cane_weight_fields_read_only()

        return cane_form_tab

    def _lock_cane_weight_fields_read_only(self):
        """Cane Weight form policy: every field on the Field Slip and Detailed
        Entry tabs is populated via 'Get Data' / weighbridge capture and is
        Read Only, except Trip Sheet No. (to look the record up) and
        Gross/Tare Weight (typed manually or captured from the bridge)."""
        editable_fields = {"trip_sheet", "gross_weight", "tare_weight"}
        for field_name, widget in self.form_fields.items():
            if field_name in editable_fields:
                continue
            if isinstance(widget, QLineEdit):
                widget.setReadOnly(True)
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit)):
                widget.setReadOnly(True)
            elif isinstance(widget, (QComboBox, QCheckBox)):
                widget.setEnabled(False)
            elif isinstance(widget, QTableWidget):
                widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
                for row in range(widget.rowCount()):
                    for col in range(widget.columnCount()):
                        cell_widget = widget.cellWidget(row, col)
                        if cell_widget is not None:
                            cell_widget.setEnabled(False)

    def _build_detailed_entry_tab(self):
        """Detailed Entry (Cane Weight tab 2): two plain, always-visible group
        boxes (no collapsible accordion, no more one-box-per-section):

        - "Basic Information": its own fields, then all Local Language (LL)
          Names fields, then all Trip Sheet & Registration Details fields,
          then Token Details fields - with the Penalty Charges table nested
          at the bottom of this same box (kept horizontal/full-width there,
          not squeezed into a side column).
        - "Details": HT Details fields, then Deduction Details fields.

        Each _fields_*() helper below builds its widgets and registers them
        in self.form_fields exactly as before (by field name) - only which
        combined box they land in, and their row/column position, changed."""
        detailed_entry_tab = QWidget()
        outer_layout = QVBoxLayout(detailed_entry_tab)
        outer_layout.setContentsMargins(6, 6, 6, 6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(8)

        # create_penalty_charges_tab()'s return value is a throwaway
        # QScrollArea/stretch wrapper with no Qt parent of its own; the
        # QGroupBox found inside it is still Qt-owned (parented) by that
        # wrapper. If the wrapper went out of scope before the group box is
        # reparented elsewhere, Python would garbage-collect the wrapper,
        # which (per Qt's C++ parent/child ownership) deletes the group
        # box's C++ object right along with it - so it's detached
        # (setParent(None)) immediately, in the same call that creates it.
        def extract_group_box(wrapper):
            boxes = wrapper.findChildren(QGroupBox)
            if not boxes:
                return None
            gb = boxes[0]
            gb.setParent(None)
            gb.setCheckable(False)  # always visible - no collapse toggle
            return gb

        # --- Group box 1: Basic Information -----------------------------------
        basic_info_group = QGroupBox("Basic Information")
        basic_info_outer = QVBoxLayout(basic_info_group)

        basic_fields_widget = QWidget()
        basic_fields_grid = QGridLayout(basic_fields_widget)
        basic_fields_grid.setSpacing(6)
        basic_items = []
        basic_items.extend(self._fields_basic_info())
        basic_items.extend(self._fields_ll_names())
        basic_items.extend(self._fields_trip_sheet_registration())
        basic_items.extend(self._fields_token_details())
        self._populate_compact_grid(basic_fields_grid, basic_items)
        basic_info_outer.addWidget(basic_fields_widget)

        penalty_group = extract_group_box(self.create_penalty_charges_tab())
        basic_info_outer.addWidget(penalty_group or QGroupBox("Penalty Charges"))

        container_layout.addWidget(basic_info_group)

        # --- Group box 2: Details (HT Details, then Deduction Details) -------
        details_group = QGroupBox("Details")
        details_grid = QGridLayout(details_group)
        details_grid.setSpacing(6)
        details_items = []
        details_items.extend(self._fields_ht_details())
        details_items.extend(self._fields_deduction_details())
        self._populate_compact_grid(details_grid, details_items)

        container_layout.addWidget(details_group)
        container_layout.addStretch()

        scroll.setWidget(container)
        outer_layout.addWidget(scroll)

        return detailed_entry_tab

    def _fields_basic_info(self):
        """Basic Information's own fields. Season, Posting Date, Branch,
        Posting Time, Shift and Factory Day live on the Field Slip tab's
        Basic Info group box instead (see create_field_slip_tab). Season Day
        moved here from that same group box."""
        company_edit = QLineEdit()
        company_edit.setText("KRANTIAGRANI DR G D BAPU LAD SAHAKARI SAKHAR KARKHANA LIMITED KUNDAL")
        self.form_fields["company"] = company_edit

        edit_check = QCheckBox()
        edit_check.setToolTip("Check to manually set Posting Date/Time; uncheck to snap back to the live system clock.")
        self.form_fields["edit"] = edit_check
        edit_check.stateChanged.connect(self._on_edit_posting_datetime_toggled)

        naming_series_combo = QComboBox()
        naming_series_combo.addItems(["CW-.YY.-"])
        self.form_fields["naming_series"] = naming_series_combo

        season_day_spin = QSpinBox()
        season_day_spin.setRange(0, 365)
        self.form_fields["season_day"] = season_day_spin

        return [
            ("Company", company_edit),
            ("Edit Posting Date & Time", edit_check),
            ("Naming Series", naming_series_combo),
            ("Season Day", season_day_spin),
        ]

    def _fields_ll_names(self):
        """Local Language (LL) Name fields not already on the Field Slip tab
        (village_ll_name, route_ll_name, circle_office_ll_name,
        crop_type_ll_name, farmer_ll_name, transporter_ll_name,
        rope_placement_ll_name, harvester_ll_name and ht_driver_ll_name live
        there instead - see create_field_slip_tab). Every field here is Read
        Only, same as the DocType's LL Name section."""
        ll_name_fields = [
            ("sub_village_ll_name", "Sub Village LL Name"),
            ("taluka_ll_name", "Taluka LL Name"),
            ("district_ll_name", "District LL Name"),
            ("state_ll_name", "State LL Name"),
            ("crop_seed_ll_name", "Crop Seed LL Name"),
            ("soil_type_ll_name", "Soil Type LL Name"),
            ("seed_type_ll_name", "Seed Type LL Name"),
            ("irrigation_method_ll_name", "Irrigation Method LL Name"),
            ("crop_variety_ll_name", "Crop Variety LL Name"),
            ("cane_deduction_type_ll_name", "Cane Deduction Type LL Name"),
        ]
        items = []
        for fieldname, label in ll_name_fields:
            ll_name_edit = QLineEdit()
            ll_name_edit.setReadOnly(True)
            self.form_fields[fieldname] = ll_name_edit
            items.append((label, ll_name_edit))
        return items

    def _fields_trip_sheet_registration(self):
        """Trip Sheet & Registration Details' fields. Trip Sheet No., Get
        Data, Cane Registration, Crop Variety and Distance stay on the Field
        Slip tab (see create_field_slip_tab) - still the same self.form_fields
        entries. Crop Type and Survey Number moved here from the Field Slip
        tab. Token No moved from here to the Field Slip tab's Basic Info group
        box (see create_field_slip_tab). Farmer, Transporter Contract,
        Harvester Contract and Branch moved here from the Field Slip tab."""
        branch_combo = QComboBox()
        branch_combo.addItems(["Bedkihal", "Kundal", "Nagpur", "Nagewadi"])
        branch_combo.setCurrentText("Kundal")
        self.form_fields["branch"] = branch_combo

        route_edit = QLineEdit()
        self.form_fields["route"] = route_edit

        is_flat_rate_check = QCheckBox()
        self.form_fields["is_flat_rate"] = is_flat_rate_check

        farmer_name_edit = QLineEdit()
        self.form_fields["farmer_name"] = farmer_name_edit

        transporter_name_edit = QLineEdit()
        self.form_fields["transporter_name"] = transporter_name_edit

        harvester_name_edit = QLineEdit()
        self.form_fields["harvester_name"] = harvester_name_edit

        area_in_acrs_edit = QLineEdit("0.000")
        area_in_acrs_edit.setValidator(QDoubleValidator(0.000, 99999.999, 3))
        self.form_fields["area_in_acrs"] = area_in_acrs_edit

        is_kisan_card_check = QCheckBox()
        self.form_fields["is_kisan_card"] = is_kisan_card_check

        circle_office_edit = QLineEdit()
        self.form_fields["circle_office"] = circle_office_edit

        crop_type_edit = QLineEdit()
        self.form_fields["crop_type"] = crop_type_edit

        survey_number_edit = QLineEdit()
        self.form_fields["survey_number"] = survey_number_edit

        farmer_edit = QLineEdit()
        self.form_fields["farmer"] = farmer_edit

        transporter_contract_edit = QLineEdit()
        self.form_fields["transporter_contract"] = transporter_contract_edit

        harvester_contract_edit = QLineEdit()
        self.form_fields["harvester_contract"] = harvester_contract_edit

        return [
            ("Branch", branch_combo),
            ("Route", route_edit),
            ("Is Flat Rate", is_flat_rate_check),
            ("Farmer Name", farmer_name_edit),
            ("Transporter Name", transporter_name_edit),
            ("Harvester Name", harvester_name_edit),
            ("Area in Acrs", area_in_acrs_edit),
            ("Is Kisan Card", is_kisan_card_check),
            ("Circle Office", circle_office_edit),
            ("Crop Type", crop_type_edit),
            ("Survey Number", survey_number_edit),
            ("Farmer", farmer_edit),
            ("Transporter Contract", transporter_contract_edit),
            ("Harvester Contract", harvester_contract_edit),
        ]

    def _fields_token_details(self):
        """Token Details' fields. Token Date and Token Time stay on the Field
        Slip tab (see create_field_slip_tab). Auto Token No moved back here
        from the Field Slip tab."""
        # Trip Sheet Selection widgets removed from the visible UI (per an
        # earlier request), but still created (not added to any layout) so
        # other code that references them (fetch_trip_sheets,
        # populate_form_from_trip_sheet, populate_form_from_trip_sheet_data,
        # submit_form's slip_no field, etc.) keeps working.
        self.slip_no_combo = QComboBox()
        self.slip_no_combo.currentIndexChanged.connect(self.populate_form_from_trip_sheet)
        slip_no_spin = QSpinBox()
        slip_no_spin.setRange(0, 999999)
        self.form_fields["slip_no"] = slip_no_spin
        slip_no_spin.editingFinished.connect(self.on_slip_no_changed)

        auto_token_no_edit = QLineEdit()
        self.form_fields["auto_token_no"] = auto_token_no_edit

        token_user_edit = QLineEdit()
        self.form_fields["token_user"] = token_user_edit

        return [("Auto Token No.", auto_token_no_edit), ("Token User", token_user_edit)]

    def _fields_ht_details(self):
        """HT Details' fields. Transporter Vehicle Type ("Vehicle Type") and
        Vehicle No moved to the Field Slip tab's Slip Details group box."""
        transporter_edit = QLineEdit()
        self.form_fields["transporter"] = transporter_edit

        transporter_gang_type_edit = QLineEdit()
        self.form_fields["transporter_gang_type"] = transporter_gang_type_edit

        harvester_edit = QLineEdit()
        self.form_fields["harvester"] = harvester_edit

        harvester_vehicle_type_edit = QLineEdit()
        self.form_fields["harvester_vehicle_type"] = harvester_vehicle_type_edit

        harvester_gang_type_edit = QLineEdit()
        self.form_fields["harvester_gang_type"] = harvester_gang_type_edit

        trolly_1_edit = QLineEdit()
        self.form_fields["trolly_1"] = trolly_1_edit

        trolly_2_edit = QLineEdit()
        self.form_fields["trolly_2"] = trolly_2_edit

        rope_placement_edit = QLineEdit()
        self.form_fields["rope_placement"] = rope_placement_edit

        return [
            ("Transporter", transporter_edit),
            ("Transporter Gang Type", transporter_gang_type_edit),
            ("Harvester", harvester_edit),
            ("Harvester Vehicle Type", harvester_vehicle_type_edit),
            ("Harvester Gang Type", harvester_gang_type_edit),
            ("Trolly 1", trolly_1_edit),
            ("Trolly 2", trolly_2_edit),
            ("Rope Placement", rope_placement_edit),
        ]

    def _fields_deduction_details(self):
        """Deduction Details' fields."""
        cane_deduction_type_edit = QLineEdit()
        self.form_fields["cane_deduction_type"] = cane_deduction_type_edit

        deduction_edit = QLineEdit("0.00")
        deduction_edit.setValidator(QDoubleValidator(0.00, 100.00, 2))
        self.form_fields["deduction"] = deduction_edit

        water_share_edit = QLineEdit("0.00")
        water_share_edit.setValidator(QDoubleValidator(0.00, 100.00, 2))
        self.form_fields["water_share"] = water_share_edit

        cane_deduction_weight_edit = QLineEdit("0.000")
        cane_deduction_weight_edit.setValidator(QDoubleValidator(0.000, 9999999.999, 3))
        self.form_fields["cane_deduction_weight"] = cane_deduction_weight_edit

        water_supplier_weight_edit = QLineEdit("0.000")
        water_supplier_weight_edit.setValidator(QDoubleValidator(0.000, 9999999.999, 3))
        self.form_fields["water_supplier_weight"] = water_supplier_weight_edit

        dcp_check = QCheckBox()
        dcp_check.setChecked(False)
        self.form_fields["dcp"] = dcp_check

        return [
            ("Cane Deduction Type", cane_deduction_type_edit),
            ("Deduction (%)", deduction_edit),
            ("Water Share (%)", water_share_edit),
            ("Cane Deduction Weight", cane_deduction_weight_edit),
            ("Water Supplier Weight", water_supplier_weight_edit),
            ("DCP (Daily Cane Purchase)", dcp_check),
        ]

    def create_field_slip_tab(self):
        """Compact 'Field Slip' quick-entry view (Cane Weight tab 1 of 2).

        Every field listed in the spec lives ONLY here - the Detailed Entry
        tab's own create_*_tab() methods (tab 2) have had these same fields
        removed from them, so self.form_fields keeps exactly one widget per
        field name (registered here instead of there) and every existing
        populate/collect/save code path (which looks fields up by name) keeps
        working untouched.

        Laid out 5 label+field slots per row (10 grid columns) with no inner
        scroll area, so the slip - weight section and action buttons included
        - fits on screen without scrolling, per spec.
        """
        field_slip_tab = QWidget()
        layout = QVBoxLayout(field_slip_tab)
        layout.setSpacing(8)

        SLOTS_PER_ROW = 5
        N_COLS = SLOTS_PER_ROW * 2

        def add_row(grid, row, items):
            """items: list of (label_or_None, widget). label=None makes the
            widget (e.g. a button) span the full label+field slot width."""
            for slot, (label, widget) in enumerate(items):
                col = slot * 2
                if label is None:
                    grid.addWidget(widget, row, col, 1, 2)
                else:
                    grid.addWidget(QLabel(label), row, col)
                    grid.addWidget(widget, row, col + 1)

        def stretch_field_columns(grid, n_cols=None):
            for c in range(1, n_cols if n_cols is not None else N_COLS, 2):
                grid.setColumnStretch(c, 1)

        def field(field_key, read_only=False):
            w = QLineEdit()
            if read_only:
                w.setReadOnly(True)
            self.form_fields[field_key] = w
            return w

        def date_field(field_key):
            w = QDateEdit()
            w.setDisplayFormat("yyyy-MM-dd")
            w.setDate(datetime.now().date())
            w.setEnabled(False)  # live: locked to the system clock (or the "Edit
            # Posting Date & Time" checkbox in Basic Information for posting_date)
            self.form_fields[field_key] = w
            return w

        def time_field(field_key):
            w = QTimeEdit()
            w.setDisplayFormat("HH:mm:ss")
            w.setTime(datetime.now().time())
            w.setEnabled(False)  # live: see date_field() above
            self.form_fields[field_key] = w
            return w

        def spin_field(field_key, minimum=0, maximum=9999):
            w = QSpinBox()
            w.setRange(minimum, maximum)
            self.form_fields[field_key] = w
            return w

        def combo_field(field_key, items, current):
            w = QComboBox()
            w.addItems(items)
            w.setCurrentText(current)
            self.form_fields[field_key] = w
            return w

        def datetime_field(field_key, read_only=False):
            w = QDateTimeEdit()
            w.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
            w.setDateTime(datetime.now())
            if read_only:
                w.setReadOnly(True)
            self.form_fields[field_key] = w
            return w

        # --- Basic Info (above Trip Sheet No.) ---------------------------------
        # Posting Date and Posting Time moved here (into the same row as
        # Season/Shift) from the Slip Details group box below. Season Day
        # moved out to the Detailed Entry tab (see _fields_basic_info). Branch
        # moved out to the Detailed Entry tab too (see
        # _fields_trip_sheet_registration). Token No/Date/Time moved in from
        # the Slip Details group box below, all in this same row.
        basic_info_fields = [
            ("Season", combo_field("season", ["2026-2027", "2027-2028" , "2028-2029" , "2029-2030"], "2026-2027")),
            ("Shift", combo_field("shift", ["1st", "2nd", "3rd"], "1st")),
            ("Posting Date", date_field("posting_date")),
            ("Posting Time", time_field("posting_time")),
            ("Factory Day", spin_field("factory_day", 0, 365)),
            ("Token No", field("token_no")),
            ("Token Date", date_field("token_date")),
            ("Token Time", time_field("token_time")),
        ]
        basic_info_group = QGroupBox("Basic Info")
        basic_info_grid = QGridLayout(basic_info_group)
        add_row(basic_info_grid, 0, basic_info_fields)
        stretch_field_columns(basic_info_grid, n_cols=len(basic_info_fields) * 2)

        # --- Row 1: Trip Sheet No. + Get Data ---------------------------------
        top_row_widget = QWidget()
        top_row_layout = QHBoxLayout(top_row_widget)
        top_row_layout.setContentsMargins(0, 0, 0, 0)

        trip_sheet_edit = QLineEdit()
        trip_sheet_edit.setPlaceholderText("e.g. 134")
        trip_sheet_edit.setToolTip('Enter only the number - the "TS/2627/" prefix for the selected Season is added automatically.')
        trip_sheet_edit.setStyleSheet("font-size: 22px; font-weight: bold; color: red;")
        self.form_fields["trip_sheet"] = trip_sheet_edit
        trip_sheet_edit.returnPressed.connect(self.fetch_cane_weight_data_from_trip_sheet_no)

        get_data_btn = QPushButton("Get Data")
        get_data_btn.setToolTip("Fetch Cane Weight data for this Trip Sheet No. and auto-fill the form")
        get_data_btn.clicked.connect(self.fetch_cane_weight_data_from_trip_sheet_no)

        top_row_layout.addWidget(QLabel("Trip Sheet No."))
        top_row_layout.addWidget(trip_sheet_edit, 1)
        top_row_layout.addWidget(get_data_btn)
        top_row_layout.addStretch(3)

        # --- Rows 2+: compact fields, 6 per row --------------------------------
        # Auto Token No., Crop Type and Survey Number live on the Detailed Entry
        # tab instead (see _fields_token_details / _fields_trip_sheet_registration).
        # Farmer, Transporter Contract and Harvester Contract moved to the
        # Detailed Entry tab (same helper). Posting Date/Posting Time and
        # Token No/Date/Time moved up to the Basic Info group box. All
        # "* LL Name" fields moved out into their own "Details" group box
        # below this one (see details_fields further down).
        compact_fields = [
            ("Cane Registration", field("cane_registration")),
            ("Crop Variety", field("crop_variety")),
            ("Vehicle Type", field("transporter_vehicle_type")),
            ("Slip Boy Name", field("slip_boy_name")),
            ("Distance", spin_field("distance", 0, 9999)),
            ("Vehicle No", field("vehicle_no")),
        ]

        heavy_vehicle_fuel_allowance_edit = field("heavy_vehicle_fuel_allowance", read_only=True)
        extra_fuel_allocation_edit = field("extra_fuel_allocation")
        extra_fuel_allocation_edit.setValidator(QDoubleValidator(0.00, 99999.00, 2))
        extra_fuel_allocation_edit.textChanged.connect(self._recalculate_diesel_allocation)
        diesel_allocation_edit = field("diesel_allocation", read_only=True)

        fuel_fields = [
            ("Heavy Vehicle Fuel Allowance", heavy_vehicle_fuel_allowance_edit),
            ("Extra Fuel Allocation", extra_fuel_allocation_edit),
            ("Diesel Allocation", diesel_allocation_edit),
        ]

        fields_group = QGroupBox("Slip Details")
        SLIP_DETAILS_SLOTS_PER_ROW = 6
        fields_grid = QGridLayout(fields_group)
        for i in range(0, len(compact_fields), SLIP_DETAILS_SLOTS_PER_ROW):
            add_row(fields_grid, i // SLIP_DETAILS_SLOTS_PER_ROW, compact_fields[i:i + SLIP_DETAILS_SLOTS_PER_ROW])

        # Row 1: Heavy Vehicle Fuel Allowance, Extra Fuel Allocation, Diesel Allocation in a single row
        for idx, (label, widget) in enumerate(fuel_fields):
            col = idx * 4
            fields_grid.addWidget(QLabel(label), 1, col)
            fields_grid.addWidget(widget, 1, col + 1, 1, 3)

        stretch_field_columns(fields_grid, n_cols=SLIP_DETAILS_SLOTS_PER_ROW * 2)

        # --- Details group box: every field that used to live in
        # Slip Details, 3 per row (LL Name removed from label) ------------
        rope_placement_ll_name_edit = field("rope_placement_ll_name", read_only=True)
        rope_placement_ll_name_edit.setMinimumWidth(320)  # holds noticeably longer text than the other fields

        farmer_ll_name_edit = field("farmer_ll_name", read_only=True)

        details_fields = [
            ("Route", field("route_ll_name", read_only=True)),
            ("Village", field("village_ll_name", read_only=True)),
            ("Crop Type", field("crop_type_ll_name", read_only=True)),
            ("Circle Office", field("circle_office_ll_name", read_only=True)),
            ("Farmer", farmer_ll_name_edit),
            ("Transporter", field("transporter_ll_name", read_only=True)),
            ("Harvester", field("harvester_ll_name", read_only=True)),
            ("HT Driver", field("ht_driver_ll_name", read_only=True)),
            ("Rope Placement", rope_placement_ll_name_edit),
        ]

        details_group = QGroupBox("Details")
        # Bigger value font for every field in this box; Rope Placement and
        # Farmer LL Name additionally get a red value, per spec.
        details_group.setStyleSheet("QGroupBox QLineEdit { font-size: 15px; }")
        red_value_style = "font-size: 15px; color: red;"
        rope_placement_ll_name_edit.setStyleSheet(red_value_style)
        farmer_ll_name_edit.setStyleSheet(red_value_style)
        DETAILS_SLOTS_PER_ROW = 3
        details_field_grid = QGridLayout(details_group)
        for i in range(0, len(details_fields), DETAILS_SLOTS_PER_ROW):
            add_row(details_field_grid, i // DETAILS_SLOTS_PER_ROW, details_fields[i:i + DETAILS_SLOTS_PER_ROW])
        stretch_field_columns(details_field_grid, n_cols=DETAILS_SLOTS_PER_ROW * 2)

        # --- Weight section (kept at the bottom, per spec) ---------------------
        # Row 1: Gross Weight. Row 2: Tare Weight. Row 3+: remaining weights,
        # 5 per row.
        get_gross_btn = QPushButton("Get Gross Weight")
        get_gross_btn.clicked.connect(self.get_gross_weight)
        get_tare_btn = QPushButton("Get Tare Weight")
        get_tare_btn.clicked.connect(self.get_tare_weight)

        # Every field in this group box is Read Only, per spec.
        # Gross/Tare Weight get a large, bold, red font so the operator can
        # read the captured value at a glance.
        weight_value_style = "font-size: 28px; font-weight: bold; color: red;"

        gross_weight_edit = field("gross_weight")
        gross_weight_edit.setValidator(QDoubleValidator(0.000, 9999.999, 3))
        gross_weight_edit.setToolTip("Type the weight manually, or use 'Get Gross Weight' to capture it from the connected weighbridge.")
        gross_weight_edit.setStyleSheet(weight_value_style)
        tare_weight_edit = field("tare_weight")
        tare_weight_edit.setValidator(QDoubleValidator(0.000, 9999.999, 3))
        tare_weight_edit.setToolTip("Type the weight manually, or use 'Get Tare Weight' to capture it from the connected weighbridge.")
        tare_weight_edit.setStyleSheet(weight_value_style)

        net_weight_edit = field("net_weight", read_only=True)
        net_weight_edit.setStyleSheet("color: red;")

        # Bridge User fields default to the logged-in user, same as Detailed Entry
        # used to (still kept in sync by _default_weight_bridge_users()).
        gross_weight_bridge_user_edit = field("gross_weight_bridge_user", read_only=True)
        gross_weight_bridge_user_edit.setText(self.primary_frappe_username or "")
        tare_weight_bridge_user_edit = field("tare_weight_bridge_user", read_only=True)
        tare_weight_bridge_user_edit.setText(self.primary_frappe_username or "")

        weight_rows = [
            [
                ("Gross Weight Bridge", field("gross_weight_bridge", read_only=True)),
                ("Gross Weight", gross_weight_edit),
                (None, get_gross_btn),
                ("Gross Weight Bridge User", gross_weight_bridge_user_edit),
                ("Gross Weight Timestamp", datetime_field("gross_weight_timestamp", read_only=True)),
            ],
            [
                ("Tare Weight Bridge", field("tare_weight_bridge", read_only=True)),
                ("Tare Weight", tare_weight_edit),
                (None, get_tare_btn),
                ("Tare Weight Bridge User", tare_weight_bridge_user_edit),
                ("Tare Weight Timestamp", datetime_field("tare_weight_timestamp", read_only=True)),
            ],
            [
                ("Cane Weight", field("cane_weight", read_only=True)),
                ("Net Weight", net_weight_edit),
                ("Binding Weight", field("binding_weight", read_only=True)),
                ("Farmer Weight", field("farmer_weight", read_only=True)),
                ("Transporter Weight", field("transporter_weight", read_only=True)),
            ],
            [
                ("Harvester Weight", field("harvester_weight", read_only=True)),
            ],
        ]

        weight_group = QGroupBox("Weight")
        weight_group.setStyleSheet(
            "QGroupBox { font-size: 17px; font-weight: bold; } "
            "QGroupBox QLabel { font-size: 15px; font-weight: 600; color: #2c3e50; } "
            "QGroupBox QLineEdit, QGroupBox QDateTimeEdit { "
            "  font-size: 16px; padding: 4px 6px; min-height: 26px; "
            "  background-color: #ffffff; border: 1px solid #b8c2cc; border-radius: 3px; "
            "} "
            "QGroupBox QLineEdit:read-only, QGroupBox QDateTimeEdit:read-only { "
            "  background-color: #f7f9fa; color: #1a1a1a; "
            "}"
        )
        weight_grid = QGridLayout(weight_group)
        weight_grid.setHorizontalSpacing(14)
        weight_grid.setVerticalSpacing(10)
        for row, items in enumerate(weight_rows):
            add_row(weight_grid, row, items)
        stretch_field_columns(weight_grid)

        # --- Form actions (moved here from Detailed Entry to keep this the one
        # compact, self-sufficient workflow tab) ---------------------------------
        actions_layout = QHBoxLayout()
        actions_layout.addStretch()

        self.cane_weight_submit_btn = QPushButton("Submit Form")
        self.cane_weight_submit_btn.setObjectName("submitBtn")
        # submit_form() no longer clears the form - the operator uses the
        # separate Clear Form button for that (see _send_cane_weight_payload's
        # clear_after=False).
        self.cane_weight_submit_btn.clicked.connect(self.submit_form)
        self.cane_weight_submit_btn.setMinimumHeight(40)
        self.cane_weight_submit_btn.setMinimumWidth(120)
        actions_layout.addWidget(self.cane_weight_submit_btn)

        self.cane_weight_save_btn = QPushButton("Save Form")
        self.cane_weight_save_btn.setObjectName("saveBtn")
        # Same as Submit above - save_form() does not clear the form either.
        self.cane_weight_save_btn.clicked.connect(self.save_form)
        self.cane_weight_save_btn.setMinimumHeight(40)
        self.cane_weight_save_btn.setMinimumWidth(120)
        actions_layout.addWidget(self.cane_weight_save_btn)

        self.cane_weight_clear_btn = QPushButton("Clear Form")
        self.cane_weight_clear_btn.setObjectName("clearBtn")
        self.cane_weight_clear_btn.clicked.connect(self.clear_form)
        self.cane_weight_clear_btn.setMinimumHeight(40)
        self.cane_weight_clear_btn.setMinimumWidth(120)
        actions_layout.addWidget(self.cane_weight_clear_btn)

        view_submitted_btn = QPushButton("View Submitted Records")
        view_submitted_btn.setObjectName("viewBtn")
        view_submitted_btn.clicked.connect(self.view_submitted_cane_weight_records)
        view_submitted_btn.setMinimumHeight(40)
        view_submitted_btn.setMinimumWidth(160)
        actions_layout.addWidget(view_submitted_btn)

        layout.addWidget(basic_info_group)
        layout.addWidget(top_row_widget)
        layout.addWidget(fields_group)
        layout.addWidget(details_group)
        layout.addWidget(weight_group)
        layout.addLayout(actions_layout)
        layout.addStretch()

        return field_slip_tab

    # def create_slip_details_tab(self):
    #     """Placeholder tab - removed as fields don't exist in DocType"""
    #     placeholder_tab = QWidget()
    #     layout = QVBoxLayout(placeholder_tab)
        
    #     info_label = QLabel("All Cane Weight fields are now organized in the other tabs.\nThis tab has been removed as the fields don't exist in the Cane Weight DocType.")
    #     info_label.setWordWrap(True)
    #     info_label.setStyleSheet("font-size: 14px; padding: 20px;")
    #     layout.addWidget(info_label)
    #     layout.addStretch()
        
    #     return placeholder_tab

    def create_penalty_charges_tab(self):
        penalty_charges_tab = QWidget()
        layout = QVBoxLayout(penalty_charges_tab)
        
        # Create a scrollable area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # Penalty Charges Section
        penalty_group = QGroupBox("Penalty Charges")
        penalty_group.setCheckable(True)  # Make collapsable
        penalty_group.setChecked(True)  # Start collapsed

        penalty_group_layout = QVBoxLayout(penalty_group)
        penalty_content_widget = QWidget()
        penalty_layout = QVBoxLayout(penalty_content_widget)
        
        # Penalty Charges Label
        penalty_label = QLabel("Penalty Charges")
        penalty_layout.addWidget(penalty_label)
        
        # Create penalty charges table. Columns match the "Cane Weight Penalty
        # Charges" child DocType exactly (it has no Deduction or Vendor Name
        # fields, so those columns were dropped); Entity Code/Name/Type are
        # Read Only (fetched from the trip sheet/API, not typed here), and
        # Deduction Method is a dropdown restricted to the DocType's Select
        # options (see PENALTY_DEDUCTION_METHODS).
        penalty_table = QTableWidget()
        penalty_table.setRowCount(3)
        penalty_table.setColumnCount(9)
        penalty_table.setHorizontalHeaderLabels([
            "No.", "Entity Code", "Entity Name", "Entity Type", "Deduction Type",
            "Deduction Method", "Deduction Rate", "Debit Account", "Credit Account"
        ])
        penalty_table.setMinimumHeight(150)

        # Set column widths
        penalty_table.setColumnWidth(0, 50)
        penalty_table.setColumnWidth(1, 100)
        penalty_table.setColumnWidth(2, 120)
        penalty_table.setColumnWidth(3, 100)
        penalty_table.setColumnWidth(4, 120)
        penalty_table.setColumnWidth(5, 120)
        penalty_table.setColumnWidth(6, 100)
        penalty_table.setColumnWidth(7, 150)
        penalty_table.setColumnWidth(8, 150)

        # Populate the initial blank rows the same way as any other row so
        # Entity Code/Name/Type start Read Only and Deduction Method starts
        # as a dropdown, instead of plain freely-editable empty cells.
        for row in range(penalty_table.rowCount()):
            penalty_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            for col in (1, 2, 3):
                penalty_table.setItem(row, col, self._make_penalty_readonly_item())
            penalty_table.setCellWidget(row, 5, self._make_penalty_deduction_method_combo())

        penalty_layout.addWidget(penalty_table)
        self.form_fields["penalty_charges"] = penalty_table
        
        # Buttons layout
        buttons_layout = QHBoxLayout()
        
        # Auto Populate button
        auto_populate_btn = QPushButton("Auto Populate")
        auto_populate_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        auto_populate_btn.clicked.connect(self.auto_populate_penalty_charges)
        auto_populate_btn.setMinimumHeight(35)
        buttons_layout.addWidget(auto_populate_btn)
        
        # Add Row button
        add_row_btn = QPushButton("Add Row")
        add_row_btn.clicked.connect(lambda: self.add_penalty_row(penalty_table))
        add_row_btn.setMinimumHeight(35)
        buttons_layout.addWidget(add_row_btn)
        
        penalty_layout.addLayout(buttons_layout)
        
        penalty_group_layout.addWidget(penalty_content_widget)
        penalty_group.toggled.connect(penalty_content_widget.setVisible)
        scroll_layout.addWidget(penalty_group)
        scroll_layout.addStretch()
        
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

        return penalty_charges_tab

    def create_fuel_sale_tab(self):
        fuel_sale_tab = QWidget()
        layout = QVBoxLayout(fuel_sale_tab)
        layout.setSpacing(10)
        
        # Create a scrollable area for the form
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        form_layout = QVBoxLayout(scroll_widget)

        # Create a horizontal splitter for the main layout
        main_horizontal_splitter = QSplitter(Qt.Horizontal)

        # Left Panel for Basic Information
        left_panel_widget = QWidget()
        left_panel_layout = QVBoxLayout(left_panel_widget)
        left_panel_layout.setContentsMargins(0, 0, 0, 0)
        left_panel_layout.setSpacing(10)
        
        # Basic Information Section
        basic_group = QGroupBox("Basic Information")
        basic_group.setCheckable(True)
        basic_group.setChecked(True)

        basic_group_layout = QVBoxLayout(basic_group)
        basic_content_widget = QWidget()
        basic_layout = QGridLayout(basic_content_widget)
        
        # Row 1: Season, Branch, Shift Type
        basic_layout.addWidget(QLabel("Season"), 0, 0)
        season_combo = QComboBox()
        season_combo.addItems(["2026-2027", "2027-2028" , "2028-2029" , "2029-2030"])
        season_combo.setCurrentText("2026-2027")
        basic_layout.addWidget(season_combo, 0, 1)
        self.fuel_sale_fields["season"] = season_combo
        season_combo.currentTextChanged.connect(lambda: self.on_fuel_sale_params_changed())
        
        basic_layout.addWidget(QLabel("Branch"), 0, 2)
        branch_combo = QComboBox()
        branch_combo.addItem("Loading branches...")
        basic_layout.addWidget(branch_combo, 0, 3)
        self.fuel_sale_fields["branch"] = branch_combo
        branch_combo.currentTextChanged.connect(lambda: self.on_fuel_sale_params_changed())
        
        basic_layout.addWidget(QLabel("Shift Type"), 0, 4)
        shift_type_combo = QComboBox()
        shift_type_combo.addItems(["1st", "2nd", "3rd"])
        shift_type_combo.setCurrentText("1st")
        basic_layout.addWidget(shift_type_combo, 0, 5)
        self.fuel_sale_fields["shift_type"] = shift_type_combo

        # Row 2: Posting Date, Posting Time
        basic_layout.addWidget(QLabel("Posting Date"), 1, 0)
        posting_date_edit = QDateEdit()
        posting_date_edit.setDisplayFormat("yyyy-MM-dd")
        posting_date_edit.setDate(datetime.now().date())
        basic_layout.addWidget(posting_date_edit, 1, 1)
        self.fuel_sale_fields["posting_date"] = posting_date_edit

        basic_layout.addWidget(QLabel("Posting Time"), 1, 2)
        posting_time_edit = QTimeEdit()
        posting_time_edit.setDisplayFormat("HH:mm:ss")
        posting_time_edit.setTime(datetime.now().time())
        basic_layout.addWidget(posting_time_edit, 1, 3)
        self.fuel_sale_fields["posting_time"] = posting_time_edit

        basic_layout.addWidget(QLabel("Edit Posting Date and Time"), 1, 4)
        edit_posting_check = QCheckBox()
        basic_layout.addWidget(edit_posting_check, 1, 5)
        self.fuel_sale_fields["edit_posting_date_and_time"] = edit_posting_check

        # Row 3: Fuel Sale Type, Contract
        basic_layout.addWidget(QLabel("Fuel Sale Type"), 2, 0)
        fuel_sale_type_combo = QComboBox()
        fuel_sale_type_combo.addItem("Loading fuel sale types...")
        basic_layout.addWidget(fuel_sale_type_combo, 2, 1)
        self.fuel_sale_fields["fuel_sale_type"] = fuel_sale_type_combo
        # When fuel sale type changes, fetch items for that type
        fuel_sale_type_combo.currentTextChanged.connect(self.on_fuel_sale_type_changed)

        basic_layout.addWidget(QLabel("Contract"), 2, 2)
        contract_combo = QComboBox()
        contract_combo.addItem("Loading contracts...")
        basic_layout.addWidget(contract_combo, 2, 3)
        self.fuel_sale_fields["contract"] = contract_combo
        contract_combo.currentTextChanged.connect(lambda: self.on_fuel_sale_params_changed())

        # Row 4: Entity Type, Party
        basic_layout.addWidget(QLabel("Entity Type"), 3, 0)
        entity_type_combo = QComboBox()
        entity_type_combo.addItem("Loading entity types...")
        basic_layout.addWidget(entity_type_combo, 3, 1)
        self.fuel_sale_fields["entity_type"] = entity_type_combo

        basic_layout.addWidget(QLabel("Party"), 3, 2)
        party_edit = QLineEdit()
        party_edit.setText("E00002")
        basic_layout.addWidget(party_edit, 3, 3)
        self.fuel_sale_fields["party"] = party_edit

        basic_layout.addWidget(QLabel("Party Name"), 3, 4)
        party_name_edit = QLineEdit()
        party_name_edit.setText("सीता")
        basic_layout.addWidget(party_name_edit, 3, 5)
        self.fuel_sale_fields["party_name"] = party_name_edit

        # Row 5: Checkboxes
        basic_layout.addWidget(QLabel("Is Extra Fuel"), 4, 0)
        is_extra_fuel_check = QCheckBox()
        basic_layout.addWidget(is_extra_fuel_check, 4, 1)
        self.fuel_sale_fields["is_extra_fuel"] = is_extra_fuel_check

        basic_layout.addWidget(QLabel("Is Returned"), 4, 2)
        is_returned_check = QCheckBox()
        basic_layout.addWidget(is_returned_check, 4, 3)
        self.fuel_sale_fields["is_returned"] = is_returned_check

        # Row 6: Debit Account, Currency
        basic_layout.addWidget(QLabel("Debit Account"), 5, 0)
        debit_account_combo = QComboBox()
        debit_account_combo.addItem("Loading accounts...")
        basic_layout.addWidget(debit_account_combo, 5, 1)
        self.fuel_sale_fields["debit_account"] = debit_account_combo

        basic_layout.addWidget(QLabel("Currency"), 5, 2)
        currency_combo = QComboBox()
        currency_combo.addItems(["INR"])  # Use configured company currency
        basic_layout.addWidget(currency_combo, 5, 3)
        self.fuel_sale_fields["currency"] = currency_combo

        # Row 7: Total Quantity, Total Amount
        basic_layout.addWidget(QLabel("Total Quantity"), 6, 0)
        total_quantity_spin = QDoubleSpinBox()
        total_quantity_spin.setRange(0, 999999.99)
        total_quantity_spin.setValue(10)
        basic_layout.addWidget(total_quantity_spin, 6, 1)
        self.fuel_sale_fields["total_quantity"] = total_quantity_spin

        basic_layout.addWidget(QLabel("Total Amount"), 6, 2)
        total_amount_spin = QDoubleSpinBox()
        total_amount_spin.setRange(0, 999999.99)
        total_amount_spin.setValue(750)
        basic_layout.addWidget(total_amount_spin, 6, 3)
        self.fuel_sale_fields["total_amount"] = total_amount_spin

        # Row 8: Total Amount in Words
        basic_layout.addWidget(QLabel("Total Amount in Words"), 7, 0)
        total_amount_words_edit = QLineEdit()
        total_amount_words_edit.setText("INR Seven Hundred And Fifty only.")
        basic_layout.addWidget(total_amount_words_edit, 7, 1, 1, 3)
        self.fuel_sale_fields["total_amount_in_words"] = total_amount_words_edit

        basic_group_layout.addWidget(basic_content_widget)
        basic_group.toggled.connect(basic_content_widget.setVisible)
        left_panel_layout.addWidget(basic_group)

        # Right Panel for Fuel Sale Items Table
        right_panel_widget = QWidget()
        right_panel_layout = QVBoxLayout(right_panel_widget)
        right_panel_layout.setContentsMargins(0, 0, 0, 0)
        right_panel_layout.setSpacing(10)

        # Fuel Sale Items Section
        items_group = QGroupBox("Fuel Sale Items")
        items_group.setCheckable(True)
        items_group.setChecked(True)

        items_group_layout = QVBoxLayout(items_group)
        
        # Create table for fuel sale items
        self.fuel_sale_items_table = QTableWidget()
        self.fuel_sale_items_table.setColumnCount(10)
        self.fuel_sale_items_table.setHorizontalHeaderLabels([
            "Item Code", "Item Name", "Quantity", "Amount", "Warehouse", 
            "Allocated Quantity", "UOM", "Rate", "Expense Account", "Income Account"
        ])
        
        # Set column widths
        header = self.fuel_sale_items_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.Stretch)
        header.setSectionResizeMode(9, QHeaderView.Stretch)


        items_group_layout.addWidget(self.fuel_sale_items_table)

        # Add/Remove row buttons
        items_buttons_layout = QHBoxLayout()
        add_item_btn = QPushButton("Add Item")
        add_item_btn.clicked.connect(self.add_fuel_sale_item_row)
        items_buttons_layout.addWidget(add_item_btn)

        remove_item_btn = QPushButton("Remove Item")
        remove_item_btn.clicked.connect(self.remove_fuel_sale_item_row)
        items_buttons_layout.addWidget(remove_item_btn)

        items_buttons_layout.addStretch()
        items_group_layout.addLayout(items_buttons_layout)

        right_panel_layout.addWidget(items_group)

        # Add the left and right panels to the splitter
        main_horizontal_splitter.addWidget(left_panel_widget)
        main_horizontal_splitter.addWidget(right_panel_widget)

        # Set initial sizes for the splitter
        main_horizontal_splitter.setSizes([400, 600])

        form_layout.addWidget(main_horizontal_splitter)

        # Action buttons
        actions_layout = QHBoxLayout()
        
        submit_btn = QPushButton("Submit Fuel Sale")
        submit_btn.clicked.connect(self.submit_fuel_sale_form)
        submit_btn.setMinimumHeight(40)
        submit_btn.setMinimumWidth(150)
        actions_layout.addWidget(submit_btn)

        save_btn = QPushButton("Save Fuel Sale")
        save_btn.clicked.connect(self.save_fuel_sale_form)
        save_btn.setMinimumHeight(40)
        save_btn.setMinimumWidth(150)
        actions_layout.addWidget(save_btn)

        clear_btn = QPushButton("Clear Form")
        clear_btn.clicked.connect(self.clear_fuel_sale_form)
        clear_btn.setMinimumHeight(40)
        clear_btn.setMinimumWidth(120)
        actions_layout.addWidget(clear_btn)

        view_submitted_fuel_btn = QPushButton("View Submitted Fuel Sales")
        view_submitted_fuel_btn.clicked.connect(self.view_submitted_fuel_sale_records)
        view_submitted_fuel_btn.setMinimumHeight(40)
        view_submitted_fuel_btn.setMinimumWidth(200)
        actions_layout.addWidget(view_submitted_fuel_btn)

        actions_layout.addStretch()
        form_layout.addLayout(actions_layout)
        form_layout.addStretch()

        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

        # Fetch dynamic options shortly after UI is ready
        QTimer.singleShot(200, self.fetch_branches_for_fuel_sale)
        QTimer.singleShot(240, self.fetch_fuel_sale_types)
        QTimer.singleShot(260, self.fetch_contracts_for_fuel_sale)
        QTimer.singleShot(280, self.fetch_entity_types_for_fuel_sale)
        QTimer.singleShot(300, self.fetch_accounts_for_fuel_sale)

        # Resolve shift type based on posting time shortly after UI is ready
        QTimer.singleShot(320, self.update_fuel_sale_shift_from_server)
        # Also update shift whenever posting time changes
        posting_time_edit.timeChanged.connect(lambda _t: self.update_fuel_sale_shift_from_server())

        return fuel_sale_tab

    def create_auto_token_tab(self):
        auto_token_tab = QWidget()
        layout = QVBoxLayout(auto_token_tab)
        layout.setSpacing(10)
        
        # Create a scrollable area for the form
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        form_layout = QVBoxLayout(scroll_widget)

        # Create a horizontal splitter for the main layout
        main_horizontal_splitter = QSplitter(Qt.Horizontal)

        # Left Panel for Basic Information
        left_panel_widget = QWidget()
        left_panel_layout = QVBoxLayout(left_panel_widget)
        left_panel_layout.setContentsMargins(0, 0, 0, 0)
        left_panel_layout.setSpacing(10)
        
        # Basic Information Section
        basic_group = QGroupBox("Basic Information")
        basic_group.setCheckable(True)
        basic_group.setChecked(True)

        basic_group_layout = QVBoxLayout(basic_group)
        basic_content_widget = QWidget()
        basic_layout = QGridLayout(basic_content_widget)
        
        # Row 1: Season, Branch, Posting Date
        basic_layout.addWidget(QLabel("Season"), 0, 0)
        season_combo = QComboBox()
        season_combo.addItem("Loading seasons...")
        basic_layout.addWidget(season_combo, 0, 1)
        self.auto_token_fields["season"] = season_combo
        
        basic_layout.addWidget(QLabel("Branch"), 0, 2)
        branch_combo = QComboBox()
        branch_combo.addItem("Loading branches...")
        basic_layout.addWidget(branch_combo, 0, 3)
        self.auto_token_fields["branch"] = branch_combo
        
        # Fetch season and branch from API
        QTimer.singleShot(0, self.fetch_seasons_for_auto_token)
        QTimer.singleShot(0, self.fetch_branches_for_auto_token)

        basic_layout.addWidget(QLabel("Posting Date"), 0, 4)
        posting_date_edit = QDateEdit()
        posting_date_edit.setDisplayFormat("yyyy-MM-dd")
        posting_date_edit.setDate(datetime.now().date())
        basic_layout.addWidget(posting_date_edit, 0, 5)
        self.auto_token_fields["posting_date"] = posting_date_edit

        # Row 2: Posting Time, Shift, Edit
        basic_layout.addWidget(QLabel("Posting Time"), 1, 0)
        posting_time_edit = QTimeEdit()
        posting_time_edit.setDisplayFormat("HH:mm:ss")
        posting_time_edit.setTime(datetime.now().time())
        basic_layout.addWidget(posting_time_edit, 1, 1)
        self.auto_token_fields["posting_time"] = posting_time_edit

        basic_layout.addWidget(QLabel("Shift"), 1, 2)
        shift_combo = QComboBox()
        shift_combo.addItems(["1st", "2nd", "3rd"])
        shift_combo.setCurrentText("3rd")
        basic_layout.addWidget(shift_combo, 1, 3)
        self.auto_token_fields["shift"] = shift_combo

        basic_layout.addWidget(QLabel("Edit"), 1, 4)
        edit_check = QCheckBox()
        edit_check.setChecked(True)
        basic_layout.addWidget(edit_check, 1, 5)
        self.auto_token_fields["edit"] = edit_check

        # Row 3: Season Day, Token No, Factory Day
        basic_layout.addWidget(QLabel("Season Day"), 2, 0)
        season_day_spin = QSpinBox()
        season_day_spin.setRange(1, 9999)
        season_day_spin.setValue(487)
        basic_layout.addWidget(season_day_spin, 2, 1)
        self.auto_token_fields["season_day"] = season_day_spin

        basic_layout.addWidget(QLabel("Token No"), 2, 2)
        token_no_edit = QLineEdit()
        token_no_edit.setText("TT-1")
        basic_layout.addWidget(token_no_edit, 2, 3)
        self.auto_token_fields["token_no"] = token_no_edit

        basic_layout.addWidget(QLabel("Factory Day"), 2, 4)
        factory_day_spin = QSpinBox()
        factory_day_spin.setRange(1, 9999)
        factory_day_spin.setValue(30)
        basic_layout.addWidget(factory_day_spin, 2, 5)
        self.auto_token_fields["factory_day"] = factory_day_spin

        # Row 4: Transporter Contract, Transporter, Transporter Name
        basic_layout.addWidget(QLabel("Transporter Contract"), 3, 0)
        transporter_contract_combo = QComboBox()
        transporter_contract_combo.addItem("Loading contracts...")
        basic_layout.addWidget(transporter_contract_combo, 3, 1)
        self.auto_token_fields["transporter_contract"] = transporter_contract_combo

        # Connect season/branch changes to contract fetch
        self.auto_token_fields["season"].currentTextChanged.connect(self.fetch_contracts_for_auto_token)
        self.auto_token_fields["branch"].currentTextChanged.connect(self.fetch_contracts_for_auto_token)
        QTimer.singleShot(0, self.fetch_contracts_for_auto_token)
        transporter_contract_combo.currentTextChanged.connect(self.fetch_transporter_data_for_auto_token)

        basic_layout.addWidget(QLabel("Transporter"), 3, 2)
        transporter_edit = QLineEdit()
        transporter_edit.setReadOnly(True) # Make it read-only
        basic_layout.addWidget(transporter_edit, 3, 3)
        self.auto_token_fields["transporter"] = transporter_edit

        basic_layout.addWidget(QLabel("Transporter Name"), 3, 4)
        transporter_name_edit = QLineEdit()
        transporter_name_edit.setReadOnly(True) # Make it read-only
        basic_layout.addWidget(transporter_name_edit, 3, 5)
        self.auto_token_fields["transporter_name"] = transporter_name_edit

        # Row 5: Vehicle No, Transporter Vehicle Type, Transporter Gang Type
        basic_layout.addWidget(QLabel("Vehicle No"), 4, 0)
        vehicle_no_edit = QLineEdit()
        vehicle_no_edit.setReadOnly(True) # Make it read-only
        basic_layout.addWidget(vehicle_no_edit, 4, 1)
        self.auto_token_fields["vehicle_no"] = vehicle_no_edit

        basic_layout.addWidget(QLabel("Transporter Vehicle Type"), 4, 2)
        transporter_vehicle_type_combo = QComboBox() # Revert to QComboBox
        transporter_vehicle_type_combo.addItem("Loading...") # Initial placeholder
        basic_layout.addWidget(transporter_vehicle_type_combo, 4, 3)
        self.auto_token_fields["transporter_vehicle_type"] = transporter_vehicle_type_combo

        basic_layout.addWidget(QLabel("Transporter Gang Type"), 4, 4)
        transporter_gang_type_edit = QLineEdit()
        transporter_gang_type_edit.setReadOnly(True) # Keep as QLineEdit and read-only
        basic_layout.addWidget(transporter_gang_type_edit, 4, 5)
        self.auto_token_fields["transporter_gang_type"] = transporter_gang_type_edit

        # Row 6: No of Trip Sheet
        basic_layout.addWidget(QLabel("No of Trip Sheet"), 5, 0)
        no_of_tripsheet_spin = QSpinBox()
        no_of_tripsheet_spin.setRange(1, 999)
        no_of_tripsheet_spin.setValue(2)
        basic_layout.addWidget(no_of_tripsheet_spin, 5, 1)
        self.auto_token_fields["no_of_tripsheet"] = no_of_tripsheet_spin

        basic_group_layout.addWidget(basic_content_widget)
        basic_group.toggled.connect(basic_content_widget.setVisible)
        left_panel_layout.addWidget(basic_group)

        # Right Panel for Trip Sheet Details Table
        right_panel_widget = QWidget()
        right_panel_layout = QVBoxLayout(right_panel_widget)
        right_panel_layout.setContentsMargins(0, 0, 0, 0)
        right_panel_layout.setSpacing(10)

        # Trip Sheet Details Section
        trip_sheet_group = QGroupBox("Trip Sheet Details")
        trip_sheet_group.setCheckable(True)
        trip_sheet_group.setChecked(True)

        trip_sheet_group_layout = QVBoxLayout(trip_sheet_group)
        
        # Create table for trip sheet details
        self.auto_token_trip_sheet_table = QTableWidget()
        self.auto_token_trip_sheet_table.setColumnCount(15) # Increased to 15 columns
        self.auto_token_trip_sheet_table.setHorizontalHeaderLabels([
            "Select", "Season", "Branch", "Posting Date", "Trip Sheet No", 
            "Rope Placement", "Cane Registration", "Route", "Area in Acrs", 
            "Farmer", "Distance", "Transporter Contract", "Transporter",
            "Harvester Contract", "Harvester" # New columns
        ])
        
        # Set column widths
        header = self.auto_token_trip_sheet_table.horizontalHeader()
        for i in range(15):
            if i == 0:  # Select column
                header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
            elif i in [3, 4, 6, 7, 9, 11, 12, 13, 14]:  # Text columns including new ones
                header.setSectionResizeMode(i, QHeaderView.Stretch)
            else:  # Number columns
                header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        # Add sample row
        self.auto_token_trip_sheet_table.setRowCount(1)
        self.add_auto_token_trip_sheet_row()

        trip_sheet_group_layout.addWidget(self.auto_token_trip_sheet_table)

        # Add row button
        add_row_btn = QPushButton("Add Trip Sheet Row")
        add_row_btn.clicked.connect(self.add_auto_token_trip_sheet_row)
        add_row_btn.setMinimumHeight(30)
        trip_sheet_group_layout.addWidget(add_row_btn)

        right_panel_layout.addWidget(trip_sheet_group)

        # Add panels to splitter
        main_horizontal_splitter.addWidget(left_panel_widget)
        main_horizontal_splitter.addWidget(right_panel_widget)
        main_horizontal_splitter.setSizes([400, 600])

        form_layout.addWidget(main_horizontal_splitter)

        # Action buttons
        actions_layout = QHBoxLayout()
        
        submit_btn = QPushButton("Submit Auto Token")
        submit_btn.clicked.connect(self.submit_auto_token_form)
        submit_btn.setMinimumHeight(40)
        submit_btn.setMinimumWidth(150)
        actions_layout.addWidget(submit_btn)

        save_btn = QPushButton("Save Auto Token")
        save_btn.clicked.connect(self.save_auto_token_form)
        save_btn.setMinimumHeight(40)
        save_btn.setMinimumWidth(150)
        actions_layout.addWidget(save_btn)

        clear_btn = QPushButton("Clear Form")
        clear_btn.clicked.connect(self.clear_auto_token_form)
        clear_btn.setMinimumHeight(40)
        clear_btn.setMinimumWidth(150)
        actions_layout.addWidget(clear_btn)

        view_submitted_auto_token_btn = QPushButton("View Submitted Auto Tokens")
        view_submitted_auto_token_btn.clicked.connect(self.view_submitted_auto_token_records)
        view_submitted_auto_token_btn.setMinimumHeight(40)
        view_submitted_auto_token_btn.setMinimumWidth(200)
        actions_layout.addWidget(view_submitted_auto_token_btn)

        show_pending_slips_btn = QPushButton("Show Pending Slips")
        show_pending_slips_btn.clicked.connect(self.show_pending_slips_for_auto_token)
        show_pending_slips_btn.setMinimumHeight(40)
        show_pending_slips_btn.setMinimumWidth(150)
        actions_layout.addWidget(show_pending_slips_btn)

        actions_layout.addStretch()
        form_layout.addLayout(actions_layout)
        form_layout.addStretch()

        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

        # Connect signals to fetch shift/season/factory day
        posting_date_edit.dateChanged.connect(self.fetch_shift_season_factory_day_for_auto_token)
        posting_time_edit.timeChanged.connect(self.fetch_shift_season_factory_day_for_auto_token)
        season_combo.currentTextChanged.connect(self.fetch_shift_season_factory_day_for_auto_token)
        QTimer.singleShot(0, self.fetch_shift_season_factory_day_for_auto_token)

        return auto_token_tab

    def create_diesel_sale_tab(self):
        diesel_sale_tab = QWidget()
        layout = QVBoxLayout(diesel_sale_tab)
        layout.setSpacing(10)
        
        # Create a scrollable area for the form
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        form_layout = QVBoxLayout(scroll_widget)

        # Create a horizontal splitter for the main layout
        main_horizontal_splitter = QSplitter(Qt.Horizontal)

        # Left Panel for Basic Information
        left_panel_widget = QWidget()
        left_panel_layout = QVBoxLayout(left_panel_widget)
        left_panel_layout.setContentsMargins(0, 0, 0, 0)
        left_panel_layout.setSpacing(10)
        
        # Basic Information Section
        basic_group = QGroupBox("Diesel Sale Information")
        basic_group.setCheckable(True)
        basic_group.setChecked(True)

        basic_group_layout = QVBoxLayout(basic_group)
        basic_content_widget = QWidget()
        basic_layout = QGridLayout(basic_content_widget)
        
        # Row 0: Scan Barcode, Contract ID
        basic_layout.addWidget(QLabel("Scan Barcode"), 0, 0)
        scan_barcode_edit = QLineEdit()
        basic_layout.addWidget(scan_barcode_edit, 0, 1)
        self.diesel_sale_fields["scan_barcode"] = scan_barcode_edit
        
        basic_layout.addWidget(QLabel("Contract ID"), 0, 2)
        contract_id_edit = QLineEdit()
        basic_layout.addWidget(contract_id_edit, 0, 3)
        self.diesel_sale_fields["contract_id"] = contract_id_edit
        
        # Row 1: Season, Date, Shift
        basic_layout.addWidget(QLabel("Season"), 1, 0)
        season_combo = QComboBox()
        season_combo.addItem("2024-2025")
        season_combo.addItem("2023-2024")
        season_combo.addItem("2025-2026")
        basic_layout.addWidget(season_combo, 1, 1)
        self.diesel_sale_fields["season"] = season_combo
        
        basic_layout.addWidget(QLabel("Date"), 1, 2)
        date_edit = QDateEdit()
        date_edit.setDisplayFormat("yyyy-MM-dd")
        date_edit.setDate(datetime.now().date())
        basic_layout.addWidget(date_edit, 1, 3)
        self.diesel_sale_fields["date"] = date_edit

        basic_layout.addWidget(QLabel("Shift"), 1, 4)
        shift_combo = QComboBox()
        shift_combo.addItems(["1st", "2nd", "3rd"])
        shift_combo.setCurrentText("3rd")
        basic_layout.addWidget(shift_combo, 1, 5)
        self.diesel_sale_fields["shift"] = shift_combo

        # Row 2: Party Name, Customer Name
        basic_layout.addWidget(QLabel("Party Name"), 2, 0)
        party_name_edit = QLineEdit()
        basic_layout.addWidget(party_name_edit, 2, 1)
        self.diesel_sale_fields["party_name"] = party_name_edit
        
        basic_layout.addWidget(QLabel("Customer Name"), 2, 2)
        customer_name_edit = QLineEdit()
        basic_layout.addWidget(customer_name_edit, 2, 3, 1, 3)
        self.diesel_sale_fields["customer_name"] = customer_name_edit

        # Row 3: Company, Plant
        basic_layout.addWidget(QLabel("Company"), 3, 0)
        company_combo = QComboBox()
        company_combo.addItem("Venkateshwara Power Projects LTD")
        basic_layout.addWidget(company_combo, 3, 1)
        self.diesel_sale_fields["company"] = company_combo
        
        basic_layout.addWidget(QLabel("Plant"), 3, 2)
        plant_combo = QComboBox()
        plant_combo.addItem("Bedkihal")
        plant_combo.addItem("Kundal")
        basic_layout.addWidget(plant_combo, 3, 3)
        self.diesel_sale_fields["plant"] = plant_combo

        # Row 4: Sale Type, Debit Account
        basic_layout.addWidget(QLabel("Sale Type"), 4, 0)
        sale_type_combo = QComboBox()
        sale_type_combo.addItem("Diesel Sale")
        sale_type_combo.addItem("Extra Diesel")
        basic_layout.addWidget(sale_type_combo, 4, 1)
        self.diesel_sale_fields["sale_type"] = sale_type_combo
        
        basic_layout.addWidget(QLabel("Debit Account"), 4, 2)
        debit_account_edit = QLineEdit()
        debit_account_edit.setText("12520005 - Advance For Diesel - VP")
        basic_layout.addWidget(debit_account_edit, 4, 3, 1, 3)
        self.diesel_sale_fields["debit_account"] = debit_account_edit

        # Row 5: Transporter, Harvester checkboxes
        basic_layout.addWidget(QLabel("Transporter"), 5, 0)
        transporter_check = QCheckBox()
        transporter_check.setChecked(True)
        basic_layout.addWidget(transporter_check, 5, 1)
        self.diesel_sale_fields["transporter"] = transporter_check
        
        basic_layout.addWidget(QLabel("Harvester"), 5, 2)
        harvester_check = QCheckBox()
        harvester_check.setChecked(False)
        basic_layout.addWidget(harvester_check, 5, 3)
        self.diesel_sale_fields["harvester"] = harvester_check

        basic_layout.addWidget(QLabel("Is Extra Diesel"), 5, 4)
        is_extra_diesel_check = QCheckBox()
        is_extra_diesel_check.setChecked(True)
        basic_layout.addWidget(is_extra_diesel_check, 5, 5)
        self.diesel_sale_fields["is_extra_diesel"] = is_extra_diesel_check

        # Row 6: Invoice Reference
        basic_layout.addWidget(QLabel("Invoice Reference"), 6, 0)
        invoice_reference_edit = QLineEdit()
        basic_layout.addWidget(invoice_reference_edit, 6, 1, 1, 3)
        self.diesel_sale_fields["invoice_reference"] = invoice_reference_edit

        # Row 7: Remarks
        basic_layout.addWidget(QLabel("Remarks"), 7, 0)
        remarks_text = QTextEdit()
        remarks_text.setMaximumHeight(60)
        basic_layout.addWidget(remarks_text, 7, 1, 1, 5)
        self.diesel_sale_fields["remarks"] = remarks_text

        # Row 8: Totals (Read-only fields)
        basic_layout.addWidget(QLabel("Total Diesel Allocated"), 8, 0)
        total_diesel_allocated_edit = QLineEdit()
        total_diesel_allocated_edit.setReadOnly(True)
        total_diesel_allocated_edit.setText("0")
        basic_layout.addWidget(total_diesel_allocated_edit, 8, 1)
        self.diesel_sale_fields["total_diesel_allocated"] = total_diesel_allocated_edit
        
        basic_layout.addWidget(QLabel("Total Distance (KM)"), 8, 2)
        total_distance_edit = QLineEdit()
        total_distance_edit.setReadOnly(True)
        total_distance_edit.setText("0")
        basic_layout.addWidget(total_distance_edit, 8, 3)
        self.diesel_sale_fields["total_distance_in_km"] = total_distance_edit

        basic_layout.addWidget(QLabel("Total Weight (Ton)"), 8, 4)
        total_weight_edit = QLineEdit()
        total_weight_edit.setReadOnly(True)
        total_weight_edit.setText("0")
        basic_layout.addWidget(total_weight_edit, 8, 5)
        self.diesel_sale_fields["total__weight_in_ton"] = total_weight_edit

        basic_group_layout.addWidget(basic_content_widget)
        basic_group.toggled.connect(basic_content_widget.setVisible)
        left_panel_layout.addWidget(basic_group)

        # Right Panel for Diesel Sale Items Table
        right_panel_widget = QWidget()
        right_panel_layout = QVBoxLayout(right_panel_widget)
        right_panel_layout.setContentsMargins(0, 0, 0, 0)
        right_panel_layout.setSpacing(10)

        # Diesel Sale Items Section
        items_group = QGroupBox("Diesel Sale Items")
        items_group.setCheckable(True)
        items_group.setChecked(True)

        items_group_layout = QVBoxLayout(items_group)
        
        # Create table for diesel sale items
        self.diesel_sale_items_table = QTableWidget()
        self.diesel_sale_items_table.setColumnCount(7)
        self.diesel_sale_items_table.setHorizontalHeaderLabels([
            "Item Code", "Item Name", "Qty", "UOM", "Rate", "Amount", "Allocation Remaining"
        ])
        
        # Set column widths
        header = self.diesel_sale_items_table.horizontalHeader()
        for i in range(7):
            if i in [0, 1, 3]:  # Item Code, Item Name, UOM
                header.setSectionResizeMode(i, QHeaderView.Stretch)
            else:  # Number columns
                header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        # Add sample row
        self.diesel_sale_items_table.setRowCount(1)
        self.add_diesel_sale_item_row()

        items_group_layout.addWidget(self.diesel_sale_items_table)

        # Add row button
        add_row_btn = QPushButton("Add Item Row")
        add_row_btn.clicked.connect(self.add_diesel_sale_item_row)
        add_row_btn.setMinimumHeight(30)
        items_group_layout.addWidget(add_row_btn)

        right_panel_layout.addWidget(items_group)

        # Add panels to splitter
        main_horizontal_splitter.addWidget(left_panel_widget)
        main_horizontal_splitter.addWidget(right_panel_widget)
        main_horizontal_splitter.setSizes([500, 500])

        form_layout.addWidget(main_horizontal_splitter)

        # Action buttons
        actions_layout = QHBoxLayout()
        
        submit_btn = QPushButton("Submit Diesel Sale")
        submit_btn.clicked.connect(self.submit_diesel_sale_form)
        submit_btn.setMinimumHeight(40)
        submit_btn.setMinimumWidth(150)
        actions_layout.addWidget(submit_btn)

        save_btn = QPushButton("Save Diesel Sale")
        save_btn.clicked.connect(self.save_diesel_sale_form)
        save_btn.setMinimumHeight(40)
        save_btn.setMinimumWidth(150)
        actions_layout.addWidget(save_btn)

        clear_btn = QPushButton("Clear Form")
        clear_btn.clicked.connect(self.clear_diesel_sale_form)
        clear_btn.setMinimumHeight(40)
        clear_btn.setMinimumWidth(150)
        actions_layout.addWidget(clear_btn)

        view_submitted_btn = QPushButton("View Submitted Diesel Sales")
        view_submitted_btn.clicked.connect(self.view_submitted_diesel_sale_records)
        view_submitted_btn.setMinimumHeight(40)
        view_submitted_btn.setMinimumWidth(200)
        actions_layout.addWidget(view_submitted_btn)

        actions_layout.addStretch()
        form_layout.addLayout(actions_layout)
        form_layout.addStretch()

        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

        return diesel_sale_tab

    def create_cane_inward_slip_tab(self):
        """Create the Cane Inward Slip tab with form fields."""
        cane_inward_slip_tab = QWidget()
        layout = QVBoxLayout(cane_inward_slip_tab)
        
        # Create scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        form_layout = QVBoxLayout(scroll_widget)

        # Create a horizontal splitter for the main layout
        main_horizontal_splitter = QSplitter(Qt.Horizontal)

        # Left Panel for Basic Information
        left_panel_widget = QWidget()
        left_panel_layout = QVBoxLayout(left_panel_widget)
        left_panel_layout.setContentsMargins(0, 0, 0, 0)
        left_panel_layout.setSpacing(10)
        
        # Basic Information Section
        basic_group = QGroupBox("Cane Inward Slip Information")
        basic_group.setCheckable(True)
        basic_group.setChecked(True)

        basic_group_layout = QVBoxLayout(basic_group)
        basic_content_widget = QWidget()
        basic_layout = QGridLayout(basic_content_widget)
        
        # Row 0: Season, Branch
        basic_layout.addWidget(QLabel("Season"), 0, 0)
        season_combo = QComboBox()
        season_combo.addItem("2024-2025")
        season_combo.addItem("2023-2024")
        season_combo.addItem("2025-2026")
        basic_layout.addWidget(season_combo, 0, 1)
        self.cane_inward_slip_fields["season"] = season_combo

        basic_layout.addWidget(QLabel("Branch (Plant)"), 0, 2)
        branch_combo = QComboBox()
        branch_combo.addItem("Bedkihal")
        branch_combo.addItem("Kundal")
        branch_combo.setCurrentText("Kundal")
        basic_layout.addWidget(branch_combo, 0, 3)
        self.cane_inward_slip_fields["branch"] = branch_combo

        # Row 1: Shift, Company
        basic_layout.addWidget(QLabel("Shift"), 1, 0)
        shift_combo = QComboBox()
        shift_combo.addItems(["1st", "2nd", "3rd"])
        basic_layout.addWidget(shift_combo, 1, 1)
        self.cane_inward_slip_fields["shift"] = shift_combo

        basic_layout.addWidget(QLabel("Company"), 1, 2)
        company_edit = QLineEdit()
        basic_layout.addWidget(company_edit, 1, 3)
        self.cane_inward_slip_fields["company"] = company_edit

        # Row 2: Posting Date, Posting Time
        basic_layout.addWidget(QLabel("Posting Date"), 2, 0)
        posting_date_edit = QDateEdit()
        posting_date_edit.setDisplayFormat("yyyy-MM-dd")
        posting_date_edit.setDate(datetime.now().date())
        basic_layout.addWidget(posting_date_edit, 2, 1)
        self.cane_inward_slip_fields["posting_date"] = posting_date_edit

        basic_layout.addWidget(QLabel("Posting Time"), 2, 2)
        posting_time_edit = QTimeEdit()
        posting_time_edit.setDisplayFormat("HH:mm:ss")
        posting_time_edit.setTime(datetime.now().time())
        basic_layout.addWidget(posting_time_edit, 2, 3)
        self.cane_inward_slip_fields["posting_time"] = posting_time_edit

        # Row 3: Token No, Factory Day
        basic_layout.addWidget(QLabel("Token No"), 3, 0)
        token_no_spin = QSpinBox()
        token_no_spin.setMaximum(999999)
        basic_layout.addWidget(token_no_spin, 3, 1)
        self.cane_inward_slip_fields["token_no"] = token_no_spin

        basic_layout.addWidget(QLabel("Factory Day"), 3, 2)
        factory_day_spin = QSpinBox()
        factory_day_spin.setMaximum(999)
        basic_layout.addWidget(factory_day_spin, 3, 3)
        self.cane_inward_slip_fields["factory_day"] = factory_day_spin

        # --- From here on the fields follow the real workflow: a tag is scanned (or,
        # with "Manually Entry for RFID" ticked, typed in) -> that resolves to a
        # Transporter Contract -> which resolves to Transporter/Transporter Name/
        # vehicle details -> "Get Slip" then pulls that transporter's pending trip
        # sheets into the table on the right. ---

        # Row 4: Manually Entry for RFID, RFID Tag
        basic_layout.addWidget(QLabel("Manually Entry for RFID"), 4, 0)
        manually_entry_check = QCheckBox()
        basic_layout.addWidget(manually_entry_check, 4, 1)
        self.cane_inward_slip_fields["manually_entry_for_rfid"] = manually_entry_check

        basic_layout.addWidget(QLabel("RFID Tag"), 4, 2)
        rfid_tag_edit = QLineEdit()
        basic_layout.addWidget(rfid_tag_edit, 4, 3)
        self.cane_inward_slip_fields["rfid_tag"] = rfid_tag_edit

        # Row 5: RFID Data (read-only - live hex from the reader socket)
        basic_layout.addWidget(QLabel("RFID Data"), 5, 0)
        rfid_data_edit = QLineEdit()
        rfid_data_edit.setReadOnly(True)
        rfid_data_edit.setStyleSheet("background-color: #f0f0f0;")
        basic_layout.addWidget(rfid_data_edit, 5, 1, 1, 3)
        self.cane_inward_slip_fields["rfid_data"] = rfid_data_edit

        # Row 6: Transporter Contract (auto-filled from the RFID tag's assignment;
        # editable only when "Manually Entry for RFID" is ticked), Transporter
        basic_layout.addWidget(QLabel("Transporter Contract"), 6, 0)
        transporter_contract_edit = QLineEdit()
        transporter_contract_edit.setReadOnly(True)
        transporter_contract_edit.setStyleSheet("background-color: #f0f0f0;")
        transporter_contract_edit.editingFinished.connect(self.fetch_transporter_data_for_cane_inward_slip)
        basic_layout.addWidget(transporter_contract_edit, 6, 1)
        self.cane_inward_slip_fields["transporter_contract"] = transporter_contract_edit

        basic_layout.addWidget(QLabel("Transporter"), 6, 2)
        transporter_edit = QLineEdit()
        transporter_edit.setReadOnly(True)
        transporter_edit.setStyleSheet("background-color: #f0f0f0;")
        basic_layout.addWidget(transporter_edit, 6, 3)
        self.cane_inward_slip_fields["transporter"] = transporter_edit

        # Row 7: Transporter Name (also derived, read-only)
        basic_layout.addWidget(QLabel("Transporter Name"), 7, 0)
        transporter_name_edit = QLineEdit()
        transporter_name_edit.setReadOnly(True)
        transporter_name_edit.setStyleSheet("background-color: #f0f0f0;")
        basic_layout.addWidget(transporter_name_edit, 7, 1, 1, 3)
        self.cane_inward_slip_fields["transporter_name"] = transporter_name_edit

        manually_entry_check.toggled.connect(self._on_cane_inward_slip_manual_rfid_toggled)

        # Row 8: Vehicle No, Transporter Vehicle Type
        basic_layout.addWidget(QLabel("Vehicle No"), 8, 0)
        vehicle_no_edit = QLineEdit()
        basic_layout.addWidget(vehicle_no_edit, 8, 1)
        self.cane_inward_slip_fields["vehicle_no"] = vehicle_no_edit

        basic_layout.addWidget(QLabel("Transporter Vehicle Type"), 8, 2)
        transporter_vehicle_type_combo = QComboBox()
        transporter_vehicle_type_combo.addItems(["TRACTOR", "TRUCK", "TROLLEY"])
        basic_layout.addWidget(transporter_vehicle_type_combo, 8, 3)
        self.cane_inward_slip_fields["transporter_vehicle_type"] = transporter_vehicle_type_combo

        # Row 9: Transporter Gang Type, No of Tripsheet
        basic_layout.addWidget(QLabel("Transporter Gang Type"), 9, 0)
        transporter_gang_type_combo = QComboBox()
        transporter_gang_type_combo.addItems(["LOCAL", "MIGRANT"])
        basic_layout.addWidget(transporter_gang_type_combo, 9, 1)
        self.cane_inward_slip_fields["transporter_gang_type"] = transporter_gang_type_combo

        basic_layout.addWidget(QLabel("No of Tripsheet"), 9, 2)
        no_of_tripsheet_spin = QSpinBox()
        no_of_tripsheet_spin.setMaximum(999)
        basic_layout.addWidget(no_of_tripsheet_spin, 9, 3)
        self.cane_inward_slip_fields["no_of_tripsheet"] = no_of_tripsheet_spin

        # Row 10: Creator
        basic_layout.addWidget(QLabel("Creator"), 10, 0)
        creator_edit = QLineEdit()
        basic_layout.addWidget(creator_edit, 10, 1, 1, 3)
        self.cane_inward_slip_fields["creator"] = creator_edit

        # Row 11: IP of Indicator, Port No of Indicator
        basic_layout.addWidget(QLabel("IP of Indicator"), 11, 0)
        ip_of_indicator_edit = QLineEdit()
        ip_of_indicator_edit.setText("192.168.10.82")
        basic_layout.addWidget(ip_of_indicator_edit, 11, 1)
        self.cane_inward_slip_fields["ip_of_indicator"] = ip_of_indicator_edit

        basic_layout.addWidget(QLabel("Port No of Indicator"), 11, 2)
        port_no_edit = QLineEdit()
        port_no_edit.setText("23")
        basic_layout.addWidget(port_no_edit, 11, 3)
        self.cane_inward_slip_fields["port_no_of_indicator"] = port_no_edit

        basic_group_layout.addWidget(basic_content_widget)
        basic_group.toggled.connect(basic_content_widget.setVisible)
        left_panel_layout.addWidget(basic_group)

        # Right Panel for Pending Slip Items Table
        right_panel_widget = QWidget()
        right_panel_layout = QVBoxLayout(right_panel_widget)
        right_panel_layout.setContentsMargins(0, 0, 0, 0)
        right_panel_layout.setSpacing(10)

        # Pending Slip Items Section
        items_group = QGroupBox("Pending Slip Items")
        items_group.setCheckable(True)
        items_group.setChecked(True)

        items_group_layout = QVBoxLayout(items_group)
        
        # Create table for pending slip items
        self.cane_inward_slip_items_table = QTableWidget()
        self.cane_inward_slip_items_table.setColumnCount(15)
        # Column order: the frequently hand-typed columns come first; season, branch,
        # posting_date, transporter, harvester, route, area_in_acrs and distance are
        # pushed to the end (they're usually carried over from the header fields /
        # trip sheet rather than typed per-row).
        self.cane_inward_slip_items_table.setHorizontalHeaderLabels([
            "Select", "Trip Sheet No", "Rope Placement", "Cane Registration", "Farmer",
            "Transporter Contract", "Harvester Contract",
            "Season", "Branch", "Posting Date", "Transporter", "Harvester",
            "Route", "Area in Acrs", "Distance"
        ])

        # Set column widths. Use fixed, user-resizable widths (not Stretch) so that with
        # 15 columns none of them get squeezed down to an unreadable/invisible sliver in
        # the split panel - the table scrolls horizontally instead.
        header = self.cane_inward_slip_items_table.horizontalHeader()
        column_widths = {
            0: 60,   # Select
            1: 110,  # Trip Sheet No
            2: 110,  # Rope Placement
            3: 130,  # Cane Registration
            4: 120,  # Farmer
            5: 140,  # Transporter Contract
            6: 130,  # Harvester Contract
            7: 90,   # Season
            8: 90,   # Branch
            9: 100,  # Posting Date
            10: 110, # Transporter
            11: 110, # Harvester
            12: 90,  # Route
            13: 90,  # Area in Acrs
            14: 80,  # Distance
        }
        for i in range(15):
            header.setSectionResizeMode(i, QHeaderView.Interactive)
            self.cane_inward_slip_items_table.setColumnWidth(i, column_widths[i])
        self.cane_inward_slip_items_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Add sample row
        self.cane_inward_slip_items_table.setRowCount(1)
        self.add_cane_inward_slip_item_row()

        items_group_layout.addWidget(self.cane_inward_slip_items_table)

        # Get Slip: pulls this transporter's pending trip sheets (Season/Branch/
        # Transporter Contract required) into the table above - same API the Auto
        # Token tab already uses (get_trip_sheet), just aimed at this table's widgets.
        get_slip_btn = QPushButton("Get Slip")
        get_slip_btn.setObjectName("syncBtn")
        get_slip_btn.clicked.connect(self.get_slip_for_cane_inward_slip)
        get_slip_btn.setMinimumHeight(30)
        items_group_layout.addWidget(get_slip_btn)

        # Add row button
        add_row_btn = QPushButton("Add Pending Slip Item Row")
        add_row_btn.clicked.connect(self.add_cane_inward_slip_item_row)
        add_row_btn.setMinimumHeight(30)
        items_group_layout.addWidget(add_row_btn)

        right_panel_layout.addWidget(items_group)

        # Add panels to splitter
        main_horizontal_splitter.addWidget(left_panel_widget)
        main_horizontal_splitter.addWidget(right_panel_widget)
        main_horizontal_splitter.setSizes([500, 500])

        form_layout.addWidget(main_horizontal_splitter)

        # Action buttons
        actions_layout = QHBoxLayout()
        
        submit_btn = QPushButton("Submit Cane Inward Slip")
        submit_btn.clicked.connect(self.submit_cane_inward_slip_form)
        submit_btn.setMinimumHeight(40)
        submit_btn.setMinimumWidth(150)
        actions_layout.addWidget(submit_btn)

        save_btn = QPushButton("Save Cane Inward Slip")
        save_btn.clicked.connect(self.save_cane_inward_slip_form)
        save_btn.setMinimumHeight(40)
        save_btn.setMinimumWidth(150)
        actions_layout.addWidget(save_btn)

        clear_btn = QPushButton("Clear Form")
        clear_btn.clicked.connect(self.clear_cane_inward_slip_form)
        clear_btn.setMinimumHeight(40)
        clear_btn.setMinimumWidth(150)
        actions_layout.addWidget(clear_btn)

        view_submitted_btn = QPushButton("View Submitted Slips")
        view_submitted_btn.clicked.connect(self.view_submitted_cane_inward_slip_records)
        view_submitted_btn.setMinimumHeight(40)
        view_submitted_btn.setMinimumWidth(200)
        actions_layout.addWidget(view_submitted_btn)

        actions_layout.addStretch()
        form_layout.addLayout(actions_layout)
        form_layout.addStretch()

        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

        return cane_inward_slip_tab

    def create_other_weight_tab(self):
        """Other Weight form, built from the "Other Weight" DocType's own JSON
        (see quantbit_agriculture_crm/doctype/other_weight/other_weight.json).
        Laid out compactly (5 label+field slots per row via
        _populate_compact_grid, no accordion, a short fixed-height items
        table) so the whole form fits on screen without scrolling."""
        other_weight_tab = QWidget()
        layout = QVBoxLayout(other_weight_tab)
        layout.setSpacing(8)

        def field(key, widget):
            self.other_weight_fields[key] = widget
            return widget

        # --- Device and Other Info / Info sections ----------------------------
        wb_combo = field("wb", QComboBox())
        wb_combo.addItems([
            "", "Weight Bridge 1", "Weight Bridge 2", "Weight Bridge 3",
            "Weight Bridge 4", "Weight Bridge 5", "Weight Bridge 6",
        ])

        # season/shift are Link fields (to Season/Factory Shift) in the
        # DocType - same shortcut the Cane Weight form uses: a plain combo
        # with the site's known values, rather than a live Link lookup.
        season_combo = field("season", QComboBox())
        season_combo.addItems(["2026-2027", "2027-2028" , "2028-2029" , "2029-2030"])
        season_combo.setCurrentText("2026-2027")

        date_edit = field("date", QDateTimeEdit())
        date_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        date_edit.setDateTime(datetime.now())

        factory_date_edit = field("factory_date", QDateEdit())
        factory_date_edit.setDisplayFormat("yyyy-MM-dd")
        factory_date_edit.setDate(datetime.now().date())

        shift_combo = field("shift", QComboBox())
        shift_combo.addItems(["1st", "2nd", "3rd"])

        # Series and Is Sync are dropped from the visible form (per request)
        # but still registered/sent, fixed at their DocType defaults, the
        # same way Cane Weight keeps its own hidden-but-still-live widgets
        # (e.g. self.slip_no_combo).
        naming_series_combo = field("naming_series", QComboBox())
        naming_series_combo.addItems(["OW-"])

        is_sync_check = field("is_sync", QCheckBox())

        weight_in_combo = field("weight_in", QComboBox())
        weight_in_combo.addItems(["", "Inward", "Outward"])

        party_name_edit = field("party_name", QLineEdit())
        vehicle_no_edit = field("vehicle_no", QLineEdit())
        customer_edit = field("customer", QLineEdit())
        driver_name_edit = field("driver_name", QLineEdit())
        supplier_edit = field("supplier", QLineEdit())

        document_no_edit = field("document_no", QLineEdit())

        # Address is a "Text" field in the DocType and Read Only there; kept
        # single-line here to stay compact.
        address_edit = field("address", QLineEdit())
        address_edit.setReadOnly(True)

        o_item_edit = field("o_item", QLineEdit())

        # --- Weight Bridge Reading section -------------------------------------
        # Gross/Tare Weight start Read Only (bridge-captured, via the Get
        # Gross/Tare Weight buttons below) - checking Manually Weight/
        # Manually Tare Weight unlocks manual typing, matching the DocType's
        # own "read_only_depends_on": "eval:doc.manually_weight==1;" rule.
        loaded_weight_edit = field("loaded_weight", QLineEdit("0"))
        loaded_weight_edit.setValidator(QDoubleValidator(0.000, 9999.999, 3))
        loaded_weight_edit.setReadOnly(True)
        loaded_weight_edit.setToolTip("Read Only unless 'Manually Weight' is checked. Otherwise, use 'Get Gross Weight' to capture it from the connected weighbridge.")

        get_gross_btn = QPushButton("Get Gross Weight")
        get_gross_btn.clicked.connect(self.get_other_weight_gross_weight)

        gross_weight_timedate_edit = field("gross_weight_timedate", QDateTimeEdit())
        gross_weight_timedate_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        gross_weight_timedate_edit.setDateTime(datetime.now())
        gross_weight_timedate_edit.setReadOnly(True)

        manually_weight_check = field("manually_weight", QCheckBox())
        manually_weight_check.toggled.connect(lambda checked: loaded_weight_edit.setReadOnly(not checked))

        # "empty_weight" is the DocType's actual field name for Tare Weight
        # (its own JSON label has a typo, "Tear Weight" - displayed correctly
        # here as "Tare Weight").
        empty_weight_edit = field("empty_weight", QLineEdit("0"))
        empty_weight_edit.setValidator(QDoubleValidator(0.000, 9999.999, 3))
        empty_weight_edit.setReadOnly(True)
        empty_weight_edit.setToolTip("Read Only unless 'Manually Tare Weight' is checked. Otherwise, use 'Get Tare Weight' to capture it from the connected weighbridge.")

        get_tare_btn = QPushButton("Get Tare Weight")
        get_tare_btn.clicked.connect(self.get_other_weight_tare_weight)

        tare_weight_timedate_edit = field("tare_weight_timedate", QDateTimeEdit())
        tare_weight_timedate_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        tare_weight_timedate_edit.setDateTime(datetime.now())

        manually_tare_weight_check = field("manually_tare_weight", QCheckBox())
        manually_tare_weight_check.toggled.connect(lambda checked: empty_weight_edit.setReadOnly(not checked))

        # Net Weight is computed (Gross - Tare), same convention as Cane
        # Weight's own net_weight - so it's Read Only here too.
        actual_weight_edit = field("actual_weight", QLineEdit("0"))
        actual_weight_edit.setReadOnly(True)

        reason_edit = field("reason", QLineEdit())

        gross_weight_user_edit = field("gross_weight_user", QLineEdit(self.primary_frappe_username or ""))
        tare_weight_user_edit = field("tare_weight_user", QLineEdit(self.primary_frappe_username or ""))

        out_date_and_time_edit = field("out_date_and_time", QDateTimeEdit())
        out_date_and_time_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        out_date_and_time_edit.setDateTime(datetime.now())
        out_date_and_time_edit.setReadOnly(True)

        # Each logical group gets its own row (chained via start_row) instead
        # of one continuous flat list, so Gross Weight's and Tare Weight's
        # fields each land together on a single row, per request.
        fields_group = QGroupBox("Other Weight")
        fields_grid = QGridLayout(fields_group)

        next_row = self._populate_compact_grid(fields_grid, [
            # Row 1 - unchanged, per request.
            ("Weight Bridge", wb_combo),
            ("Season", season_combo),
            ("Date", date_edit),
            ("Factory Date", factory_date_edit),
            ("Shift", shift_combo),
        ], slots_per_row=5)

        next_row = self._populate_compact_grid(fields_grid, [
            # Series and Is Sync removed from view (still sent, at their
            # defaults - see the field() calls above).
            ("Weight In", weight_in_combo),
            ("Party Name", party_name_edit),
            ("Vehicle No", vehicle_no_edit),
            ("Customer", customer_edit),
            ("Driver Name", driver_name_edit),
            ("Supplier", supplier_edit),
            ("Document No", document_no_edit),
            ("O Item", o_item_edit),
        ], slots_per_row=5, start_row=next_row)

        next_row = self._populate_compact_grid(fields_grid, [
            # Gross Weight group, all in one row.
            ("Gross Weight User", gross_weight_user_edit),
            ("Gross Weight", loaded_weight_edit),
            ("", get_gross_btn),
            ("Gross Weight Time/Date", gross_weight_timedate_edit),
            ("Manually Weight", manually_weight_check),
        ], slots_per_row=5, start_row=next_row)

        next_row = self._populate_compact_grid(fields_grid, [
            # Tare Weight group, all in one row.
            ("Tare Weight User", tare_weight_user_edit),
            ("Tare Weight", empty_weight_edit),
            ("", get_tare_btn),
            ("Tare Weight Time/Date", tare_weight_timedate_edit),
            ("Manually Tare Weight", manually_tare_weight_check),
        ], slots_per_row=5, start_row=next_row)

        next_row = self._populate_compact_grid(fields_grid, [
            ("Net Weight", actual_weight_edit),
            ("Out Date and Time", out_date_and_time_edit),
        ], slots_per_row=5, start_row=next_row)

        self._populate_compact_grid(fields_grid, [
            # Reason and Address land together in their own last row.
            ("Reason", reason_edit),
            ("Address", address_edit),
        ], slots_per_row=5, start_row=next_row)

        # --- Items (Other Weight Item child table) -----------------------------
        items_group = QGroupBox("Items")
        items_layout = QVBoxLayout(items_group)

        # Description last (per request) and stretched to fill the table's
        # full width, instead of leaving blank space past a fixed-width
        # last column.
        items_table = QTableWidget()
        items_table.setColumnCount(5)
        items_table.setHorizontalHeaderLabels(["Item Code", "Item Name", "Quantity", "UOM", "Description"])
        items_table.setMaximumHeight(110)
        for col, width in enumerate([150, 200, 90, 90]):
            items_table.setColumnWidth(col, width)
        items_table.horizontalHeader().setStretchLastSection(True)
        self.other_weight_fields["general_weight_item"] = items_table
        items_layout.addWidget(items_table)
        # Two starting rows, same as "Add Row" (so UOM defaults to TON here too).
        self.add_other_weight_item_row(items_table)
        self.add_other_weight_item_row(items_table)

        add_item_btn = QPushButton("Add Row")
        add_item_btn.clicked.connect(lambda: self.add_other_weight_item_row(items_table))
        items_layout.addWidget(add_item_btn)

        # --- Form actions -------------------------------------------------------
        actions_layout = QHBoxLayout()
        actions_layout.addStretch()

        submit_btn = QPushButton("Submit Form")
        submit_btn.setObjectName("submitBtn")
        submit_btn.clicked.connect(self.submit_other_weight_form)
        submit_btn.setMinimumHeight(40)
        submit_btn.setMinimumWidth(120)
        actions_layout.addWidget(submit_btn)

        save_btn = QPushButton("Save Form")
        save_btn.setObjectName("saveBtn")
        save_btn.clicked.connect(self.save_other_weight_form)
        save_btn.setMinimumHeight(40)
        save_btn.setMinimumWidth(120)
        actions_layout.addWidget(save_btn)

        clear_btn = QPushButton("Clear Form")
        clear_btn.setObjectName("clearBtn")
        clear_btn.clicked.connect(self.clear_other_weight_form)
        clear_btn.setMinimumHeight(40)
        clear_btn.setMinimumWidth(120)
        actions_layout.addWidget(clear_btn)

        view_submitted_btn = QPushButton("View Submitted Records")
        view_submitted_btn.setObjectName("viewBtn")
        view_submitted_btn.clicked.connect(self.view_submitted_other_weight_records)
        view_submitted_btn.setMinimumHeight(40)
        view_submitted_btn.setMinimumWidth(160)
        actions_layout.addWidget(view_submitted_btn)

        layout.addWidget(fields_group)
        layout.addWidget(items_group)
        layout.addLayout(actions_layout)
        layout.addStretch()

        return other_weight_tab

    def _recalculate_other_weight_net(self):
        try:
            gross = float(self.other_weight_fields["loaded_weight"].text() or 0)
            tare = float(self.other_weight_fields["empty_weight"].text() or 0)
            self.other_weight_fields["actual_weight"].setText(str(round(gross - tare, 3)))
        except (ValueError, KeyError):
            pass

    def get_other_weight_gross_weight(self):
        """Capture the live weighbridge reading into Gross Weight (loaded_weight)."""
        if not (self.connected and self.reader):
            QMessageBox.warning(self, "Warning", "Not connected to serial port!")
            return
        if self.current_weight is None:
            QMessageBox.warning(self, "Warning", "No weight data available. Please wait for weight reading.")
            return
        weight_kg = self.current_weight
        self.other_weight_fields["loaded_weight"].setText(str(float(weight_kg)))
        self.other_weight_fields["gross_weight_timedate"].setDateTime(datetime.now())
        self._recalculate_other_weight_net()
        self.output.append(f"[Other Weight] Gross Weight captured: {float(weight_kg)} at {datetime.now().strftime('%H:%M:%S')}")
        QMessageBox.information(self, "Success", f"Gross Weight: {weight_kg}")

    def get_other_weight_tare_weight(self):
        """Capture the live weighbridge reading into Tare Weight (empty_weight)."""
        if not (self.connected and self.reader):
            QMessageBox.warning(self, "Warning", "Not connected to serial port!")
            return
        if self.current_weight is None:
            QMessageBox.warning(self, "Warning", "No weight data available. Please wait for weight reading.")
            return
        weight_kg = self.current_weight
        self.other_weight_fields["empty_weight"].setText(str(float(weight_kg)))
        self.other_weight_fields["tare_weight_timedate"].setDateTime(datetime.now())
        self._recalculate_other_weight_net()
        self.output.append(f"[Other Weight] Tare Weight captured: {float(weight_kg)} at {datetime.now().strftime('%H:%M:%S')}")
        QMessageBox.information(self, "Success", f"Tare Weight: {weight_kg}")

    def add_other_weight_item_row(self, table):
        row = table.rowCount()
        table.insertRow(row)
        for col in range(table.columnCount()):
            # Columns are Item Code, Item Name, Quantity, UOM, Description -
            # UOM (column 3) defaults to "TON", matching the DocType field's
            # own default.
            table.setItem(row, col, QTableWidgetItem("TON" if col == 3 else ""))

    def _collect_other_weight_payload(self):
        """Collect the Other Weight form into a payload for
        quantbit_agriculture_crm.exe_api.save_other_weight_form /
        submit_other_weight_form. docstatus is controlled server-side by
        those methods, not sent here - same convention as Cane Weight."""
        f = self.other_weight_fields
        items = []
        table = f.get("general_weight_item")
        if table:
            for row in range(table.rowCount()):
                # Columns are Item Code, Item Name, Quantity, UOM, Description.
                item_code_item = table.item(row, 0)
                item_name_item = table.item(row, 1)
                qty_item = table.item(row, 2)
                uom_item = table.item(row, 3)
                desc_item = table.item(row, 4)
                item_code = item_code_item.text().strip() if item_code_item else ""
                qty_text = qty_item.text().strip() if qty_item else ""
                if not item_code and not qty_text:
                    continue  # skip genuinely blank rows
                try:
                    qty = float(qty_text) if qty_text else 0.0
                except ValueError:
                    qty = 0.0
                items.append({
                    "item_code": item_code,
                    "item_name": item_name_item.text().strip() if item_name_item else "",
                    "description": desc_item.text().strip() if desc_item else "",
                    "qty": qty,
                    "uom": (uom_item.text().strip() if uom_item and uom_item.text().strip() else "TON"),
                })

        return {
            "doctype": "Other Weight",
            "wb": f["wb"].currentText(),
            "season": f["season"].currentText(),
            "date": f["date"].dateTime().toString("yyyy-MM-dd HH:mm:ss"),
            "factory_date": f["factory_date"].date().toString("yyyy-MM-dd"),
            "shift": f["shift"].currentText(),
            "naming_series": f["naming_series"].currentText(),
            "weight_in": f["weight_in"].currentText(),
            "party_name": f["party_name"].text(),
            "vehicle_no": f["vehicle_no"].text(),
            "customer": f["customer"].text(),
            "driver_name": f["driver_name"].text(),
            "supplier": f["supplier"].text(),
            "is_sync": 1 if f["is_sync"].isChecked() else 0,
            "document_no": f["document_no"].text(),
            "address": f["address"].text(),
            "o_item": f["o_item"].text(),
            "loaded_weight": float(f["loaded_weight"].text() or 0),
            "manually_weight": 1 if f["manually_weight"].isChecked() else 0,
            "gross_weight_timedate": f["gross_weight_timedate"].dateTime().toString("yyyy-MM-dd HH:mm:ss"),
            "empty_weight": float(f["empty_weight"].text() or 0),
            "manually_tare_weight": 1 if f["manually_tare_weight"].isChecked() else 0,
            "tare_weight_timedate": f["tare_weight_timedate"].dateTime().toString("yyyy-MM-dd HH:mm:ss"),
            "actual_weight": float(f["actual_weight"].text() or 0),
            "reason": f["reason"].text(),
            "gross_weight_user": f["gross_weight_user"].text(),
            "tare_weight_user": f["tare_weight_user"].text(),
            "out_date_and_time": f["out_date_and_time"].dateTime().toString("yyyy-MM-dd HH:mm:ss"),
            "general_weight_item": items,
        }

    def _send_other_weight_payload(self, action_label):
        """Collect and send the Other Weight form to the dedicated
        save_other_weight_form / submit_other_weight_form whitelisted
        methods in exe_api.py (same calling convention as Cane Weight's
        _send_cane_weight_payload). If this form was previously saved or
        loaded (self.current_other_weight_doc set), its name is included so
        the backend updates that same document instead of creating a
        duplicate. Returns the saved/submitted document name, or None on
        failure (an error dialog has already been shown in that case)."""
        if not self.primary_frappe_logged_in:
            QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance. Please login first.")
            self.output.append(f"[Other Weight] {action_label} aborted: not logged in to primary instance.")
            return None

        try:
            doc_data = self._collect_other_weight_payload()
            if self.current_other_weight_doc:
                doc_data["name"] = self.current_other_weight_doc

            # doctype is managed by the backend method itself - the child
            # table (general_weight_item) and, when present, name are sent
            # as-is; doc.update(data) on the server side handles both.
            send_payload = {k: v for k, v in doc_data.items() if k != "doctype"}

            method_name = "submit_other_weight_form" if action_label == "Submit" else "save_other_weight_form"
            url = f"{self.primary_frappe_site_url}/api/method/quantbit_agriculture_crm.exe_api.{method_name}"
            headers = {"Accept": "application/json"}

            self.output.append(f"[Other Weight] {action_label} -> {url}")
            response = self.primary_frappe_session.post(url, json={"data": send_payload}, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            result_data = result.get("message") or {}

            if not result_data.get("success"):
                error_msg = result_data.get("error") or "Unknown error"
                self.output.append(f"[Other Weight] {action_label} failed: {error_msg}")
                QMessageBox.critical(self, "Failed", f"Failed to {action_label.lower()} Other Weight:\n\n{error_msg}")
                return None

            doc_name = (result_data.get("data") or {}).get("name", "Unknown")
            status_text = result_data.get("message", "Other Weight saved")
            self.output.append(f"[Other Weight] {status_text} (Name: {doc_name})")
            QMessageBox.information(self, "Success", f"{status_text}\n\nName: {doc_name}")
            return doc_name

        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            self.output.append(f"[Other Weight] {action_label} failed: {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to {action_label.lower()} Other Weight: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            self.output.append(f"[Other Weight] Network error: {error_msg}")
            QMessageBox.critical(self, "Network Error", f"Failed to {action_label.lower()}: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Other Weight] Error: {error_msg}")
            QMessageBox.critical(self, "Error", f"Error {action_label.lower()}ing Other Weight: {error_msg}")

        return None

    def submit_other_weight_form(self):
        """Submit the Other Weight form to Frappe (docstatus=1)."""
        doc_name = self._send_other_weight_payload("Submit")
        if doc_name:
            self.clear_other_weight_form()

    def save_other_weight_form(self):
        """Save the Other Weight form to Frappe as a draft (docstatus=0)."""
        doc_name = self._send_other_weight_payload("Save")
        if doc_name:
            self.current_other_weight_doc = doc_name

    def clear_other_weight_form(self):
        """Reset every Other Weight field back to its default state."""
        for field_name, widget in self.other_weight_fields.items():
            if isinstance(widget, QTableWidget):
                widget.setRowCount(0)
                self.add_other_weight_item_row(widget)
                self.add_other_weight_item_row(widget)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(False)
            elif isinstance(widget, QDateEdit):
                # QDateEdit is a QDateTimeEdit subclass, so this check must
                # come first or every QDateEdit would match that branch instead.
                widget.setDate(datetime.now().date())
            elif isinstance(widget, QDateTimeEdit):
                widget.setDateTime(datetime.now())
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(0)
            elif isinstance(widget, QLineEdit):
                widget.clear()

        self.other_weight_fields["season"].setCurrentText("2026-2027")
        self.other_weight_fields["shift"].setCurrentText("1st")
        self.other_weight_fields["naming_series"].setCurrentText("OW-")
        self.other_weight_fields["loaded_weight"].setText("0")
        self.other_weight_fields["empty_weight"].setText("0")
        self.other_weight_fields["actual_weight"].setText("0")
        self.other_weight_fields["gross_weight_user"].setText(self.primary_frappe_username or "")
        self.other_weight_fields["tare_weight_user"].setText(self.primary_frappe_username or "")
        self.current_other_weight_doc = None

    def view_submitted_other_weight_records(self):
        if not self.primary_frappe_logged_in:
            QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance. Please login first.")
            self.output.append("[Other Weight Records] View aborted: not logged in to primary instance.")
            return

        if not self.primary_frappe_site_url:
            QMessageBox.warning(self, "Warning", "Primary Frappe site URL is not configured.")
            self.output.append("[Other Weight Records] View aborted: primary site URL missing.")
            return

        try:
            fields = ["name", "season", "party_name", "vehicle_no", "weight_in", "actual_weight", "modified"]
            url = f"{self.primary_frappe_site_url}/api/method/quantbit_agriculture_crm.exe_api.get_other_weight_records"
            headers = {"Accept": "application/json"}
            self.output.append(f"[Other Weight Records] Fetching submitted records: {url}")

            response = self.primary_frappe_session.get(url, params={"limit_page_length": 50}, headers=headers, timeout=20)
            response.raise_for_status()
            result_data = response.json().get("message") or {}
            if not result_data.get("success"):
                error_msg = result_data.get("error") or "Unknown error"
                self.output.append(f"[Other Weight Records] Fetch failed: {error_msg}")
                QMessageBox.critical(self, "Error", f"Failed to fetch records: {error_msg}")
                return
            data = result_data.get("data") or []

            if not data:
                QMessageBox.information(self, "No Records", "No submitted Other Weight records were found.")
                self.output.append("[Other Weight Records] No submitted records returned.")
                return

            dialog = QDialog(self)
            dialog.setWindowTitle("Submitted Other Weight Records")
            dialog.resize(900, 400)

            dialog_layout = QVBoxLayout(dialog)
            table = QTableWidget(len(data), len(fields))
            table.setHorizontalHeaderLabels([
                "Name", "Season", "Party Name", "Vehicle No", "Weight In", "Net Weight", "Modified"
            ])
            table.setSelectionMode(QAbstractItemView.SingleSelection)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)

            header = table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.Stretch)

            for row, record in enumerate(data):
                table.setItem(row, 0, QTableWidgetItem(str(record.get("name", ""))))
                table.setItem(row, 1, QTableWidgetItem(str(record.get("season", ""))))
                table.setItem(row, 2, QTableWidgetItem(str(record.get("party_name", ""))))
                table.setItem(row, 3, QTableWidgetItem(str(record.get("vehicle_no", ""))))
                table.setItem(row, 4, QTableWidgetItem(str(record.get("weight_in", ""))))
                table.setItem(row, 5, QTableWidgetItem(str(record.get("actual_weight", ""))))
                table.setItem(row, 6, QTableWidgetItem(str(record.get("modified", ""))))

            dialog_layout.addWidget(table)

            def load_selected_record():
                selected_rows = table.selectionModel().selectedRows()
                if not selected_rows:
                    QMessageBox.warning(dialog, "Selection Required", "Please select a record to load.")
                    return
                row = selected_rows[0].row()
                doc_item = table.item(row, 0)
                if not doc_item:
                    QMessageBox.warning(dialog, "Invalid Selection", "Unable to determine the document to load.")
                    return
                doc_name = doc_item.text().strip()
                if not doc_name:
                    QMessageBox.warning(dialog, "Invalid Selection", "Selected record is missing a document name.")
                    return
                if self.load_other_weight_record(doc_name):
                    dialog.accept()

            table.itemDoubleClicked.connect(lambda _: load_selected_record())

            buttons_layout = QHBoxLayout()
            load_btn = QPushButton("Load Selected")
            load_btn.clicked.connect(load_selected_record)
            buttons_layout.addWidget(load_btn)
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.reject)
            buttons_layout.addWidget(close_btn)
            dialog_layout.addLayout(buttons_layout)

            dialog.exec()

        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            self.output.append(f"[Other Weight Records] Failed to fetch: {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to fetch records: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            self.output.append(f"[Other Weight Records] Network error: {error_msg}")
            QMessageBox.critical(self, "Network Error", f"Failed to fetch records: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Other Weight Records] Unexpected error: {error_msg}")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {error_msg}")

    def load_other_weight_record(self, doc_name: str) -> bool:
        if not self.primary_frappe_logged_in:
            QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance. Please login first.")
            return False
        if not self.primary_frappe_site_url:
            QMessageBox.warning(self, "Warning", "Primary Frappe site URL is not configured.")
            return False

        try:
            url = f"{self.primary_frappe_site_url}/api/method/quantbit_agriculture_crm.exe_api.get_other_weight_record"
            headers = {"Accept": "application/json"}
            self.output.append(f"[Other Weight Records] Loading document: {doc_name} ({url})")

            response = self.primary_frappe_session.get(url, params={"name": doc_name}, headers=headers, timeout=20)
            response.raise_for_status()
            result_data = response.json().get("message") or {}

            if not result_data.get("success"):
                error_msg = result_data.get("error") or "Unknown error"
                QMessageBox.warning(self, "Not Found", f"Unable to load Other Weight document '{doc_name}': {error_msg}")
                self.output.append(f"[Other Weight Records] Failed to load '{doc_name}': {error_msg}")
                return False

            record = result_data.get("data")
            if not record:
                QMessageBox.warning(self, "Not Found", f"Unable to load Other Weight document '{doc_name}'.")
                self.output.append(f"[Other Weight Records] Document '{doc_name}' returned empty response.")
                return False

            # populate_other_weight_form() clears the form first (which resets
            # current_other_weight_doc to None) - so it must run before, not
            # after, this is set to the loaded document's name.
            self.populate_other_weight_form(record)
            self.current_other_weight_doc = record.get("name") or doc_name
            self.output.append(f"[Other Weight Records] Loaded document '{doc_name}' into form.")
            return True

        except requests.exceptions.HTTPError as e:
            response = e.response
            status = response.status_code if response is not None else "N/A"
            text = response.text if response is not None else "No response text"
            self.output.append(f"[Other Weight Records] Failed to load '{doc_name}': HTTP {status}: {text}")
            QMessageBox.critical(self, "Error", f"Failed to load document: HTTP {status}")
        except requests.exceptions.RequestException as e:
            self.output.append(f"[Other Weight Records] Network error while loading '{doc_name}': {e}")
            QMessageBox.critical(self, "Network Error", f"Failed to load document: {e}")
        except Exception as e:
            self.output.append(f"[Other Weight Records] Unexpected error while loading '{doc_name}': {e}")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {e}")

        return False

    def populate_other_weight_form(self, doc):
        """Populate the Other Weight form from a fetched Other Weight document
        (generic-by-fieldname loop, same convention as populate_form_from_cane_weight)."""
        self.clear_other_weight_form()

        date_fields = ["factory_date"]
        datetime_fields = ["date", "gross_weight_timedate", "tare_weight_timedate", "out_date_and_time"]

        for field_name, widget in self.other_weight_fields.items():
            value = doc.get(field_name)
            if value is None:
                continue

            if field_name == "general_weight_item" and isinstance(widget, QTableWidget):
                # Columns are Item Code, Item Name, Quantity, UOM, Description.
                widget.setRowCount(0)
                if isinstance(value, list):
                    for row_idx, item in enumerate(value):
                        widget.insertRow(row_idx)
                        widget.setItem(row_idx, 0, QTableWidgetItem(str(item.get("item_code", ""))))
                        widget.setItem(row_idx, 1, QTableWidgetItem(str(item.get("item_name", ""))))
                        widget.setItem(row_idx, 2, QTableWidgetItem(str(item.get("qty", ""))))
                        widget.setItem(row_idx, 3, QTableWidgetItem(str(item.get("uom", ""))))
                        widget.setItem(row_idx, 4, QTableWidgetItem(str(item.get("description", ""))))
            elif isinstance(widget, QLineEdit):
                widget.setText(str(value))
            elif isinstance(widget, QComboBox):
                text = str(value)
                if widget.findText(text) == -1:
                    widget.addItem(text)
                widget.setCurrentText(text)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QDateEdit):
                # QDateEdit is a QDateTimeEdit subclass, so this check must
                # come first or factory_date would match the branch below
                # instead and (since it's not in datetime_fields) never populate.
                if field_name in date_fields:
                    date = QDate.fromString(str(value), "yyyy-MM-dd")
                    if date.isValid():
                        widget.setDate(date)
            elif isinstance(widget, QDateTimeEdit):
                if field_name in datetime_fields:
                    dt = QDateTime.fromString(str(value), "yyyy-MM-dd HH:mm:ss")
                    if dt.isValid():
                        widget.setDateTime(dt)

        self.output.append(f"[Other Weight] Form populated from Other Weight DocType: {doc.get('name', 'Unknown')}")

    def fetch_seasons_for_auto_token(self):
        """Fetch Season list from Trip Sheet ERP using token auth and populate auto token season combo."""
        try:
            url = f"{self.trip_sheet_api_base}/api/method/quantbit_agriculture_crm.agriculture_utils.get_seasons"
            headers = {
                "Authorization": f"token {self.trip_sheet_api_key}:{self.trip_sheet_api_secret}",
                "Accept": "application/json",
            }
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            result = response.json()
            seasons = set()
            if isinstance(result, dict):
                if "message" in result and isinstance(result["message"], list):
                    for item in result["message"]:
                        if isinstance(item, dict) and "name" in item:
                            seasons.add(item["name"])
                elif "data" in result and isinstance(result["data"], list):
                    for item in result["data"]:
                        if isinstance(item, dict) and "name" in item:
                            seasons.add(item["name"])
            combo: QComboBox = self.auto_token_fields.get("season")
            if not combo:
                return
            combo.blockSignals(True)
            combo.clear()
            if seasons:
                for season in sorted(seasons, reverse=True):
                    combo.addItem(season)
                combo.setCurrentIndex(0)
                # Manually emit the signal to trigger fetching shift/season/factory day for the default season
                combo.currentTextChanged.emit(combo.currentText())
                self.output.append(f"[Auto Token] Loaded {len(seasons)} seasons from Trip Sheet ERP.")
            else:
                combo.addItem("No seasons found")
                self.output.append("[Auto Token] No seasons returned by API.")
            combo.blockSignals(False)
        except requests.exceptions.HTTPError as e:
            self.output.append(f"[Auto Token Seasons] HTTP {e.response.status_code}: {e.response.text}")
        except requests.exceptions.RequestException as e:
            self.output.append(f"[Auto Token Seasons] Network error: {str(e)}")
        except Exception as e:
            self.output.append(f"[Auto Token Seasons] Unexpected error: {str(e)}")

    def fetch_branches_for_auto_token(self):
        """Fetch Branch list from Trip Sheet ERP using token auth and populate auto token branch combo."""
        try:
            url = f"{self.trip_sheet_api_base}/api/method/quantbit_agriculture_crm.agriculture_utils.get_branches"
            headers = {
                "Authorization": f"token {self.trip_sheet_api_key}:{self.trip_sheet_api_secret}",
                "Accept": "application/json",
            }
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            result = response.json()
            branches = []
            if isinstance(result, dict):
                if "message" in result and isinstance(result["message"], list):
                    branches = result["message"]
                elif "data" in result and isinstance(result["data"], list):
                    branches = result["data"]
            combo: QComboBox = self.auto_token_fields.get("branch")
            if not combo:
                return
            combo.blockSignals(True)
            combo.clear()
            if branches:
                for name in self._to_list(branches):
                    if isinstance(name, dict):
                        label = name.get("name") or name.get("branch") or str(name)
                    else:
                        label = str(name)
                    combo.addItem(label)
                index = combo.findText("Kundal")
                combo.setCurrentIndex(index if index >= 0 else 0)
                self.output.append(f"[Auto Token] Loaded {len(branches)} branches from Trip Sheet ERP.")
            else:
                combo.addItem("No branches found")
                self.output.append("[Auto Token] No branches returned by API.")
            combo.blockSignals(False)
        except requests.exceptions.HTTPError as e:
            self.output.append(f"[Auto Token Branches] HTTP {e.response.status_code}: {e.response.text}")
        except requests.exceptions.RequestException as e:
            self.output.append(f"[Auto Token Branches] Network error: {str(e)}")
        except Exception as e:
            self.output.append(f"[Auto Token Branches] Unexpected error: {str(e)}")

    def fetch_trip_sheets(self):
        if not self.trip_sheet_frappe_logged_in:
            self.trip_sheet_status_label.setText("Status: Not logged in")
            self.trip_sheet_status_indicator.set_status(False)
            QMessageBox.warning(self, "Warning", "Trip Sheet instance not logged in! Auto-login may have failed.")
            return
    
        try:
            self.trip_sheet_status_label.setText("Status: Fetching trip sheets...")
            fields = '["name","season","branch","posting_date","cane_registration","crop_variety","route","farmer","crop_type","distance","is_flat_rate","farmer_name","area_in_acrs","circle_office","survey_number","is_kisan_card","transporter_contract","transporter","transporter_name","vehicle_no","transporter_vehicle_type","trolly_1","trolly_2","transporter_gang_type","harvester_contract","harvester","harvester_name","harvester_vehicle_type","harvester_gang_type","rope_placement"]'
            url = f"{self.trip_sheet_frappe_site_url}/api/resource/Trip Sheet?fields={fields}&limit_page_length=200"
            response = self.trip_sheet_frappe_session.get(url)
            response.raise_for_status()
            data = response.json().get('data', [])
            self.trip_sheets_data = data
            
            # Temporarily block signals to prevent auto-triggering populate_form_from_trip_sheet
            self.slip_no_combo.blockSignals(True)
            self.slip_no_combo.clear()
            for doc in data:
                slip_no_display = doc['name']
                self.slip_no_combo.addItem(slip_no_display, doc)
            # Unblock signals
            self.slip_no_combo.blockSignals(False)
            
            # Manually trigger form population for the first item if data exists
            # if data:
            #     self.populate_form_from_trip_sheet(self.slip_no_combo.currentIndex())
            
            self.trip_sheet_status_label.setText(f"Status: {len(data)} trip sheets loaded")
            self.trip_sheet_status_indicator.set_status(True)
            self.output.append(f"[Trip Sheet] Fetched {len(data)} trip sheets")
            # QMessageBox.information(self, "Success", f"Fetched {len(data)} trip sheets")
            
        except Exception as e:
            error_msg = str(e)
            self.trip_sheet_status_label.setText("Status: Fetch failed")
            self.trip_sheet_status_indicator.set_status(False)
            self.output.append(f"[Trip Sheet Error] Failed to fetch trip sheets: {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to fetch trip sheets: {error_msg}")

    def populate_form_from_trip_sheet(self, index):
        if index < 0 or not self.trip_sheets_data:
            return
        doc = self.slip_no_combo.itemData(index)
        self.load_trip_sheet_doc_for_cane_weight(doc)

    def on_slip_no_changed(self):
        """Auto-fetch and populate trip sheet when slip number is entered"""
        slip_no = self.form_fields["slip_no"].value()
        
        # Ignore if slip_no is 0 or empty
        if slip_no == 0:
            return
        
        # Check if trip sheets are loaded
        if not self.trip_sheets_data:
            self.output.append("[Slip No Auto-Fetch] Trip sheets not loaded. Fetching now...")
            self.fetch_trip_sheets()
            if not self.trip_sheets_data:
                self.output.append("[Slip No Auto-Fetch] Failed to load trip sheets.")
                return
        
        # Try to find matching trip sheet by searching for the slip number in the name
        # Format: TS/2526/00017 where 17 is the slip number
        matching_docs = []
        for doc in self.trip_sheets_data:
            trip_sheet_name = doc.get('name', '')
            # Extract the numeric part from the end of the trip sheet name
            try:
                parts = trip_sheet_name.split('/')
                if len(parts) >= 3:
                    # Get the last part and remove leading zeros for comparison
                    last_part = parts[-1].strip()
                    numeric_part = int(last_part)
                    if numeric_part == slip_no:
                        matching_docs.append(doc)
            except (ValueError, IndexError):
                continue
        
        if matching_docs:
            # Use the first matching document
            doc = matching_docs[0]
            self.output.append(f"[Slip No Auto-Fetch] Found trip sheet: {doc.get('name')} for slip_no: {slip_no}")
            
            # Update the combo box to show the selected trip sheet
            combo_index = self.slip_no_combo.findText(str(doc.get("name", "")))
            if combo_index >= 0:
                self.slip_no_combo.blockSignals(True)
                self.slip_no_combo.setCurrentIndex(combo_index)
                self.slip_no_combo.blockSignals(False)
            else:
                self.slip_no_combo.blockSignals(True)
                self.slip_no_combo.addItem(str(doc.get("name", "")), doc)
                self.slip_no_combo.setCurrentIndex(self.slip_no_combo.count() - 1)
                self.slip_no_combo.blockSignals(False)
            
            # Load the trip sheet data
            self.load_trip_sheet_doc_for_cane_weight(doc)
        else:
            self.output.append(f"[Slip No Auto-Fetch] No trip sheet found for slip_no: {slip_no}")

    def search_trip_sheet_for_cane_weight(self):
        if not self.trip_sheets_data:
            self.fetch_trip_sheets()
            if not self.trip_sheets_data:
                self.output.append("[Trip Sheet Search] No trip sheets available for search dialog.")
                return

        dialog = QDialog(self)
        dialog.setWindowTitle("Search Trip Sheets")
        dialog.resize(820, 460)

        dialog_layout = QVBoxLayout(dialog)

        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        search_input = QLineEdit()
        search_input.setPlaceholderText("Trip Sheet, Farmer, Vehicle, Transporter...")
        search_layout.addWidget(search_input)
        dialog_layout.addLayout(search_layout)

        columns = [
            ("name", "Trip Sheet"),
            ("posting_date", "Posting Date"),
            ("farmer", "Farmer Code"),
            ("farmer_name", "Farmer Name"),
            ("vehicle_no", "Vehicle"),
            ("transporter", "Transporter"),
            ("route", "Route"),
        ]

        table = QTableWidget(0, len(columns))
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setHorizontalHeaderLabels([header for _, header in columns])

        header = table.horizontalHeader()
        for col_idx in range(len(columns)):
            if col_idx <= 1:
                header.setSectionResizeMode(col_idx, QHeaderView.ResizeToContents)
            else:
                header.setSectionResizeMode(col_idx, QHeaderView.Stretch)

        dialog_layout.addWidget(table)

        current_rows = []

        def populate_table(rows):
            nonlocal current_rows
            current_rows = rows
            table.setRowCount(len(rows))
            for row_idx, record in enumerate(rows):
                for col_idx, (field, _) in enumerate(columns):
                    table.setItem(row_idx, col_idx, QTableWidgetItem(str(record.get(field, ""))))

        def apply_filter():
            pattern = search_input.text().strip().lower()
            if not pattern:
                populate_table(self.trip_sheets_data)
                return
            filtered = []
            for record in self.trip_sheets_data:
                if any(pattern in str(record.get(field, "")).lower() for field, _ in columns):
                    filtered.append(record)
            populate_table(filtered)

        populate_table(self.trip_sheets_data)
        search_input.textChanged.connect(apply_filter)

        def load_selected_trip_sheet():
            selected_rows = table.selectionModel().selectedRows()
            if not selected_rows:
                QMessageBox.warning(dialog, "Selection Required", "Please select a trip sheet to load.")
                return
            row = selected_rows[0].row()
            if row < 0 or row >= len(current_rows):
                QMessageBox.warning(dialog, "Invalid Selection", "Could not determine the selected trip sheet.")
                return

            doc = current_rows[row]

            combo_index = self.slip_no_combo.findText(str(doc.get("name", "")))
            if combo_index >= 0:
                self.slip_no_combo.setCurrentIndex(combo_index)
            else:
                self.slip_no_combo.addItem(str(doc.get("name", "")), doc)
                self.slip_no_combo.setCurrentIndex(self.slip_no_combo.count() - 1)

            self.load_trip_sheet_doc_for_cane_weight(doc)
            dialog.accept()

        table.itemDoubleClicked.connect(lambda _: load_selected_trip_sheet())

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        load_btn = QPushButton("Load Selected")
        load_btn.clicked.connect(load_selected_trip_sheet)
        button_layout.addWidget(load_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(close_btn)
        dialog_layout.addLayout(button_layout)

        dialog.exec()

    def load_trip_sheet_doc_for_cane_weight(self, doc):
        if not doc:
            return

        # Track last trip sheet used for Cane Weight tab only
        self.current_trip_sheet_doc = dict(doc)

        slip_num_for_search = 0
        try:
            slip_name_parts = doc.get('name', '').split('/')
            # if len(slip_name_parts) > 1:
            #     clean_numeric = re.sub(r'[^\d]', '', slip_name_parts[-1].strip())
            #     if clean_numeric:
            #         slip_num_for_search = int(float(clean_numeric))
        except (ValueError, IndexError):
            slip_num_for_search = 0

        cane_weight_doc = self.fetch_cane_weight_doc(slip_name_parts) if slip_name_parts else None

        if cane_weight_doc:
            self.output.append(f"[Trip Sheet] Found existing Cane Weight DocType for slip_no: {slip_name_parts} (DocStatus: {cane_weight_doc.get('docstatus')}). Populating cane weight form for update.")
            self.current_cane_weight_doc = cane_weight_doc
            self.populate_form_from_cane_weight(slip_name_parts)
        else:
            if slip_name_parts:
                self.output.append(f"[Trip Sheet] No Cane Weight DocType for slip_no: {slip_name_parts}. Populating cane weight form from selected trip sheet.")
            else:
                self.output.append("[Trip Sheet] Unable to derive slip number; populating cane weight form from selected trip sheet data.")
            self.current_cane_weight_doc = None
            self.populate_form_from_trip_sheet_data(doc)

    def fetch_cane_weight_doc(self, slip_no):
        if not self.primary_frappe_logged_in:
            self.output.append("[Cane Weight Fetch] Not logged in to Primary Frappe instance. Skipping fetch.")
            return None
        
        if not self.primary_frappe_site_url:
            self.output.append("[Cane Weight Fetch] Primary Frappe site URL not configured. Skipping fetch.")
            return None

        try:
            # Search for Cane Weight document by slip_no
            filters = [["trip_sheet", "=", str(slip_no)]]
            fields = '["*"]' # Fetch all fields
            url = f"{self.primary_frappe_site_url}/api/resource/Cane Weight?filters={json.dumps(filters)}&fields={fields}&limit_page_length=1"
            
            self.output.append(f"[Cane Weight Fetch Debug] Querying for slip_no: {slip_no}")
            self.output.append(f"[Cane Weight Fetch Debug] Constructed URL: {url}")
            self.output.append(f"[Cane Weight Fetch Debug] Filters used: {json.dumps(filters)}")
            
            response = self.primary_frappe_session.get(url)
            response.raise_for_status()
            response_json = response.json()
            data = response_json.get('data', [])
            
            self.output.append(f"[Cane Weight Fetch Debug] Raw API Response: {json.dumps(response_json, indent=2)}")

            if data:
                self.output.append(f"[Cane Weight Fetch] Found existing Cane Weight document for slip_no {slip_no}.")
                return data[0] # Return the first matching document
            else:
                warning_msg = f"No existing Cane Weight document found for slip_no {slip_no}.\n\nDebug Info:\nURL: {url}\nFilters: {json.dumps(filters)}\nResponse: {json.dumps(response_json, indent=2)}"
                self.output.append(f"[Cane Weight Fetch] {warning_msg}")
                QMessageBox.information(self, "Cane Weight Fetch Info", warning_msg)
                return None
        except requests.exceptions.RequestException as e:
            error_msg = f"[Cane Weight Fetch Error] Failed to fetch Cane Weight document: {e}"
            self.output.append(error_msg)
            QMessageBox.critical(self, "Cane Weight Fetch Error", error_msg)
            return None

    def load_cane_weight_record(self, doc_name: str) -> bool:
        if not self.primary_frappe_logged_in:
            QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance. Please login first.")
            self.output.append("[Cane Weight Records] Load aborted: not logged in to primary instance.")
            return False

        if not self.primary_frappe_site_url:
            QMessageBox.warning(self, "Warning", "Primary Frappe site URL is not configured.")
            self.output.append("[Cane Weight Records] Load aborted: primary site URL missing.")
            return False

        try:
            encoded_name = quote(doc_name)
            url = f"{self.primary_frappe_site_url}/api/resource/Cane Weight/{encoded_name}"
            headers = {"Accept": "application/json"}
            self.output.append(f"[Cane Weight Records] Loading document: {doc_name} ({url})")

            response = self.primary_frappe_session.get(url, headers=headers, timeout=20)
            response.raise_for_status()
            payload = response.json()
            record = payload.get("data") if isinstance(payload, dict) else None

            if not record:
                QMessageBox.warning(self, "Not Found", f"Unable to load Cane Weight document '{doc_name}'.")
                self.output.append(f"[Cane Weight Records] Document '{doc_name}' returned empty response.")
                return False

            self.current_cane_weight_doc = record
            self.populate_form_from_cane_weight(record)
            self.output.append(f"[Cane Weight Records] Loaded document '{doc_name}' into form.")
            return True

        except requests.exceptions.HTTPError as e:
            response = e.response
            status = response.status_code if response is not None else "N/A"
            text = response.text if response is not None else "No response text"
            error_msg = f"HTTP {status}: {text}"
            self.output.append(f"[Cane Weight Records] Failed to load document '{doc_name}': {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to load document: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            self.output.append(f"[Cane Weight Records] Network error while loading '{doc_name}': {error_msg}")
            QMessageBox.critical(self, "Network Error", f"Failed to load document: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Cane Weight Records] Unexpected error while loading '{doc_name}': {error_msg}")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {error_msg}")

        return False

    def view_submitted_fuel_sale_records(self):
        if not self.primary_frappe_logged_in:
            QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance. Please login first.")
            self.output.append("[Fuel Sale Records] View aborted: not logged in to primary instance.")
            return

        if not self.primary_frappe_site_url:
            QMessageBox.warning(self, "Warning", "Primary Frappe site URL is not configured.")
            self.output.append("[Fuel Sale Records] View aborted: primary site URL missing.")
            return

        try:
            filters = [["docstatus", "=", 1]]
            fields = [
                "name", "season", "branch", "posting_date", "fuel_sale_type",
                "party", "total_quantity", "total_amount", "modified"
            ]
            resource = quote("Fuel Sale")
            params = {
                "filters": json.dumps(filters),
                "fields": json.dumps(fields),
                "limit_page_length": 50,
                "order_by": "modified desc",
            }

            url = f"{self.primary_frappe_site_url}/api/resource/{resource}"
            headers = {"Accept": "application/json"}
            self.output.append(f"[Fuel Sale Records] Fetching submitted records: {url} | params={params}")

            data = []
            try:
                response = self.primary_frappe_session.get(url, params=params, headers=headers, timeout=20)
                response.raise_for_status()
                data = response.json().get("data", [])
            except requests.exceptions.HTTPError as primary_error:
                primary_response = primary_error.response
                status = primary_response.status_code if primary_response is not None else "N/A"
                text = primary_response.text if primary_response is not None else "No response text"
                self.output.append(
                    f"[Fuel Sale Records] Primary fetch failed with HTTP {status}: {text}"
                )

                fallback_payload = {
                    "doctype": "Fuel Sale",
                    "filters": filters,
                    "fields": fields,
                    "order_by": "modified desc",
                    "limit_page_length": 50,
                }
                fallback_url = f"{self.primary_frappe_site_url}/api/method/frappe.client.get_list"
                fallback_headers = {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                }
                self.output.append(
                    f"[Fuel Sale Records] Falling back to frappe.client.get_list via {fallback_url}"
                )
                fallback_response = self.primary_frappe_session.post(
                    fallback_url,
                    json=fallback_payload,
                    headers=fallback_headers,
                    timeout=20,
                )
                fallback_response.raise_for_status()
                fallback_json = fallback_response.json()
                data = fallback_json.get("message") or fallback_json.get("data") or []

            if not data:
                QMessageBox.information(self, "No Records", "No submitted Fuel Sale records were found.")
                self.output.append("[Fuel Sale Records] No submitted records returned.")
                return

            dialog = QDialog(self)
            dialog.setWindowTitle("Submitted Fuel Sale Records")
            dialog.resize(900, 400)

            dialog_layout = QVBoxLayout(dialog)
            table = QTableWidget(len(data), len(fields))
            table.setHorizontalHeaderLabels([
                "Name", "Season", "Branch", "Posting Date", "Type",
                "Party", "Total Qty", "Total Amount", "Modified"
            ])
            table.setSelectionMode(QAbstractItemView.SingleSelection)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)

            header = table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.Stretch)

            for row, record in enumerate(data):
                table.setItem(row, 0, QTableWidgetItem(str(record.get("name", ""))))
                table.setItem(row, 1, QTableWidgetItem(str(record.get("season", ""))))
                table.setItem(row, 2, QTableWidgetItem(str(record.get("branch", ""))))
                table.setItem(row, 3, QTableWidgetItem(str(record.get("posting_date", ""))))
                table.setItem(row, 4, QTableWidgetItem(str(record.get("fuel_sale_type", ""))))
                table.setItem(row, 5, QTableWidgetItem(str(record.get("party", ""))))
                table.setItem(row, 6, QTableWidgetItem(str(record.get("total_quantity", ""))))
                table.setItem(row, 7, QTableWidgetItem(str(record.get("total_amount", ""))))
                table.setItem(row, 8, QTableWidgetItem(str(record.get("modified", ""))))

            dialog_layout.addWidget(table)

            def load_selected_record():
                selected_rows = table.selectionModel().selectedRows()
                if not selected_rows:
                    QMessageBox.warning(dialog, "Selection Required", "Please select a record to load.")
                    return
                row = selected_rows[0].row()
                doc_item = table.item(row, 0)
                if not doc_item:
                    QMessageBox.warning(dialog, "Invalid Selection", "Unable to determine the document to load.")
                    return
                doc_name = doc_item.text().strip()
                if not doc_name:
                    QMessageBox.warning(dialog, "Invalid Selection", "Selected record is missing a document name.")
                    return

                if self.load_fuel_sale_record(doc_name):
                    dialog.accept()

            table.itemDoubleClicked.connect(lambda _: load_selected_record())

            button_layout = QHBoxLayout()
            load_btn = QPushButton("Load Selected")
            load_btn.clicked.connect(load_selected_record)
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.reject)
            button_layout.addStretch()
            button_layout.addWidget(load_btn)
            button_layout.addWidget(close_btn)
            dialog_layout.addLayout(button_layout)

            dialog.exec()

        except requests.exceptions.HTTPError as e:
            response = e.response
            response_text = response.text if response is not None else "No response text"
            error_msg = f"HTTP {response.status_code if response is not None else 'N/A'}: {response_text}"
            self.output.append(f"[Fuel Sale Records] Fetch failed: {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to fetch records: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            self.output.append(f"[Fuel Sale Records] Network error: {error_msg}")
            QMessageBox.critical(self, "Network Error", f"Failed to fetch records: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Fuel Sale Records] Unexpected error: {error_msg}")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {error_msg}")

    def load_fuel_sale_record(self, doc_name: str) -> bool:
        if not self.primary_frappe_logged_in:
            QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance. Please login first.")
            self.output.append("[Fuel Sale Records] Load aborted: not logged in to primary instance.")
            return False

        if not self.primary_frappe_site_url:
            QMessageBox.warning(self, "Warning", "Primary Frappe site URL is not configured.")
            self.output.append("[Fuel Sale Records] Load aborted: primary site URL missing.")
            return False

        try:
            encoded_name = quote(doc_name)
            url = f"{self.primary_frappe_site_url}/api/resource/Fuel Sale/{encoded_name}"
            headers = {"Accept": "application/json"}
            self.output.append(f"[Fuel Sale Records] Loading document: {doc_name} ({url})")

            response = self.primary_frappe_session.get(url, headers=headers, timeout=20)
            response.raise_for_status()
            payload = response.json()
            record = payload.get("data") if isinstance(payload, dict) else None

            if not record:
                QMessageBox.warning(self, "Not Found", f"Unable to load Fuel Sale document '{doc_name}'.")
                self.output.append(f"[Fuel Sale Records] Document '{doc_name}' returned empty response.")
                return False

            self.current_fuel_sale_doc = record
            self.populate_fuel_sale_form(record)
            self.output.append(f"[Fuel Sale Records] Loaded document '{doc_name}' into form.")
            return True

        except requests.exceptions.HTTPError as e:
            response = e.response
            status = response.status_code if response is not None else "N/A"
            text = response.text if response is not None else "No response text"
            error_msg = f"HTTP {status}: {text}"
            self.output.append(f"[Fuel Sale Records] Failed to load document '{doc_name}': {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to load document: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            self.output.append(f"[Fuel Sale Records] Network error while loading '{doc_name}': {error_msg}")
            QMessageBox.critical(self, "Network Error", f"Failed to load document: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Fuel Sale Records] Unexpected error while loading '{doc_name}': {error_msg}")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {error_msg}")

        return False

    def populate_fuel_sale_form(self, doc):
        field_map = {
            "season": QComboBox,
            "branch": QComboBox,
            "shift_type": QComboBox,
            "fuel_sale_type": QComboBox,
            "contract": QComboBox,
            "entity_type": QComboBox,
            "debit_account": QComboBox,
            "currency": QComboBox,
        }

        for key in ["season", "branch", "shift_type", "fuel_sale_type", "contract", "entity_type", "debit_account", "currency"]:
            value = doc.get(key)
            widget = self.fuel_sale_fields.get(key)
            if value is None or not isinstance(widget, field_map.get(key, object)):
                continue
            idx = widget.findText(str(value))
            if idx < 0 and str(value):
                widget.addItem(str(value))
                idx = widget.findText(str(value))
            if idx >= 0:
                widget.setCurrentIndex(idx)

        posting_date_widget: QDateEdit = self.fuel_sale_fields.get("posting_date")
        if posting_date_widget and doc.get("posting_date"):
            date = QDate.fromString(str(doc.get("posting_date")), "yyyy-MM-dd")
            if date.isValid():
                posting_date_widget.setDate(date)

        posting_time_widget: QTimeEdit = self.fuel_sale_fields.get("posting_time")
        if posting_time_widget and doc.get("posting_time"):
            time_obj = QTime.fromString(str(doc.get("posting_time")), "HH:mm:ss")
            if time_obj.isValid():
                posting_time_widget.setTime(time_obj)

        line_edit_fields = [
            ("party", QLineEdit),
            ("party_name", QLineEdit),
            ("total_amount_in_words", QLineEdit),
        ]

        for key, widget_type in line_edit_fields:
            widget = self.fuel_sale_fields.get(key)
            if isinstance(widget, widget_type) and doc.get(key) is not None:
                widget.setText(str(doc.get(key)))

        check_fields = [
            "is_extra_fuel",
            "is_returned",
            "edit_posting_date_and_time",
        ]
        for key in check_fields:
            widget = self.fuel_sale_fields.get(key)
            if isinstance(widget, QCheckBox) and doc.get(key) is not None:
                widget.setChecked(bool(doc.get(key)))

        double_fields = ["total_quantity", "total_amount"]
        for key in double_fields:
            widget = self.fuel_sale_fields.get(key)
            if isinstance(widget, QDoubleSpinBox) and doc.get(key) is not None:
                try:
                    widget.setValue(float(doc.get(key)))
                except (TypeError, ValueError):
                    pass

        # Populate items table
        items = doc.get("fuel_sale_item", [])
        self.fuel_sale_items_table.setRowCount(0)
        for row_idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            self.fuel_sale_items_table.insertRow(row_idx)
            self.fuel_sale_items_table.setItem(row_idx, 0, QTableWidgetItem(str(item.get("item_code", ""))))
            self.fuel_sale_items_table.setItem(row_idx, 1, QTableWidgetItem(str(item.get("item_name", ""))))
            self.fuel_sale_items_table.setItem(row_idx, 2, QTableWidgetItem(str(item.get("quantity", ""))))
            self.fuel_sale_items_table.setItem(row_idx, 3, QTableWidgetItem(str(item.get("amount", ""))))
            self.fuel_sale_items_table.setItem(row_idx, 4, QTableWidgetItem(str(item.get("warehouse", ""))))
            self.fuel_sale_items_table.setItem(row_idx, 5, QTableWidgetItem(str(item.get("allocated_quantity", ""))))
            self.fuel_sale_items_table.setItem(row_idx, 6, QTableWidgetItem(str(item.get("uom", ""))))
            self.fuel_sale_items_table.setItem(row_idx, 7, QTableWidgetItem(str(item.get("rate", ""))))
            self.fuel_sale_items_table.setItem(row_idx, 8, QTableWidgetItem(str(item.get("expense_account", ""))))
            self.fuel_sale_items_table.setItem(row_idx, 9, QTableWidgetItem(str(item.get("income_account", ""))))

        if not items:
            self.add_fuel_sale_item_row()

        self.output.append(f"[Fuel Sale] Form populated from Fuel Sale DocType: {doc.get('name', 'Unknown')}")
        QMessageBox.information(self, "Form Populated", "Fuel Sale form populated successfully!")

    def view_submitted_auto_token_records(self):
        if not self.primary_frappe_logged_in:
            QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance. Please login first.")
            self.output.append("[Auto Token Records] View aborted: not logged in to primary instance.")
            return

        if not self.primary_frappe_site_url:
            QMessageBox.warning(self, "Warning", "Primary Frappe site URL is not configured.")
            self.output.append("[Auto Token Records] View aborted: primary site URL missing.")
            return

        try:
            filters = [["docstatus", "=", 1]]
            fields = [
                "name", "season", "branch", "posting_date", "token_no",
                "transporter", "vehicle_no", "no_of_tripsheet", "modified"
            ]
            resource = quote("Auto Token")
            params = {
                "filters": json.dumps(filters),
                "fields": json.dumps(fields),
                "limit_page_length": 50,
                "order_by": "modified desc",
            }

            url = f"{self.primary_frappe_site_url}/api/resource/{resource}"
            headers = {"Accept": "application/json"}
            self.output.append(f"[Auto Token Records] Fetching submitted records: {url} | params={params}")

            data = []
            try:
                response = self.primary_frappe_session.get(url, params=params, headers=headers, timeout=20)
                response.raise_for_status()
                data = response.json().get("data", [])
            except requests.exceptions.HTTPError as primary_error:
                primary_response = primary_error.response
                status = primary_response.status_code if primary_response is not None else "N/A"
                text = primary_response.text if primary_response is not None else "No response text"
                self.output.append(
                    f"[Auto Token Records] Primary fetch failed with HTTP {status}: {text}"
                )

                fallback_payload = {
                    "doctype": "Auto Token",
                    "filters": filters,
                    "fields": fields,
                    "order_by": "modified desc",
                    "limit_page_length": 50,
                }
                fallback_url = f"{self.primary_frappe_site_url}/api/method/frappe.client.get_list"
                fallback_headers = {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                }
                self.output.append(
                    f"[Auto Token Records] Falling back to frappe.client.get_list via {fallback_url}"
                )
                fallback_response = self.primary_frappe_session.post(
                    fallback_url,
                    json=fallback_payload,
                    headers=fallback_headers,
                    timeout=20,
                )
                fallback_response.raise_for_status()
                fallback_json = fallback_response.json()
                data = fallback_json.get("message") or fallback_json.get("data") or []

            if not data:
                # QMessageBox.information(self, "No Records", "No submitted Auto Token records were found.")
                self.output.append("[Auto Token Records] No submitted records returned.")
                return

            dialog = QDialog(self)
            dialog.setWindowTitle("Submitted Auto Token Records")
            dialog.resize(900, 400)

            dialog_layout = QVBoxLayout(dialog)
            table = QTableWidget(len(data), len(fields))
            table.setHorizontalHeaderLabels([
                "Name", "Season", "Branch", "Posting Date", "Token No",
                "Transporter", "Vehicle No", "Trip Sheets", "Modified"
            ])
            table.setSelectionMode(QAbstractItemView.SingleSelection)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)

            header = table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.Stretch)

            for row, record in enumerate(data):
                table.setItem(row, 0, QTableWidgetItem(str(record.get("name", ""))))
                table.setItem(row, 1, QTableWidgetItem(str(record.get("season", ""))))
                table.setItem(row, 2, QTableWidgetItem(str(record.get("branch", ""))))
                table.setItem(row, 3, QTableWidgetItem(str(record.get("posting_date", ""))))
                table.setItem(row, 4, QTableWidgetItem(str(record.get("token_no", ""))))
                table.setItem(row, 5, QTableWidgetItem(str(record.get("transporter", ""))))
                table.setItem(row, 6, QTableWidgetItem(str(record.get("vehicle_no", ""))))
                table.setItem(row, 7, QTableWidgetItem(str(record.get("no_of_tripsheet", ""))))
                table.setItem(row, 8, QTableWidgetItem(str(record.get("modified", ""))))

            dialog_layout.addWidget(table)

            def load_selected_record():
                selected_rows = table.selectionModel().selectedRows()
                if not selected_rows:
                    QMessageBox.warning(dialog, "Selection Required", "Please select a record to load.")
                    return
                row = selected_rows[0].row()
                doc_item = table.item(row, 0)
                if not doc_item:
                    QMessageBox.warning(dialog, "Invalid Selection", "Unable to determine the document to load.")
                    return
                doc_name = doc_item.text().strip()
                if not doc_name:
                    QMessageBox.warning(dialog, "Invalid Selection", "Selected record is missing a document name.")
                    return

                if self.load_auto_token_record(doc_name):
                    dialog.accept()

            table.itemDoubleClicked.connect(lambda _: load_selected_record())

            button_layout = QHBoxLayout()
            load_btn = QPushButton("Load Selected")
            load_btn.clicked.connect(load_selected_record)
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.reject)
            button_layout.addStretch()
            button_layout.addWidget(load_btn)
            button_layout.addWidget(close_btn)
            dialog_layout.addLayout(button_layout)

            dialog.exec()

        except requests.exceptions.HTTPError as e:
            response = e.response
            response_text = response.text if response is not None else "No response text"
            error_msg = f"HTTP {response.status_code if response is not None else 'N/A'}: {response_text}"
            self.output.append(f"[Auto Token Records] Fetch failed: {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to fetch records: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            self.output.append(f"[Auto Token Records] Network error: {error_msg}")
            QMessageBox.critical(self, "Network Error", f"Failed to fetch records: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Auto Token Records] Unexpected error: {error_msg}")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {error_msg}")

    def load_auto_token_record(self, doc_name: str) -> bool:
        if not self.primary_frappe_logged_in:
            QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance. Please login first.")
            self.output.append("[Auto Token Records] Load aborted: not logged in to primary instance.")
            return False

        if not self.primary_frappe_site_url:
            QMessageBox.warning(self, "Warning", "Primary Frappe site URL is not configured.")
            self.output.append("[Auto Token Records] Load aborted: primary site URL missing.")
            return False

        try:
            encoded_name = quote(doc_name)
            url = f"{self.primary_frappe_site_url}/api/resource/Auto Token/{encoded_name}"
            headers = {"Accept": "application/json"}
            self.output.append(f"[Auto Token Records] Loading document: {doc_name} ({url})")

            response = self.primary_frappe_session.get(url, headers=headers, timeout=20)
            response.raise_for_status()
            payload = response.json()
            record = payload.get("data") if isinstance(payload, dict) else None

            if not record:
                QMessageBox.warning(self, "Not Found", f"Unable to load Auto Token document '{doc_name}'.")
                self.output.append(f"[Auto Token Records] Document '{doc_name}' returned empty response.")
                return False

            self.current_auto_token_doc = record
            self.populate_auto_token_form(record)
            self.output.append(f"[Auto Token Records] Loaded document '{doc_name}' into form.")
            return True

        except requests.exceptions.HTTPError as e:
            response = e.response
            status = response.status_code if response is not None else "N/A"
            text = response.text if response is not None else "No response text"
            error_msg = f"HTTP {status}: {text}"
            self.output.append(f"[Auto Token Records] Failed to load document '{doc_name}': {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to load document: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            self.output.append(f"[Auto Token Records] Network error while loading '{doc_name}': {error_msg}")
            QMessageBox.critical(self, "Network Error", f"Failed to load document: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Auto Token Records] Unexpected error while loading '{doc_name}': {error_msg}")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {error_msg}")

        return False

    def populate_auto_token_form(self, doc):
        combo_fields = [
            "season",
            "branch",
            "shift",
            "transporter_contract",
            "transporter_vehicle_type",
        ]

        for key in combo_fields:
            widget = self.auto_token_fields.get(key)
            value = doc.get(key)
            if isinstance(widget, QComboBox) and value is not None:
                idx = widget.findText(str(value))
                if idx < 0 and str(value):
                    widget.addItem(str(value))
                    idx = widget.findText(str(value))
                if idx >= 0:
                    widget.setCurrentIndex(idx)

        posting_date_widget: QDateEdit = self.auto_token_fields.get("posting_date")
        if posting_date_widget and doc.get("posting_date"):
            date = QDate.fromString(str(doc.get("posting_date")), "yyyy-MM-dd")
            if date.isValid():
                posting_date_widget.setDate(date)

        posting_time_widget: QTimeEdit = self.auto_token_fields.get("posting_time")
        if posting_time_widget and doc.get("posting_time"):
            time_obj = QTime.fromString(str(doc.get("posting_time")), "HH:mm:ss")
            if time_obj.isValid():
                posting_time_widget.setTime(time_obj)

        check_fields = ["edit"]
        for key in check_fields:
            widget = self.auto_token_fields.get(key)
            if isinstance(widget, QCheckBox) and doc.get(key) is not None:
                widget.setChecked(bool(doc.get(key)))

        spin_fields_int = [
            "season_day",
            "factory_day",
            "no_of_tripsheet",
        ]
        for key in spin_fields_int:
            widget = self.auto_token_fields.get(key)
            if isinstance(widget, QSpinBox) and doc.get(key) is not None:
                try:
                    widget.setValue(int(doc.get(key)))
                except (TypeError, ValueError):
                    pass

        line_fields = [
            ("token_no", QLineEdit),
            ("transporter", QLineEdit),
            ("transporter_name", QLineEdit),
            ("vehicle_no", QLineEdit),
            ("transporter_gang_type", QLineEdit),
        ]
        for key, widget_type in line_fields:
            widget = self.auto_token_fields.get(key)
            if isinstance(widget, widget_type) and doc.get(key) is not None:
                widget.setText(str(doc.get(key)))

        table_data = doc.get("auto_token_trip_sheet_table", [])
        self.auto_token_trip_sheet_table.setRowCount(0)
        for row_idx, row_data in enumerate(table_data):
            if not isinstance(row_data, dict):
                continue
            self.auto_token_trip_sheet_table.insertRow(row_idx)

            select_checkbox = QCheckBox()
            select_checkbox.setChecked(bool(row_data.get("select", 0)))
            select_checkbox.stateChanged.connect(self.update_no_of_tripsheet_count)
            self.auto_token_trip_sheet_table.setCellWidget(row_idx, 0, select_checkbox)

            column_keys = [
                "season",
                "branch",
                "posting_date",
                "trip_sheet_no",
                "rope_placement",
                "cane_registration",
                "route",
                "area_in_acrs",
                "farmer",
                "distance",
                "transporter_contract",
                "transporter",
                "harvester_contract",
                "harvester",
            ]

            for col_offset, key in enumerate(column_keys, start=1):
                value = row_data.get(key, "")
                self.auto_token_trip_sheet_table.setItem(row_idx, col_offset, QTableWidgetItem(str(value)))

        if not table_data:
            self.add_auto_token_trip_sheet_row()

        self.update_no_of_tripsheet_count()

        self.output.append(f"[Auto Token] Form populated from Auto Token DocType: {doc.get('name', 'Unknown')}")
        QMessageBox.information(self, "Form Populated", "Auto Token form populated successfully!")

    def populate_form_from_cane_weight(self, doc):
        # This function will map fields from the Cane Weight DocType to your form fields
        # You'll need to ensure the field names match or map them explicitly
        self.clear_form() # Clear existing form data before populating

        # Define numeric, checkbox, date, datetime, and time fields for proper handling
        numeric_fields = [
            "crop_day", "slip_no", "distancekm", "total_diesel_allocated","cane_weight_no"
            "water_share_", "cane_deduction", "gross_weight_bridge", 
            "tare_weight_bridge", "wb_value", "wb_second_value", 
            "gross_weight", "tare_weight", "cane_weight", "binding_weightton", 
            "cane_deductionton", "harvester_weight", "farmer_actual_weight", 
            "net_weightton", "binding_weightkg", "transporter_weight", 
            "water_supplier_weight", "area_acre", "percentage", 
            "daily_cane_purchase", "tolly_1", "tolly_2"
        ]
        checkbox_fields = [
            "manually__gross_weight", "is_kisan_card", "h_and_t_billing_status", 
            "weight_partner_status", "show_all_plot_fields", "manually_tear_weight"
        ]
        date_fields = [
            "date", "plantation_date", "cane_inward_slip_date", "entry_date"
        ]
        datetime_fields = [
            "gross_weight_timedate", "tare_weight_timedate"
        ]
        time_fields = [
            "time", "cane_inward_slip_time", "entry_time"
        ]

        for field_name, widget in self.form_fields.items():
            value = doc.get(field_name)
            if value is None:
                continue

            if isinstance(widget, QLineEdit):
                if field_name in numeric_fields:
                    widget.setText(str(value))
                else:
                    widget.setText(str(value))
            elif isinstance(widget, QComboBox):
                widget.setCurrentText(str(value))
            elif isinstance(widget, QSpinBox):
                if field_name in numeric_fields:
                    try:
                        widget.setValue(int(value))
                    except ValueError:
                        widget.setValue(0)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value)) # Assuming Frappe sends 0 or 1 for checkboxes
            elif isinstance(widget, QDateEdit):
                if field_name in date_fields:
                    date = QDate.fromString(str(value), "yyyy-MM-dd")
                    if date.isValid():
                        widget.setDate(date)
            elif isinstance(widget, QDateTimeEdit):
                if field_name in datetime_fields:
                    datetime_obj = QDateTime.fromString(str(value), "yyyy-MM-dd HH:mm:ss")
                    if datetime_obj.isValid():
                        widget.setDateTime(datetime_obj)
            # Handle QTableWidget for penalty charges
            elif field_name == "penalty_charges" and isinstance(widget, QTableWidget):
                widget.setRowCount(0) # Clear existing rows
                if isinstance(value, list):
                    for row_idx, penalty_item in enumerate(value):
                        self.add_penalty_row(widget)
                        widget.setItem(row_idx, 0, QTableWidgetItem(str(penalty_item.get('idx', row_idx + 1))))
                        widget.setItem(row_idx, 1, QTableWidgetItem(str(penalty_item.get('vendor_name', ''))))
                        widget.setItem(row_idx, 2, QTableWidgetItem(str(penalty_item.get('penalty_type', ''))))
                        widget.setItem(row_idx, 3, QTableWidgetItem(str(penalty_item.get('deduction_type', ''))))
                        widget.setItem(row_idx, 4, QTableWidgetItem(str(penalty_item.get('deduction_method', ''))))
                        widget.setItem(row_idx, 5, QTableWidgetItem(str(penalty_item.get('deduction_amount', 0.0))))
        
        # Manually update specific fields not covered by the generic loop or requiring special handling
        if 'slip_no' in doc and 'slip_no' in self.form_fields:
            try:
                self.form_fields['slip_no'].setValue(int(float(doc['slip_no'])))
            except ValueError:
                self.form_fields['slip_no'].setValue(0) # Default to 0 if conversion fails

        self.output.append(f"[Cane Weight] Form populated from Cane Weight DocType: {doc.get('name', 'Unknown')}")
        
        # Auto-populate penalty charges after loading the form
        self.output.append("[Cane Weight] Auto-populating penalty charges...")
        self.auto_populate_penalty_charges(show_success_message=False)

    def add_penalty_row(self, table):
        """Add a new row to the penalty charges table"""
        current_rows = table.rowCount()
        table.setRowCount(current_rows + 1)

        # Add default items to new row
        table.setItem(current_rows, 0, QTableWidgetItem(str(current_rows + 1)))
        for col in (1, 2, 3):
            table.setItem(current_rows, col, self._make_penalty_readonly_item())
        table.setCellWidget(current_rows, 5, self._make_penalty_deduction_method_combo())
        for col in (4, 6, 7, 8):
            table.setItem(current_rows, col, QTableWidgetItem(""))
    
    def auto_populate_penalty_charges(self, show_success_message=True):
        """Auto-populate penalty charges table with farmer, transporter, and harvester details
        
        Args:
            show_success_message (bool): Whether to show success message box. Default True.
        """
        if not self.primary_frappe_logged_in:
            if show_success_message:
                QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance. Please login first.")
            return
        
        try:
            # Get debit and credit accounts from Frappe
            self.output.append("[Penalty Charges] Fetching deduction type accounts...")
            # Endpoint of the whitelisted method
            url = f"{self.trip_sheet_api_base}/api/method/quantbit_agriculture_crm.agriculture_utils.append_details"

            headers = {
                "Authorization": f"token {self.trip_sheet_api_key}:{self.trip_sheet_api_secret}",
                "Accept": "application/json",
            }

            # We use a plain requests call separate from session login
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            result = response.json()
            
            account_data = result.get("message", {})
            debit_account = account_data.get("debit_account", "")
            credit_account = account_data.get("credit_account", "")
            
            self.output.append(f"[Penalty Charges] Retrieved accounts - Debit: {debit_account}, Credit: {credit_account}")
            
            # Get form field values
            farmer_code = self.form_fields.get("farmer_code").text() if self.form_fields.get("farmer_code") else ""
            farmer_name = self.form_fields.get("farmer_name").text() if self.form_fields.get("farmer_name") else ""
            transporter_code = self.form_fields.get("transporter_code").text() if self.form_fields.get("transporter_code") else ""
            transporter_name = self.form_fields.get("transporter_name").text() if self.form_fields.get("transporter_name") else ""
            harvester_name = self.form_fields.get("harvester_name").text() if self.form_fields.get("harvester_name") else ""
            harvester_ht_code = self.form_fields.get("harvester_ht_code").text() if self.form_fields.get("harvester_ht_code") else ""
            cane_deduction_type = self.form_fields.get("cane_deduction_type").text() if self.form_fields.get("cane_deduction_type") else ""

            # Get penalty charges table
            penalty_table = self.form_fields.get("penalty_charges")
            if not penalty_table:
                QMessageBox.warning(self, "Warning", "Penalty charges table not found!")
                return
            
            # Clear existing rows
            penalty_table.setRowCount(0)
            
            # Row 1: Farmer
            if farmer_code or farmer_name:
                row = penalty_table.rowCount()
                penalty_table.insertRow(row)
                penalty_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))  # No.
                penalty_table.setItem(row, 1, self._make_penalty_readonly_item(farmer_code))  # Entity Code
                penalty_table.setItem(row, 2, self._make_penalty_readonly_item(farmer_name))  # Entity Name
                penalty_table.setItem(row, 3, self._make_penalty_readonly_item("Farmer"))  # Entity Type
                penalty_table.setItem(row, 4, QTableWidgetItem(cane_deduction_type or ""))  # Deduction Type
                penalty_table.setCellWidget(row, 5, self._make_penalty_deduction_method_combo("Percentage"))  # Deduction Method
                penalty_table.setItem(row, 6, QTableWidgetItem("0"))  # Deduction Rate
                penalty_table.setItem(row, 7, QTableWidgetItem(""))  # Debit Account
                penalty_table.setItem(row, 8, QTableWidgetItem(""))  # Credit Account

            # Row 2: Transporter
            if transporter_code or transporter_name:
                row = penalty_table.rowCount()
                penalty_table.insertRow(row)
                penalty_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))  # No.
                penalty_table.setItem(row, 1, self._make_penalty_readonly_item(transporter_code))  # Entity Code
                penalty_table.setItem(row, 2, self._make_penalty_readonly_item(transporter_name))  # Entity Name
                penalty_table.setItem(row, 3, self._make_penalty_readonly_item("Transporter"))  # Entity Type
                penalty_table.setItem(row, 4, QTableWidgetItem("Penalty"))  # Deduction Type
                penalty_table.setCellWidget(row, 5, self._make_penalty_deduction_method_combo("Amount Per Ton"))  # Deduction Method
                penalty_table.setItem(row, 6, QTableWidgetItem("0"))  # Deduction Rate
                penalty_table.setItem(row, 7, QTableWidgetItem(debit_account))  # Debit Account
                penalty_table.setItem(row, 8, QTableWidgetItem(credit_account))  # Credit Account

            # Row 3: Harvester
            if harvester_ht_code or harvester_name:
                row = penalty_table.rowCount()
                penalty_table.insertRow(row)
                penalty_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))  # No.
                penalty_table.setItem(row, 1, self._make_penalty_readonly_item(harvester_ht_code))  # Entity Code
                penalty_table.setItem(row, 2, self._make_penalty_readonly_item(harvester_name))  # Entity Name
                penalty_table.setItem(row, 3, self._make_penalty_readonly_item("Harvester"))  # Entity Type
                penalty_table.setItem(row, 4, QTableWidgetItem("Penalty"))  # Deduction Type
                penalty_table.setCellWidget(row, 5, self._make_penalty_deduction_method_combo("Amount Per Ton"))  # Deduction Method
                penalty_table.setItem(row, 6, QTableWidgetItem("0"))  # Deduction Rate
                penalty_table.setItem(row, 7, QTableWidgetItem(debit_account))  # Debit Account
                penalty_table.setItem(row, 8, QTableWidgetItem(credit_account))  # Credit Account

            self.output.append(f"[Penalty Charges] Auto-populated {penalty_table.rowCount()} rows")
            if show_success_message:
                QMessageBox.information(self, "Success", f"Penalty charges table populated with {penalty_table.rowCount()} entries!")
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to fetch deduction type accounts: {str(e)}"
            self.output.append(f"[Penalty Charges Error] {error_msg}")
            if show_success_message:
                QMessageBox.critical(self, "Error", error_msg)
        except Exception as e:
            error_msg = f"Error auto-populating penalty charges: {str(e)}"
            self.output.append(f"[Penalty Charges Error] {error_msg}")
            if show_success_message:
                QMessageBox.critical(self, "Error", error_msg)
    
    def save_primary_frappe_credentials(self):
        self.primary_frappe_site_url = self.primary_frappe_site_url_input.text().strip()
        self.primary_frappe_username = self.primary_frappe_username_input.text().strip()
        self.primary_frappe_password = self.primary_frappe_password_input.text().strip()
        
        if not self.primary_frappe_site_url or not self.primary_frappe_username or not self.primary_frappe_password:
            QMessageBox.warning(self, "Warning", "Please fill in all primary Frappe credentials fields!")
            return
        
        # Validate Site URL format
        if not (self.primary_frappe_site_url.startswith("http://") or self.primary_frappe_site_url.startswith("https://")):
            QMessageBox.warning(self, "Warning", "Primary Site URL must start with http:// or https://")
            return
        
        self.output.append(f"[Settings] Primary Frappe credentials saved: Site URL={self.primary_frappe_site_url}, Username={self.primary_frappe_username}")
        QMessageBox.information(self, "Success", "Primary Frappe credentials saved successfully!")

    def save_rfid_settings(self):
        """Apply RFID Reader Settings from the Settings tab and reconnect using the new
        values immediately - no app restart needed."""
        new_ip = self.rfid_ip_input.text().strip()
        new_port_text = self.rfid_port_input.text().strip()
        new_endpoint = self.rfid_api_endpoint_input.text().strip()
        new_token = self.rfid_api_token_input.text().strip()

        if not new_ip or not new_port_text or not new_endpoint or not new_token:
            QMessageBox.warning(self, "Warning", "Please fill in all RFID settings fields!")
            return

        try:
            new_port = int(new_port_text)
        except ValueError:
            QMessageBox.warning(self, "Warning", "RFID Reader Port must be a number.")
            return

        if not (new_endpoint.startswith("http://") or new_endpoint.startswith("https://")):
            QMessageBox.warning(self, "Warning", "RFID API Endpoint must start with http:// or https://")
            return

        # Tear down the current socket/threads before swapping in the new settings so
        # the old reader connection doesn't keep running alongside the new one.
        self.stop_rfid_connection()

        self.rfid_ip = new_ip
        self.rfid_port = new_port
        self.rfid_api_endpoint = new_endpoint
        self.rfid_api_token = new_token

        self.rfid_status_label.setText("Status: Reconnecting...")
        self.output.append(
            f"[RFID Settings] Updated reader={self.rfid_ip}:{self.rfid_port}, endpoint={self.rfid_api_endpoint}"
        )

        # Give the old read/send threads a brief moment to notice rfid_running is False
        # and exit before starting fresh ones on the new socket.
        QTimer.singleShot(300, self.start_rfid_connection_thread)

        QMessageBox.information(self, "Success", "RFID settings saved. Reconnecting to reader...")

    def save_secondary_frappe_credentials(self):
        self.secondary_site_url = self.secondary_site_url_input.text().strip()
        self.secondary_frappe_username = self.secondary_frappe_username_input.text().strip()
        self.secondary_frappe_password = self.secondary_frappe_password_input.text().strip()
        
        if not self.secondary_site_url or not self.secondary_frappe_username or not self.secondary_frappe_password:
            QMessageBox.warning(self, "Warning", "Please fill in all secondary Frappe credentials fields!")
            return
        
        # Validate Site URL format
        if not (self.secondary_site_url.startswith("http://") or self.secondary_site_url.startswith("https://")):
            QMessageBox.warning(self, "Warning", "Secondary Site URL must start with http:// or https://")
            return
        
        self.output.append(f"[Settings] Secondary Frappe credentials saved: Site URL={self.secondary_site_url}, Username={self.secondary_frappe_username}")
        QMessageBox.information(self, "Success", "Secondary Frappe credentials saved successfully!")
    
    def save_third_frappe_credentials(self):
        self.third_frappe_site_url = self.third_frappe_site_url_input.text().strip()
        self.third_frappe_username = self.third_frappe_username_input.text().strip()
        self.third_frappe_password = self.third_frappe_password_input.text().strip()
        
        if not self.third_frappe_site_url or not self.third_frappe_username or not self.third_frappe_password:
            QMessageBox.warning(self, "Warning", "Please fill in all third Frappe instance credentials fields!")
            return
        
        if not (self.third_frappe_site_url.startswith("http://") or self.third_frappe_site_url.startswith("https://")):
            QMessageBox.warning(self, "Warning", "Third Frappe Site URL must start with http:// or https://")
            return
        
        self.output.append(f"[Settings] Third Frappe credentials saved: Site URL={self.third_frappe_site_url}, Username={self.third_frappe_username}")
        QMessageBox.information(self, "Success", "Third Frappe credentials saved successfully!")

    def save_trip_sheet_credentials(self):
        self.trip_sheet_frappe_site_url = self.trip_sheet_site_url_input.text().strip()
        self.trip_sheet_frappe_username = self.trip_sheet_username_input.text().strip()
        self.trip_sheet_frappe_password = self.trip_sheet_password_input.text().strip()
        
        if not self.trip_sheet_frappe_site_url or not self.trip_sheet_frappe_username or not self.trip_sheet_frappe_password:
            QMessageBox.warning(self, "Warning", "Please fill in all Trip Sheet Frappe credentials fields!")
            return
        
        if not (self.trip_sheet_frappe_site_url.startswith("http://") or self.trip_sheet_frappe_site_url.startswith("https://")):
            QMessageBox.warning(self, "Warning", "Trip Sheet Frappe Site URL must start with http:// or https://")
            return
        
        self.output.append(f"[Settings] Trip Sheet Frappe credentials saved: Site URL={self.trip_sheet_frappe_site_url}, Username={self.trip_sheet_frappe_username}")
        QMessageBox.information(self, "Success", "Trip Sheet Frappe credentials saved successfully!")

    def login_primary_frappe(self):
        site_url = self.primary_frappe_site_url_input.text().strip()
        username = self.primary_frappe_username_input.text().strip()
        password = self.primary_frappe_password_input.text().strip()
        
        if not site_url or not username or not password:
            QMessageBox.warning(self, "Warning", "Please fill in all primary Frappe credentials!")
            return
        
        try:
            # Use the session object for login
            response = self.primary_frappe_session.post(
                f"{site_url}/api/method/login",
                json={"usr": username, "pwd": password}
            )
            response.raise_for_status()
            
            self.primary_frappe_logged_in = True
            self.primary_frappe_login_btn.setEnabled(False)
            self.primary_frappe_logout_btn.setEnabled(True)
            # The session object automatically handles the cookie
            self.output.append(f"[Frappe] Primary Frappe logged in successfully.")
            QMessageBox.information(self, "Success", "Primary Frappe logged in successfully.")
        except requests.exceptions.HTTPError as e:
            error_msg = f"[Frappe Error] HTTP {e.response.status_code}: {e.response.text}"
            self.output.append(error_msg)
            QMessageBox.critical(self, "Error", f"Failed to log in to Primary Frappe: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = f"[Frappe Error] Network error: {str(e)}"
            self.output.append(error_msg)
            QMessageBox.critical(self, "Error", f"Failed to log in to Primary Frappe: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Frappe Error] {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to log in to Primary Frappe: {error_msg}")
    
    def logout_primary_frappe(self):
        site_url = self.primary_frappe_site_url_input.text().strip()
        if not site_url:
            QMessageBox.warning(self, "Warning", "Primary Site URL not configured!")
            return
        
        try:
            # Use the session object for logout
            response = self.primary_frappe_session.post(
                f"{site_url}/api/method/logout"
            )
            response.raise_for_status()
            self.primary_frappe_logged_in = False
            self.primary_frappe_login_btn.setEnabled(True)
            self.primary_frappe_logout_btn.setEnabled(False)
            # Clear session cookies if necessary (though session.post might do it)
            self.primary_frappe_session.cookies.clear()
            self.output.append(f"[Frappe] Primary Frappe logged out successfully.")
            QMessageBox.information(self, "Success", "Primary Frappe logged out successfully.")
        except requests.exceptions.HTTPError as e:
            error_msg = f"[Frappe Error] HTTP {e.response.status_code}: {e.response.text}"
            self.output.append(error_msg)
            QMessageBox.critical(self, "Error", f"Failed to log out from Primary Frappe: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = f"[Frappe Error] Network error: {str(e)}"
            self.output.append(error_msg)
            QMessageBox.critical(self, "Error", f"Failed to log out from Primary Frappe: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Frappe Error] {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to log out from Primary Frappe: {error_msg}")

    def login_secondary_frappe(self):
        site_url = self.secondary_site_url_input.text().strip()
        username = self.secondary_frappe_username_input.text().strip()
        password = self.secondary_frappe_password_input.text().strip()
        
        if not site_url or not username or not password:
            QMessageBox.warning(self, "Warning", "Please fill in all secondary Frappe credentials!")
            return
        
        try:
            # Use the session object for login
            response = self.secondary_frappe_session.post(
                f"{site_url}/api/method/login",
                json={"usr": username, "pwd": password}
            )
            response.raise_for_status()
            
            self.secondary_frappe_logged_in = True
            self.secondary_frappe_login_btn.setEnabled(False)
            self.secondary_frappe_logout_btn.setEnabled(True)
            # The session object automatically handles the cookie
            self.output.append(f"[Frappe] Secondary Frappe logged in successfully.")
            QMessageBox.information(self, "Success", "Secondary Frappe logged in successfully.")
        except requests.exceptions.HTTPError as e:
            error_msg = f"[Frappe Error] HTTP {e.response.status_code}: {e.response.text}"
            self.output.append(error_msg)
            QMessageBox.critical(self, "Error", f"Failed to log in to Secondary Frappe: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = f"[Frappe Error] Network error: {str(e)}"
            self.output.append(error_msg)
            QMessageBox.critical(self, "Error", f"Failed to log in to Secondary Frappe: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Frappe Error] {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to log in to Secondary Frappe: {error_msg}")
    
    def logout_secondary_frappe(self):
        site_url = self.secondary_site_url_input.text().strip()
        if not site_url:
            QMessageBox.warning(self, "Warning", "Secondary Site URL not configured!")
            return
        
        try:
            # Use the session object for logout
            response = self.secondary_frappe_session.post(
                f"{site_url}/api/method/logout"
            )
            response.raise_for_status()
            self.secondary_frappe_logged_in = False
            self.secondary_frappe_login_btn.setEnabled(True)
            self.secondary_frappe_logout_btn.setEnabled(False)
            # Clear session cookies if necessary
            self.secondary_frappe_session.cookies.clear()
            self.output.append(f"[Frappe] Secondary Frappe logged out successfully.")
            QMessageBox.information(self, "Success", "Secondary Frappe logged out successfully.")
        except requests.exceptions.HTTPError as e:
            error_msg = f"[Frappe Error] HTTP {e.response.status_code}: {e.response.text}"
            self.output.append(error_msg)
            QMessageBox.critical(self, "Error", f"Failed to log out from Secondary Frappe: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = f"[Frappe Error] Network error: {str(e)}"
            self.output.append(error_msg)
            QMessageBox.critical(self, "Error", f"Failed to log out from Secondary Frappe: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Frappe Error] {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to log out from Secondary Frappe: {error_msg}")

    def login_third_frappe(self):
        site_url = self.third_frappe_site_url_input.text().strip()
        username = self.third_frappe_username_input.text().strip()
        password = self.third_frappe_password_input.text().strip()
        
        if not site_url or not username or not password:
            QMessageBox.warning(self, "Warning", "Please fill in all third Frappe credentials!")
            return
        
        try:
            response = self.third_frappe_session.post(
                f"{site_url}/api/method/login",
                json={"usr": username, "pwd": password}
            )
            response.raise_for_status()
            self.third_frappe_logged_in = True
            self.third_frappe_login_btn.setEnabled(False)
            self.third_frappe_logout_btn.setEnabled(True)
            self.output.append(f"[Frappe] Third Frappe logged in successfully.")
            QMessageBox.information(self, "Success", "Third Frappe logged in successfully.")
        except requests.exceptions.HTTPError as e:
            error_msg = f"[Frappe Error] HTTP {e.response.status_code}: {e.response.text}"
            self.output.append(error_msg)
            QMessageBox.critical(self, "Error", f"Failed to log in to Third Frappe: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = f"[Frappe Error] Network error: {str(e)}"
            self.output.append(error_msg)
            QMessageBox.critical(self, "Error", f"Failed to log in to Third Frappe: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Frappe Error] {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to log in to Third Frappe: {error_msg}")

    def logout_third_frappe(self):
        site_url = self.third_frappe_site_url_input.text().strip()
        if not site_url:
            QMessageBox.warning(self, "Warning", "Third Frappe Site URL not configured!")
            return
        
        try:
            response = self.third_frappe_session.post(
                f"{site_url}/api/method/logout"
            )
            response.raise_for_status()
            self.third_frappe_logged_in = False
            self.third_frappe_login_btn.setEnabled(True)
            self.third_frappe_logout_btn.setEnabled(False)
            self.third_frappe_session.cookies.clear()
            self.output.append(f"[Frappe] Third Frappe logged out successfully.")
            QMessageBox.information(self, "Success", "Third Frappe logged out successfully.")
        except requests.exceptions.HTTPError as e:
            error_msg = f"[Frappe Error] HTTP {e.response.status_code}: {e.response.text}"
            self.output.append(error_msg)
            QMessageBox.critical(self, "Error", f"Failed to log out from Third Frappe: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = f"[Frappe Error] Network error: {str(e)}"
            self.output.append(error_msg)
            QMessageBox.critical(self, "Error", f"Failed to log out from Third Frappe: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Frappe Error] {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to log out from Third Frappe: {error_msg}")

    def login_trip_sheet_frappe(self):
        site_url = self.trip_sheet_site_url_input.text().strip()
        username = self.trip_sheet_username_input.text().strip()
        password = self.trip_sheet_password_input.text().strip()
        
        if not site_url or not username or not password:
            QMessageBox.warning(self, "Warning", "Please fill in all Trip Sheet Frappe credentials!")
            return
        
        try:
            response = self.trip_sheet_frappe_session.post(
                f"{site_url}/api/method/login",
                json={"usr": username, "pwd": password}
            )
            response.raise_for_status()
            self.trip_sheet_frappe_logged_in = True
            self.trip_sheet_login_btn.setEnabled(False)
            self.trip_sheet_logout_btn.setEnabled(True)
            self.output.append(f"[Frappe] Trip Sheet Frappe logged in successfully.")
            QMessageBox.information(self, "Success", "Trip Sheet Frappe logged in successfully.")
        except requests.exceptions.HTTPError as e:
            error_msg = f"[Frappe Error] HTTP {e.response.status_code}: {e.response.text}"
            self.output.append(error_msg)
            QMessageBox.critical(self, "Error", f"Failed to log in to Trip Sheet Frappe: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = f"[Frappe Error] Network error: {str(e)}"
            self.output.append(error_msg)
            QMessageBox.critical(self, "Error", f"Failed to log in to Trip Sheet Frappe: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Frappe Error] {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to log in to Trip Sheet Frappe: {error_msg}")

    def logout_trip_sheet_frappe(self):
        site_url = self.trip_sheet_site_url_input.text().strip()
        if not site_url:
            QMessageBox.warning(self, "Warning", "Trip Sheet Frappe Site URL not configured!")
            return
        
        try:
            response = self.trip_sheet_frappe_session.post(
                f"{site_url}/api/method/logout"
            )
            response.raise_for_status()
            self.trip_sheet_frappe_logged_in = False
            self.trip_sheet_login_btn.setEnabled(True)
            self.trip_sheet_logout_btn.setEnabled(False)
            self.trip_sheet_frappe_session.cookies.clear()
            self.output.append(f"[Frappe] Trip Sheet Frappe logged out successfully.")
            QMessageBox.information(self, "Success", "Trip Sheet Frappe logged out successfully.")
        except requests.exceptions.HTTPError as e:
            error_msg = f"[Frappe Error] HTTP {e.response.status_code}: {e.response.text}"
            self.output.append(error_msg)
            QMessageBox.critical(self, "Error", f"Failed to log out from Trip Sheet Frappe: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = f"[Frappe Error] Network error: {str(e)}"
            self.output.append(error_msg)
            QMessageBox.critical(self, "Error", f"Failed to log out from Trip Sheet Frappe: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Frappe Error] {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to log out from Trip Sheet Frappe: {error_msg}")

    def toggle_primary_to_secondary_auto_sync(self, state):
        is_checked = self.primary_to_secondary_auto_sync_checkbox.isChecked()
        if is_checked:
            self.primary_to_secondary_auto_sync_enabled = True
            self.primary_to_secondary_auto_sync_timer.start(5000)  # 5 seconds interval
            self.output.append("[Auto-Sync Primary to Secondary] Automatic synchronization enabled.")
            self.sync_primary_to_secondary_data() # Immediate sync on enable
        else:
            self.primary_to_secondary_auto_sync_enabled = False
            self.primary_to_secondary_auto_sync_timer.stop()
            self.output.append("[Auto-Sync Primary to Secondary] Automatic synchronization disabled.")

    def toggle_third_to_primary_auto_sync(self, state):
        is_checked = self.third_to_primary_auto_sync_checkbox.isChecked()
        if is_checked:
            self.third_to_primary_auto_sync_enabled = True
            self.third_to_primary_auto_sync_timer.start(10000)  # 10 seconds interval
            self.output.append("[Auto-Sync Third to Primary] Automatic synchronization enabled.")
            self.sync_third_to_primary_data() # Immediate sync on enable
        else:
            self.third_to_primary_auto_sync_enabled = False
            self.third_to_primary_auto_sync_timer.stop()
            self.output.append("[Auto-Sync Third to Primary] Automatic synchronization disabled.")

    def sync_primary_to_secondary_data(self):
        if not self.primary_frappe_logged_in:
            QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance!")
            return
        
        if not self.secondary_frappe_logged_in:
            QMessageBox.warning(self, "Warning", "Not logged in to Secondary Frappe instance!")
            return
        
        try:
            headers = {
                "Accept": "application/json",
            }
            page_length = 1000
            start = 0
            docs = []
            
            # Build URL with fields parameter to retrieve all document fields
            url = f"{self.primary_frappe_site_url}/api/resource/Cane Weight?limit_page_length={page_length}&limit_start={start}&fields=[\"*\"]"
            
            # Fetch documents with pagination using the session object
            while True:
                response = self.primary_frappe_session.get(url, headers=headers)
                response.raise_for_status()
                page_docs = response.json().get('data', [])
                docs.extend(page_docs)
                if len(page_docs) < page_length:
                    break
                start += page_length
                url = f"{self.primary_frappe_site_url}/api/resource/Cane Weight?limit_page_length={page_length}&limit_start={start}&fields=[\"*\"]"
            
            if not docs:
                self.output.append(f"[Sync Primary to Secondary] No documents found to sync")
                # QMessageBox.information(self, "Info", f"No documents found to sync from Primary to Secondary!")
                return
            
            headers_secondary = {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            
            synced_count = 0
            failed_count = 0
            for doc in docs:
                excluded_fields = ['name', 'owner', 'creation', 'modified', 'modified_by', 'docstatus', 'idx', '__last_sync_on']
                payload = {k: v for k, v in doc.items() if k not in excluded_fields}
                
                # Define numeric, checkbox, date, datetime, and time fields for proper handling
                numeric_fields = [
                    "crop_day", "slip_no", "distancekm", "total_diesel_allocated", 
                    "water_share_", "cane_deduction", "gross_weight_bridge", 
                    "tare_weight_bridge", "wb_value", "wb_second_value", 
                    "gross_weight", "tare_weight", "cane_weight", "binding_weightton", 
                    "cane_deductionton", "harvester_weight", "farmer_actual_weight", 
                    "net_weightton", "binding_weightkg", "transporter_weight", 
                    "water_supplier_weight", "area_acre", "percentage", 
                    "daily_cane_purchase", "tolly_1", "tolly_2"
                ]
                checkbox_fields = [
                    "manually__gross_weight", "is_kisan_card", "h_and_t_billing_status", 
                    "weight_partner_status", "show_all_plot_fields", "manually_tear_weight"
                ]
                date_fields = [
                    "date", "plantation_date", "cane_inward_slip_date", "entry_date"
                ]
                datetime_fields = [
                    "gross_weight_timedate", "tare_weight_timedate"
                ]
                time_fields = [
                    "time", "cane_inward_slip_time", "entry_time"
                ]

                # Process payload fields for correct types and default values
                for field_name, value in payload.items():
                    if field_name in numeric_fields:
                        try:
                            payload[field_name] = float(value) if value is not None and value != "" else 0.0
                        except ValueError:
                            payload[field_name] = 0.0 # Default to 0.0 if conversion fails
                    elif field_name in checkbox_fields:
                        payload[field_name] = 1 if value else 0 # Ensure it's 0 or 1
                    elif field_name in date_fields:
                        payload[field_name] = value if value else datetime.now().strftime("%Y-%m-%d")
                    elif field_name in datetime_fields:
                        payload[field_name] = value if value else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    elif field_name in time_fields:
                        payload[field_name] = value if value else datetime.now().strftime("%H:%M:%S")
                    elif value is None:
                        payload[field_name] = "" # Default None to empty string for other fields
                
                # Special handling for uin, ensure it is a string
                if "uin" in payload and payload["uin"] is None:
                    payload["uin"] = ""

                self.output.append(f"[Sync Primary to Secondary] Syncing document with fields: {list(payload.keys())}")
                self.output.append(f"[Sync Primary to Secondary] Payload being sent: {json.dumps(payload, indent=2)}")
                try:
                    response_sec = self.secondary_frappe_session.post(
                        f"{self.secondary_site_url}/api/resource/Cane Weight",
                        json=payload,
                        headers=headers_secondary
                    )
                    response_sec.raise_for_status()
                    synced_count += 1
                    doc_name = response_sec.json().get("data", {}).get("name", "Unknown")
                    self.output.append(f"[Sync Primary to Secondary] Successfully synced document: {doc_name}")
                    self.output.append(f"[Sync Primary to Secondary] Full response: {response_sec.text}")
                except requests.exceptions.HTTPError as e:
                    failed_count += 1
                    error_msg = f"Failed to sync document: HTTP {e.response.status_code}: {e.response.text}"
                    self.output.append(f"[Sync Primary to Secondary Error] {error_msg}")
            
            self.output.append(f"[Sync Primary to Secondary] Synced {synced_count} documents successfully, {failed_count} failed")
            # QMessageBox.information(self, "Success", f"Synced {synced_count} documents from Primary to Secondary, {failed_count} failed")
        
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            self.output.append(f"[Sync Primary to Secondary Error] {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to sync Primary to Secondary: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error: {str(e)}"
            self.output.append(f"[Sync Primary to Secondary Error] {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to sync Primary to Secondary: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Sync Primary to Secondary Error] {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to sync Primary to Secondary: {error_msg}")

    def sync_third_to_primary_data(self):
        if not self.third_frappe_logged_in:
            QMessageBox.warning(self, "Warning", "Not logged in to Third Frappe instance!")
            return
        
        if not self.primary_frappe_logged_in:
            QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance (for third to primary sync)! ")
            return
        
        try:
            headers_third = {
                "Accept": "application/json",
            }
            page_length = 1
            start = 0
            docs = []
            
            # Fetch documents from Third Frappe Instance
            url_third = f"{self.third_frappe_site_url}/api/resource/Trip Sheet?limit_page_length={page_length}&limit_start={start}&fields=[\"*\"]"
            while True:
                response_third = self.third_frappe_session.get(url_third, headers=headers_third)
                response_third.raise_for_status()
                page_docs = response_third.json().get('data', [])
                docs.extend(page_docs)
                if len(page_docs) < page_length:
                    break
                start += page_length
                url_third = f"{self.third_frappe_site_url}/api/resource/Trip Sheet?limit_page_length={page_length}&limit_start={start}&fields=[\"*\"]"
            
            if not docs:
                self.output.append(f"[Sync Third to Primary] No documents found to sync")
                # QMessageBox.information(self, "Info", f"No documents found to sync from Third to Primary!")
                return
            
            headers_primary = {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            
            synced_count = 0
            failed_count = 0
            for doc in docs:
                excluded_fields = ['name', 'owner', 'creation', 'modified', 'modified_by', 'docstatus', 'idx', '__last_sync_on']
                payload = {k: v for k, v in doc.items() if k not in excluded_fields}
                self.output.append(f"[Sync Third to Primary] Syncing document with fields: {list(payload.keys())}")
                self.output.append(f"[Sync Third to Primary] Payload being sent: {json.dumps(payload, indent=2)}")
                try:
                    response_primary = self.primary_frappe_session.post(
                        f"{self.primary_frappe_site_url}/api/resource/Trip Sheet",
                        json=payload,
                        headers=headers_primary
                    )
                    response_primary.raise_for_status()
                    synced_count += 1
                    doc_name = response_primary.json().get("data", {}).get("name", "Unknown")
                    self.output.append(f"[Sync Third to Primary] Successfully synced document: {doc_name}")
                    self.output.append(f"[Sync Third to Primary] Full response: {response_primary.text}")
                except requests.exceptions.HTTPError as e:
                    failed_count += 1
                    error_msg = f"Failed to sync document: HTTP {e.response.status_code}: {e.response.text}"
                    self.output.append(f"[Sync Third to Primary Error] {error_msg}")
            
            self.output.append(f"[Sync Third to Primary] Synced {synced_count} documents successfully, {failed_count} failed")
            # QMessageBox.information(self, "Success", f"Synced {synced_count} documents from Third to Primary, {failed_count} failed")
        
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            self.output.append(f"[Sync Third to Primary Error] {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to sync Third to Primary: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error: {str(e)}"
            self.output.append(f"[Sync Third to Primary Error] {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to sync Third to Primary: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Sync Third to Primary Error] {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to sync Third to Primary: {error_msg}")

    def setup_styles(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
                font-family: 'Segoe UI', Arial, sans-serif;
            } 
                headerFrame QLabel {
                background: transparent;
                }


            
            #titleLabel {
                color: white;
                font-size: 24px;
                font-weight: bold;
            }
            
            #subtitleLabel {
                color: rgba(255, 255, 255, 0.8);
                font-size: 12px;
            }
            
            #statusLabel {
                color: white;
                font-weight: bold;
            }
            
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                color: #2c3e50;
                border: 2px solid #bdc3c7;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 5px;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 10px 0 10px;
                background-color: #f8f9fa;
            }
            
            #settingsGroup {
                border-color: #3498db;
            }
            
            #dataGroup {
                border-color: #27ae60;
            }

            /* Settings tab: each group gets its own accent color so the sections are
               easy to tell apart at a glance. */
            #serialSettingsGroup {
                border-color: #3498db;
            }

            #secondaryFrappeGroup {
                border-color: #9b59b6;
            }

            #thirdFrappeGroup {
                border-color: #e67e22;
            }

            #tripSheetGroup {
                border-color: #16a085;
            }

            #autoSyncGroup {
                border-color: #27ae60;
            }

            #rfidSettingsGroup {
                border-color: #c0392b;
            }

            #settingsStatusPill {
                background-color: #ecf0f1;
                color: #2c3e50;
                font-weight: 600;
                font-size: 11px;
                padding: 6px 10px;
                border-radius: 6px;
                border: 1px solid #dbe1e8;
            }

            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
                min-height: 20px;
            }
            
            QPushButton:hover {
                background-color: #2980b9;
            }
            
            QPushButton:pressed {
                background-color: #21618c;
            }
            
            #connectBtn {
                background-color: #27ae60;
                min-width: 100px;
            }
            
            #connectBtn:hover {
                background-color: #229954;
            }
            
            #connectBtn[connected="true"] {
                background-color: #e74c3c;
            }
            
            #connectBtn[connected="true"]:hover {
                background-color: #c0392b;
            }
            
            #clearBtn {
                background-color: #f39c12;
            }
            
            #clearBtn:hover {
                background-color: #e67e22;
            }
            
            #saveBtn, #saveApiBtn {
                background-color: #9b59b6;
            }
            
            #saveBtn:hover, #saveApiBtn:hover {
                background-color: #8e44ad;
            }
            
            #sendBtn, #submitBtn {
                background-color: #e74c3c;
            }
            
            #sendBtn:hover, #submitBtn:hover {
                background-color: #c0392b;
            }
            
            #syncBtn {
                background-color: #27ae60;
            }
            
            #syncBtn:hover {
                background-color: #229954;
            }
            
            QLineEdit, QComboBox, QSpinBox, QDateEdit, QDateTimeEdit, QTableWidget {
                padding: 8px;
                border: 2px solid #bdc3c7;
                border-radius: 6px;
                background-color: white;
                font-size: 11px;
            }
            
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus, QDateTimeEdit:focus, QTableWidget:focus {
                border-color: #3498db;
            }
            
            #dataOutput {
                background-color: #2c3e50;
                color: #ecf0f1;
                border: 2px solid #34495e;
                border-radius: 6px;
                padding: 10px;
                font-family: 'Consolas', 'Monaco', monospace;
            }
            
            #sendHistory {
                background-color: #ecf0f1;
                color: #2c3e50;
                border: 2px solid #bdc3c7;
                border-radius: 6px;
                padding: 5px;
            }
            
            #statusBar {
                background-color: #34495e;
                color: white;
                border-radius: 6px;
                padding: 8px;
                margin-top: 5px;
            }
            
            QTabWidget::pane {
                border: 2px solid #bdc3c7;
                border-radius: 6px;
                background-color: white;
            }
            
            QTabBar::tab {
                background-color: #ecf0f1;
                padding: 8px 20px;
                margin: 2px;
                border-radius: 6px;
            }
            
            QTabBar::tab:selected {
                background-color: #3498db;
                color: white;
            }
            
            QCheckBox {
                spacing: 8px;
                font-size: 11px;
            }
            
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 3px;
                border: 2px solid #bdc3c7;
                background-color: white;
            }
            
            QCheckBox::indicator:checked {
                background-color: #3498db;
                border-color: #3498db;
            }
        """)
    
    def refresh_ports(self):
        current_port = self.port_combo.currentText()
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        port_names = []
        for port in sorted(ports, key=lambda x: x.device):
            port_info = f"{port.device}"
            if port.description and port.description != 'n/a':
                port_info += f" - {port.description}"
            port_names.append(port_info)
            self.port_combo.addItem(port_info, port.device)
        if not port_names:
            self.port_combo.addItem("No ports available", "")
        index = self.port_combo.findText(current_port)
        if index >= 0:
            self.port_combo.setCurrentIndex(index)
    
    def toggle_connection(self):
        """Toggle serial port connection on/off."""
        if not self.connected:
            self.connect_serial()
        else:
            self.disconnect_serial()
    
    def connect_serial(self):
        """Establish connection to the selected serial port."""
        port_text = self.port_combo.currentText()
        if not port_text or port_text == "No ports available":
            QMessageBox.warning(self, "Warning", "No COM port selected!")
            self.output.append("[ERROR] No COM port selected. Please select a valid port.")
            return
        
        port = self.port_combo.currentData() or port_text.split(' -')[0]
        try:
            baud = int(self.baud_combo.currentText())
        except ValueError:
            QMessageBox.warning(self, "Warning", "Invalid baud rate!")
            self.output.append("[ERROR] Invalid baud rate selected.")
            return
        
        timeout = self.timeout_spin.value()
        
        # Update button to show connecting state
        self.connect_btn.setText("⏳ Connecting...")
        self.connect_btn.setEnabled(False)
        self.connect_btn.setProperty("connected", "connecting")
        self.connect_btn.style().unpolish(self.connect_btn)
        self.connect_btn.style().polish(self.connect_btn)
        
        # Disable port settings during connection
        self.port_combo.setEnabled(False)
        self.baud_combo.setEnabled(False)
        self.timeout_spin.setEnabled(False)
        
        # Start serial reader thread
        self.reader = SerialReader(port, baud, timeout)
        self.reader.data_received.connect(self.display_data)
        self.reader.connection_status.connect(self.update_connection_status)
        self.reader.start()
        
        self.output.append(f"[INFO] Attempting to connect to {port} at {baud} baud...")
    
    def disconnect_serial(self):
        """Disconnect from the serial port and stop reading."""
        # Update button to show disconnecting state
        self.connect_btn.setText("⏳ Disconnecting...")
        self.connect_btn.setEnabled(False)
        
        if self.reader:
            self.output.append("[INFO] Disconnecting from serial port...")
            self.reader.stop()
            self.reader.wait(3000)
            if self.reader.isRunning():
                self.reader.terminate()
                self.output.append("[WARNING] Serial reader thread was forcefully terminated.")
        
        self.update_connection_status(False, "Disconnected")
        self.output.append("[INFO] Serial port disconnected successfully.")
    
    def update_connection_status(self, connected, message):
        """Update UI elements based on connection status."""
        self.connected = connected
        self.status_indicator.set_status(connected)
        self.status_label.setText(message)
        
        if connected:
            # Connected state - enable disconnect
            self.connect_btn.setText("🔌 Disconnect")
            self.connect_btn.setProperty("connected", "true")
            self.connect_btn.setEnabled(True)
            
            # Enable send controls
            self.send_btn.setEnabled(True)
            self.send_input.setEnabled(True)
            
            # Keep port settings disabled while connected
            self.port_combo.setEnabled(False)
            self.baud_combo.setEnabled(False)
            self.timeout_spin.setEnabled(False)
            
            self.connection_start_time = datetime.now()
            self.output.append(f"[SUCCESS] Connected to serial port: {message}")
        else:
            # Disconnected state - enable connect
            self.connect_btn.setText("🔌 Connect")
            self.connect_btn.setProperty("connected", "false")
            self.connect_btn.setEnabled(True)
            
            # Disable send controls
            self.send_btn.setEnabled(False)
            self.send_input.setEnabled(False)
            
            # Re-enable port settings for configuration
            self.port_combo.setEnabled(True)
            self.baud_combo.setEnabled(True)
            self.timeout_spin.setEnabled(True)
        
        # Refresh button styling
        self.connect_btn.style().unpolish(self.connect_btn)
        self.connect_btn.style().polish(self.connect_btn)
       
    def display_data(self, data):
        print(f"[DEBUG] Raw data received: '{data}'")

        clean_data = data
        if data.startswith('[') and '] ' in data:
            clean_data = data.split('] ', 1)[1]
            print(f"[DEBUG] After removing timestamp: '{clean_data}'")

        try:
            # Extract digits only
            digits = ''.join(filter(str.isdigit, clean_data))
            if digits:
                weight_kg = int(digits)
                tons = weight_kg / 1_000
                self.current_weight = tons
                print(f"[DEBUG] ✓ Weight parsed successfully: {weight_kg} kg = {self.current_weight:.5f} tons")
            else:
                print(f"[DEBUG] ✗ No digits found in data: '{clean_data}'")
        except Exception as e:
            print(f"[DEBUG] ✗ Error parsing weight: {e}")

        # Display the data in the output terminal
        if not self.timestamp_check.isChecked():
            if data.startswith('[') and '] ' in data:
                data = data.split('] ', 1)[1]
        self.output.append(data)
        self.bytes_received += len(data.encode('utf-8'))
        if self.autoscroll_check.isChecked():
            cursor = self.output.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.output.setTextCursor(cursor)

    
    def send_data(self):
        if not self.connected or not self.reader:
            return
        data = self.send_input.text().strip()
        if not data:
            return
        if self.reader.send_data(data):
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.send_history.append(f"[{timestamp}] {data}")
            self.send_input.clear()
            self.bytes_sent += len(data.encode('utf-8'))
            cursor = self.send_history.textCursor()
            cursor.movePosition(cursor.End)
            self.send_history.setTextCursor(cursor)
    
    def clear_received_data(self):
        self.output.clear()
        self.bytes_received = 0
    
    def save_log(self):
        from PySide6.QtWidgets import QFileDialog
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Log", f"serial_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text Files (*.txt);;All Files (*)"
        )
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.output.toPlainText())
                QMessageBox.information(self, "Success", f"Log saved to {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save log: {str(e)}")
    
    def update_stats(self):
        if hasattr(self, 'header_clock_label'):
            self.header_clock_label.setText(datetime.now().strftime("%H:%M:%S"))
        self.rx_label.setText(f"RX: {self.bytes_received:,} bytes")
        self.tx_label.setText(f"TX: {self.bytes_sent:,} bytes")
        if self.connected and hasattr(self, 'connection_start_time'):
            elapsed = datetime.now() - self.connection_start_time
            hours, remainder = divmod(elapsed.total_seconds(), 3600)
            minutes, seconds = divmod(remainder, 60)
            self.time_label.setText(f"Connected: {int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}")
        else:
            self.time_label.setText("Connected: 00:00:00")
    
    def get_gross_weight(self):
        print(f"[DEBUG] get_gross_weight called. Connected: {self.connected}, current_weight: {self.current_weight}")
        
        if self.connected and self.reader:
            # Check if we have a current weight reading (including 0)
            if self.current_weight is not None:
                # The weight value is already in kg (e.g., 20 means 20 kg)
                weight_kg = self.current_weight
                
                # Update the gross weight field
                if "gross_weight" in self.form_fields:
                    self.form_fields["gross_weight"].setText(str(float(weight_kg)))
                    print(f"[DEBUG] Gross Weight field updated to: {float(weight_kg)} ton")
                    
                    # Stamp the real capture moment and freeze the live-ticking timestamp there
                    if "gross_weight_timestamp" in self.form_fields:
                        self.form_fields["gross_weight_timestamp"].setDateTime(datetime.now())
                    self._gross_weight_captured = True

                    self.output.append(f"[SYSTEM] Gross Weight captured: {float(weight_kg)} ton at {datetime.now().strftime('%H:%M:%S')}")
                    QMessageBox.information(self, "Success", f"Gross Weight: {str(weight_kg)} ton")
                else:
                    QMessageBox.warning(self, "Warning", "Gross weight field not found!")
            else:
                print(f"[DEBUG] current_weight is None - no weight data available")
                QMessageBox.warning(self, "Warning", "No weight data available. Please wait for weight reading.")
        else:
            print(f"[DEBUG] Not connected to serial port")
            QMessageBox.warning(self, "Warning", "Not connected to serial port!")
    
#     def get_tare_weight(self):
#         if self.connected and self.reader:
#             self.reader.send_data("GET_TARE_WEIGHT")
#         else:
#             QMessageBox.warning(self, "Warning", "Not connected to serial port!")
    
    
    def get_tare_weight(self):
        print(f"[DEBUG] get_tare_weight called. Connected: {self.connected}, current_weight: {self.current_weight}")
        
        if self.connected and self.reader:
            # Check if we have a current weight reading (including 0)
            if self.current_weight is not None:
                # The weight value is already in kg (e.g., 20 means 20 kg)
                weight_kg = self.current_weight
                
                # Update the tare weight field
                if "tare_weight" in self.form_fields:
                    self.form_fields["tare_weight"].setText(str(float(weight_kg)))
                    print(f"[DEBUG] Tare Weight field updated to: {float(weight_kg)} kg")
                    
                    # Stamp the real capture moment and freeze the live-ticking timestamp there
                    if "tare_weight_timestamp" in self.form_fields:
                        self.form_fields["tare_weight_timestamp"].setDateTime(datetime.now())
                    self._tare_weight_captured = True

                    self.output.append(f"[SYSTEM] Tare Weight captured: {float(weight_kg)} kg at {datetime.now().strftime('%H:%M:%S')}")
                    # QMessageBox.information(self, "Success", f"Tare Weight: {float(weight_kg)} kg")
                else:
                    QMessageBox.warning(self, "Warning", "Tare weight field not found!")
            else:
                print(f"[DEBUG] current_weight is None - no weight data available")
                QMessageBox.warning(self, "Warning", "No weight data available. Please wait for weight reading.")
        else:
            print(f"[DEBUG] Not connected to serial port")
            QMessageBox.warning(self, "Warning", "Not connected to serial port!")
    
    def _collect_cane_weight_form_data(self):
        """Collect the current value of every Cane Weight form widget, keyed by field name."""
        form_data = {}
        for field_name, widget in self.form_fields.items():
            if isinstance(widget, QLineEdit):
                value = widget.text().strip()
                form_data[field_name] = value if value != "" else None
            elif isinstance(widget, QComboBox):
                form_data[field_name] = widget.currentText()
            elif isinstance(widget, QSpinBox):
                form_data[field_name] = widget.value()
            elif isinstance(widget, QCheckBox):
                form_data[field_name] = 1 if widget.isChecked() else 0
            elif isinstance(widget, QDateEdit):
                form_data[field_name] = widget.date().toString("yyyy-MM-dd")
            elif isinstance(widget, QTimeEdit):
                form_data[field_name] = widget.time().toString("HH:mm:ss")
            elif isinstance(widget, QDateTimeEdit):
                form_data[field_name] = widget.dateTime().toString("yyyy-MM-dd HH:mm:ss")
        return form_data

    def _build_cane_weight_payload(self, form_data, action_label):
        """Build the Cane Weight DocType payload from collected form data. Returns the
        payload dict, or None (after showing an error dialog) if building failed."""
        try:
            payload = {"doctype": "Cane Weight"}
            now = datetime.now()

            # Basic Information fields
            payload["company"] = form_data.get("company") or ""
            payload["season"] = form_data.get("season") or None
            payload["branch"] = form_data.get("branch") or None
            payload["shift"] = form_data.get("shift") or None
            payload["posting_date"] = form_data.get("posting_date") or None
            payload["posting_time"] = form_data.get("posting_time") or now.strftime("%H:%M:%S")
            payload["season_day"] = int(form_data.get("season_day", 0)) if form_data.get("season_day") else 0
            payload["factory_day"] = int(form_data.get("factory_day", 0)) if form_data.get("factory_day") else 0
            payload["edit"] = form_data.get("edit", 0)
            payload["naming_series"] = form_data.get("naming_series") or ""
            payload["is_sync"] = 0  # Default value for sync status

            # Trip Sheet & Registration fields
            payload["trip_sheet"] = form_data.get("trip_sheet") or ""
            payload["cane_registration"] = form_data.get("cane_registration") or ""
            payload["crop_variety"] = form_data.get("crop_variety") or ""
            payload["route"] = form_data.get("route") or ""
            payload["is_flat_rate"] = form_data.get("is_flat_rate", 0)
            payload["farmer"] = form_data.get("farmer") or ""
            payload["farmer_name"] = form_data.get("farmer_name") or ""
            payload["transporter_contract"] = form_data.get("transporter_contract") or ""
            payload["transporter_name"] = form_data.get("transporter_name") or ""
            payload["harvester_contract"] = form_data.get("harvester_contract") or ""
            payload["harvester_name"] = form_data.get("harvester_name") or ""
            payload["distance"] = int(form_data.get("distance", 0)) if form_data.get("distance") else 0
            payload["token_no"] = form_data.get("token_no") or ""
            payload["crop_type"] = form_data.get("crop_type") or ""
            payload["survey_number"] = form_data.get("survey_number") or ""
            payload["area_in_acrs"] = float(form_data.get("area_in_acrs", 0)) if form_data.get("area_in_acrs") else 0.0
            payload["is_kisan_card"] = form_data.get("is_kisan_card", 0)
            payload["circle_office"] = form_data.get("circle_office") or ""

            # HT Details fields
            payload["transporter"] = form_data.get("transporter") or ""
            payload["transporter_vehicle_type"] = form_data.get("transporter_vehicle_type") or ""
            payload["transporter_gang_type"] = form_data.get("transporter_gang_type") or ""
            payload["harvester"] = form_data.get("harvester") or ""
            payload["harvester_vehicle_type"] = form_data.get("harvester_vehicle_type") or ""
            payload["harvester_gang_type"] = form_data.get("harvester_gang_type") or ""
            payload["vehicle_no"] = form_data.get("vehicle_no") or ""
            payload["trolly_1"] = form_data.get("trolly_1") or ""
            payload["trolly_2"] = form_data.get("trolly_2") or ""
            payload["rope_placement"] = form_data.get("rope_placement") or ""

            # Slip No (from Token & Deduction tab)
            payload["slip_no"] = int(form_data.get("slip_no", 0)) if form_data.get("slip_no") else 0

            # Token Details fields
            payload["auto_token_no"] = form_data.get("auto_token_no") or ""
            payload["token_date"] = form_data.get("token_date") or now.strftime("%Y-%m-%d")
            payload["token_time"] = form_data.get("token_time") or now.strftime("%H:%M:%S")
            payload["token_user"] = form_data.get("token_user") or ""
            payload["slip_boy_name"] = form_data.get("slip_boy_name") or ""

            # Deduction fields
            payload["cane_deduction_type"] = form_data.get("cane_deduction_type") or ""
            payload["deduction"] = float(form_data.get("deduction", 0)) if form_data.get("deduction") else 0.0
            payload["water_share"] = float(form_data.get("water_share", 0)) if form_data.get("water_share") else 0.0
            payload["cane_deduction_weight"] = float(form_data.get("cane_deduction_weight", 0)) if form_data.get("cane_deduction_weight") else 0.0
            payload["water_supplier_weight"] = float(form_data.get("water_supplier_weight", 0)) if form_data.get("water_supplier_weight") else 0.0
            payload["dcp"] = form_data.get("dcp", 0)

            # Weight Information fields
            payload["gross_weight_bridge"] = form_data.get("gross_weight_bridge") or ""
            payload["gross_weight_bridge_user"] = form_data.get("gross_weight_bridge_user") or ""
            payload["gross_weight"] = float(form_data.get("gross_weight", 0)) if form_data.get("gross_weight") else 0.0
            payload["gross_weight_timestamp"] = form_data.get("gross_weight_timestamp") or now.strftime("%Y-%m-%d %H:%M:%S")
            payload["tare_weight_bridge"] = form_data.get("tare_weight_bridge") or ""
            payload["tare_weight_bridge_user"] = form_data.get("tare_weight_bridge_user") or ""
            payload["tare_weight"] = float(form_data.get("tare_weight", 0)) if form_data.get("tare_weight") else 0.0
            payload["tare_weight_timestamp"] = form_data.get("tare_weight_timestamp") or now.strftime("%Y-%m-%d %H:%M:%S")
            payload["binding_weight"] = float(form_data.get("binding_weight", 0)) if form_data.get("binding_weight") else 0.0
            payload["farmer_weight"] = float(form_data.get("farmer_weight", 0)) if form_data.get("farmer_weight") else 0.0
            payload["transporter_weight"] = float(form_data.get("transporter_weight", 0)) if form_data.get("transporter_weight") else 0.0
            payload["harvester_weight"] = float(form_data.get("harvester_weight", 0)) if form_data.get("harvester_weight") else 0.0

            # Fuel fields
            payload["heavy_vehicle_fuel_allowance"] = float(form_data.get("heavy_vehicle_fuel_allowance", 0)) if form_data.get("heavy_vehicle_fuel_allowance") else 0.0
            payload["extra_fuel_allocation"] = float(form_data.get("extra_fuel_allocation", 0)) if form_data.get("extra_fuel_allocation") else 0.0
            payload["diesel_allocation"] = float(form_data.get("diesel_allocation", 0)) if form_data.get("diesel_allocation") else 0.0

            # Local Language (LL) Name fields - Read Only display fields, passed
            # through as-is so the values fetched from the Trip Sheet are persisted.
            for ll_field in (
                "village_ll_name", "route_ll_name", "sub_village_ll_name",
                "circle_office_ll_name", "taluka_ll_name", "district_ll_name",
                "state_ll_name", "crop_type_ll_name", "crop_seed_ll_name",
                "soil_type_ll_name", "seed_type_ll_name", "irrigation_method_ll_name",
                "crop_variety_ll_name", "farmer_ll_name", "transporter_ll_name",
                "cane_deduction_type_ll_name", "rope_placement_ll_name", "harvester_ll_name",
                "ht_driver_ll_name",
            ):
                payload[ll_field] = form_data.get(ll_field) or ""
        except Exception as e:
            error_msg = f"Failed to build form payload: {str(e)}"
            self.output.append(f"[{action_label} Error] {error_msg}")
            import traceback
            traceback_str = traceback.format_exc()
            self.output.append(traceback_str)
            QMessageBox.critical(self, "Form Build Error", f"{error_msg}\n\n{traceback_str}")
            return None

        # Calculate cane_weight/binding_weight/net_weight/transporter_weight/
        # harvester_weight/farmer_weight exactly the way CaneWeight.actual_weight()
        # does server-side (cane_weight.py), so what the operator sees here matches
        # what Save/Submit will actually persist:
        #   cane_weight = gross_weight - tare_weight
        #   binding_weight = cane_weight * (binding_weight_percent / 100)
        #   net_weight = cane_weight - binding_weight
        #   transporter_weight = harvester_weight = farmer_weight = net_weight
        # (binding_weight_percent comes from Get Data - see
        # _populate_cane_weight_form_from_exe_api - not from a stale field value.)
        try:
            gross_weight = payload["gross_weight"]
            tare_weight = payload["tare_weight"]

            if gross_weight > 0 and tare_weight >= 0:
                cane_weight_val = gross_weight - tare_weight
                binding_weight_val = cane_weight_val * (self._cane_weight_binding_percent / 100)
                net_weight_val = cane_weight_val - binding_weight_val

                payload['cane_weight'] = round(cane_weight_val, 3)
                payload['binding_weight'] = round(binding_weight_val, 3)
                payload['net_weight'] = round(net_weight_val, 3)
                payload['transporter_weight'] = payload['net_weight']
                payload['harvester_weight'] = payload['net_weight']
                payload['farmer_weight'] = payload['net_weight']

                # Update UI fields with calculated values
                for field_name in ("cane_weight", "binding_weight", "net_weight",
                                    "transporter_weight", "harvester_weight", "farmer_weight"):
                    widget = self.form_fields.get(field_name)
                    if widget is not None:
                        widget.setText(str(payload[field_name]))
            else:
                for field_name in ("cane_weight", "binding_weight", "net_weight",
                                    "transporter_weight", "harvester_weight", "farmer_weight"):
                    payload[field_name] = 0.0
        except (ValueError, KeyError) as e:
            self.output.append(f"[Warning] Weight calculation error: {e}")
            for field_name in ("cane_weight", "binding_weight", "net_weight",
                                "transporter_weight", "harvester_weight", "farmer_weight"):
                payload[field_name] = 0.0

        # Handle Penalty Charges (child table)
        if "penalty_charges" in self.form_fields:
            penalty_table_widget = self.form_fields["penalty_charges"]
            penalty_items = []
            for row in range(penalty_table_widget.rowCount()):
                # Map header labels to actual DocField names for the "Cane Weight Penalty
                # Charges" child table. Columns are: No., Entity Code, Entity Name,
                # Entity Type, Deduction Type, Deduction Method, Deduction Rate, Debit
                # Account, Credit Account. Deduction Method is a QComboBox cell widget
                # (see _make_penalty_deduction_method_combo), not a QTableWidgetItem.
                temp_row_data = {}
                for col in range(penalty_table_widget.columnCount()):
                    header = penalty_table_widget.horizontalHeaderItem(col).text()
                    if header == "Deduction Method":
                        combo = penalty_table_widget.cellWidget(row, col)
                        value = combo.currentText() if combo else ""
                    else:
                        item = penalty_table_widget.item(row, col)
                        value = item.text() if item else ""

                    if header == "No.":
                        temp_row_data["idx"] = int(value) if value.isdigit() else (row + 1)
                    elif header == "Entity Code":
                        temp_row_data["entity_code"] = value
                    elif header == "Entity Name":
                        temp_row_data["entity_name"] = value
                    elif header == "Entity Type":
                        temp_row_data["entity_type"] = value
                    elif header == "Deduction Type":
                        temp_row_data["deduction_type"] = value
                    elif header == "Deduction Method":
                        temp_row_data["deduction_method"] = value
                    elif header == "Deduction Rate":
                        temp_row_data["deduction_rate"] = float(value) if value and value.replace('.', '', 1).isdigit() else 0.0
                    elif header == "Debit Account":
                        temp_row_data["debit_account"] = value
                    elif header == "Credit Account":
                        temp_row_data["credit_account"] = value

                # A row only counts as real data if it identifies an entity -
                # Deduction Method is a dropdown that's never blank (it defaults
                # to its first option), so it can't be used to detect a blank row.
                if temp_row_data.get("entity_code") or temp_row_data.get("entity_name"):
                    penalty_items.append(temp_row_data)

            if penalty_items:
                payload["penalty_charges"] = penalty_items  # Assuming the fieldname in Cane Weight is 'penalty_charges'

        self.output.append(f"[{action_label}] Payload built with {len(payload)} fields")

        if not payload.get("company") or payload.get("company") == "":
            self.output.append("[Error] Company is required")
            QMessageBox.warning(self, "Warning", "Company field is required!")
            return None

        return payload

    def _cane_weight_action_buttons(self):
        return [
            getattr(self, "cane_weight_submit_btn", None),
            getattr(self, "cane_weight_save_btn", None),
            getattr(self, "cane_weight_clear_btn", None),
        ]

    def _send_cane_weight_payload(self, payload, action_label, clear_after):
        """Send the Cane Weight payload to the dedicated save_cane_weight_form /
        submit_cane_weight_form whitelisted methods. These handle create-vs-update
        entirely server-side (keyed by trip_sheet, not slip_no) - so we no longer need
        (or want) to guess it client-side; that was causing duplicate-entry errors
        when our own lookup missed a document the backend would have found.

        Runs the actual POST on a background QThread (CaneWeightSaveWorker) so
        the UI stays responsive instead of freezing for the duration of the
        request - Submit/Save/Clear are disabled meanwhile so a second click
        can't fire a duplicate request."""
        self.output.append(f"[{action_label}] Preparing to send to Frappe...")
        self.output.append(f"[{action_label}] company: {payload.get('company')}, farmer: {payload.get('farmer')}, trip_sheet: {payload.get('trip_sheet')}")

        # doctype/name/docstatus are managed by the backend method itself - don't send
        # them as part of `data`, doc.update(data) would try to set them directly.
        send_payload = {k: v for k, v in payload.items() if k not in ("doctype", "name", "docstatus")}

        method_name = "submit_cane_weight_form" if action_label == "Submit" else "save_cane_weight_form"
        url = f"{self.primary_frappe_site_url}/api/method/quantbit_agriculture_crm.exe_api.{method_name}"

        for btn in self._cane_weight_action_buttons():
            if btn is not None:
                btn.setEnabled(False)
        busy_btn = self.cane_weight_submit_btn if action_label == "Submit" else self.cane_weight_save_btn
        busy_btn.setText("Submitting..." if action_label == "Submit" else "Saving...")

        worker = CaneWeightSaveWorker(self.primary_frappe_session, url, send_payload)
        self._cane_weight_save_worker = worker  # keep a reference alive until it finishes
        # Qt.QueuedConnection is required here: these signals are emitted from
        # the worker thread, but the slots touch widgets/QMessageBox and must
        # run on the main GUI thread. Connecting to a plain lambda (rather
        # than a bound Qt slot) makes Qt unable to infer that on its own and
        # it would otherwise run the slot directly on the worker thread.
        worker.finished_ok.connect(
            lambda result: self._on_cane_weight_send_ok(result, action_label, clear_after, send_payload),
            Qt.QueuedConnection,
        )
        worker.finished_error.connect(
            lambda error_msg: self._on_cane_weight_send_error(error_msg, action_label),
            Qt.QueuedConnection,
        )
        worker.start()

    def _reset_cane_weight_action_buttons(self):
        for btn in self._cane_weight_action_buttons():
            if btn is not None:
                btn.setEnabled(True)
        self.cane_weight_submit_btn.setText("Submit Form")
        self.cane_weight_save_btn.setText("Save Form")

    def _on_cane_weight_send_ok(self, result, action_label, clear_after, send_payload):
        self._reset_cane_weight_action_buttons()
        result_data = result.get("message") or {}

        if not result_data.get("success"):
            error_msg = result_data.get("error") or "Unknown error"
            self.output.append(f"[Frappe Error] {error_msg}")
            QMessageBox.critical(self, "Failed", f"Failed to send to Frappe:\n\n{error_msg}")
            return

        doc_name = (result_data.get("data") or {}).get("name", "Unknown")
        status_text = result_data.get("message", "Cane Weight saved")
        self.output.append(f"[Frappe] {status_text} (Name: {doc_name})")
        QMessageBox.information(self, "Success", f"{status_text}\n\nName: {doc_name}")

        # Optionally send form data over serial
        data_str = json.dumps(send_payload)
        if self.connected and self.reader:
            self.reader.send_data(data_str)
            self.output.append(f"[Sent Form Data via Serial] {data_str}")

        if clear_after:
            self.current_cane_weight_doc = None
            self.clear_form()
        else:
            # Remember this doc so we can show/track it if needed - the backend no
            # longer needs it from us though, it always looks up by trip_sheet itself.
            self.current_cane_weight_doc = {"name": doc_name}

    def _on_cane_weight_send_error(self, error_msg, action_label):
        self._reset_cane_weight_action_buttons()
        self.output.append(f"[Frappe Error] {error_msg}")
        QMessageBox.critical(self, "Failed", f"Failed to send to Frappe:\n\n{error_msg}")

    def submit_form(self):
        """Submit Cane Weight form to Frappe (creates a new entry as submitted, or finalizes one
        already loaded for editing). Does not clear the form - use the Clear Form button for that."""
        self.output.append("[Submit] Submit button clicked - starting form submission...")
        self._default_weight_bridge_users()  # ensure Gross/Tare Weight Bridge User is never blank

        form_data = self._collect_cane_weight_form_data()
        self.output.append(f"[Submit] Collected data from {len(form_data)} form fields")

        payload = self._build_cane_weight_payload(form_data, "Submit")
        if payload is None:
            return

        # Always set docstatus=1 to submit the document (both for new and existing docs)
        payload["docstatus"] = 1

        self._send_cane_weight_payload(payload, "Submit", clear_after=False)

    def save_form(self):
        """Save Form: creates (or updates) a Cane Weight entry in Frappe as a draft.
        Does not clear the form - use the Clear Form button for that."""
        self.output.append("[Save] Save button clicked - saving entry to Frappe...")
        self._default_weight_bridge_users()  # ensure Gross/Tare Weight Bridge User is never blank

        form_data = self._collect_cane_weight_form_data()
        self.output.append(f"[Save] Collected data from {len(form_data)} form fields")

        payload = self._build_cane_weight_payload(form_data, "Save")
        if payload is None:
            return

        payload["docstatus"] = 0  # Save always keeps the entry a draft

        self._send_cane_weight_payload(payload, "Save", clear_after=False)

    def clear_form(self):
        for field_name, widget in self.form_fields.items():
            if isinstance(widget, QLineEdit):
                widget.clear()
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(0)
            elif isinstance(widget, QSpinBox):
                widget.setValue(0)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(True)
            elif isinstance(widget, QDateEdit):
                widget.setDate(datetime.now().date())
            elif isinstance(widget, QDateTimeEdit):
                widget.setDateTime(datetime.now())
            elif isinstance(widget, QTableWidget):
                for row in range(widget.rowCount()):
                    for col in range(widget.columnCount()):
                        widget.setItem(row, col, QTableWidgetItem(""))
        self.slip_no_combo.clear()
        # setCurrentIndex(0) above resets Branch to its first combo item
        # ("Bedkihal") rather than the required default - put it back to Kundal.
        self.form_fields["branch"].setCurrentText("Kundal")
        self._refresh_posting_datetime_now()  # posting_date/time always live, not blank
        self._default_weight_bridge_users()  # weight bridge users default to logged-in user
        # New truck, no weight captured yet - Gross/Tare Weight Timestamp go back to live-ticking
        self._gross_weight_captured = False
        self._tare_weight_captured = False
        # New trip sheet's vehicle type hasn't been fetched yet - back to the default
        # until the next Get Data call sets it (see _build_cane_weight_payload).
        self._cane_weight_binding_percent = 1
        self._base_diesel_allocation = 0.0
        # QMessageBox.information(self, "Success", "Form cleared!")
    
    def add_fuel_sale_item_row(self):
        """Add a new row to the fuel sale items table."""
        row_count = self.fuel_sale_items_table.rowCount()
        self.fuel_sale_items_table.insertRow(row_count)
        
        # Set default values for new row
        self.fuel_sale_items_table.setItem(row_count, 0, QTableWidgetItem(""))
        self.fuel_sale_items_table.setItem(row_count, 1, QTableWidgetItem(""))
        self.fuel_sale_items_table.setItem(row_count, 2, QTableWidgetItem("0"))
        self.fuel_sale_items_table.setItem(row_count, 3, QTableWidgetItem("0"))
        self.fuel_sale_items_table.setItem(row_count, 4, QTableWidgetItem("Stores - QSPL"))
        self.fuel_sale_items_table.setItem(row_count, 5, QTableWidgetItem("0"))
        self.fuel_sale_items_table.setItem(row_count, 6, QTableWidgetItem("Litre"))
        self.fuel_sale_items_table.setItem(row_count, 7, QTableWidgetItem("0"))
        self.fuel_sale_items_table.setItem(row_count, 8, QTableWidgetItem("5111 - Cost of Goods Sold - QSPL"))
        self.fuel_sale_items_table.setItem(row_count, 9, QTableWidgetItem("4110 - Sales - QSPL"))
    
    def remove_fuel_sale_item_row(self):
        """Remove the selected row from the fuel sale items table."""
        current_row = self.fuel_sale_items_table.currentRow()
        if current_row >= 0:
            self.fuel_sale_items_table.removeRow(current_row)
        else:
            QMessageBox.warning(self, "Warning", "Please select a row to remove.")
    
    def submit_fuel_sale_form(self):
        """Submit the fuel sale form data."""
        try:
            # Collect form data
            fuel_sale_data = {
                "doctype": "Fuel Sale",
                "naming_series": "FS-",
                "fuel_ledger_entry_created": 0,
                "status": "Not Issued",
                "company": "Quantbit Sugar Pvt Ltd",
                "season": self.fuel_sale_fields["season"].currentText(),
                "branch": self.fuel_sale_fields["branch"].currentText(),
                "shift_type": self.fuel_sale_fields["shift_type"].currentText(),
                "posting_date": self.fuel_sale_fields["posting_date"].date().toString("yyyy-MM-dd"),
                "edit_posting_date_and_time": 1 if self.fuel_sale_fields["edit_posting_date_and_time"].isChecked() else 0,
                "posting_time": self.fuel_sale_fields["posting_time"].time().toString("HH:mm:ss"),
                "fuel_sale_type": self.fuel_sale_fields["fuel_sale_type"].currentText(),
                "contract": self.fuel_sale_fields["contract"].currentText(),
                "entity_type": self.fuel_sale_fields["entity_type"].currentText(),
                "party": self.fuel_sale_fields["party"].text(),
                "party_name": self.fuel_sale_fields["party_name"].text(),
                "is_extra_fuel": 1 if self.fuel_sale_fields["is_extra_fuel"].isChecked() else 0,
                "is_returned": 1 if self.fuel_sale_fields["is_returned"].isChecked() else 0,
                "debit_account": self.fuel_sale_fields["debit_account"].currentText(),
                "currency": self.fuel_sale_fields["currency"].currentText(),
                "total_quantity": self.fuel_sale_fields["total_quantity"].value(),
                "total_amount": self.fuel_sale_fields["total_amount"].value(),
                "total_amount_in_words": self.fuel_sale_fields["total_amount_in_words"].text(),
                "fuel_sale_item": []
            }
            
            # Collect items data
            for row in range(self.fuel_sale_items_table.rowCount()):
                item_data = {
                    "doctype": "Fuel Sale Item",
                    "item_code": self.fuel_sale_items_table.item(row, 0).text() if self.fuel_sale_items_table.item(row, 0) else "",
                    "item_name": self.fuel_sale_items_table.item(row, 1).text() if self.fuel_sale_items_table.item(row, 1) else "",
                    "quantity": float(self.fuel_sale_items_table.item(row, 2).text()) if self.fuel_sale_items_table.item(row, 2) and self.fuel_sale_items_table.item(row, 2).text() else 0,
                    "amount": float(self.fuel_sale_items_table.item(row, 3).text()) if self.fuel_sale_items_table.item(row, 3) and self.fuel_sale_items_table.item(row, 3).text() else 0,
                    "warehouse": self.fuel_sale_items_table.item(row, 4).text() if self.fuel_sale_items_table.item(row, 4) else "",
                    "allocated_quantity": float(self.fuel_sale_items_table.item(row, 5).text()) if self.fuel_sale_items_table.item(row, 5) and self.fuel_sale_items_table.item(row, 5).text() else 0,
                    "uom": self.fuel_sale_items_table.item(row, 6).text() if self.fuel_sale_items_table.item(row, 6) else "",
                    "rate": float(self.fuel_sale_items_table.item(row, 7).text()) if self.fuel_sale_items_table.item(row, 7) and self.fuel_sale_items_table.item(row, 7).text() else 0,
                    "expense_account": self.fuel_sale_items_table.item(row, 8).text() if self.fuel_sale_items_table.item(row, 8) else "",
                    "income_account": self.fuel_sale_items_table.item(row, 9).text() if self.fuel_sale_items_table.item(row, 9) else ""
                }
                fuel_sale_data["fuel_sale_item"].append(item_data)
            
            # Submit to Frappe
            if self.primary_frappe_logged_in:
                response = self.primary_frappe_session.post(
                    f"{self.primary_frappe_site_url}/api/resource/Fuel Sale",
                    json=fuel_sale_data
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("data"):
                        QMessageBox.information(self, "Success", f"Fuel Sale submitted successfully! Document: {result['data']['name']}")
                        self.output.append(f"[Fuel Sale] Submitted successfully: {result['data']['name']}")
                    else:
                        QMessageBox.warning(self, "Warning", "Fuel Sale submission failed. Check the response.")
                        self.output.append(f"[Fuel Sale Error] Submission failed: {result}")
                else:
                    QMessageBox.critical(self, "Error", f"Failed to submit Fuel Sale. Status: {response.status_code}")
                    self.output.append(f"[Fuel Sale Error] HTTP {response.status_code}: {response.text}")
            else:
                QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance!")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error submitting Fuel Sale: {str(e)}")
            self.output.append(f"[Fuel Sale Error] Exception: {str(e)}")
    
    def save_fuel_sale_form(self):
        """Save the fuel sale form data (draft)."""
        try:
            # Similar to submit but with docstatus = 0 (draft)
            fuel_sale_data = {
                "doctype": "Fuel Sale",
                "naming_series": "FS-",
                "fuel_ledger_entry_created": 0,
                "status": "Draft",
                "docstatus": 1,
                "company": "Quantbit Sugar Pvt Ltd",
                "season": self.fuel_sale_fields["season"].currentText(),
                "branch": self.fuel_sale_fields["branch"].currentText(),
                "shift_type": self.fuel_sale_fields["shift_type"].currentText(),
                "posting_date": self.fuel_sale_fields["posting_date"].date().toString("yyyy-MM-dd"),
                "edit_posting_date_and_time": 1 if self.fuel_sale_fields["edit_posting_date_and_time"].isChecked() else 0,
                "posting_time": self.fuel_sale_fields["posting_time"].time().toString("HH:mm:ss"),
                "fuel_sale_type": self.fuel_sale_fields["fuel_sale_type"].currentText(),
                "contract": self.fuel_sale_fields["contract"].currentText(),
                "entity_type": self.fuel_sale_fields["entity_type"].currentText(),
                "party": self.fuel_sale_fields["party"].text(),
                "party_name": self.fuel_sale_fields["party_name"].text(),
                "is_extra_fuel": 1 if self.fuel_sale_fields["is_extra_fuel"].isChecked() else 0,
                "is_returned": 1 if self.fuel_sale_fields["is_returned"].isChecked() else 0,
                "debit_account": self.fuel_sale_fields["debit_account"].currentText(),
                "currency": self.fuel_sale_fields["currency"].currentText(),
                "total_quantity": self.fuel_sale_fields["total_quantity"].value(),
                "total_amount": self.fuel_sale_fields["total_amount"].value(),
                "total_amount_in_words": self.fuel_sale_fields["total_amount_in_words"].text(),
                "fuel_sale_item": []
            }
            
            # Collect items data (same as submit)
            for row in range(self.fuel_sale_items_table.rowCount()):
                item_data = {
                    "doctype": "Fuel Sale Item",
                    "item_code": self.fuel_sale_items_table.item(row, 0).text() if self.fuel_sale_items_table.item(row, 0) else "",
                    "item_name": self.fuel_sale_items_table.item(row, 1).text() if self.fuel_sale_items_table.item(row, 1) else "",
                    "quantity": float(self.fuel_sale_items_table.item(row, 2).text()) if self.fuel_sale_items_table.item(row, 2) and self.fuel_sale_items_table.item(row, 2).text() else 0,
                    "amount": float(self.fuel_sale_items_table.item(row, 3).text()) if self.fuel_sale_items_table.item(row, 3) and self.fuel_sale_items_table.item(row, 3).text() else 0,
                    "warehouse": self.fuel_sale_items_table.item(row, 4).text() if self.fuel_sale_items_table.item(row, 4) else "",
                    "allocated_quantity": float(self.fuel_sale_items_table.item(row, 5).text()) if self.fuel_sale_items_table.item(row, 5) and self.fuel_sale_items_table.item(row, 5).text() else 0,
                    "uom": self.fuel_sale_items_table.item(row, 6).text() if self.fuel_sale_items_table.item(row, 6) else "",
                    "rate": float(self.fuel_sale_items_table.item(row, 7).text()) if self.fuel_sale_items_table.item(row, 7) and self.fuel_sale_items_table.item(row, 7).text() else 0,
                    "expense_account": self.fuel_sale_items_table.item(row, 8).text() if self.fuel_sale_items_table.item(row, 8) else "",
                    "income_account": self.fuel_sale_items_table.item(row, 9).text() if self.fuel_sale_items_table.item(row, 9) else ""
                }
                fuel_sale_data["fuel_sale_item"].append(item_data)
            
            # Save to Frappe
            if self.primary_frappe_logged_in:
                response = self.primary_frappe_session.post(
                    f"{self.primary_frappe_site_url}/api/resource/Fuel Sale",
                    json=fuel_sale_data
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("data"):
                        QMessageBox.information(self, "Success", f"Fuel Sale saved as draft! Document: {result['data']['name']}")
                        self.output.append(f"[Fuel Sale] Saved as draft: {result['data']['name']}")
                    else:
                        QMessageBox.warning(self, "Warning", "Fuel Sale save failed. Check the response.")
                        self.output.append(f"[Fuel Sale Error] Save failed: {result}")
                else:
                    QMessageBox.critical(self, "Error", f"Failed to save Fuel Sale. Status: {response.status_code}")
                    self.output.append(f"[Fuel Sale Error] HTTP {response.status_code}: {response.text}")
            else:
                QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance!")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error saving Fuel Sale: {str(e)}")
            self.output.append(f"[Fuel Sale Error] Exception: {str(e)}")
    
    def clear_fuel_sale_form(self):
        """Clear all fuel sale form fields."""
        for field_name, widget in self.fuel_sale_fields.items():
            if isinstance(widget, QLineEdit):
                widget.clear()
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(0)
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(0)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(False)
            elif isinstance(widget, QDateEdit):
                widget.setDate(datetime.now().date())
            elif isinstance(widget, QTimeEdit):
                widget.setTime(datetime.now().time())

        # setCurrentIndex(0) above resets Branch to whatever combo item
        # happens to be first from the API load - put it back to Kundal.
        branch_combo = self.fuel_sale_fields.get("branch")
        if branch_combo is not None:
            index = branch_combo.findText("Kundal")
            if index >= 0:
                branch_combo.setCurrentIndex(index)

        # Clear the items table
        self.fuel_sale_items_table.setRowCount(0)
        self.add_fuel_sale_item_row()  # Add one empty row
        
        # QMessageBox.information(self, "Success", "Fuel Sale form cleared!")
        self.current_fuel_sale_doc = None

    def fetch_branches_for_fuel_sale(self):
        """Fetch Branch list from Trip Sheet ERP using token auth and populate fuel sale branch combo."""
        try:
            # Endpoint of the whitelisted method
            url = f"{self.trip_sheet_api_base}/api/method/quantbit_agriculture_crm.agriculture_utils.get_branches"

            headers = {
                "Authorization": f"token {self.trip_sheet_api_key}:{self.trip_sheet_api_secret}",
                "Accept": "application/json",
            }

            # We use a plain requests call separate from session login
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            result = response.json()

            # Frappe convention: result may be in message or data
            branches = []
            if isinstance(result, dict):
                if "message" in result and isinstance(result["message"], list):
                    branches = result["message"]
                elif "data" in result and isinstance(result["data"], list):
                    branches = result["data"]

            combo: QComboBox = self.fuel_sale_fields.get("branch")
            if not combo:
                return

            combo.blockSignals(True)
            combo.clear()
            if branches:
                for name in self._to_list(branches):
                    # accept either dict with name or plain string
                    if isinstance(name, dict):
                        label = name.get("name") or name.get("branch") or str(name)
                    else:
                        label = str(name)
                    combo.addItem(label)
                # Optionally set a default if present
                index = combo.findText("Kundal")
                combo.setCurrentIndex(index if index >= 0 else 0)
                self.output.append(f"[Fuel Sale] Loaded {len(branches)} branches from Trip Sheet ERP.")
            else:
                combo.addItem("No branches found")
                self.output.append("[Fuel Sale] No branches returned by API.")
            combo.blockSignals(False)

        except requests.exceptions.HTTPError as e:
            self.output.append(f"[Fuel Sale Branches] HTTP {e.response.status_code}: {e.response.text}")
        except requests.exceptions.RequestException as e:
            self.output.append(f"[Fuel Sale Branches] Network error: {str(e)}")
        except Exception as e:
            self.output.append(f"[Fuel Sale Branches] Unexpected error: {str(e)}")

    def update_fuel_sale_shift_from_server(self):
        """Call server method to resolve shift from posting_time and set in UI (Fuel Sale)."""
        try:
            posting_time_widget: QTimeEdit = self.fuel_sale_fields.get("posting_time")
            shift_widget: QComboBox = self.fuel_sale_fields.get("shift_type")
            if not posting_time_widget or not shift_widget:
                return

            posting_time_str = posting_time_widget.time().toString("HH:mm:ss")

            # Assuming a whitelisted method exposed similarly to get_branches
            # If the method is bound to a DocType, you can create a generic endpoint
            url = f"{self.trip_sheet_api_base}/api/method/quantbit_agriculture_crm.agriculture_utils.get_shift_type"

            headers = {
                "Authorization": f"token {self.trip_sheet_api_key}:{self.trip_sheet_api_secret}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            # Send posting_time as argument; frappe allows args via query or JSON
            payload = {"posting_time": posting_time_str}
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            response.raise_for_status()
            result = response.json()

            # Value can be in message
            shift_name = None
            if isinstance(result, dict):
                shift_name = result.get("message") or (result.get("data") if isinstance(result.get("data"), str) else None)

            if shift_name:
                # Update combo to this shift if present; if not present, add
                idx = shift_widget.findText(str(shift_name))
                if idx < 0:
                    shift_widget.addItem(str(shift_name))
                    idx = shift_widget.findText(str(shift_name))
                if idx >= 0:
                    shift_widget.setCurrentIndex(idx)
                self.output.append(f"[Fuel Sale] Shift resolved to: {shift_name}")
            else:
                self.output.append("[Fuel Sale] Shift not resolved by server method.")

        except requests.exceptions.HTTPError as e:
            self.output.append(f"[Fuel Sale Shift] HTTP {e.response.status_code}: {e.response.text}")
        except requests.exceptions.RequestException as e:
            self.output.append(f"[Fuel Sale Shift] Network error: {str(e)}")
        except Exception as e:
            self.output.append(f"[Fuel Sale Shift] Unexpected error: {str(e)}")

    def _token_headers(self):
        return {
            "Authorization": f"token {self.trip_sheet_api_key}:{self.trip_sheet_api_secret}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _to_list(self, data):
        if data is None:
            return []
        if isinstance(data, list):
            return data
        return [data]

    def fetch_fuel_sale_types(self):
        try:
            url = f"{self.trip_sheet_api_base}/api/method/quantbit_agriculture_crm.agriculture_utils.get_fuel_sale_types"
            response = requests.get(url, headers=self._token_headers(), timeout=15)
            response.raise_for_status()
            result = response.json()
            items = self._to_list(result.get("message") or result.get("data"))
            combo: QComboBox = self.fuel_sale_fields.get("fuel_sale_type")
            if not combo:
                return
            combo.blockSignals(True)
            combo.clear()
            if items:
                for row in items:
                    label = row.get("name") if isinstance(row, dict) else str(row)
                    combo.addItem(label)
                # After loading, trigger fetch for current selection
                current = combo.currentText()
                combo.blockSignals(False)
                self.on_fuel_sale_type_changed(current)
            else:
                combo.addItem("No fuel sale types")
            if combo.signalsBlocked():
                combo.blockSignals(False)
        except Exception as e:
            self.output.append(f"[Fuel Sale Types] Error: {str(e)}")

    def fetch_contracts_for_fuel_sale(self):
        try:
            url = f"{self.trip_sheet_api_base}/api/method/quantbit_agriculture_crm.agriculture_utils.get_contracts"
            response = requests.get(url, headers=self._token_headers(), timeout=15)
            response.raise_for_status()
            result = response.json()
            items = result.get("message") or result.get("data") or []
            combo: QComboBox = self.fuel_sale_fields.get("contract")
            if not combo:
                return
            combo.blockSignals(True)
            combo.clear()
            if items:
                for row in items:
                    label = row.get("name") if isinstance(row, dict) else str(row)
                    combo.addItem(label)
            else:
                combo.addItem("No contracts")
            combo.blockSignals(False)
        except Exception as e:
            self.output.append(f"[Fuel Sale Contracts] Error: {str(e)}")

    def fetch_entity_types_for_fuel_sale(self):
        try:
            url = f"{self.trip_sheet_api_base}/api/method/quantbit_agriculture_crm.agriculture_utils.get_entity_types"
            response = requests.get(url, headers=self._token_headers(), timeout=15)
            response.raise_for_status()
            result = response.json()
            items = result.get("message") or result.get("data") or []
            combo: QComboBox = self.fuel_sale_fields.get("entity_type")
            if not combo:
                return
            combo.blockSignals(True)
            combo.clear()
            if items:
                for row in items:
                    label = row.get("name") if isinstance(row, dict) else str(row)
                    combo.addItem(label)
            else:
                combo.addItem("No entity types")
            combo.blockSignals(False)
        except Exception as e:
            self.output.append(f"[Fuel Sale Entity Types] Error: {str(e)}")

    def fetch_accounts_for_fuel_sale(self):
        try:
            # Company is fixed per sample data; could be tied to user selection
            company = "Quantbit Sugar Pvt Ltd"
            url = f"{self.trip_sheet_api_base}/api/method/quantbit_agriculture_crm.agriculture_utils.get_accounts_data"
            params = {"company": company}
            response = requests.get(url, headers=self._token_headers(), params=params, timeout=15)
            response.raise_for_status()
            result = response.json()
            items = self._to_list(result.get("message") or result.get("data"))
            combo: QComboBox = self.fuel_sale_fields.get("debit_account")
            if not combo:
                return
            combo.blockSignals(True)
            combo.clear()
            if items:
                for row in items:
                    label = row.get("name") if isinstance(row, dict) else str(row)
                    combo.addItem(label)
            else:
                combo.addItem("No accounts")
            combo.blockSignals(False)
        except Exception as e:
            self.output.append(f"[Fuel Sale Accounts] Error: {str(e)}")

    def on_fuel_sale_type_changed(self, type_name: str):
        # Ignore placeholder text
        if not type_name or type_name.lower().startswith("loading") or type_name.lower().startswith("no "):
            return
        self.output.append(f"[Fuel Sale] Fuel sale type changed to '{type_name}', fetching items...")
        QTimer.singleShot(10, lambda: self.fetch_items_for_fuel_sale_type(type_name))

    def fetch_items_for_fuel_sale_type(self, type_name: str):
        """Fetch items/config for selected fuel sale type and populate items table and debit account."""
        try:
            url = f"{self.trip_sheet_api_base}/api/method/quantbit_agriculture_crm.agriculture_utils.get_item_codes_from_fuel_sale_type"
            url1 =f"{self.trip_sheet_api_base}/api/method/quantbit_agriculture_crm.agriculture_utils.get_alloted_fuel_from_ledger"
            payload = {"name": type_name}  # Changed from 'fuel_sale_type' to 'name'            # First try JSON body
            payload1={"company": "Quantbit Sugar Pvt Ltd","season": self.fuel_sale_fields["season"].currentText(),"branch": self.fuel_sale_fields["branch"].currentText(),"contract": self.fuel_sale_fields["contract"].currentText(),"fuel_sale_type": type_name} # Changed from 'fuel_sale_type' to 'name'            # First try JSON body
            self.output.append(f"[Fuel Sale Items] Payload1: {payload1}")
            response = requests.post(url, headers=self._token_headers(), json=payload, timeout=20)
            response.raise_for_status()
            result = response.json()
            response1 = requests.post(url1, headers=self._token_headers(), json=payload1, timeout=20)

            result1 = response1.json()
            response1.raise_for_status()
            rows = self._to_list(result.get("message") or result.get("data"))
            rows1 = self._to_list(result1.get("message") or result1.get("data"))
            self.output.append(f"[Fuel Sale Items] Rows1 response: {rows1}")
            # If empty, try GET with params as some frappe methods read from query/form dict
            if not rows:
                response = requests.get(url, headers=self._token_headers(), params=payload, timeout=20)
                response.raise_for_status()
                result = response.json()
                rows = self._to_list(result.get("message") or result.get("data"))

            # Determine allocated quantity source
            default_allocated_quantity = "0"
            allocated_qty_map = {}
            if len(rows1) == 1 and isinstance(rows1[0], (int, float)):
                default_allocated_quantity = str(rows1[0])
            else:
                # Create a dictionary for quick lookup of allocated quantities by item_code
                allocated_qty_map = {r1.get("item_code"): r1.get("allocated_quantity", "0") for r1 in rows1 if isinstance(r1, dict) and r1.get("item_code")}

            # Clear table and repopulate
            self.fuel_sale_items_table.setRowCount(0)

            debit_account_from_type = None
            total_qty = 0.0
            total_amt = 0.0
            for idx, r in enumerate(rows):
                if not isinstance(r, dict):
                    self.output.append(f"[Fuel Sale Items] Skipping unexpected item format: {r}")
                    continue

                self.fuel_sale_items_table.insertRow(idx)
                # Expected keys from SQL: debit_account, item_code, item_name, item_group, price_list_rate,
                # default_uom, default_warehouse, default_expense_account, default_income_account
                item_code = str(r.get("item_code", ""))
                self.fuel_sale_items_table.setItem(idx, 0, QTableWidgetItem(item_code))
                self.fuel_sale_items_table.setItem(idx, 1, QTableWidgetItem(str(r.get("item_name", ""))))
                qty_val = 1.0  # default quantity 1
                self.fuel_sale_items_table.setItem(idx, 2, QTableWidgetItem(str(qty_val)))
                rate = float(r.get("price_list_rate", 0) or 0)
                amt = rate * qty_val
                self.fuel_sale_items_table.setItem(idx, 3, QTableWidgetItem(str(amt)))
                self.fuel_sale_items_table.setItem(idx, 4, QTableWidgetItem(str(r.get("default_warehouse", ""))))
                allocated_quantity = allocated_qty_map.get(item_code, default_allocated_quantity)  # Lookup using the map or default
                self.fuel_sale_items_table.setItem(idx, 5, QTableWidgetItem(str(allocated_quantity)))
                self.fuel_sale_items_table.setItem(idx, 6, QTableWidgetItem(str(r.get("default_uom", "Litre"))))
                self.fuel_sale_items_table.setItem(idx, 7, QTableWidgetItem(str(rate)))
                self.fuel_sale_items_table.setItem(idx, 8, QTableWidgetItem(str(r.get("default_expense_account", ""))))
                self.fuel_sale_items_table.setItem(idx, 9, QTableWidgetItem(str(r.get("default_income_account", ""))))

                if not debit_account_from_type and r.get("debit_account"):
                    debit_account_from_type = r.get("debit_account")

                total_qty += qty_val
                total_amt += amt

            # Set debit account combo to suggested debit_account from type if present
            if debit_account_from_type:
                debit_combo: QComboBox = self.fuel_sale_fields.get("debit_account")
                if debit_combo:
                    found = debit_combo.findText(debit_account_from_type)
                    if found < 0:
                        debit_combo.addItem(debit_account_from_type)
                        found = debit_combo.findText(debit_account_from_type)
                    if found >= 0:
                        debit_combo.setCurrentIndex(found)

            # Update totals in UI
            tq = self.fuel_sale_fields.get("total_quantity")
            ta = self.fuel_sale_fields.get("total_amount")
            if isinstance(tq, QDoubleSpinBox):
                tq.setValue(total_qty)
            if isinstance(ta, QDoubleSpinBox):
                ta.setValue(total_amt)

            self.output.append(f"[Fuel Sale] Loaded {len(rows)} items for type '{type_name}'.")

        except requests.exceptions.HTTPError as e:
            self.output.append(f"[Fuel Sale Items] HTTP {e.response.status_code}: {e.response.text}")
        except requests.exceptions.RequestException as e:
            self.output.append(f"[Fuel Sale Items] Network error: {str(e)}")
        except Exception as e:
            self.output.append(f"[Fuel Sale Items] Unexpected error: {str(e)}")

    def add_auto_token_trip_sheet_row(self):
        """Add a new row to the auto token trip sheet table."""
        row_count = self.auto_token_trip_sheet_table.rowCount()
        self.auto_token_trip_sheet_table.insertRow(row_count)
        
        # Add checkbox for select column
        select_checkbox = QCheckBox()
        select_checkbox.setChecked(True)
        select_checkbox.stateChanged.connect(self.update_no_of_tripsheet_count) # Connect for new rows
        self.auto_token_trip_sheet_table.setCellWidget(row_count, 0, select_checkbox)
        
        # Add sample data based on the JSON
        self.auto_token_trip_sheet_table.setItem(row_count, 1, QTableWidgetItem("2025-2026"))  # Season
        self.auto_token_trip_sheet_table.setItem(row_count, 2, QTableWidgetItem("Ahilyanagar"))  # Branch
        self.auto_token_trip_sheet_table.setItem(row_count, 3, QTableWidgetItem("2025-09-30"))  # Posting Date
        self.auto_token_trip_sheet_table.setItem(row_count, 4, QTableWidgetItem("TS/2526/00012"))  # Trip Sheet No
        self.auto_token_trip_sheet_table.setItem(row_count, 5, QTableWidgetItem("All"))  # Rope Placement
        self.auto_token_trip_sheet_table.setItem(row_count, 6, QTableWidgetItem("C00264"))  # Cane Registration
        self.auto_token_trip_sheet_table.setItem(row_count, 7, QTableWidgetItem("Atpadi"))  # Route
        self.auto_token_trip_sheet_table.setItem(row_count, 8, QTableWidgetItem("123"))  # Area in Acrs
        self.auto_token_trip_sheet_table.setItem(row_count, 9, QTableWidgetItem("E00128"))  # Farmer
        self.auto_token_trip_sheet_table.setItem(row_count, 10, QTableWidgetItem("51"))  # Distance
        self.auto_token_trip_sheet_table.setItem(row_count, 11, QTableWidgetItem("HTC00002"))  # Transporter Contract
        self.auto_token_trip_sheet_table.setItem(row_count, 12, QTableWidgetItem("E00002"))  # Transporter

    def update_no_of_tripsheet_count(self):
        """Updates the 'No of Trip Sheet' field with the count of selected rows in the table."""
        selected_count = 0
        for row in range(self.auto_token_trip_sheet_table.rowCount()):
            select_checkbox = self.auto_token_trip_sheet_table.cellWidget(row, 0)
            if select_checkbox and select_checkbox.isChecked():
                selected_count += 1
        self.auto_token_fields["no_of_tripsheet"].setValue(selected_count)

    def submit_auto_token_form(self):
        """Submit the auto token form data."""
        try:
            # Collect form data
            auto_token_data = {
                "doctype": "Auto Token",
                "season": self.auto_token_fields["season"].currentText(),
                "branch": self.auto_token_fields["branch"].currentText(),
                "posting_date": self.auto_token_fields["posting_date"].date().toString("yyyy-MM-dd"),
                "posting_time": self.auto_token_fields["posting_time"].time().toString("HH:mm:ss"),
                "shift": self.auto_token_fields["shift"].currentText(),
                "edit": 1 if self.auto_token_fields["edit"].isChecked() else 0,
                "season_day": self.auto_token_fields["season_day"].value(),
                "token_no": self.auto_token_fields["token_no"].text(),
                "factory_day": self.auto_token_fields["factory_day"].value(),
                "transporter_contract": self.auto_token_fields["transporter_contract"].currentText(),
                "transporter": self.auto_token_fields["transporter"].text(),
                "transporter_name": self.auto_token_fields["transporter_name"].text(),
                "vehicle_no": self.auto_token_fields["vehicle_no"].text(),
                "transporter_vehicle_type": self.auto_token_fields["transporter_vehicle_type"].currentText(),
                "transporter_gang_type": self.auto_token_fields["transporter_gang_type"].text(),
                "no_of_tripsheet": self.auto_token_fields["no_of_tripsheet"].value(),
                "company": "Quantbit Sugar Pvt Ltd",
                "auto_token_trip_sheet_table": []
            }
            
            # Collect trip sheet details data
            for row in range(self.auto_token_trip_sheet_table.rowCount()):
                select_checkbox = self.auto_token_trip_sheet_table.cellWidget(row, 0)
                if select_checkbox and select_checkbox.isChecked():
                    trip_sheet_data = {
                        "doctype": "Auto Token Trip sheet Details",
                        "select": 1,
                        "season": self.auto_token_trip_sheet_table.item(row, 1).text() if self.auto_token_trip_sheet_table.item(row, 1) else "",
                        "branch": self.auto_token_trip_sheet_table.item(row, 2).text() if self.auto_token_trip_sheet_table.item(row, 2) else "",
                        "posting_date": self.auto_token_trip_sheet_table.item(row, 3).text() if self.auto_token_trip_sheet_table.item(row, 3) else "",
                        "trip_sheet_no": self.auto_token_trip_sheet_table.item(row, 4).text() if self.auto_token_trip_sheet_table.item(row, 4) else "",
                        "rope_placement": self.auto_token_trip_sheet_table.item(row, 5).text() if self.auto_token_trip_sheet_table.item(row, 5) else "",
                        "cane_registration": self.auto_token_trip_sheet_table.item(row, 6).text() if self.auto_token_trip_sheet_table.item(row, 6) else "",
                        "route": self.auto_token_trip_sheet_table.item(row, 7).text() if self.auto_token_trip_sheet_table.item(row, 7) else "",
                        "area_in_acrs": float(self.auto_token_trip_sheet_table.item(row, 8).text()) if self.auto_token_trip_sheet_table.item(row, 8) and self.auto_token_trip_sheet_table.item(row, 8).text() else 0,
                        "farmer": self.auto_token_trip_sheet_table.item(row, 9).text() if self.auto_token_trip_sheet_table.item(row, 9) else "",
                        "distance": float(self.auto_token_trip_sheet_table.item(row, 10).text()) if self.auto_token_trip_sheet_table.item(row, 10) and self.auto_token_trip_sheet_table.item(row, 10).text() else 0,
                        "transporter_contract": self.auto_token_trip_sheet_table.item(row, 11).text() if self.auto_token_trip_sheet_table.item(row, 11) else "",
                        "transporter": self.auto_token_trip_sheet_table.item(row, 12).text() if self.auto_token_trip_sheet_table.item(row, 12) else "",
                        "harvester_contract": self.auto_token_fields["transporter_contract"].currentText(),
                        "harvester": self.auto_token_fields["transporter"].text()
                    }
                    auto_token_data["auto_token_trip_sheet_table"].append(trip_sheet_data)

            self.output.append(f"[Auto Token] Submit Payload: {auto_token_data}")

            # Submit to Frappe
            if self.primary_frappe_logged_in:
                response = self.primary_frappe_session.post(
                    f"{self.primary_frappe_site_url}/api/resource/Auto Token",
                    json=auto_token_data
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("data"):
                        QMessageBox.information(self, "Success", f"Auto Token submitted successfully! Document: {result['data']['name']}")
                        self.output.append(f"[Auto Token] Submitted successfully: {result['data']['name']}")
                    else:
                        QMessageBox.warning(self, "Warning", "Auto Token submission failed. Check the response.")
                        self.output.append(f"[Auto Token Error] Submission failed: {result}")
                else:
                    QMessageBox.critical(self, "Error", f"Failed to submit Auto Token. Status: {response.status_code}")
                    self.output.append(f"[Auto Token Error] HTTP {response.status_code}: {response.text}")
            else:
                QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance!")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error submitting Auto Token: {str(e)}")
            self.output.append(f"[Auto Token Error] Exception: {str(e)}")

    def save_auto_token_form(self):
        """Save the auto token form data (draft)."""
        try:
            # Similar to submit but with docstatus = 0 (draft)
            auto_token_data = {
                "doctype": "Auto Token",
                "docstatus": 1,
                "season": self.auto_token_fields["season"].currentText(),
                "branch": self.auto_token_fields["branch"].currentText(),
                "posting_date": self.auto_token_fields["posting_date"].date().toString("yyyy-MM-dd"),
                "posting_time": self.auto_token_fields["posting_time"].time().toString("HH:mm:ss"),
                "shift": self.auto_token_fields["shift"].currentText(),
                "edit": 1 if self.auto_token_fields["edit"].isChecked() else 0,
                "season_day": self.auto_token_fields["season_day"].value(),
                "token_no": self.auto_token_fields["token_no"].text(),
                "factory_day": self.auto_token_fields["factory_day"].value(),
                "transporter_contract": self.auto_token_fields["transporter_contract"].currentText(),
                "transporter": self.auto_token_fields["transporter"].text(),
                "transporter_name": self.auto_token_fields["transporter_name"].text(),
                "vehicle_no": self.auto_token_fields["vehicle_no"].text(),
                "transporter_vehicle_type": self.auto_token_fields["transporter_vehicle_type"].currentText(),
                "transporter_gang_type": self.auto_token_fields["transporter_gang_type"].text(),
                "no_of_tripsheet": self.auto_token_fields["no_of_tripsheet"].value(),
                "company": "Quantbit Sugar Pvt Ltd",
                "auto_token_trip_sheet_table": []
            }
            
            # Collect trip sheet details data (same as submit)
            for row in range(self.auto_token_trip_sheet_table.rowCount()):
                select_checkbox = self.auto_token_trip_sheet_table.cellWidget(row, 0)
                if select_checkbox and select_checkbox.isChecked():
                    trip_sheet_data = {
                        "doctype": "Auto Token Trip sheet Details",
                        "select": 1,
                        "season": self.auto_token_trip_sheet_table.item(row, 1).text() if self.auto_token_trip_sheet_table.item(row, 1) else "",
                        "branch": self.auto_token_trip_sheet_table.item(row, 2).text() if self.auto_token_trip_sheet_table.item(row, 2) else "",
                        "posting_date": self.auto_token_trip_sheet_table.item(row, 3).text() if self.auto_token_trip_sheet_table.item(row, 3) else "",
                        "trip_sheet_no": self.auto_token_trip_sheet_table.item(row, 4).text() if self.auto_token_trip_sheet_table.item(row, 4) else "",
                        "rope_placement": self.auto_token_trip_sheet_table.item(row, 5).text() if self.auto_token_trip_sheet_table.item(row, 5) else "",
                        "cane_registration": self.auto_token_trip_sheet_table.item(row, 6).text() if self.auto_token_trip_sheet_table.item(row, 6) else "",
                        "route": self.auto_token_trip_sheet_table.item(row, 7).text() if self.auto_token_trip_sheet_table.item(row, 7) else "",
                        "area_in_acrs": float(self.auto_token_trip_sheet_table.item(row, 8).text()) if self.auto_token_trip_sheet_table.item(row, 8) and self.auto_token_trip_sheet_table.item(row, 8).text() else 0,
                        "farmer": self.auto_token_trip_sheet_table.item(row, 9).text() if self.auto_token_trip_sheet_table.item(row, 9) else "",
                        "distance": float(self.auto_token_trip_sheet_table.item(row, 10).text()) if self.auto_token_trip_sheet_table.item(row, 10) and self.auto_token_trip_sheet_table.item(row, 10).text() else 0,
                        "transporter_contract": self.auto_token_trip_sheet_table.item(row, 11).text() if self.auto_token_trip_sheet_table.item(row, 11) else "",
                        "transporter": self.auto_token_trip_sheet_table.item(row, 12).text() if self.auto_token_trip_sheet_table.item(row, 12) else "",
                        "harvester_contract": self.auto_token_fields["transporter_contract"].currentText(),
                        "harvester": self.auto_token_fields["transporter"].text()
                    }
                    auto_token_data["auto_token_trip_sheet_table"].append(trip_sheet_data)
            
            self.output.append(f"[Auto Token] Save Payload: {auto_token_data}")

            # Save to Frappe
            if self.primary_frappe_logged_in:
                response = self.primary_frappe_session.post(
                    f"{self.primary_frappe_site_url}/api/resource/Auto Token",
                    json=auto_token_data
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("data"):
                        QMessageBox.information(self, "Success", f"Auto Token saved as draft! Document: {result['data']['name']}")
                        self.output.append(f"[Auto Token] Saved as draft: {result['data']['name']}")
                    else:
                        QMessageBox.warning(self, "Warning", "Auto Token save failed. Check the response.")
                        self.output.append(f"[Auto Token Error] Save failed: {result}")
                else:
                    QMessageBox.critical(self, "Error", f"Failed to save Auto Token. Status: {response.status_code}")
                    self.output.append(f"[Auto Token Error] HTTP {response.status_code}: {response.text}")
            else:
                QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance!")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error saving Auto Token: {str(e)}")
            self.output.append(f"[Auto Token Error] Exception: {str(e)}")

    def clear_auto_token_form(self):
        """Clear all auto token form fields."""
        for field_name, widget in self.auto_token_fields.items():
            if isinstance(widget, QLineEdit):
                widget.clear()
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(0)
            elif isinstance(widget, QSpinBox):
                widget.setValue(0)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(False)
            elif isinstance(widget, QDateEdit):
                widget.setDate(datetime.now().date())
            elif isinstance(widget, QTimeEdit):
                widget.setTime(datetime.now().time())
        
        # Reset some fields to default values
        self.auto_token_fields["season"].setCurrentText("2025-2026")
        self.auto_token_fields["branch"].setCurrentText("Kundal")
        self.auto_token_fields["shift"].setCurrentText("3rd")
        self.auto_token_fields["edit"].setChecked(True)
        self.auto_token_fields["season_day"].setValue(487)
        self.auto_token_fields["token_no"].setText("TT-1")
        self.auto_token_fields["factory_day"].setValue(30)
        self.auto_token_fields["transporter_contract"].setText("HTC00002")
        self.auto_token_fields["transporter"].setText("E00002")
        self.auto_token_fields["transporter_name"].setText("Sita")
        self.auto_token_fields["vehicle_no"].setText("0")
        self.auto_token_fields["transporter_vehicle_type"].setCurrentText("TRACTOR")
        self.auto_token_fields["transporter_gang_type"].setText("BEED")
        self.auto_token_fields["no_of_tripsheet"].setValue(2)
        
        # Clear the trip sheet table
        self.auto_token_trip_sheet_table.setRowCount(0)
        self.add_auto_token_trip_sheet_row()  # Add one empty row
        
        # QMessageBox.information(self, "Success", "Auto Token form cleared!")
        self.current_auto_token_doc = None
    
    # Diesel Sale Methods
    def add_diesel_sale_item_row(self):
        """Add a new row to the diesel sale items table."""
        row_position = self.diesel_sale_items_table.rowCount()
        self.diesel_sale_items_table.insertRow(row_position)
        
        # Item Code
        item_code_edit = QLineEdit()
        item_code_edit.setPlaceholderText("e.g., 1447")
        self.diesel_sale_items_table.setCellWidget(row_position, 0, item_code_edit)
        
        # Item Name
        item_name_edit = QLineEdit()
        item_name_edit.setText("DIESEL")
        self.diesel_sale_items_table.setCellWidget(row_position, 1, item_name_edit)
        
        # Qty
        qty_spin = QSpinBox()
        qty_spin.setRange(0, 99999)
        qty_spin.setValue(0)
        qty_spin.valueChanged.connect(lambda: self.calculate_diesel_sale_item_amount(row_position))
        self.diesel_sale_items_table.setCellWidget(row_position, 2, qty_spin)
        
        # UOM
        uom_combo = QComboBox()
        uom_combo.addItems(["LTR", "KG", "Unit"])
        uom_combo.setCurrentText("LTR")
        self.diesel_sale_items_table.setCellWidget(row_position, 3, uom_combo)
        
        # Rate
        rate_spin = QDoubleSpinBox()
        rate_spin.setRange(0, 999999.99)
        rate_spin.setDecimals(2)
        rate_spin.setValue(89.57)
        rate_spin.valueChanged.connect(lambda: self.calculate_diesel_sale_item_amount(row_position))
        self.diesel_sale_items_table.setCellWidget(row_position, 4, rate_spin)
        
        # Amount (read-only)
        amount_edit = QLineEdit()
        amount_edit.setReadOnly(True)
        amount_edit.setText("0.00")
        self.diesel_sale_items_table.setCellWidget(row_position, 5, amount_edit)
        
        # Allocation Remaining
        allocation_spin = QDoubleSpinBox()
        allocation_spin.setRange(0, 999999.99)
        allocation_spin.setDecimals(2)
        allocation_spin.setValue(0)
        self.diesel_sale_items_table.setCellWidget(row_position, 6, allocation_spin)

    def calculate_diesel_sale_item_amount(self, row):
        """Calculate amount for a diesel sale item row."""
        try:
            qty_widget = self.diesel_sale_items_table.cellWidget(row, 2)
            rate_widget = self.diesel_sale_items_table.cellWidget(row, 4)
            amount_widget = self.diesel_sale_items_table.cellWidget(row, 5)
            
            if qty_widget and rate_widget and amount_widget:
                qty = qty_widget.value()
                rate = rate_widget.value()
                amount = qty * rate
                amount_widget.setText(f"{amount:.2f}")
        except Exception as e:
            self.output.append(f"[Diesel Sale] Error calculating amount: {str(e)}")

    def submit_diesel_sale_form(self):
        """Submit the diesel sale form to Frappe."""
        if not self.primary_frappe_logged_in:
            QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance. Please login first.")
            self.output.append("[Diesel Sale] Submit aborted: not logged in to primary instance.")
            return

        try:
            # Collect form data
            doc_data = {
                "doctype": "Diesel Sale",
                "scan_barcode": self.diesel_sale_fields["scan_barcode"].text(),
                "contract_id": self.diesel_sale_fields["contract_id"].text(),
                "season": self.diesel_sale_fields["season"].currentText(),
                "date": self.diesel_sale_fields["date"].date().toString("yyyy-MM-dd"),
                "shift": self.diesel_sale_fields["shift"].currentText(),
                "party_name": self.diesel_sale_fields["party_name"].text(),
                "customer_name": self.diesel_sale_fields["customer_name"].text(),
                "company": self.diesel_sale_fields["company"].currentText(),
                "plant": self.diesel_sale_fields["plant"].currentText(),
                "sale_type": self.diesel_sale_fields["sale_type"].currentText(),
                "debit_account": self.diesel_sale_fields["debit_account"].text(),
                "transporter": 1 if self.diesel_sale_fields["transporter"].isChecked() else 0,
                "harvester": 1 if self.diesel_sale_fields["harvester"].isChecked() else 0,
                "is_extra_diesel": 1 if self.diesel_sale_fields["is_extra_diesel"].isChecked() else 0,
                "invoice_reference": self.diesel_sale_fields["invoice_reference"].text(),
                "remarks": self.diesel_sale_fields["remarks"].toPlainText(),
                "total_diesel_allocated": float(self.diesel_sale_fields["total_diesel_allocated"].text() or 0),
                "total_distance_in_km": float(self.diesel_sale_fields["total_distance_in_km"].text() or 0),
                "total__weight_in_ton": float(self.diesel_sale_fields["total__weight_in_ton"].text() or 0),
                "naming_series": "DS-.season.-.####.",
                "diseal_sale_item": []
            }

            # Collect items from table
            for row in range(self.diesel_sale_items_table.rowCount()):
                item_code_widget = self.diesel_sale_items_table.cellWidget(row, 0)
                item_name_widget = self.diesel_sale_items_table.cellWidget(row, 1)
                qty_widget = self.diesel_sale_items_table.cellWidget(row, 2)
                uom_widget = self.diesel_sale_items_table.cellWidget(row, 3)
                rate_widget = self.diesel_sale_items_table.cellWidget(row, 4)
                amount_widget = self.diesel_sale_items_table.cellWidget(row, 5)
                allocation_widget = self.diesel_sale_items_table.cellWidget(row, 6)

                if item_code_widget and qty_widget and qty_widget.value() > 0:
                    item = {
                        "item_code": item_code_widget.text(),
                        "item_name": item_name_widget.text() if item_name_widget else "DIESEL",
                        "qty": qty_widget.value(),
                        "uom": uom_widget.currentText() if uom_widget else "LTR",
                        "rate": rate_widget.value() if rate_widget else 0,
                        "amount": float(amount_widget.text() or 0) if amount_widget else 0,
                        "allocation_remaining": allocation_widget.value() if allocation_widget else 0
                    }
                    doc_data["diseal_sale_item"].append(item)

            if not doc_data["diseal_sale_item"]:
                QMessageBox.warning(self, "Warning", "Please add at least one item with quantity > 0.")
                return

            # Submit to Frappe
            url = f"{self.primary_frappe_site_url}/api/resource/Diesel Sale"
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            self.output.append(f"[Diesel Sale] Submitting to {url}")
            response = self.primary_frappe_session.post(url, json={"data": doc_data}, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            doc_name = result.get("data", {}).get("name", "Unknown")
            
            QMessageBox.information(self, "Success", f"Diesel Sale submitted successfully!\nDocument: {doc_name}")
            self.output.append(f"[Diesel Sale] Successfully submitted: {doc_name}")
            
            # Optionally clear form after successful submission
            # self.clear_diesel_sale_form()
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            self.output.append(f"[Diesel Sale] Submit failed: {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to submit Diesel Sale: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            self.output.append(f"[Diesel Sale] Network error: {error_msg}")
            QMessageBox.critical(self, "Network Error", f"Failed to submit: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Diesel Sale] Error: {error_msg}")
            QMessageBox.critical(self, "Error", f"Error submitting Diesel Sale: {error_msg}")

    def save_diesel_sale_form(self):
        """Save the diesel sale form as draft (docstatus=0)."""
        if not self.primary_frappe_logged_in:
            QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance. Please login first.")
            self.output.append("[Diesel Sale] Save aborted: not logged in to primary instance.")
            return

        try:
            # Collect form data (similar to submit but with docstatus=0)
            doc_data = {
                "doctype": "Diesel Sale",
                "docstatus": 0,  # Draft
                "scan_barcode": self.diesel_sale_fields["scan_barcode"].text(),
                "contract_id": self.diesel_sale_fields["contract_id"].text(),
                "season": self.diesel_sale_fields["season"].currentText(),
                "date": self.diesel_sale_fields["date"].date().toString("yyyy-MM-dd"),
                "shift": self.diesel_sale_fields["shift"].currentText(),
                "party_name": self.diesel_sale_fields["party_name"].text(),
                "customer_name": self.diesel_sale_fields["customer_name"].text(),
                "company": self.diesel_sale_fields["company"].currentText(),
                "plant": self.diesel_sale_fields["plant"].currentText(),
                "sale_type": self.diesel_sale_fields["sale_type"].currentText(),
                "debit_account": self.diesel_sale_fields["debit_account"].text(),
                "transporter": 1 if self.diesel_sale_fields["transporter"].isChecked() else 0,
                "harvester": 1 if self.diesel_sale_fields["harvester"].isChecked() else 0,
                "is_extra_diesel": 1 if self.diesel_sale_fields["is_extra_diesel"].isChecked() else 0,
                "invoice_reference": self.diesel_sale_fields["invoice_reference"].text(),
                "remarks": self.diesel_sale_fields["remarks"].toPlainText(),
                "naming_series": "DS-.season.-.####.",
                "diseal_sale_item": []
            }

            # Collect items from table
            for row in range(self.diesel_sale_items_table.rowCount()):
                item_code_widget = self.diesel_sale_items_table.cellWidget(row, 0)
                item_name_widget = self.diesel_sale_items_table.cellWidget(row, 1)
                qty_widget = self.diesel_sale_items_table.cellWidget(row, 2)
                uom_widget = self.diesel_sale_items_table.cellWidget(row, 3)
                rate_widget = self.diesel_sale_items_table.cellWidget(row, 4)
                amount_widget = self.diesel_sale_items_table.cellWidget(row, 5)
                allocation_widget = self.diesel_sale_items_table.cellWidget(row, 6)

                if item_code_widget and qty_widget:
                    item = {
                        "item_code": item_code_widget.text(),
                        "item_name": item_name_widget.text() if item_name_widget else "DIESEL",
                        "qty": qty_widget.value(),
                        "uom": uom_widget.currentText() if uom_widget else "LTR",
                        "rate": rate_widget.value() if rate_widget else 0,
                        "amount": float(amount_widget.text() or 0) if amount_widget else 0,
                        "allocation_remaining": allocation_widget.value() if allocation_widget else 0
                    }
                    doc_data["diseal_sale_item"].append(item)

            # Save to Frappe
            url = f"{self.primary_frappe_site_url}/api/resource/Diesel Sale"
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            self.output.append(f"[Diesel Sale] Saving draft to {url}")
            response = self.primary_frappe_session.post(url, json={"data": doc_data}, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            doc_name = result.get("data", {}).get("name", "Unknown")
            
            # QMessageBox.information(self, "Success", f"Diesel Sale saved as draft!\nDocument: {doc_name}")
            self.output.append(f"[Diesel Sale] Successfully saved draft: {doc_name}")
            self.current_diesel_sale_doc = doc_name
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            self.output.append(f"[Diesel Sale] Save failed: {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to save Diesel Sale: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            self.output.append(f"[Diesel Sale] Network error: {error_msg}")
            QMessageBox.critical(self, "Network Error", f"Failed to save: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Diesel Sale] Error: {error_msg}")
            QMessageBox.critical(self, "Error", f"Error saving Diesel Sale: {error_msg}")

    def clear_diesel_sale_form(self):
        """Clear all diesel sale form fields."""
        for field_name, widget in self.diesel_sale_fields.items():
            if isinstance(widget, QLineEdit):
                widget.clear()
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(0)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(False)
            elif isinstance(widget, QDateEdit):
                widget.setDate(datetime.now().date())
            elif isinstance(widget, QTextEdit):
                widget.clear()
        
        # Reset some fields to default values
        self.diesel_sale_fields["season"].setCurrentText("2024-2025")
        self.diesel_sale_fields["shift"].setCurrentText("3rd")
        self.diesel_sale_fields["company"].setCurrentText("Venkateshwara Power Projects LTD")
        self.diesel_sale_fields["plant"].setCurrentText("Bedkihal")
        self.diesel_sale_fields["sale_type"].setCurrentText("Diesel Sale")
        self.diesel_sale_fields["debit_account"].setText("12520005 - Advance For Diesel - VP")
        self.diesel_sale_fields["transporter"].setChecked(True)
        self.diesel_sale_fields["is_extra_diesel"].setChecked(True)
        self.diesel_sale_fields["total_diesel_allocated"].setText("0")
        self.diesel_sale_fields["total_distance_in_km"].setText("0")
        self.diesel_sale_fields["total__weight_in_ton"].setText("0")
        
        # Clear the items table
        self.diesel_sale_items_table.setRowCount(0)
        self.add_diesel_sale_item_row()  # Add one empty row
        
        # QMessageBox.information(self, "Success", "Diesel Sale form cleared!")
        self.current_diesel_sale_doc = None

    def view_submitted_diesel_sale_records(self):
        """View submitted diesel sale records from Frappe."""
        if not self.primary_frappe_logged_in:
            QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance. Please login first.")
            self.output.append("[Diesel Sale Records] View aborted: not logged in to primary instance.")
            return

        if not self.primary_frappe_site_url:
            QMessageBox.warning(self, "Warning", "Primary Frappe site URL is not configured.")
            self.output.append("[Diesel Sale Records] View aborted: primary site URL missing.")
            return

        try:
            filters = {}
            fields = [
                "name", "season", "date", "shift", "party_name", "customer_name",
                "sale_type", "invoice_reference", "modified"
            ]
            resource = quote("Diesel Sale")
            params = {
                "filters": json.dumps(filters),
                "fields": json.dumps(fields),
                "limit_page_length": 100,
                "order_by": "modified desc"
            }

            url = f"{self.primary_frappe_site_url}/api/resource/{resource}"
            headers = {"Accept": "application/json"}
            self.output.append(f"[Diesel Sale Records] Fetching submitted records: {url} | params={params}")

            data = []
            try:
                primary_response = self.primary_frappe_session.get(url, params=params, headers=headers, timeout=30)
                primary_response.raise_for_status()
                primary_json = primary_response.json()
                data = primary_json.get("data", [])
            except Exception as primary_error:
                self.output.append(f"[Diesel Sale Records] Primary fetch failed: {str(primary_error)}")

            if not data:
                # QMessageBox.information(self, "No Records", "No submitted Diesel Sale records were found.")
                self.output.append("[Diesel Sale Records] No submitted records returned.")
                return

            dialog = QDialog(self)
            dialog.setWindowTitle("Submitted Diesel Sale Records")
            dialog.resize(1000, 500)

            dialog_layout = QVBoxLayout(dialog)
            table = QTableWidget()
            table.setColumnCount(len(fields))
            table.setHorizontalHeaderLabels(fields)
            table.setRowCount(len(data))
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.setSelectionBehavior(QTableWidget.SelectRows)

            for row_idx, record in enumerate(data):
                for col_idx, field in enumerate(fields):
                    value = record.get(field, "")
                    table.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))

            header = table.horizontalHeader()
            for i in range(len(fields)):
                header.setSectionResizeMode(i, QHeaderView.Stretch)

            dialog_layout.addWidget(table)

            button_layout = QHBoxLayout()
            load_btn = QPushButton("Load Selected")
            load_btn.clicked.connect(lambda: self.load_selected_diesel_sale_record(table, dialog))
            button_layout.addWidget(load_btn)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.close)
            button_layout.addWidget(close_btn)

            dialog_layout.addLayout(button_layout)
            dialog.exec_()

        except requests.exceptions.HTTPError as e:
            response = e.response
            response_text = response.text if response is not None else "No response text"
            error_msg = f"HTTP {response.status_code if response is not None else 'N/A'}: {response_text}"
            self.output.append(f"[Diesel Sale Records] Fetch failed: {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to fetch records: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            self.output.append(f"[Diesel Sale Records] Network error: {error_msg}")
            QMessageBox.critical(self, "Network Error", f"Failed to fetch records: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Diesel Sale Records] Unexpected error: {error_msg}")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {error_msg}")

    def load_selected_diesel_sale_record(self, table, dialog):
        """Load the selected diesel sale record into the form."""
        selected_rows = table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "Warning", "Please select a record to load.")
            return

        row = selected_rows[0].row()
        doc_name = table.item(row, 0).text()
        
        dialog.close()
        self.load_diesel_sale_record(doc_name)

    def load_diesel_sale_record(self, doc_name: str) -> bool:
        """Load a diesel sale record from Frappe into the form."""
        if not self.primary_frappe_logged_in:
            QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance.")
            self.output.append("[Diesel Sale Records] Load aborted: not logged in.")
            return False

        try:
            encoded_name = quote(doc_name)
            url = f"{self.primary_frappe_site_url}/api/resource/Diesel Sale/{encoded_name}"
            headers = {"Accept": "application/json"}
            
            self.output.append(f"[Diesel Sale] Loading record: {url}")
            response = self.primary_frappe_session.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            doc = result.get("data", {})
            
            # Populate form fields
            if doc.get("scan_barcode"):
                self.diesel_sale_fields["scan_barcode"].setText(str(doc["scan_barcode"]))
            if doc.get("contract_id"):
                self.diesel_sale_fields["contract_id"].setText(str(doc["contract_id"]))
            if doc.get("season"):
                self.diesel_sale_fields["season"].setCurrentText(str(doc["season"]))
            if doc.get("date"):
                date = QDate.fromString(str(doc["date"]), "yyyy-MM-dd")
                if date.isValid():
                    self.diesel_sale_fields["date"].setDate(date)
            if doc.get("shift"):
                self.diesel_sale_fields["shift"].setCurrentText(str(doc["shift"]))
            if doc.get("party_name"):
                self.diesel_sale_fields["party_name"].setText(str(doc["party_name"]))
            if doc.get("customer_name"):
                self.diesel_sale_fields["customer_name"].setText(str(doc["customer_name"]))
            if doc.get("company"):
                self.diesel_sale_fields["company"].setCurrentText(str(doc["company"]))
            if doc.get("plant"):
                self.diesel_sale_fields["plant"].setCurrentText(str(doc["plant"]))
            if doc.get("sale_type"):
                self.diesel_sale_fields["sale_type"].setCurrentText(str(doc["sale_type"]))
            if doc.get("debit_account"):
                self.diesel_sale_fields["debit_account"].setText(str(doc["debit_account"]))
            
            self.diesel_sale_fields["transporter"].setChecked(bool(doc.get("transporter", 0)))
            self.diesel_sale_fields["harvester"].setChecked(bool(doc.get("harvester", 0)))
            self.diesel_sale_fields["is_extra_diesel"].setChecked(bool(doc.get("is_extra_diesel", 0)))
            
            if doc.get("invoice_reference"):
                self.diesel_sale_fields["invoice_reference"].setText(str(doc["invoice_reference"]))
            if doc.get("remarks"):
                self.diesel_sale_fields["remarks"].setPlainText(str(doc["remarks"]))
            
            # Load items
            self.diesel_sale_items_table.setRowCount(0)
            items = doc.get("diseal_sale_item", [])
            for item in items:
                row = self.diesel_sale_items_table.rowCount()
                self.diesel_sale_items_table.insertRow(row)
                
                item_code_edit = QLineEdit(str(item.get("item_code", "")))
                self.diesel_sale_items_table.setCellWidget(row, 0, item_code_edit)
                
                item_name_edit = QLineEdit(str(item.get("item_name", "")))
                self.diesel_sale_items_table.setCellWidget(row, 1, item_name_edit)
                
                qty_spin = QSpinBox()
                qty_spin.setRange(0, 99999)
                qty_spin.setValue(int(item.get("qty", 0)))
                self.diesel_sale_items_table.setCellWidget(row, 2, qty_spin)
                
                uom_combo = QComboBox()
                uom_combo.addItems(["LTR", "KG", "Unit"])
                uom_combo.setCurrentText(str(item.get("uom", "LTR")))
                self.diesel_sale_items_table.setCellWidget(row, 3, uom_combo)
                
                rate_spin = QDoubleSpinBox()
                rate_spin.setRange(0, 999999.99)
                rate_spin.setDecimals(2)
                rate_spin.setValue(float(item.get("rate", 0)))
                self.diesel_sale_items_table.setCellWidget(row, 4, rate_spin)
                
                amount_edit = QLineEdit(str(item.get("amount", 0)))
                amount_edit.setReadOnly(True)
                self.diesel_sale_items_table.setCellWidget(row, 5, amount_edit)
                
                allocation_spin = QDoubleSpinBox()
                allocation_spin.setRange(0, 999999.99)
                allocation_spin.setDecimals(2)
                allocation_spin.setValue(float(item.get("allocation_remaining", 0)))
                self.diesel_sale_items_table.setCellWidget(row, 6, allocation_spin)
            
            self.current_diesel_sale_doc = doc_name
            self.output.append(f"[Diesel Sale] Successfully loaded record: {doc_name}")
            # QMessageBox.information(self, "Success", f"Loaded Diesel Sale: {doc_name}")
            return True
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            self.output.append(f"[Diesel Sale] Load failed: {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to load record: {error_msg}")
            return False
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Diesel Sale] Error: {error_msg}")
            QMessageBox.critical(self, "Error", f"Error loading record: {error_msg}")
            return False

    # Cane Inward Slip Methods
    def add_cane_inward_slip_item_row(self):
        """Add a new row to the cane inward slip items table."""
        row_position = self.cane_inward_slip_items_table.rowCount()
        self.cane_inward_slip_items_table.insertRow(row_position)
        
        # Select checkbox
        select_checkbox = QCheckBox()
        select_checkbox.setChecked(False)
        self.cane_inward_slip_items_table.setCellWidget(row_position, 0, select_checkbox)

        # Trip Sheet No
        trip_sheet_edit = QLineEdit()
        self.cane_inward_slip_items_table.setCellWidget(row_position, 1, trip_sheet_edit)

        # Rope Placement
        rope_placement_edit = QLineEdit()
        self.cane_inward_slip_items_table.setCellWidget(row_position, 2, rope_placement_edit)

        # Cane Registration
        cane_registration_edit = QLineEdit()
        self.cane_inward_slip_items_table.setCellWidget(row_position, 3, cane_registration_edit)

        # Farmer
        farmer_edit = QLineEdit()
        self.cane_inward_slip_items_table.setCellWidget(row_position, 4, farmer_edit)

        # Transporter Contract
        transporter_contract_edit = QLineEdit()
        self.cane_inward_slip_items_table.setCellWidget(row_position, 5, transporter_contract_edit)

        # Harvester Contract
        harvester_contract_edit = QLineEdit()
        self.cane_inward_slip_items_table.setCellWidget(row_position, 6, harvester_contract_edit)

        # Season (moved to the end)
        season_edit = QLineEdit()
        self.cane_inward_slip_items_table.setCellWidget(row_position, 7, season_edit)

        # Branch (moved to the end)
        branch_edit = QLineEdit()
        self.cane_inward_slip_items_table.setCellWidget(row_position, 8, branch_edit)

        # Posting Date (moved to the end)
        posting_date_edit = QLineEdit()
        self.cane_inward_slip_items_table.setCellWidget(row_position, 9, posting_date_edit)

        # Transporter (moved to the end)
        transporter_edit = QLineEdit()
        self.cane_inward_slip_items_table.setCellWidget(row_position, 10, transporter_edit)

        # Harvester (moved to the end)
        harvester_edit = QLineEdit()
        self.cane_inward_slip_items_table.setCellWidget(row_position, 11, harvester_edit)

        # Route (moved to the end)
        route_edit = QLineEdit()
        self.cane_inward_slip_items_table.setCellWidget(row_position, 12, route_edit)

        # Area in Acrs (moved to the end)
        area_in_acrs_spin = QDoubleSpinBox()
        area_in_acrs_spin.setDecimals(2)
        area_in_acrs_spin.setMaximum(9999.99)
        self.cane_inward_slip_items_table.setCellWidget(row_position, 13, area_in_acrs_spin)

        # Distance (moved to the end)
        distance_spin = QDoubleSpinBox()
        distance_spin.setDecimals(1)
        distance_spin.setMaximum(9999.9)
        self.cane_inward_slip_items_table.setCellWidget(row_position, 14, distance_spin)

    def _on_cane_inward_slip_manual_rfid_toggled(self, checked):
        """"Manually Entry for RFID" ticked -> Transporter Contract becomes editable so
        staff can type it directly when the RFID reader/lookup isn't available.
        Unticked (default) -> Transporter Contract is read-only, only ever set by the
        RFID tag -> Transporter Contract lookup."""
        transporter_contract_edit = self.cane_inward_slip_fields.get("transporter_contract")
        if not transporter_contract_edit:
            return
        transporter_contract_edit.setReadOnly(not checked)
        transporter_contract_edit.setStyleSheet(
            "background-color: white;" if checked else "background-color: #f0f0f0;"
        )

    def fetch_transporter_data_for_cane_inward_slip(self):
        """Resolve Transporter / Transporter Name / vehicle details for the current
        Transporter Contract - same transporter_data API the Auto Token tab uses
        (fetch_transporter_data_for_auto_token). Called after RFID resolves a
        contract, or after manually typing one in with "Manually Entry for RFID"
        ticked."""
        try:
            transporter_contract = self.cane_inward_slip_fields["transporter_contract"].text().strip()
            if not transporter_contract:
                self.cane_inward_slip_fields["transporter"].setText("")
                self.cane_inward_slip_fields["transporter_name"].setText("")
                self.cane_inward_slip_fields["vehicle_no"].setText("")
                return

            url = f"{self.trip_sheet_api_base}/api/method/quantbit_agriculture_crm.agriculture_utils.transporter_data"
            headers = {
                "Authorization": f"token {self.trip_sheet_api_key}:{self.trip_sheet_api_secret}",
                "Accept": "application/json",
            }
            params = {"transporter_contract": transporter_contract}
            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            result = response.json()
            transporter_data = []
            if isinstance(result, dict):
                if "message" in result and isinstance(result["message"], list):
                    transporter_data = result["message"]
                elif "data" in result and isinstance(result["data"], list):
                    transporter_data = result["data"]

            if transporter_data:
                data = transporter_data[0]
                self.cane_inward_slip_fields["transporter"].setText(data.get("transporter", ""))
                self.cane_inward_slip_fields["transporter_name"].setText(data.get("transporter_name", ""))

                vehicle_type_combo = self.cane_inward_slip_fields.get("transporter_vehicle_type")
                if vehicle_type_combo:
                    vehicle_type = data.get("vehicle_type", "")
                    index = vehicle_type_combo.findText(vehicle_type)
                    if index >= 0:
                        vehicle_type_combo.setCurrentIndex(index)
                    elif vehicle_type:
                        vehicle_type_combo.addItem(vehicle_type)
                        vehicle_type_combo.setCurrentText(vehicle_type)

                gang_type_combo = self.cane_inward_slip_fields.get("transporter_gang_type")
                if gang_type_combo:
                    gang_type = data.get("gang_type", "")
                    index = gang_type_combo.findText(gang_type)
                    if index >= 0:
                        gang_type_combo.setCurrentIndex(index)
                    elif gang_type:
                        gang_type_combo.addItem(gang_type)
                        gang_type_combo.setCurrentText(gang_type)

                self.cane_inward_slip_fields["vehicle_no"].setText(data.get("vehicle_no", ""))
                self.output.append(f"[Cane Inward Slip] Loaded transporter data for contract {transporter_contract}.")
            else:
                self.cane_inward_slip_fields["transporter"].setText("")
                self.cane_inward_slip_fields["transporter_name"].setText("")
                self.cane_inward_slip_fields["vehicle_no"].setText("")
                self.output.append(f"[Cane Inward Slip] No transporter data found for contract {transporter_contract}.")
        except requests.exceptions.HTTPError as e:
            self.output.append(f"[Cane Inward Slip Transporter Data] HTTP {e.response.status_code}: {e.response.text}")
        except requests.exceptions.RequestException as e:
            self.output.append(f"[Cane Inward Slip Transporter Data] Network error: {str(e)}")
        except Exception as e:
            self.output.append(f"[Cane Inward Slip Transporter Data] Unexpected error: {str(e)}")

    def get_slip_for_cane_inward_slip(self):
        """Fetch this transporter's pending trip sheets (Season / Branch / Transporter
        Contract required) and load them into the Pending Slip Items table - the same
        get_trip_sheet API the Auto Token tab's "Show Pending Slips" already uses,
        aimed at this table's per-cell widgets instead of QTableWidgetItems."""
        try:
            season = self.cane_inward_slip_fields["season"].currentText()
            branch = self.cane_inward_slip_fields["branch"].currentText()
            transporter_contract = self.cane_inward_slip_fields["transporter_contract"].text().strip()

            if not (season and branch and transporter_contract):
                QMessageBox.warning(self, "Input Error", "Season, Branch, and Transporter Contract are mandatory to get slips.")
                self.output.append("[Cane Inward Slip] Missing mandatory fields for Get Slip.")
                return

            url = f"{self.trip_sheet_api_base}/api/method/quantbit_agriculture_crm.agriculture_utils.get_trip_sheet"
            headers = {
                "Authorization": f"token {self.trip_sheet_api_key}:{self.trip_sheet_api_secret}",
                "Accept": "application/json",
            }
            params = {"transporter_contract": transporter_contract, "branch": branch, "season": season}
            self.output.append(f"[Cane Inward Slip] Get Slip parameters: {params}")
            response = requests.get(url, headers=headers, params=params, timeout=20)
            response.raise_for_status()
            result = response.json()
            trip_sheets = result.get("message") or result.get("data") or []

            self.cane_inward_slip_items_table.setRowCount(0)

            if not trip_sheets:
                QMessageBox.information(self, "No Pending Slips", "No pending trip sheets found for the selected criteria.")
                self.output.append("[Cane Inward Slip] No pending trip sheets found.")
                self.add_cane_inward_slip_item_row()  # keep one empty row available
                return

            for sheet in trip_sheets:
                row = self.cane_inward_slip_items_table.rowCount()
                self.add_cane_inward_slip_item_row()

                select_widget = self.cane_inward_slip_items_table.cellWidget(row, 0)
                if select_widget:
                    select_widget.setChecked(True)

                self.cane_inward_slip_items_table.cellWidget(row, 1).setText(str(sheet.get("name", "")))
                self.cane_inward_slip_items_table.cellWidget(row, 2).setText(str(sheet.get("rope_placement", "")))
                self.cane_inward_slip_items_table.cellWidget(row, 3).setText(str(sheet.get("cane_registration", "")))
                self.cane_inward_slip_items_table.cellWidget(row, 4).setText(str(sheet.get("farmer", "")))
                self.cane_inward_slip_items_table.cellWidget(row, 5).setText(str(sheet.get("transporter_contract", "")))
                self.cane_inward_slip_items_table.cellWidget(row, 6).setText(str(sheet.get("harvester_contract", "")))
                self.cane_inward_slip_items_table.cellWidget(row, 7).setText(str(sheet.get("season", "")))
                self.cane_inward_slip_items_table.cellWidget(row, 8).setText(str(sheet.get("branch", "")))
                self.cane_inward_slip_items_table.cellWidget(row, 9).setText(str(sheet.get("posting_date", "")))
                self.cane_inward_slip_items_table.cellWidget(row, 10).setText(str(sheet.get("transporter", "")))
                self.cane_inward_slip_items_table.cellWidget(row, 11).setText(str(sheet.get("harvester", "")))
                self.cane_inward_slip_items_table.cellWidget(row, 12).setText(str(sheet.get("route", "")))
                try:
                    self.cane_inward_slip_items_table.cellWidget(row, 13).setValue(float(sheet.get("area_in_acrs") or 0))
                except (TypeError, ValueError):
                    pass
                try:
                    self.cane_inward_slip_items_table.cellWidget(row, 14).setValue(float(sheet.get("distance") or 0))
                except (TypeError, ValueError):
                    pass

            self.output.append(f"[Cane Inward Slip] Loaded {len(trip_sheets)} pending trip sheet(s) for transporter {transporter_contract}.")

        except requests.exceptions.HTTPError as e:
            self.output.append(f"[Cane Inward Slip] Get Slip HTTP {e.response.status_code}: {e.response.text}")
            QMessageBox.critical(self, "API Error", f"Failed to fetch pending slips: {e.response.status_code} - {e.response.text}")
        except requests.exceptions.RequestException as e:
            self.output.append(f"[Cane Inward Slip] Get Slip network error: {str(e)}")
            QMessageBox.critical(self, "Network Error", f"Failed to fetch pending slips: {str(e)}")
        except Exception as e:
            self.output.append(f"[Cane Inward Slip] Get Slip unexpected error: {str(e)}")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {str(e)}")

    def submit_cane_inward_slip_form(self):
        """Submit the cane inward slip form to Frappe."""
        if not self.primary_frappe_logged_in:
            QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance. Please login first.")
            self.output.append("[Cane Inward Slip] Submit aborted: not logged in to primary instance.")
            return

        try:
            # Collect form data
            doc_data = {
                "doctype": "Cane Inward Slip",
                "docstatus": 1,  # Submitted
                "season": self.cane_inward_slip_fields["season"].currentText(),
                "branch": self.cane_inward_slip_fields["branch"].currentText(),
                "company": self.cane_inward_slip_fields["company"].text(),
                "shift": self.cane_inward_slip_fields["shift"].currentText(),
                "posting_date": self.cane_inward_slip_fields["posting_date"].date().toString("yyyy-MM-dd"),
                "posting_time": self.cane_inward_slip_fields["posting_time"].time().toString("HH:mm:ss"),
                "token_no": self.cane_inward_slip_fields["token_no"].value(),
                "factory_day": self.cane_inward_slip_fields["factory_day"].value(),
                "transporter_contract": self.cane_inward_slip_fields["transporter_contract"].text(),
                "transporter": self.cane_inward_slip_fields["transporter"].text(),
                "transporter_name": self.cane_inward_slip_fields["transporter_name"].text(),
                "vehicle_no": self.cane_inward_slip_fields["vehicle_no"].text(),
                "transporter_vehicle_type": self.cane_inward_slip_fields["transporter_vehicle_type"].currentText(),
                "transporter_gang_type": self.cane_inward_slip_fields["transporter_gang_type"].currentText(),
                "no_of_tripsheet": self.cane_inward_slip_fields["no_of_tripsheet"].value(),
                "creator": self.cane_inward_slip_fields["creator"].text(),
                "manually_entry_for_rfid": 1 if self.cane_inward_slip_fields["manually_entry_for_rfid"].isChecked() else 0,
                "rfid_tag": self.cane_inward_slip_fields["rfid_tag"].text(),
                "ip_of_indicator": self.cane_inward_slip_fields["ip_of_indicator"].text(),
                "port_no_of_indicator": self.cane_inward_slip_fields["port_no_of_indicator"].text(),
            }

            # Collect pending slip items
            doc_data["pending_slip"] = []
            for row in range(self.cane_inward_slip_items_table.rowCount()):
                select_widget = self.cane_inward_slip_items_table.cellWidget(row, 0)
                if select_widget and select_widget.isChecked():
                    trip_sheet_widget = self.cane_inward_slip_items_table.cellWidget(row, 1)
                    rope_placement_widget = self.cane_inward_slip_items_table.cellWidget(row, 2)
                    cane_registration_widget = self.cane_inward_slip_items_table.cellWidget(row, 3)
                    farmer_widget = self.cane_inward_slip_items_table.cellWidget(row, 4)
                    transporter_contract_widget = self.cane_inward_slip_items_table.cellWidget(row, 5)
                    harvester_contract_widget = self.cane_inward_slip_items_table.cellWidget(row, 6)
                    season_widget = self.cane_inward_slip_items_table.cellWidget(row, 7)
                    branch_widget = self.cane_inward_slip_items_table.cellWidget(row, 8)
                    posting_date_widget = self.cane_inward_slip_items_table.cellWidget(row, 9)
                    transporter_widget = self.cane_inward_slip_items_table.cellWidget(row, 10)
                    harvester_widget = self.cane_inward_slip_items_table.cellWidget(row, 11)
                    route_widget = self.cane_inward_slip_items_table.cellWidget(row, 12)
                    area_in_acrs_widget = self.cane_inward_slip_items_table.cellWidget(row, 13)
                    distance_widget = self.cane_inward_slip_items_table.cellWidget(row, 14)

                    item = {
                        "season": season_widget.text() if season_widget else "",
                        "branch": branch_widget.text() if branch_widget else "",
                        "posting_date": posting_date_widget.text() if posting_date_widget else "",
                        "trip_sheet_no": trip_sheet_widget.text() if trip_sheet_widget else "",
                        "rope_placement": rope_placement_widget.text() if rope_placement_widget else "",
                        "cane_registration": cane_registration_widget.text() if cane_registration_widget else "",
                        "route": route_widget.text() if route_widget else "",
                        "area_in_acrs": area_in_acrs_widget.value() if area_in_acrs_widget else 0,
                        "farmer": farmer_widget.text() if farmer_widget else "",
                        "distance": distance_widget.value() if distance_widget else 0,
                        "transporter_contract": transporter_contract_widget.text() if transporter_contract_widget else "",
                        "transporter": transporter_widget.text() if transporter_widget else "",
                        "harvester_contract": harvester_contract_widget.text() if harvester_contract_widget else "",
                        "harvester": harvester_widget.text() if harvester_widget else "",
                        "select": 1,
                    }
                    doc_data["pending_slip"].append(item)

            if not doc_data["pending_slip"]:
                QMessageBox.warning(self, "Warning", "Please select at least one pending slip item.")
                return

            # Submit to Frappe
            url = f"{self.primary_frappe_site_url}/api/resource/Cane Inward Slip"
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            self.output.append(f"[Cane Inward Slip] Submitting to {url}")
            response = self.primary_frappe_session.post(url, json={"data": doc_data}, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            doc_name = result.get("data", {}).get("name", "Unknown")
            
            QMessageBox.information(self, "Success", f"Cane Inward Slip submitted successfully!\nDocument: {doc_name}")
            self.output.append(f"[Cane Inward Slip] Successfully submitted: {doc_name}")
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            self.output.append(f"[Cane Inward Slip] Submit failed: {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to submit Cane Inward Slip: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            self.output.append(f"[Cane Inward Slip] Network error: {error_msg}")
            QMessageBox.critical(self, "Network Error", f"Failed to submit: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Cane Inward Slip] Error: {error_msg}")
            QMessageBox.critical(self, "Error", f"Error submitting Cane Inward Slip: {error_msg}")

    def save_cane_inward_slip_form(self):
        """Save the cane inward slip form as draft (docstatus=0)."""
        if not self.primary_frappe_logged_in:
            QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance. Please login first.")
            self.output.append("[Cane Inward Slip] Save aborted: not logged in to primary instance.")
            return

        try:
            # Collect form data (similar to submit but with docstatus=0)
            doc_data = {
                "doctype": "Cane Inward Slip",
                "docstatus": 0,  # Draft
                "season": self.cane_inward_slip_fields["season"].currentText(),
                "branch": self.cane_inward_slip_fields["branch"].currentText(),
                "company": self.cane_inward_slip_fields["company"].text(),
                "shift": self.cane_inward_slip_fields["shift"].currentText(),
                "posting_date": self.cane_inward_slip_fields["posting_date"].date().toString("yyyy-MM-dd"),
                "posting_time": self.cane_inward_slip_fields["posting_time"].time().toString("HH:mm:ss"),
                "token_no": self.cane_inward_slip_fields["token_no"].value(),
                "factory_day": self.cane_inward_slip_fields["factory_day"].value(),
                "transporter_contract": self.cane_inward_slip_fields["transporter_contract"].text(),
                "transporter": self.cane_inward_slip_fields["transporter"].text(),
                "transporter_name": self.cane_inward_slip_fields["transporter_name"].text(),
                "vehicle_no": self.cane_inward_slip_fields["vehicle_no"].text(),
                "transporter_vehicle_type": self.cane_inward_slip_fields["transporter_vehicle_type"].currentText(),
                "transporter_gang_type": self.cane_inward_slip_fields["transporter_gang_type"].currentText(),
                "no_of_tripsheet": self.cane_inward_slip_fields["no_of_tripsheet"].value(),
                "creator": self.cane_inward_slip_fields["creator"].text(),
                "manually_entry_for_rfid": 1 if self.cane_inward_slip_fields["manually_entry_for_rfid"].isChecked() else 0,
                "rfid_tag": self.cane_inward_slip_fields["rfid_tag"].text(),
                "ip_of_indicator": self.cane_inward_slip_fields["ip_of_indicator"].text(),
                "port_no_of_indicator": self.cane_inward_slip_fields["port_no_of_indicator"].text(),
            }

            # Collect pending slip items
            doc_data["pending_slip"] = []
            for row in range(self.cane_inward_slip_items_table.rowCount()):
                select_widget = self.cane_inward_slip_items_table.cellWidget(row, 0)
                if select_widget and select_widget.isChecked():
                    trip_sheet_widget = self.cane_inward_slip_items_table.cellWidget(row, 1)
                    rope_placement_widget = self.cane_inward_slip_items_table.cellWidget(row, 2)
                    cane_registration_widget = self.cane_inward_slip_items_table.cellWidget(row, 3)
                    farmer_widget = self.cane_inward_slip_items_table.cellWidget(row, 4)
                    transporter_contract_widget = self.cane_inward_slip_items_table.cellWidget(row, 5)
                    harvester_contract_widget = self.cane_inward_slip_items_table.cellWidget(row, 6)
                    season_widget = self.cane_inward_slip_items_table.cellWidget(row, 7)
                    branch_widget = self.cane_inward_slip_items_table.cellWidget(row, 8)
                    posting_date_widget = self.cane_inward_slip_items_table.cellWidget(row, 9)
                    transporter_widget = self.cane_inward_slip_items_table.cellWidget(row, 10)
                    harvester_widget = self.cane_inward_slip_items_table.cellWidget(row, 11)
                    route_widget = self.cane_inward_slip_items_table.cellWidget(row, 12)
                    area_in_acrs_widget = self.cane_inward_slip_items_table.cellWidget(row, 13)
                    distance_widget = self.cane_inward_slip_items_table.cellWidget(row, 14)

                    item = {
                        "season": season_widget.text() if season_widget else "",
                        "branch": branch_widget.text() if branch_widget else "",
                        "posting_date": posting_date_widget.text() if posting_date_widget else "",
                        "trip_sheet_no": trip_sheet_widget.text() if trip_sheet_widget else "",
                        "rope_placement": rope_placement_widget.text() if rope_placement_widget else "",
                        "cane_registration": cane_registration_widget.text() if cane_registration_widget else "",
                        "route": route_widget.text() if route_widget else "",
                        "area_in_acrs": area_in_acrs_widget.value() if area_in_acrs_widget else 0,
                        "farmer": farmer_widget.text() if farmer_widget else "",
                        "distance": distance_widget.value() if distance_widget else 0,
                        "transporter_contract": transporter_contract_widget.text() if transporter_contract_widget else "",
                        "transporter": transporter_widget.text() if transporter_widget else "",
                        "harvester_contract": harvester_contract_widget.text() if harvester_contract_widget else "",
                        "harvester": harvester_widget.text() if harvester_widget else "",
                        "select": 1,
                    }
                    doc_data["pending_slip"].append(item)

            # Save to Frappe
            url = f"{self.primary_frappe_site_url}/api/resource/Cane Inward Slip"
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            self.output.append(f"[Cane Inward Slip] Saving draft to {url}")
            response = self.primary_frappe_session.post(url, json={"data": doc_data}, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            doc_name = result.get("data", {}).get("name", "Unknown")
            
            QMessageBox.information(self, "Success", f"Cane Inward Slip saved as draft!\nDocument: {doc_name}")
            self.output.append(f"[Cane Inward Slip] Successfully saved draft: {doc_name}")
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            self.output.append(f"[Cane Inward Slip] Save failed: {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to save Cane Inward Slip: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            self.output.append(f"[Cane Inward Slip] Network error: {error_msg}")
            QMessageBox.critical(self, "Network Error", f"Failed to save: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Cane Inward Slip] Error: {error_msg}")
            QMessageBox.critical(self, "Error", f"Error saving Cane Inward Slip: {error_msg}")

    def clear_cane_inward_slip_form(self):
        """Clear all cane inward slip form fields."""
        for field_name, widget in self.cane_inward_slip_fields.items():
            if isinstance(widget, QLineEdit):
                widget.clear()
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(0)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(False)
            elif isinstance(widget, QDateEdit):
                widget.setDate(datetime.now().date())
            elif isinstance(widget, QTimeEdit):
                widget.setTime(datetime.now().time())
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setValue(0)
        
        # Reset some fields to default values
        self.cane_inward_slip_fields["season"].setCurrentText("2024-2025")
        self.cane_inward_slip_fields["branch"].setCurrentText("Kundal")
        self.cane_inward_slip_fields["shift"].setCurrentText("1st")
        self.cane_inward_slip_fields["transporter_vehicle_type"].setCurrentText("TRACTOR")
        self.cane_inward_slip_fields["transporter_gang_type"].setCurrentText("LOCAL")
        self.cane_inward_slip_fields["ip_of_indicator"].setText("192.168.10.82")
        self.cane_inward_slip_fields["port_no_of_indicator"].setText("23")
        
        # Clear the items table
        self.cane_inward_slip_items_table.setRowCount(0)
        self.add_cane_inward_slip_item_row()  # Add one empty row
        
        # QMessageBox.information(self, "Success", "Cane Inward Slip form cleared!")

    def view_submitted_cane_inward_slip_records(self):
        """View submitted cane inward slip records from Frappe."""
        if not self.primary_frappe_logged_in:
            QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance. Please login first.")
            self.output.append("[Cane Inward Slip Records] View aborted: not logged in to primary instance.")
            return

        if not self.primary_frappe_site_url:
            QMessageBox.warning(self, "Warning", "Primary Frappe site URL is not configured.")
            self.output.append("[Cane Inward Slip Records] View aborted: primary site URL missing.")
            return

        try:
            filters = [["docstatus", "=", 1]]
            fields = [
                "name", "season", "branch", "posting_date", "shift", "token_no", "factory_day",
                "transporter_name", "vehicle_no", "modified"
            ]
            resource = quote("Cane Inward Slip")
            params = {
                "filters": json.dumps(filters),
                "fields": json.dumps(fields),
                "limit_page_length": 50,
                "order_by": "modified desc",
            }

            url = f"{self.primary_frappe_site_url}/api/resource/{resource}"
            headers = {"Accept": "application/json"}
            self.output.append(f"[Cane Inward Slip Records] Fetching submitted records: {url}")

            response = self.primary_frappe_session.get(url, params=params, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json().get("data", [])

            if not data:
                # QMessageBox.information(self, "No Records", "No submitted Cane Inward Slip records found.")
                self.output.append("[Cane Inward Slip Records] No records found.")
                return

            # Create dialog to display records
            dialog = QDialog(self)
            dialog.setWindowTitle("Submitted Cane Inward Slip Records")
            dialog.resize(1000, 600)
            dialog_layout = QVBoxLayout(dialog)

            table = QTableWidget()
            table.setColumnCount(len(fields))
            table.setHorizontalHeaderLabels(fields)
            table.setRowCount(len(data))
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.setSelectionBehavior(QTableWidget.SelectRows)

            for row_idx, record in enumerate(data):
                for col_idx, field in enumerate(fields):
                    value = record.get(field, "")
                    table.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))

            header = table.horizontalHeader()
            for i in range(len(fields)):
                header.setSectionResizeMode(i, QHeaderView.Stretch)

            dialog_layout.addWidget(table)

            button_layout = QHBoxLayout()
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.close)
            button_layout.addWidget(close_btn)

            dialog_layout.addLayout(button_layout)
            dialog.exec_()

        except requests.exceptions.HTTPError as e:
            response = e.response
            response_text = response.text if response is not None else "No response text"
            error_msg = f"HTTP {response.status_code if response is not None else 'N/A'}: {response_text}"
            self.output.append(f"[Cane Inward Slip Records] Fetch failed: {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to fetch records: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            self.output.append(f"[Cane Inward Slip Records] Network error: {error_msg}")
            QMessageBox.critical(self, "Network Error", f"Failed to fetch records: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Cane Inward Slip Records] Unexpected error: {error_msg}")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {error_msg}")
    
    def closeEvent(self, event):
        if self.connected and self.reader:
            self.reader.stop()
            self.reader.wait(1000)

        # Cleanly close the RFID socket/threads on exit
        self.stop_rfid_connection()

        # Logout from primary Frappe instance when MainWindow closes
        if self.primary_frappe_logged_in:
            try:
                self.primary_frappe_session.post(f"{self.primary_frappe_site_url}/api/method/logout")
                self.output.append("[Frappe] Logged out from Primary Frappe on exit.")
            except Exception as e:
                self.output.append(f"[Frappe Error] Failed to log out from Primary Frappe on exit: {e}")
        
        # Logout from Trip Sheet instance if logged in
        if self.trip_sheet_frappe_logged_in:
            try:
                self.trip_sheet_frappe_session.post(f"{self.trip_sheet_frappe_site_url}/api/method/logout")
                self.output.append("[Frappe] Logged out from Trip Sheet Frappe on exit.")
            except Exception as e:
                self.output.append(f"[Frappe Error] Failed to log out from Trip Sheet Frappe on exit: {e}")
        
        event.accept()

    def populate_form_from_trip_sheet_data(self, doc):
        """Populates the form fields using data from the Trip Sheet document."""
        self.clear_form() # Clear existing form data before populating
        
        # Map fields - Ensure slip_no is set properly
        if 'name' in doc:
            # Extract numeric part from trip sheet name (e.g., "TS-2025/001" -> 1)
            try:
                # Try to extract numeric part from the end of the name
                slip_name_parts = doc['name'].split('/')
                if len(slip_name_parts) > 1:
                    import re
                    clean_numeric = re.sub(r'[^\d]', '', slip_name_parts[-1].strip())
                    if clean_numeric:
                        slip_num = int(float(clean_numeric))
                        self.form_fields['slip_no'].setValue(slip_num)
                        self.output.append(f"[Trip Sheet] Set slip_no to {slip_num} from {doc['name']}")
                    else:
                        # Fallback: use the full name as string
                        self.form_fields['slip_no'].setValue(0)
                        self.output.append(f"[Trip Sheet] Could not extract numeric slip_no from {doc['name']}, set to 0")
                else:
                    self.form_fields['slip_no'].setValue(0)
                    self.output.append(f"[Trip Sheet] Invalid slip name format: {doc['name']}")
            except (ValueError, IndexError) as e:
                self.form_fields['slip_no'].setValue(0)
                self.output.append(f"[Trip Sheet] Error extracting slip_no: {e}, set to 0")
        
        # Rest of the existing mapping code...
        if 'season' in doc:
            self.form_fields['season'].setCurrentText(doc['season'])
        if 'branch' in doc:
            self.form_fields['branch'].setCurrentText(doc['branch'])
        if 'posting_date' in doc:
            date = QDate.fromString(doc['posting_date'], "yyyy-MM-dd")
            if date.isValid():
                self.form_fields['posting_date'].setDate(date)
        if 'farmer' in doc:
            self.form_fields['farmer'].setText(doc['farmer'])
        if 'farmer_name' in doc:
            self.form_fields['farmer_name'].setText(doc['farmer_name'])
        if 'area_in_acrs' in doc:
            self.form_fields['area_in_acrs'].setText(str(doc['area_in_acrs']))
        if 'circle_office' in doc:
            self.form_fields['circle_office'].setText(doc['circle_office'])
        if 'survey_number' in doc:
            self.form_fields['survey_number'].setText(str(doc['survey_number']))
        if 'is_kisan_card' in doc:
            self.form_fields['is_kisan_card'].setChecked(bool(doc['is_kisan_card']))
        if 'transporter' in doc:
            self.form_fields['transporter'].setText(doc['transporter'])
        if 'transporter_name' in doc:
            self.form_fields['transporter_name'].setText(doc['transporter_name'])
        if 'vehicle_no' in doc:
            self.form_fields['vehicle_no'].setText(doc['vehicle_no'])
        if 'transporter_vehicle_type' in doc:
            self.form_fields['transporter_vehicle_type'].setText(doc['transporter_vehicle_type'])
        if 'trolly_1' in doc:
            self.form_fields['trolly_1'].setText(str(doc['trolly_1']))
        if 'trolly_2' in doc:
            self.form_fields['trolly_2'].setText(str(doc['trolly_2']))
        if 'transporter_gang_type' in doc:
            self.form_fields['transporter_gang_type'].setText(doc['transporter_gang_type'])
        if 'harvester' in doc:
            self.form_fields['harvester'].setText(doc['harvester'])
        if 'harvester_name' in doc:
            self.form_fields['harvester_name'].setText(doc['harvester_name'])
        if 'rope_placement' in doc:
            self.form_fields['rope_placement'].setText(doc['rope_placement'])
        if 'distance' in doc:
            self.form_fields['distance'].setValue(int(doc['distance']))
        if 'route' in doc:
            self.form_fields['route'].setText(doc['route'])
        if 'crop_variety' in doc:
            self.form_fields['crop_variety'].setText(doc['crop_variety'])
        if 'transporter_contract' in doc:
            self.form_fields['transporter_contract'].setText(doc['transporter_contract'])
        if 'harvester_contract' in doc:
            self.form_fields['harvester_contract'].setText(doc['harvester_contract'])
        if 'crop_type' in doc:
            self.form_fields['crop_type'].setText(doc['crop_type'])
        if 'token_no' in doc:
            self.form_fields['token_no'].setText(str(doc.get('token_no', '')))
        if 'is_flat_rate' in doc:
            self.form_fields['is_flat_rate'].setChecked(bool(doc['is_flat_rate']))
        if 'trip_sheet' in doc:
            self.form_fields['trip_sheet'].setText(doc.get('name', ''))
        if 'cane_registration' in doc:
            self.form_fields['cane_registration'].setText(doc.get('cane_registration', ''))
        if 'harvester_vehicle_type' in doc:
            self.form_fields['harvester_vehicle_type'].setText(doc.get('harvester_vehicle_type', ''))
        if 'harvester_gang_type' in doc:
            self.form_fields['harvester_gang_type'].setText(doc.get('harvester_gang_type', ''))
        
        self.output.append(f"[Trip Sheet] Populated form from {doc['name']} with slip_no: {self.form_fields['slip_no'].value()}")
        
        # Auto-populate penalty charges after loading the form
        self.output.append("[Trip Sheet] Auto-populating penalty charges...")
        self.auto_populate_penalty_charges(show_success_message=False)

    def on_fuel_sale_params_changed(self):
        # This method will be called whenever the fuel sale parameters change
        # You can add any additional logic you want to execute when these parameters change
        # Trigger re-fetching fuel sale items
        current_fuel_sale_type = self.fuel_sale_fields["fuel_sale_type"].currentText()
        if current_fuel_sale_type and not current_fuel_sale_type.lower().startswith("loading") and not current_fuel_sale_type.lower().startswith("no "):
            self.output.append(f"[Fuel Sale] Parameters changed, re-fetching items for type '{current_fuel_sale_type}'...")
            self.fetch_items_for_fuel_sale_type(current_fuel_sale_type)

    def fetch_contracts_for_auto_token(self):
        """Fetch contracts for selected season and branch and populate transporter contract combo."""
        try:
            season = self.auto_token_fields["season"].currentText()
            branch = self.auto_token_fields["branch"].currentText()
            if not season or not branch or season.startswith("No ") or branch.startswith("No "):
                combo: QComboBox = self.auto_token_fields.get("transporter_contract")
                if combo:
                    combo.blockSignals(True)
                    combo.clear()
                    combo.addItem("Select season and branch")
                    combo.blockSignals(False)
                return
            url = f"{self.trip_sheet_api_base}/api/method/quantbit_agriculture_crm.agriculture_utils.get_contractss"
            headers = {
                "Authorization": f"token {self.trip_sheet_api_key}:{self.trip_sheet_api_secret}",
                "Accept": "application/json",
            }
            params = {"season": season, "branch": branch, "company": "Quantbit Sugar Pvt Ltd"}
            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            result = response.json()
            contracts = []
            if isinstance(result, dict):
                if "message" in result and isinstance(result["message"], list):
                    contracts = result["message"]
                elif "data" in result and isinstance(result["data"], list):
                    contracts = result["data"]
            combo: QComboBox = self.auto_token_fields.get("transporter_contract")
            if not combo:
                return
            combo.blockSignals(True)
            combo.clear()
            if contracts:
                for name in contracts:
                    combo.addItem(str(name))
                combo.setCurrentIndex(0)
                self.output.append(f"[Auto Token] Loaded {len(contracts)} contracts for {season}, {branch}.")
                self.fetch_transporter_data_for_auto_token() # Direct call to ensure data population
            else:
                combo.addItem("No contracts found")
                self.output.append(f"[Auto Token] No contracts for {season}, {branch}.")
                self.fetch_transporter_data_for_auto_token() # Direct call for clearing fields
            combo.blockSignals(False)
        except requests.exceptions.HTTPError as e:
            self.output.append(f"[Auto Token Contracts] HTTP {e.response.status_code}: {e.response.text}")
        except requests.exceptions.RequestException as e:
            self.output.append(f"[Auto Token Contracts] Network error: {str(e)}")
        except Exception as e:
            self.output.append(f"[Auto Token Contracts] Unexpected error: {str(e)}")

    def fetch_transporter_data_for_auto_token(self):
        """Fetch transporter data for selected transporter contract and populate relevant fields."""
        try:
            transporter_contract = self.auto_token_fields["transporter_contract"].currentText()
            if not transporter_contract or transporter_contract.startswith("No ") or transporter_contract.startswith("Loading "):
                self.auto_token_fields["transporter"].setText("")
                self.auto_token_fields["transporter_name"].setText("")
                self.auto_token_fields["transporter_vehicle_type"].setText("")
                self.auto_token_fields["transporter_gang_type"].setText("")
                self.auto_token_fields["vehicle_no"].setText("")
                return

            url = f"{self.trip_sheet_api_base}/api/method/quantbit_agriculture_crm.agriculture_utils.transporter_data"
            headers = {
                "Authorization": f"token {self.trip_sheet_api_key}:{self.trip_sheet_api_secret}",
                "Accept": "application/json",
            }
            params = {"transporter_contract": transporter_contract}
            # self.output.append(f"[Auto Token] Parameters passed to get_trip_sheet: {params}") # Revert this line
            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            result = response.json()
            transporter_data = []
            if isinstance(result, dict):
                if "message" in result and isinstance(result["message"], list):
                    transporter_data = result["message"]
                elif "data" in result and isinstance(result["data"], list):
                    transporter_data = result["data"]

            if transporter_data:
                # Assuming only one result is expected for a given contract
                data = transporter_data[0]
                self.auto_token_fields["transporter"].setText(data.get("transporter", ""))
                self.auto_token_fields["transporter_name"].setText(data.get("transporter_name", ""))
                
                # For QComboBox, find text and set current index
                vehicle_type_combo: QComboBox = self.auto_token_fields.get("transporter_vehicle_type")
                if vehicle_type_combo:
                    vehicle_type = data.get("vehicle_type", "")
                    index = vehicle_type_combo.findText(vehicle_type)
                    if index >= 0:
                        vehicle_type_combo.setCurrentIndex(index)
                    else:
                        # If not found, add it and select it
                        vehicle_type_combo.addItem(vehicle_type)
                        vehicle_type_combo.setCurrentText(vehicle_type)

                self.auto_token_fields["transporter_gang_type"].setText(data.get("gang_type", ""))
                self.auto_token_fields["vehicle_no"].setText(data.get("vehicle_no", ""))
                self.output.append(f"[Auto Token] Loaded transporter data for contract {transporter_contract}.")
            else:
                self.auto_token_fields["transporter"].setText("")
                self.auto_token_fields["transporter_name"].setText("")
                
                # For QComboBox, clear and add placeholder
                vehicle_type_combo: QComboBox = self.auto_token_fields.get("transporter_vehicle_type")
                if vehicle_type_combo:
                    vehicle_type_combo.clear()
                    vehicle_type_combo.addItem("Loading...")

                self.auto_token_fields["transporter_gang_type"].setText("")
                self.auto_token_fields["vehicle_no"].setText("")
                self.output.append(f"[Auto Token] No transporter data found for contract {transporter_contract}.")
        except requests.exceptions.HTTPError as e:
            self.output.append(f"[Auto Token Transporter Data] HTTP {e.response.status_code}: {e.response.text}")
        except requests.exceptions.RequestException as e:
            self.output.append(f"[Auto Token Transporter Data] Network error: {str(e)}")
        except Exception as e:
            self.output.append(f"[Auto Token Transporter Data] Unexpected error: {str(e)}")

    def fetch_shift_season_factory_day_for_auto_token(self):
        """Fetch shift, season day, and factory day from API and set on form."""
        try:
            posting_date = self.auto_token_fields["posting_date"].date().toString("yyyy-MM-dd")
            posting_time = self.auto_token_fields["posting_time"].time().toString("HH:mm:ss")
            season = self.auto_token_fields["season"].currentText()
            url = f"{self.trip_sheet_api_base}/api/method/quantbit_agriculture_crm.agriculture_utils.get_shift_season_factory_day"
            headers = {
                "Authorization": f"token {self.trip_sheet_api_key}:{self.trip_sheet_api_secret}",
                "Accept": "application/json",
            }
            params = {"posting_date": posting_date, "posting_time": posting_time, "season": season}
            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            result = response.json()
            data = result.get("message") or result.get("data") or {}
            self.output.append(f"[Auto Token] Shift/Season/Factory day data: {data}")
            shift = data.get("shift", "")
            season_day = data.get("season_day", 0)
            factory_day = data.get("factory_day", 0)
            # Set values on form
            shift_combo: QComboBox = self.auto_token_fields.get("shift")
            if shift_combo:
                idx = shift_combo.findText(shift)
                if idx >= 0:
                    shift_combo.setCurrentIndex(idx)
                elif shift:
                    shift_combo.addItem(shift)
                    shift_combo.setCurrentText(shift)
            self.auto_token_fields["season_day"].setValue(season_day)
            self.auto_token_fields["factory_day"].setValue(factory_day)
            self.output.append(f"[Auto Token] Shift/Season/Factory day set: shift={shift}, season_day={season_day}, factory_day={factory_day}")
        except Exception as e:
            self.output.append(f"[Auto Token Error] Shift/Season/Factory day fetch failed: {str(e)}")

    def show_pending_slips_for_auto_token(self):
        """Fetch pending trip sheets from API and populate the auto token trip sheet table."""
        try:
            transporter_contract = self.auto_token_fields["transporter_contract"].currentText()
            branch = self.auto_token_fields["branch"].currentText()
            season = self.auto_token_fields["season"].currentText()

            if not (transporter_contract and branch and season) or \
               transporter_contract.startswith("No ") or transporter_contract.startswith("Loading ") or \
               branch.startswith("No ") or branch.startswith("Loading ") or \
               season.startswith("No ") or season.startswith("Loading "):
                QMessageBox.warning(self, "Input Error", "Season, Branch, and Transporter Contract are mandatory to show pending slips.")
                self.output.append("[Auto Token] Missing mandatory fields for fetching pending slips.")
                return

            url = f"{self.trip_sheet_api_base}/api/method/quantbit_agriculture_crm.agriculture_utils.get_trip_sheet"
            headers = {
                "Authorization": f"token {self.trip_sheet_api_key}:{self.trip_sheet_api_secret}",
                "Accept": "application/json",
            }
            params = {"transporter_contract": transporter_contract, "branch": branch, "season": season}
            self.output.append(f"[Auto Token] Parameters passed to get_trip_sheet: {params}")
            response = requests.get(url, headers=headers, params=params, timeout=20)
            response.raise_for_status()
            result = response.json()
            self.output.append(f"[Auto Token] Pending trip sheets response: {result}")
            trip_sheets = result.get("message") or result.get("data") or []
            self.output.append(f"[Auto Token] Pending trip sheets: {trip_sheets}")

            self.auto_token_trip_sheet_table.setRowCount(0) # Clear existing rows

            if trip_sheets:
                for row_idx, sheet in enumerate(trip_sheets):
                    self.auto_token_trip_sheet_table.insertRow(row_idx)

                    select_checkbox = QCheckBox()
                    select_checkbox.setChecked(True)
                    # Connect the checkbox state change to update the count
                    select_checkbox.stateChanged.connect(self.update_no_of_tripsheet_count)
                    self.auto_token_trip_sheet_table.setCellWidget(row_idx, 0, select_checkbox)

                    self.auto_token_trip_sheet_table.setItem(row_idx, 1, QTableWidgetItem(str(sheet.get("season", ""))))
                    self.auto_token_trip_sheet_table.setItem(row_idx, 2, QTableWidgetItem(str(sheet.get("branch", ""))))
                    self.auto_token_trip_sheet_table.setItem(row_idx, 3, QTableWidgetItem(str(sheet.get("posting_date", ""))))
                    self.auto_token_trip_sheet_table.setItem(row_idx, 4, QTableWidgetItem(str(sheet.get("name", "")))) # Trip Sheet No
                    self.auto_token_trip_sheet_table.setItem(row_idx, 5, QTableWidgetItem(str(sheet.get("rope_placement", ""))))
                    self.auto_token_trip_sheet_table.setItem(row_idx, 6, QTableWidgetItem(str(sheet.get("cane_registration", ""))))
                    self.auto_token_trip_sheet_table.setItem(row_idx, 7, QTableWidgetItem(str(sheet.get("route", ""))))
                    self.auto_token_trip_sheet_table.setItem(row_idx, 8, QTableWidgetItem(str(sheet.get("area_in_acrs", ""))))
                    self.auto_token_trip_sheet_table.setItem(row_idx, 9, QTableWidgetItem(str(sheet.get("farmer", ""))))
                    self.auto_token_trip_sheet_table.setItem(row_idx, 10, QTableWidgetItem(str(sheet.get("distance", ""))))
                    self.auto_token_trip_sheet_table.setItem(row_idx, 11, QTableWidgetItem(str(sheet.get("transporter_contract", ""))))
                    self.auto_token_trip_sheet_table.setItem(row_idx, 12, QTableWidgetItem(str(sheet.get("transporter", ""))))
                    self.auto_token_trip_sheet_table.setItem(row_idx, 13, QTableWidgetItem(str(sheet.get("harvester_contract", "")))) # New column
                    self.auto_token_trip_sheet_table.setItem(row_idx, 14, QTableWidgetItem(str(sheet.get("harvester", "")))) # New column

                self.output.append(f"[Auto Token] Loaded {len(trip_sheets)} pending trip sheets.")
                self.update_no_of_tripsheet_count() # Initial update after loading
            else:
                QMessageBox.information(self, "No Pending Slips", "No pending trip sheets found for the selected criteria.")
                self.output.append("[Auto Token] No pending trip sheets found.")
                self.update_no_of_tripsheet_count() # Clear count if no slips found

        except requests.exceptions.HTTPError as e:
            self.output.append(f"[Auto Token Pending Slips] HTTP {e.response.status_code}: {e.response.text}")
            QMessageBox.critical(self, "API Error", f"Failed to fetch pending slips: {e.response.status_code} - {e.response.text}")
        except requests.exceptions.RequestException as e:
            self.output.append(f"[Auto Token Pending Slips] Network error: {str(e)}")
            QMessageBox.critical(self, "Network Error", f"Failed to fetch pending slips: {str(e)}")
        except Exception as e:
            self.output.append(f"[Auto Token Pending Slips] Unexpected error: {str(e)}")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {str(e)}")


    def view_submitted_cane_weight_records(self):
        if not self.primary_frappe_logged_in:
            QMessageBox.warning(self, "Warning", "Not logged in to Primary Frappe instance. Please login first.")
            self.output.append("[Cane Weight Records] View aborted: not logged in to primary instance.")
            return

        if not self.primary_frappe_site_url:
            QMessageBox.warning(self, "Warning", "Primary Frappe site URL is not configured.")
            self.output.append("[Cane Weight Records] View aborted: primary site URL missing.")
            return

        try:
            filters = [["docstatus", "=", 1]]
            fields = [
                "name", "season", "branch", "trip_sheet", "farmer_name",
                "vehicle_no", "net_weight", "modified"
            ]
            resource = quote("Cane Weight")
            params = {
                "filters": json.dumps(filters),
                "fields": json.dumps(fields),
                "limit_page_length": 50,
                "order_by": "modified desc",
            }

            url = f"{self.primary_frappe_site_url}/api/resource/{resource}"
            headers = {"Accept": "application/json"}
            self.output.append(f"[Cane Weight Records] Fetching submitted records: {url} | params={params}")

            data = []
            try:
                response = self.primary_frappe_session.get(url, params=params, headers=headers, timeout=20)
                response.raise_for_status()
                data = response.json().get("data", [])
            except requests.exceptions.HTTPError as primary_error:
                primary_response = primary_error.response
                status = primary_response.status_code if primary_response is not None else "N/A"
                text = primary_response.text if primary_response is not None else "No response text"
                self.output.append(
                    f"[Cane Weight Records] Primary fetch failed with HTTP {status}: {text}"
                )

                fallback_payload = {
                    "doctype": "Cane Weight",
                    "filters": filters,
                    "fields": fields,
                    "order_by": "modified desc",
                    "limit_page_length": 50,
                }
                fallback_url = f"{self.primary_frappe_site_url}/api/method/frappe.client.get_list"
                fallback_headers = {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                }
                self.output.append(
                    f"[Cane Weight Records] Falling back to frappe.client.get_list via {fallback_url}"
                )
                fallback_response = self.primary_frappe_session.post(
                    fallback_url,
                    json=fallback_payload,
                    headers=fallback_headers,
                    timeout=20,
                )
                fallback_response.raise_for_status()
                fallback_json = fallback_response.json()
                data = fallback_json.get("message") or fallback_json.get("data") or []

            if not data:
                QMessageBox.information(self, "No Records", "No submitted Cane Weight records were found.")
                self.output.append("[Cane Weight Records] No submitted records returned.")
                return

            dialog = QDialog(self)
            dialog.setWindowTitle("Submitted Cane Weight Records")
            dialog.resize(900, 400)

            dialog_layout = QVBoxLayout(dialog)
            table = QTableWidget(len(data), len(fields))
            table.setHorizontalHeaderLabels([
                "Name", "Season", "Branch", "Slip No", "Farmer",
                "Vehicle Number", "Cane Weight", "Modified"
            ])
            table.setSelectionMode(QAbstractItemView.SingleSelection)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)

            header = table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.Stretch)

            for row, record in enumerate(data):
                table.setItem(row, 0, QTableWidgetItem(str(record.get("name", ""))))
                table.setItem(row, 1, QTableWidgetItem(str(record.get("season", ""))))
                table.setItem(row, 2, QTableWidgetItem(str(record.get("branch", ""))))
                table.setItem(row, 3, QTableWidgetItem(str(record.get("trip_sheet", ""))))
                table.setItem(row, 4, QTableWidgetItem(str(record.get("farmer_name", ""))))
                table.setItem(row, 5, QTableWidgetItem(str(record.get("vehicle_no", ""))))
                table.setItem(row, 6, QTableWidgetItem(str(record.get("net_weight", ""))))
                table.setItem(row, 7, QTableWidgetItem(str(record.get("modified", ""))))

            dialog_layout.addWidget(table)

            def load_selected_record():
                selected_rows = table.selectionModel().selectedRows()
                if not selected_rows:
                    QMessageBox.warning(dialog, "Selection Required", "Please select a record to load.")
                    return
                row = selected_rows[0].row()
                doc_item = table.item(row, 0)
                if not doc_item:
                    QMessageBox.warning(dialog, "Invalid Selection", "Unable to determine the document to load.")
                    return
                doc_name = doc_item.text().strip()
                if not doc_name:
                    QMessageBox.warning(dialog, "Invalid Selection", "Selected record is missing a document name.")
                    return

                if self.load_cane_weight_record(doc_name):
                    dialog.accept()

            table.itemDoubleClicked.connect(lambda _: load_selected_record())

            button_layout = QHBoxLayout()
            load_btn = QPushButton("Load Selected")
            load_btn.clicked.connect(load_selected_record)
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.reject)
            button_layout.addStretch()
            button_layout.addWidget(load_btn)
            button_layout.addWidget(close_btn)
            dialog_layout.addLayout(button_layout)

            dialog.exec()

        except requests.exceptions.HTTPError as e:
            response = e.response
            response_text = response.text if response is not None else "No response text"
            error_msg = f"HTTP {response.status_code if response is not None else 'N/A'}: {response_text}"
            self.output.append(f"[Cane Weight Records] Fetch failed: {error_msg}")
            QMessageBox.critical(self, "Error", f"Failed to fetch records: {error_msg}")
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            self.output.append(f"[Cane Weight Records] Network error: {error_msg}")
            QMessageBox.critical(self, "Network Error", f"Failed to fetch records: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            self.output.append(f"[Cane Weight Records] Unexpected error: {error_msg}")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {error_msg}")


    # RFID Connection Methods
    def bytes_to_hex_string(self, data):
        """Convert bytes to hex string."""
        hex_string = "".join(format(byte, '02X') for byte in data)
        return hex_string

    def rfid_read_weight(self):
        """Read RFID data from socket connection."""
        while self.rfid_running:
            try:
                if self.rfid_socket is None:
                    time.sleep(1)
                    continue
                    
                ready_sockets, _, _ = select.select([self.rfid_socket], [], [], 0.1)
            except select.error:
                continue

            for sock in ready_sockets:
                if sock == self.rfid_socket:
                    try:
                        # Data received from the socket
                        data = self.rfid_socket.recv(1024)
                        if not data:
                            # Socket connection is closed
                            self.output.append("[RFID] Socket connection closed by the remote host.")
                            self.rfid_running = False
                            if hasattr(self, "rfid_status_label"):
                                self.rfid_status_label.setText("Status: Disconnected (use Save & Reconnect in Settings)")
                            return

                        self.rfid_hex_string = self.bytes_to_hex_string(data)
                        self.output.append(f"[RFID] Received: {self.rfid_hex_string}")
                        
                        # Update the RFID Data field in the UI
                        if "rfid_data" in self.cane_inward_slip_fields:
                            self.cane_inward_slip_fields["rfid_data"].setText(self.rfid_hex_string)
                    except Exception as e:
                        self.output.append(f"[RFID] Error reading data: {str(e)}")

    def rfid_send_weight(self):
        """Send RFID data to API endpoint."""
        prev_rfid_connected = False  # Store the previous RFID connection status
        while self.rfid_running:
            try:
                if self.rfid_hex_string is not None:
                    data = {"rfid_1": self.rfid_hex_string, "doctype": "Rfid tag Reading", "module": "RFID"}
                    headers = {'Authorization': f'Token {self.rfid_api_token}'}
                    response = requests.put(self.rfid_api_endpoint, data=data, headers=headers, timeout=10)

                    if response.status_code == 200:
                        self.output.append("[RFID] Data sent to Frappe successfully!")
                    else:
                        self.output.append(f"[RFID] Failed to send data to Frappe. Status code: {response.status_code}")
                        self.output.append(f"[RFID] Response: {response.text}")

                if prev_rfid_connected != (self.rfid_hex_string is not None):
                    status_data = {
                        'rfid1_status': 'Connected.' if self.rfid_hex_string is not None else 'Not Connected.',
                        "doctype": "Rfid tag Reading",
                        "module": "RFID",
                        "ip_of_rfid1": self.rfid_local_ip,
                        "rfid_1": ""
                    }

                    response = requests.put(self.rfid_api_endpoint, data=status_data, headers=headers, timeout=10)
                    if response.status_code != 200:
                        self.output.append(f"[RFID] Failed to send status data to Frappe. Status code: {response.status_code}")
                        self.output.append(f"[RFID] Response: {response.text}")

                    prev_rfid_connected = self.rfid_hex_string is not None

                self.rfid_hex_string = None
                time.sleep(0.1)

            except requests.exceptions.RequestException as e:
                self.output.append(f"[RFID] API error: {e}")
                prev_rfid_connected = False
                time.sleep(2)
            
            time.sleep(0.5)

    def start_rfid_connection(self):
        """Initialize and start RFID socket connection."""
        self.rfid_running = True
        
        # Try to connect to RFID socket
        while self.rfid_running:
            try:
                self.rfid_socket = socket.socket()
                self.rfid_socket.connect((self.rfid_ip, self.rfid_port))
                self.rfid_socket.setblocking(0)
                self.output.append(f"[RFID] Socket connection established on IP: {self.rfid_local_ip}")
                self.output.append(f"[RFID] Connected to {self.rfid_ip}:{self.rfid_port}")
                if hasattr(self, "rfid_status_label"):
                    self.rfid_status_label.setText(f"Status: Connected to {self.rfid_ip}:{self.rfid_port}")
                break
            except socket.error as e:
                self.output.append(f"[RFID] Socket error: {e}")
                if hasattr(self, "rfid_status_label"):
                    self.rfid_status_label.setText(f"Status: Retrying connection to {self.rfid_ip}:{self.rfid_port}...")
                time.sleep(2)

        # Start read and send threads
        self.rfid_read_thread = threading.Thread(target=self.rfid_read_weight, daemon=True)
        self.rfid_send_thread = threading.Thread(target=self.rfid_send_weight, daemon=True)

        self.rfid_read_thread.start()
        self.rfid_send_thread.start()
        
        self.output.append("[RFID] RFID connection threads started successfully")

    def stop_rfid_connection(self):
        """Stop RFID connection and close socket."""
        self.rfid_running = False

        if self.rfid_socket:
            try:
                self.rfid_socket.close()
                self.output.append("[RFID] Socket connection closed")
            except Exception as e:
                self.output.append(f"[RFID] Error closing socket: {str(e)}")
        self.rfid_socket = None

        if hasattr(self, "rfid_status_label"):
            self.rfid_status_label.setText("Status: Disconnected")

        self.output.append("[RFID] RFID connection stopped")


class LoginPage(QWidget):
    login_successful = Signal(str, str, str, object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Quantbit Cane Weighbridge – Smart, Simple, Secure")
        self.setGeometry(200, 200, 400, 250)
        
        self.setup_ui()
        self.setup_styles()
        self.setWindowIcon(self.load_logo_icon())
        
        self.session = requests.Session()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title_label = QLabel("Log In to Quantbit Cane Weighbridge System")
        title_label.setObjectName("titleLabel")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        form_layout = QGridLayout()
        form_layout.setSpacing(10)

        form_layout.addWidget(QLabel("Site URL:"), 0, 0)
        self.site_url_input = QLineEdit()
        self.site_url_input.setPlaceholderText("e.g., http://103.219.1.138:4424/")
        self.site_url_input.setText("https://uatkranti.quantcloud.in")
        form_layout.addWidget(self.site_url_input, 0, 1)

        form_layout.addWidget(QLabel("Username:"), 1, 0)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter Username")
        self.username_input.setText("administrator")
        form_layout.addWidget(self.username_input, 1, 1)

        form_layout.addWidget(QLabel("Password:"), 2, 0)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Enter Password")
        self.password_input.setText("erpadmin")
        form_layout.addWidget(self.password_input, 2, 1)

        layout.addLayout(form_layout)

        self.login_btn = QPushButton("Login")
        self.login_btn.setObjectName("loginBtn")
        self.login_btn.setMinimumHeight(35)
        self.login_btn.clicked.connect(self.attempt_login)
        layout.addWidget(self.login_btn)

        layout.addStretch()
        self.setLayout(layout)

    def load_logo_icon(self):
        """Load the logo image from URL and create a QIcon for the window."""
        logo_url = "https://media.licdn.com/dms/image/v2/D560BAQEMpaC_iBLQyw/company-logo_200_200/company-logo_200_200/0/1719257928420/quantbit_technologies_logo?e=2147483647&v=beta&t=B5LgukVqoYKt0Pls_rXBAjLhnqrHmi5yTxX1k9cKcz0"
        logo_pixmap = QPixmap()
        
        try:
            response = requests.get(logo_url)
            response.raise_for_status()  # Raise error for bad status codes
            if logo_pixmap.loadFromData(response.content):
                # Scale for icon (window icons are small; 32x32 or 64x64 works well)
                logo_pixmap = logo_pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                icon = QIcon(logo_pixmap)
                return icon
            else:
                raise ValueError("Failed to load pixmap from data")
        except Exception as e:
            # Fallback: Create a simple colored icon with text "QT" (Quantbit)
            fallback_pixmap = QPixmap(64, 64)
            fallback_pixmap.fill(QColor("#667eea"))  # Blue background
            # painter = QPainter(fallback_pixmap)
            # painter.setPen(QColor("white"))
            # painter.setFont(QFont("Arial", 24, QFont.Bold))
            # painter.drawText(fallback_pixmap.rect(), Qt.AlignCenter, "QT")
            # painter.end()
            fallback_icon = QIcon(fallback_pixmap)
            
            # Log error if output is available
            if hasattr(self, 'output'):
                self.output.append(f"[Window Icon] Failed to load logo from {logo_url}: {str(e)}. Using fallback icon.")
            
            return fallback_icon

    def setup_styles(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #f0f2f5;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            #titleLabel {
                color: #2c3e50;
                font-size: 20px;
                font-weight: bold;
                margin-bottom: 15px;
            }
            QLineEdit {
                padding: 8px;
                border: 1px solid #cccccc;
                border-radius: 5px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border-color: #3498db;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #21618c;
            }
        """)
    
    def attempt_login(self):
        site_url = self.site_url_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not site_url or not username or not password:
            QMessageBox.warning(self, "Login Error", "Please fill in all fields!")
            return
        
        if not (site_url.startswith("http://") or site_url.startswith("https://")):
            QMessageBox.warning(self, "Login Error", "Site URL must start with http:// or https://")
            return

        try:
            response = self.session.post(
                f"{site_url}/api/method/login",
                json={"usr": username, "pwd": password}
            )
            response.raise_for_status()
            self.login_successful.emit(site_url, username, password, self.session)
            self.close()
        except requests.exceptions.HTTPError as e:
            error_msg = f"Login failed: HTTP {e.response.status_code}: {e.response.text}"
            QMessageBox.critical(self, "Login Error", error_msg)
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error during login: {str(e)}"
            QMessageBox.critical(self, "Login Error", error_msg)
        except Exception as e:
            error_msg = f"An unexpected error occurred: {str(e)}"
            QMessageBox.critical(self, "Login Error", error_msg)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("RS232 Terminal")
    app.setApplicationVersion("2.0")
    
    login_page = LoginPage()
    # When login is successful, connect to a slot to show the main window
    login_page.login_successful.connect(lambda site_url, username, password, session: show_main_window(site_url, username, password, session, app))
    login_page.show()
    
    def show_main_window(site_url, username, password, session, app_instance):
        window = MainWindow(site_url, username, password, session)
        window.show()
        # The login_page is closed, but we need to ensure the application exits when MainWindow closes
        app_instance.lastWindowClosed.connect(app_instance.quit)

    sys.exit(app.exec())