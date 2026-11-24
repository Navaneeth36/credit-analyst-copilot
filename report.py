from datetime import date


def fmt(value, suffix=""):
    return "n/a" if value is None else f"{value:,}{suffix}"


def build(company, figures, ratio_results, warnings, flag_results):
    lines = [
        f"# Credit screening note: {company}",
        "",
        f"Generated {date.today():%d %B %Y} by Credit Analyst Copilot. "
        "Every figure is checked against a quote from the report; verify before relying on it.",
        "",
    ]

    lines += ["## Key figures (millions)", "",
              "| Figure | Latest | Prior | Status | Page | Source line |",
              "|---|---|---|---|---|---|"]
    for f in figures:
        # | breaks the md table
        quote = (f["quote"] or "").replace("|", "/")
        lines.append(f"| {f['figure']} | {fmt(f['current_m'])} | {fmt(f['prior_m'])} | "
                     f"{f['status']} | {f['page'] or ''} | {quote} |")

    now, before = ratio_results["current"], ratio_results["prior"]
    lines += [
        "", "## Health check", "",
        "| Ratio | Latest | Prior | Flag |",
        "|---|---|---|---|",
        f"| Net debt / EBITDA | {fmt(now['Net debt / EBITDA'], 'x')} | "
        f"{fmt(before['Net debt / EBITDA'], 'x')} | {now['Leverage flag']} |",
        f"| Interest cover | {fmt(now['Interest cover'], 'x')} | "
        f"{fmt(before['Interest cover'], 'x')} | {now['Cover flag']} |",
        f"| Profit margin | {fmt(now['Profit margin %'], '%')} | "
        f"{fmt(before['Profit margin %'], '%')} | |",
    ]

    if warnings:
        lines += ["", "## Data warnings", ""] + [f"- {w}" for w in warnings]

    lines += ["", "## Red flags", ""]
    for flag in flag_results:
        lines.append(f"- **{flag['name']}**: {flag['status']}")
        if flag["status"] != "Not found":
            lines.append(f"  - {flag['explanation']} (page {flag['page']}): \"{flag['quote']}\"")

    lines += ["", "_Not found means not found in the passages searched, not proof it is absent._"]
    return "\n".join(lines)
