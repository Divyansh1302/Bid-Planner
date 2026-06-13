"""
Bid Timeline Planner -- Flask Backend
=====================================
A professional bid-management scheduling tool that automatically calculates
and visualises a chronological RFP schedule from start / end dates.

Run:
    pip install flask
    python app.py
"""

from __future__ import annotations

import csv
import io
import json
import os
import math
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response, send_file

app = Flask(__name__)

# Directory for persisting saved plans
PLANS_DIR = Path(__file__).parent / "saved_plans"
PLANS_DIR.mkdir(exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE TEMPLATES
# ══════════════════════════════════════════════════════════════════════════════

TEMPLATES: dict[str, dict] = {
    "full": {
        "label": "Full Cycle -- Pink / Red / Gold",
        "description": "Standard 3-gate review process for large proposals.",
        "phases": [
            {"name": "RFP Receipt & Compliance Matrix", "category": "STRATEGY & PLANNING",   "pctStart": 0.00, "pctEnd": 0.06, "owner": "Bid Manager"},
            {"name": "Bid/No-Bid Decision",            "category": "STRATEGY & PLANNING",   "pctStart": 0.06, "pctEnd": 0.10, "owner": "Capture Lead"},
            {"name": "Kickoff Meeting",                "category": "GOVERNANCE",            "pctStart": 0.10, "pctEnd": 0.10, "owner": "Bid Manager"},
            {"name": "Solution Architecture & Design", "category": "SOLUTION & PRICING",    "pctStart": 0.10, "pctEnd": 0.40, "owner": "Solution Lead"},
            {"name": "Pricing Strategy",               "category": "SOLUTION & PRICING",    "pctStart": 0.10, "pctEnd": 0.45, "owner": "Pricing Lead"},
            {"name": "Pink Team Review",               "category": "REVIEWS",               "pctStart": 0.30, "pctEnd": 0.35, "owner": "Review Board"},
            {"name": "Storyboarding & Win Themes",     "category": "CONTENT DEVELOPMENT",   "pctStart": 0.35, "pctEnd": 0.50, "owner": "Proposal Writer"},
            {"name": "Proposal Draft 1",               "category": "CONTENT DEVELOPMENT",   "pctStart": 0.45, "pctEnd": 0.65, "owner": "Proposal Writer"},
            {"name": "Red Team Review",                "category": "REVIEWS",               "pctStart": 0.65, "pctEnd": 0.75, "owner": "Review Board"},
            {"name": "Proposal Draft 2 (Final)",       "category": "CONTENT DEVELOPMENT",   "pctStart": 0.75, "pctEnd": 0.88, "owner": "Proposal Writer"},
            {"name": "Gold Team Review",               "category": "REVIEWS",               "pctStart": 0.88, "pctEnd": 0.92, "owner": "Executive Sponsor"},
            {"name": "Final QA & Formatting",          "category": "GOVERNANCE",            "pctStart": 0.92, "pctEnd": 0.97, "owner": "Bid Manager"},
            {"name": "Submission",                     "category": "GOVERNANCE",            "pctStart": 1.00, "pctEnd": 1.00, "owner": "Bid Manager"},
        ],
    },
    "compressed": {
        "label": "Compressed -- Single Review Pass",
        "description": "Streamlined single-review process for fast-turnaround bids.",
        "phases": [
            {"name": "RFP Receipt & Compliance Matrix", "category": "STRATEGY & PLANNING",   "pctStart": 0.00, "pctEnd": 0.06, "owner": "Bid Manager"},
            {"name": "Bid/No-Bid Decision",            "category": "STRATEGY & PLANNING",   "pctStart": 0.06, "pctEnd": 0.10, "owner": "Capture Lead"},
            {"name": "Kickoff Meeting",                "category": "GOVERNANCE",            "pctStart": 0.10, "pctEnd": 0.10, "owner": "Bid Manager"},
            {"name": "Solution Architecture & Design", "category": "SOLUTION & PRICING",    "pctStart": 0.10, "pctEnd": 0.42, "owner": "Solution Lead"},
            {"name": "Pricing Strategy",               "category": "SOLUTION & PRICING",    "pctStart": 0.10, "pctEnd": 0.48, "owner": "Pricing Lead"},
            {"name": "Storyboarding & Win Themes",     "category": "CONTENT DEVELOPMENT",   "pctStart": 0.30, "pctEnd": 0.50, "owner": "Proposal Writer"},
            {"name": "Proposal Draft",                 "category": "CONTENT DEVELOPMENT",   "pctStart": 0.48, "pctEnd": 0.75, "owner": "Proposal Writer"},
            {"name": "Consolidated Review",            "category": "REVIEWS",               "pctStart": 0.75, "pctEnd": 0.85, "owner": "Review Board"},
            {"name": "Final Revisions & Formatting",   "category": "GOVERNANCE",            "pctStart": 0.85, "pctEnd": 0.97, "owner": "Bid Manager"},
            {"name": "Submission",                     "category": "GOVERNANCE",            "pctStart": 1.00, "pctEnd": 1.00, "owner": "Bid Manager"},
        ],
    },
    "government": {
        "label": "Government RFP",
        "description": "Compliance-heavy government procurement with LPTA/best-value structure.",
        "phases": [
            {"name": "RFP Receipt & Initial Review",     "category": "STRATEGY & PLANNING",   "pctStart": 0.00, "pctEnd": 0.04, "owner": "Bid Manager"},
            {"name": "Compliance Matrix & Shred-Out",     "category": "STRATEGY & PLANNING",   "pctStart": 0.04, "pctEnd": 0.10, "owner": "Compliance Lead"},
            {"name": "Bid/No-Bid Gate",                   "category": "GOVERNANCE",            "pctStart": 0.10, "pctEnd": 0.10, "owner": "Capture Manager"},
            {"name": "Kickoff & Author Assignments",      "category": "GOVERNANCE",            "pctStart": 0.11, "pctEnd": 0.11, "owner": "Bid Manager"},
            {"name": "Questions to Contracting Officer",   "category": "STRATEGY & PLANNING",   "pctStart": 0.10, "pctEnd": 0.18, "owner": "Contracts"},
            {"name": "Technical Volume Development",       "category": "CONTENT DEVELOPMENT",   "pctStart": 0.12, "pctEnd": 0.45, "owner": "Technical Lead"},
            {"name": "Management Volume Development",      "category": "CONTENT DEVELOPMENT",   "pctStart": 0.15, "pctEnd": 0.45, "owner": "PM Lead"},
            {"name": "Past Performance Volume",            "category": "CONTENT DEVELOPMENT",   "pctStart": 0.12, "pctEnd": 0.40, "owner": "Proposal Writer"},
            {"name": "Pricing / Cost Volume",              "category": "SOLUTION & PRICING",    "pctStart": 0.15, "pctEnd": 0.55, "owner": "Pricing Lead"},
            {"name": "Pink Team Review",                   "category": "REVIEWS",               "pctStart": 0.35, "pctEnd": 0.40, "owner": "Review Board"},
            {"name": "Red Team Review",                    "category": "REVIEWS",               "pctStart": 0.60, "pctEnd": 0.68, "owner": "Review Board"},
            {"name": "Final Draft & Integration",          "category": "CONTENT DEVELOPMENT",   "pctStart": 0.68, "pctEnd": 0.82, "owner": "Proposal Writer"},
            {"name": "Gold Team Review",                   "category": "REVIEWS",               "pctStart": 0.82, "pctEnd": 0.88, "owner": "Executive Sponsor"},
            {"name": "Compliance & Format Check",          "category": "GOVERNANCE",            "pctStart": 0.88, "pctEnd": 0.94, "owner": "Compliance Lead"},
            {"name": "Production & Packaging",             "category": "GOVERNANCE",            "pctStart": 0.94, "pctEnd": 0.98, "owner": "Bid Manager"},
            {"name": "Submission",                         "category": "GOVERNANCE",            "pctStart": 1.00, "pctEnd": 1.00, "owner": "Bid Manager"},
        ],
    },
    "commercial": {
        "label": "Commercial Proposal",
        "description": "Agile commercial bid with rapid turnaround and executive approval.",
        "phases": [
            {"name": "Opportunity Assessment",        "category": "STRATEGY & PLANNING",   "pctStart": 0.00, "pctEnd": 0.08, "owner": "Sales Lead"},
            {"name": "Go/No-Go Decision",             "category": "GOVERNANCE",            "pctStart": 0.08, "pctEnd": 0.08, "owner": "VP Sales"},
            {"name": "Kickoff & Strategy Session",    "category": "GOVERNANCE",            "pctStart": 0.10, "pctEnd": 0.10, "owner": "Bid Manager"},
            {"name": "Client Discovery & Needs",      "category": "STRATEGY & PLANNING",   "pctStart": 0.10, "pctEnd": 0.22, "owner": "Account Manager"},
            {"name": "Solution Design",               "category": "SOLUTION & PRICING",    "pctStart": 0.15, "pctEnd": 0.45, "owner": "Solution Architect"},
            {"name": "Commercial Pricing Model",      "category": "SOLUTION & PRICING",    "pctStart": 0.20, "pctEnd": 0.50, "owner": "Pricing Lead"},
            {"name": "Executive Summary & Win Themes", "category": "CONTENT DEVELOPMENT",  "pctStart": 0.35, "pctEnd": 0.50, "owner": "Proposal Writer"},
            {"name": "Proposal Drafting",             "category": "CONTENT DEVELOPMENT",   "pctStart": 0.45, "pctEnd": 0.70, "owner": "Proposal Writer"},
            {"name": "Internal Review",               "category": "REVIEWS",               "pctStart": 0.70, "pctEnd": 0.80, "owner": "Review Board"},
            {"name": "Final Edits & Design",          "category": "CONTENT DEVELOPMENT",   "pctStart": 0.80, "pctEnd": 0.92, "owner": "Graphic Designer"},
            {"name": "Executive Sign-Off",            "category": "GOVERNANCE",            "pctStart": 0.92, "pctEnd": 0.92, "owner": "VP Sales"},
            {"name": "Submission",                    "category": "GOVERNANCE",            "pctStart": 1.00, "pctEnd": 1.00, "owner": "Bid Manager"},
        ],
    },
    "it_services": {
        "label": "IT Services / MSP Bid",
        "description": "Technical services bid with SLA definition and transition planning.",
        "phases": [
            {"name": "RFP Analysis & Scoping",         "category": "STRATEGY & PLANNING",   "pctStart": 0.00, "pctEnd": 0.08, "owner": "Bid Manager"},
            {"name": "Bid/No-Bid Decision",            "category": "GOVERNANCE",            "pctStart": 0.08, "pctEnd": 0.08, "owner": "Delivery Director"},
            {"name": "Kickoff Meeting",                "category": "GOVERNANCE",            "pctStart": 0.10, "pctEnd": 0.10, "owner": "Bid Manager"},
            {"name": "Technical Architecture Design",  "category": "SOLUTION & PRICING",    "pctStart": 0.10, "pctEnd": 0.35, "owner": "Technical Architect"},
            {"name": "SLA & KPI Framework",            "category": "SOLUTION & PRICING",    "pctStart": 0.12, "pctEnd": 0.30, "owner": "Service Manager"},
            {"name": "Staffing & Resource Plan",       "category": "SOLUTION & PRICING",    "pctStart": 0.15, "pctEnd": 0.40, "owner": "Resource Manager"},
            {"name": "Pricing & Commercial Model",     "category": "SOLUTION & PRICING",    "pctStart": 0.20, "pctEnd": 0.50, "owner": "Pricing Lead"},
            {"name": "Transition & Transformation Plan","category": "CONTENT DEVELOPMENT",  "pctStart": 0.30, "pctEnd": 0.55, "owner": "Transition Lead"},
            {"name": "Proposal Writing",               "category": "CONTENT DEVELOPMENT",   "pctStart": 0.45, "pctEnd": 0.70, "owner": "Proposal Writer"},
            {"name": "Technical Review",               "category": "REVIEWS",               "pctStart": 0.65, "pctEnd": 0.75, "owner": "CTO / Review Board"},
            {"name": "Final Draft & Revision",         "category": "CONTENT DEVELOPMENT",   "pctStart": 0.75, "pctEnd": 0.90, "owner": "Proposal Writer"},
            {"name": "Executive Approval",             "category": "GOVERNANCE",            "pctStart": 0.90, "pctEnd": 0.90, "owner": "Managing Director"},
            {"name": "QA & Formatting",                "category": "GOVERNANCE",            "pctStart": 0.90, "pctEnd": 0.97, "owner": "Bid Manager"},
            {"name": "Submission",                     "category": "GOVERNANCE",            "pctStart": 1.00, "pctEnd": 1.00, "owner": "Bid Manager"},
        ],
    },
    "sbir_grant": {
        "label": "SBIR / STTR Grant",
        "description": "Small-business innovation research grant application workflow.",
        "phases": [
            {"name": "Solicitation Review",            "category": "STRATEGY & PLANNING",   "pctStart": 0.00, "pctEnd": 0.06, "owner": "PI"},
            {"name": "Topic Selection & Feasibility",  "category": "STRATEGY & PLANNING",   "pctStart": 0.06, "pctEnd": 0.14, "owner": "PI"},
            {"name": "Go/No-Go Decision",              "category": "GOVERNANCE",            "pctStart": 0.14, "pctEnd": 0.14, "owner": "Director"},
            {"name": "Technical Objectives & Approach", "category": "CONTENT DEVELOPMENT",  "pctStart": 0.15, "pctEnd": 0.40, "owner": "PI"},
            {"name": "Work Plan & Milestones",         "category": "CONTENT DEVELOPMENT",   "pctStart": 0.25, "pctEnd": 0.45, "owner": "PI"},
            {"name": "Budget & Justification",         "category": "SOLUTION & PRICING",    "pctStart": 0.30, "pctEnd": 0.55, "owner": "Grants Manager"},
            {"name": "Facilities & Equipment",         "category": "CONTENT DEVELOPMENT",   "pctStart": 0.40, "pctEnd": 0.55, "owner": "PI"},
            {"name": "Commercialization Plan",         "category": "STRATEGY & PLANNING",   "pctStart": 0.45, "pctEnd": 0.65, "owner": "Business Development"},
            {"name": "Internal Review",                "category": "REVIEWS",               "pctStart": 0.65, "pctEnd": 0.75, "owner": "Review Board"},
            {"name": "Final Revisions",                "category": "CONTENT DEVELOPMENT",   "pctStart": 0.75, "pctEnd": 0.90, "owner": "PI"},
            {"name": "Administrative Review",          "category": "GOVERNANCE",            "pctStart": 0.90, "pctEnd": 0.95, "owner": "Grants Manager"},
            {"name": "Submission",                     "category": "GOVERNANCE",            "pctStart": 1.00, "pctEnd": 1.00, "owner": "Grants Manager"},
        ],
    },
}


# ══════════════════════════════════════════════════════════════════════════════
#  CALCULATION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def _distribute_phases(
    start_date: date,
    end_date: date,
    template_key: str,
) -> list[dict]:
    """Proportionally distribute phase dates across the total window."""
    total_days = max(0, (end_date - start_date).days)

    template = TEMPLATES.get(template_key, TEMPLATES["full"])
    phases_tmpl = template["phases"]
    phases = []

    for idx, ph in enumerate(phases_tmpl):
        s_offset = round(ph["pctStart"] * total_days)
        e_offset = round(ph["pctEnd"]   * total_days)
        s = start_date + timedelta(days=s_offset)
        e = start_date + timedelta(days=e_offset)
        duration = (e - s).days
        phases.append({
            "id":        idx,
            "name":      ph["name"],
            "category":  ph["category"],
            "startDate": s.isoformat(),
            "endDate":   e.isoformat(),
            "duration":  duration,
            "label":     "Milestone" if duration == 0 else f"{duration} day{'s' if duration != 1 else ''}",
            "owner":     ph["owner"],
            "excluded":  False,
            "status":    "not_started",
        })

    return phases


