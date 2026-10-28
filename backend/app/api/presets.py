"""Curated playground presets for the guided judge journey.

These are inputs only. Whatever the models actually return is what the UI
shows — escalation happens only if the quality gate genuinely fails.
"""

PRESETS = [
    {
        "id": "strict-extraction",
        "title": "Strict schema extraction",
        "blurb": "Structured extraction with a strict JSON schema, enums and date formats. Starts on Nano so you can watch the quality gate decide whether escalation is needed.",
        "request": {
            "task": (
                "Extract every shipment from the dispatch log below. Return JSON {\"shipments\": [...]} where each item is "
                "{\"id\": string, \"origin\": IATA code, \"destination\": IATA code, \"departure\": \"YYYY-MM-DDTHH:MM\" (24h, local), "
                "\"status\": one of \"scheduled\",\"delayed\",\"cancelled\", \"delay_minutes\": integer or null, \"hazmat\": boolean}.\n\n"
                "Dispatch log:\n"
                "- SHP-4410 MIA→ATL leaves 3 Nov 2026 at 6:45pm, running about an hour and a half late, contains lithium batteries.\n"
                "- SHP-4411 from Orlando (MCO) to Newark (EWR), 4 Nov 2026 07:10, on time, general cargo.\n"
                "- SHP-4412 PBI→JFK, 4 Nov 2026 at noon — scrubbed due to weather. Carries dry ice (hazmat).\n"
                "- SHP-4413 TPA→ORD departs 5 Nov 2026 9:05 PM, 20 min delay, no hazardous goods."
            ),
            "category": "structured_json",
            "output_format": "json",
            "forced_tier": "small",
            "allow_escalation": True,
            "quality_threshold": 0.85,
            "json_schema": {
                "type": "object", "required": ["shipments"],
                "properties": {"shipments": {"type": "array", "minItems": 4, "maxItems": 4, "items": {
                    "type": "object",
                    "required": ["id", "origin", "destination", "departure", "status", "delay_minutes", "hazmat"],
                    "properties": {
                        "id": {"type": "string", "pattern": "^SHP-\\d{4}$"},
                        "origin": {"type": "string", "pattern": "^[A-Z]{3}$"},
                        "destination": {"type": "string", "pattern": "^[A-Z]{3}$"},
                        "departure": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}$"},
                        "status": {"enum": ["scheduled", "delayed", "cancelled"]},
                        "delay_minutes": {"type": ["integer", "null"]},
                        "hazmat": {"type": "boolean"}}}}},
            },
            "expected_fields": {
                "shipments.0.departure": "2026-11-03T18:45", "shipments.0.status": "delayed", "shipments.0.delay_minutes": 90, "shipments.0.hazmat": True,
                "shipments.1.origin": "MCO", "shipments.1.status": "scheduled",
                "shipments.2.status": "cancelled", "shipments.2.departure": "2026-11-04T12:00", "shipments.2.hazmat": True,
                "shipments.3.departure": "2026-11-05T21:05", "shipments.3.delay_minutes": 20, "shipments.3.hazmat": False,
            },
        },
    },
    {
        "id": "routine-classification",
        "title": "Routine classification",
        "blurb": "A simple routing task. The policy should pick the cheapest tier that meets the quality target — no need for a frontier model.",
        "request": {
            "task": "Route this support ticket to one team: billing, technical, account, or shipping. Reply with only the team name.\n\nTicket: \"The tracking page says delivered but the package never arrived at my door.\"",
            "category": "classification",
            "output_format": "text",
            "exact_answer": "shipping",
        },
    },
    {
        "id": "multi-step-reasoning",
        "title": "Multi-step reasoning",
        "blurb": "A constraint puzzle with an objectively checkable answer. Watch the router weigh a cheap first try against the probability of needing escalation.",
        "request": {
            "task": (
                "Four lab samples A, B, C, D were processed in some order, one per hour starting at 08:00. "
                "C was processed immediately after A. B was not processed first or last. D was processed before A. "
                "At what time was C processed? Reason briefly, then end with a line 'Answer: HH:MM'."
            ),
            "category": "reasoning",
            "output_format": "text",
            "required_terms": ["Answer: 11:00"],
        },
    },
    {
        "id": "exec-summary",
        "title": "Constrained summary",
        "blurb": "Summarization with hard constraints (word limit, required facts) checked deterministically.",
        "request": {
            "task": (
                "Summarize for a city council member in at most 45 words. Must mention the cost and the payback period.\n\n"
                "Staff report: Replacing 18 diesel maintenance trucks with battery-electric models costs $3.6 million after grants. "
                "Fuel and maintenance savings are estimated at $610,000 per year, giving a payback of about 5.9 years. "
                "Two depot chargers ($240,000) are included. Range is sufficient for 16 of 18 routes; two rural routes keep diesel units until 2028."
            ),
            "category": "summarization",
            "output_format": "text",
            "required_terms": ["3.6 million", "5.9"],
            "max_words": 45,
        },
    },
]
