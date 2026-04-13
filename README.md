# Network Config Auditor (FastAPI + PyATS Genie + Ollama)

Professional project for automatically analyzing Cisco IOS-XE, NX-OS, IOS-XR, AireOS (WLC), and IOS configuration files and auditing compliance based on Golden Configs. It provides structured analysis via PyATS Genie and intelligent report refinement using Ollama LLM.

---

## Key Features

### 1. Multi-Platform & Intelligent Golden Config Management
- **Multi-OS Support**: Supports IOS-XE, NX-OS, IOS-XR, AireOS (WLC), and classic IOS devices.
- **Auto Section Detection**: Analyzes indentation rules in IOS configurations to automatically classify sections like Interface, OSPF, BGP, ACLs, etc.
- **Visual Grouping**: Items are organized by logical section with distinct icons (🔗 for interfaces, 📂 for common configs) in both Golden and Compare tabs.
- **Bulk Item Management**: Group-level "Select All" and "Select None" controls for efficient template customization.

### 2. Robust Comparison Engine (Expert Audit)
- **Extreme Normalization**: Ignores whitespace variances, tabs, non-breaking spaces, and casing differences to eliminate false-negative mismatches.
- **Double-Layered Fallback**: If a specific configuration block is shadowed or moved, the engine performs a global section-wide search to ensure compliance.
- **Word Wrap Support**: Long configuration lines (e.g., complex description fields or long ACLs) are automatically wrapped for optimal readability.

### 3. Persistent History & Detailed Viewing
- **Audit Archive**: Every audit run is saved to the SQLite database.
- **Interactive Result Modal**: Historic results in the "Report" tab can be revisited at any time via a dedicated Modal UI that mirrors the real-time execution view.
- **Dynamic Decision Making**: Choose between immediate feedback in the "Compare" tab and long-term audit tracking in the "Report" tab.

### 4. Hostname-Based Dynamic Actions (Conditional Rules)
- **Regex-Based Matching**: Analyzes device hostnames using regular expressions.
- **Conditional Validation**: Loads dynamic actions, e.g., specifically including certain interface settings or ACLs only when the hostname matches `^SH-.*-AGG`.

### 5. Multi-Tier Audit Results (Pass / Review / Fail)
- **Pass**: All mandatory and optional items match the expected values.
- **Review**: Discrepancies or missing items for low-weight optional settings.
- **Fail**: Mandatory settings are missing or differ from expected values.

### 6. LLM-Based Report Enrichment
- **Ollama Integration**: Uses local LLMs to process audit results into professional-grade reports.
- **Impact Analysis**: Automatically analyzes the impact of violations on network infrastructure and provides remediation roadmaps.

### 7. Maintenance & Reliability
- **Automatic Migrations**: The system automatically updates the database schema when new features are added, ensuring zero-configuration upgrades.

---

## Tech Stack

- **Backend**: Python 3.12, FastAPI, Uvicorn
- **Parsing**: PyATS / Genie (Cisco Library)
- **Storage**: SQLite (SQLAlchemy)
- **LLM**: Ollama API (Local LLM)
- **Frontend**: Vanilla JS, CSS (Premium Dark Theme), HTML5

---

## Installation & Running

### Method 1: Using uv (Recommended - Fast)
`uv` is an extremely fast Python package manager written in Rust.
```bash
# 1. Create virtual environment and sync packages
# (Automatically detects pyproject.toml or requirements.txt)
uv venv
source .venv/bin/activate  # or .venv\Scripts\activate

# 2. Install packages
uv pip install -r requirements.txt

# 3. Run server
cd webapp
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

### Method 2: Using pip and venv
```bash
# Create and enter virtual environment
python -m venv .venv
source .venv/bin/activate

# Install required packages
spip install -r requirements.txt

# Run server
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## 🗄 Database Configuration (SQLite)

This project uses **SQLite**, which is ready for immediate use without additional DB server installation.

- **Location**: Stored as a file at `webapp/data.db`.
- **ORM**: Handles data modeling and queries via SQLAlchemy.
- **Main Tables**:
  - `templates`: Golden Config items, hostname Regex, conditional rule definitions.
  - `results`: Audit execution history and detailed Pass/Fail data.
  - `settings`: System configuration values like Ollama URL and model used.

---

## 📂 File & Template Management

All data in this project is managed locally within the project folder, minimizing risk of external data leakage.

1. **Uploaded Config Files**:
   - **Location**: `webapp/uploads/`
   - **Description**: Temporary configuration files uploaded via the browser for comparison and analysis. These are included in `.gitignore` and not stored in Git.

2. **Golden Config Templates**:
   - **Location**: `webapp/data.db` (Inside SQLite)
   - **Description**: Stored as serialized entries in the `templates` table instead of separate JSON/YAML files. This allows for easy modification, deletion, and version management via the UI.

3. **Audit Result Reports**:
   - **Location**: `webapp/data.db` (Inside SQLite)
   - **Description**: All audit history, scores, and detailed mismatch results are stored in the DB for future retrieval.

### 3. Ollama Installation (For LLM Features)
```bash
# Install from https://ollama.ai/ and download model
ollama pull llama3  # Recommended model
ollama serve
```

---

## How to Use

1. **[Golden Tab]**: Upload a baseline configuration file to create a template. (Dynamic rules per hostname can be configured)
2. **[Compare Tab]**: Upload audit target files to check results.
3. **[Report Tab]**: Use LLM options to generate refined reports and copy/download them.
4. **[Bulk Tab]**: Perform large-scale auditing for enterprise-wide devices.

---

## Project Structure

```
/webapp
├── main.py              # FastAPI entry point and API definitions
├── core/
│   ├── parser.py        # Genie parser and section splitting logic
│   ├── comparator.py    # Pass/Review/Fail comparison and dynamic action engine
│   └── llm.py           # Ollama prompts and report refinement logic
├── db/
│   ├── database.py      # SQLite CRUD and settings table management
├── static/              # Frontend assets (Premium UI)
│   ├── index.html
│   ├── css/style.css
│   └── js/              # Reactive JS modules
└── data.db              # Local database
```

---