def _build_response(
    bid_name: str,
    rfp_release: str,
    submission: str,
    qa_deadline: str,
    review_cycle: str,
    phases: list[dict],
) -> dict:
    """Build the full plan response dict."""
    rfp = date.fromisoformat(rfp_release)
    sub = date.fromisoformat(submission)
    return {
        "bidName":        bid_name,
        "rfpRelease":     rfp_release,
        "submission":     submission,
        "qaDeadline":     qa_deadline,
        "reviewCycle":    review_cycle,
        "phases":         phases,
        "totalWindow":    (sub - rfp).days,
        "daysToDeadline": (sub - date.today()).days,
    }


# ── Sample seed data ─────────────────────────────────────────────────────────

SAMPLE_DATA = {
    "bidName":       "Sample RFP -- Cloud Migration",
    "rfpRelease":    "2026-06-04",
    "submission":    "2026-07-04",
    "qaDeadline":    "",
    "reviewCycle":   "full",
}


# ══════════════════════════════════════════════════════════════════════════════
#  ROUTES — PAGES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/print")
def print_view():
    """Render a clean print-friendly page for PDF export via browser."""
    return render_template("print.html")


# ══════════════════════════════════════════════════════════════════════════════
#  ROUTES — API: PLAN GENERATION
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/sample")
def api_sample():
    """Return the pre-seeded sample data + generated phases."""
    d = dict(SAMPLE_DATA)
    phases = _distribute_phases(
        date.fromisoformat(d["rfpRelease"]),
        date.fromisoformat(d["submission"]),
        d["reviewCycle"],
    )
    return jsonify(_build_response(
        d["bidName"], d["rfpRelease"], d["submission"],
        d["qaDeadline"], d["reviewCycle"], phases,
    ))


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """Generate a plan from user-supplied parameters."""
    body  = request.get_json(force=True)
    rfp   = date.fromisoformat(body["rfpRelease"])
    sub   = date.fromisoformat(body["submission"])
    cycle = body.get("reviewCycle", "full")
    phases = _distribute_phases(rfp, sub, cycle)
    return jsonify(_build_response(
        body.get("bidName", ""), body["rfpRelease"], body["submission"],
        body.get("qaDeadline", ""), cycle, phases,
    ))


