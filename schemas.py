"""Tool schemas — what the model reads."""

HOMELAB_STATUS = {
    "name": "homelab_status",
    "description": (
        "Check the user's home network, servers, websites and devices right now and say what is "
        "wrong. Failures are rolled up to their root cause (a router outage is one problem, not ten). "
        "Use this for questions like 'is everything OK at home?', 'is Plex up?' or 'how is the miner "
        "doing?'. Read-only: it never restarts or changes anything."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "Optional target id or name to report on alone (e.g. 'plex').",
            },
            "detail": {
                "type": "boolean",
                "description": "Include every target's status and metrics, not just the summary.",
            },
        },
    },
}

HOMELAB_HEARTBEAT = {
    "name": "homelab_heartbeat",
    "description": (
        "Record that a scheduled job or agent finished, so Homelab Watch alerts if it stops checking "
        "in. Call it at the end of a cron job with the job's name."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Name of the job or agent checking in."},
            "every_minutes": {
                "type": "integer",
                "description": "How often it is expected to check in. Missing two in a row raises an alert.",
            },
        },
        "required": ["name"],
    },
}