# ══════════════════════════════════════════════════════════════════════════════
#  ROUTES — API: TEMPLATES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/templates")
def api_templates():
    """Return available template metadata (without full phase arrays)."""
    result = []
    for key, tmpl in TEMPLATES.items():
        result.append({
            "key":         key,
            "label":       tmpl["label"],
            "description": tmpl["description"],
            "phaseCount":  len(tmpl["phases"]),
        })
    return jsonify(result)


# ══════════════════════════════════════════════════════════════════════════════
#  ROUTES — API: SAVE / LOAD / DELETE PLANS
# ══════════════════════════════════════════════════════════════════════════════

def _safe_filename(name: str) -> str:
    """Sanitize a bid name into a safe filename."""
    cleaned = re.sub(r'[^\w\s-]', '', name).strip()
    cleaned = re.sub(r'[\s]+', '_', cleaned)
    return cleaned[:80] if cleaned else "unnamed"


@app.route("/api/plans", methods=["GET"])
def api_list_plans():
    """List all saved plans."""
    plans = []
    for f in sorted(PLANS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            plans.append({
                "filename":    f.name,
                "bidName":     data.get("bidName", f.stem),
                "rfpRelease":  data.get("rfpRelease", ""),
                "submission":  data.get("submission", ""),
                "reviewCycle": data.get("reviewCycle", ""),
                "phaseCount":  len(data.get("phases", [])),
                "savedAt":     datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
        except (json.JSONDecodeError, KeyError):
            continue
    return jsonify(plans)


@app.route("/api/save", methods=["POST"])
def api_save_plan():
    """Save the current plan to a JSON file."""
    body = request.get_json(force=True)
    bid_name = body.get("bidName", "Unnamed Plan")
    safe_name = _safe_filename(bid_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_name}_{timestamp}.json"
    filepath = PLANS_DIR / filename

    # Add save metadata
    body["savedAt"] = datetime.now().isoformat()

    filepath.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")

    return jsonify({
        "ok": True,
        "filename": filename,
        "message": f"Plan saved as {filename}",
    })


@app.route("/api/load/<filename>")
def api_load_plan(filename: str):
    """Load a previously saved plan."""
    filepath = PLANS_DIR / filename
    if not filepath.exists() or not filepath.suffix == ".json":
        return jsonify({"error": "Plan not found"}), 404

    data = json.loads(filepath.read_text(encoding="utf-8"))

    # Recalculate dynamic fields
    try:
        rfp = date.fromisoformat(data["rfpRelease"])
        sub = date.fromisoformat(data["submission"])
        data["totalWindow"]    = (sub - rfp).days
        data["daysToDeadline"] = (sub - date.today()).days
    except (KeyError, ValueError):
        pass

    return jsonify(data)


@app.route("/api/plans/<filename>", methods=["DELETE"])
def api_delete_plan(filename: str):
    """Delete a saved plan."""
    filepath = PLANS_DIR / filename
    if filepath.exists() and filepath.suffix == ".json":
        filepath.unlink()
        return jsonify({"ok": True, "message": f"Deleted {filename}"})
    return jsonify({"error": "Plan not found"}), 404


# ══════════════════════════════════════════════════════════════════════════════
#  ROUTES — API: EXPORT
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/export/csv", methods=["POST"])
def api_export_csv():
    """Export the current plan as a downloadable CSV."""
    body   = request.get_json(force=True)
    phases = body.get("phases", [])
    bid    = body.get("bidName", "Bid Plan")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["#", "Phase", "Category", "Start Date", "End Date", "Duration", "Owner", "Status"])
    for i, ph in enumerate(phases):
        if ph.get("excluded"):
            continue
        writer.writerow([
            i + 1,
            ph["name"],
            ph["category"],
            ph["startDate"],
            ph["endDate"],
            ph["label"],
            ph["owner"],
            ph.get("status", "not_started").replace("_", " ").title(),
        ])

    buf.seek(0)
    safe = _safe_filename(bid)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe}_plan.csv"'},
    )


@app.route("/api/export/json", methods=["POST"])
def api_export_json():
    """Export the full plan as a downloadable JSON file."""
    body = request.get_json(force=True)
    bid  = body.get("bidName", "Bid Plan")
    safe = _safe_filename(bid)

    return Response(
        json.dumps(body, indent=2, ensure_ascii=False),
        mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{safe}_plan.json"'},
    )


@app.route("/api/import", methods=["POST"])
def api_import_json():
    """Import a plan from an uploaded JSON file."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if not file.filename.endswith(".json"):
        return jsonify({"error": "Only .json files are accepted"}), 400

    try:
        data = json.loads(file.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return jsonify({"error": "Invalid JSON file"}), 400

    # Validate minimum fields
    required = ["bidName", "rfpRelease", "submission", "phases"]
    missing  = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    # Recalculate dynamic fields
    try:
        rfp = date.fromisoformat(data["rfpRelease"])
        sub = date.fromisoformat(data["submission"])
        data["totalWindow"]    = (sub - rfp).days
        data["daysToDeadline"] = (sub - date.today()).days
    except (KeyError, ValueError):
        pass

    return jsonify(data)


# ══════════════════════════════════════════════════════════════════════════════
#  ROUTES — API: STATISTICS
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/stats", methods=["POST"])
def api_stats():
    """Compute plan statistics for the dashboard."""
    body   = request.get_json(force=True)
    phases = [p for p in body.get("phases", []) if not p.get("excluded")]
    today  = date.today().isoformat()

    total      = len(phases)
    completed  = sum(1 for p in phases if p.get("endDate", "9999") < today)
    in_progress = sum(1 for p in phases if p.get("startDate", "") <= today <= p.get("endDate", ""))
    upcoming   = total - completed - in_progress
    milestones = sum(1 for p in phases if p.get("duration", 1) == 0)

    # Category breakdown
    cat_counts = {}
    for p in phases:
        c = p.get("category", "OTHER")
        cat_counts[c] = cat_counts.get(c, 0) + 1

    # Progress percentage
    progress_pct = round((completed / total) * 100) if total > 0 else 0

    return jsonify({
        "total":       total,
        "completed":   completed,
        "inProgress":  in_progress,
        "upcoming":    upcoming,
        "milestones":  milestones,
        "progressPct": progress_pct,
        "categories":  cat_counts,
    })


# Keep the old /api/export endpoint for backward compatibility
@app.route("/api/export", methods=["POST"])
def api_export_csv_legacy():
    """Legacy CSV export endpoint."""
    return api_export_csv()


# ══════════════════════════════════════════════════════════════════════════════
#  RUN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n  Bid Timeline Planner v2.0")
    print("  -------------------------")
    print(f"  Plans directory: {PLANS_DIR.resolve()}")
    print("  Open  http://127.0.0.1:5000  in your browser\n")
    app.run(debug=True, port=5000)
